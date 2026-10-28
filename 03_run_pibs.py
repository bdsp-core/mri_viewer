"""
03_run_pibs.py
==============
Pibs (pibs_alpha_v4) with ALL anatomical sequences, registered, on the BIND 10-diagnosis cases (run on the server, env
pibs_reg, one process per GPU). Same method as the mortality all-sequence run
(mrigoth/mortality_mri_eeg/pipeline/run_pibs_allseq.py): every other sequence is rigidly registered onto the T1 (sunbox
Rigid, NCC) and all volumes are fed together; multi-frame series are skipped; on GPU OOM the fallbacks full ->
t1_spacing -> drop_k are tried (column `fallback`).

  T1       picked from the downloaded files: MPRAGE > SPGR > spin-echo T1w > other T1w (no T1-FLAIR)
  prompts  "segment the <diagnosis> lesion" and the generic "segment the lesion"
  cases    for each diagnosis, candidates in rank order until --n_ok cases succeed (the rest are spares)

Outputs in <out>/viz/<case_id>/ (for FreeBrowse): t1.nii.gz, reg_<sequence file>.nii.gz (each other sequence after
registration), pibs_diagnosis_prob.nii.gz, pibs_generic_prob.nii.gz. Results appended to <out>/pibs_shard<k>.csv
(restart resumes): max_prob, n_vox (prob > 0.5), volume_ml, mask centroid (x/y/z mm, RAS), side, files_used,
fallback. (pibs_reg has no scipy; connected components are computed later from the saved maps.)

Usage:
  python 03_run_pibs.py --device cuda:0 --shard 0 --nshards 4
"""
import os
os.environ.setdefault('PYTORCH_CUDA_ALLOC_CONF', 'expandable_segments:True')
import argparse
import csv
import glob
import shutil
import sys
import time

sys.path.insert(0, os.path.expanduser('~/Documents/EEG_report/voxelpack_experimental'))
sys.path.insert(0, os.path.expanduser('~/mars_stub'))
import pandas as pd
import torch
import voxel as vx
import voxarcs
from voxelpack.models.pibs import Pibs
from sunbox.registration import Rigid, NCC

ap = argparse.ArgumentParser()
ap.add_argument('--cases', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cases.csv'))
ap.add_argument('--out', default='/data/imaging_test/bind_10dx')
ap.add_argument('--device', default='cuda:0')
ap.add_argument('--shard', type=int, default=0)
ap.add_argument('--nshards', type=int, default=1)
ap.add_argument('--n_ok', type=int, default=10)
args = ap.parse_args()
torch.set_num_threads(4)

CKPT = os.path.expanduser('~/Documents/EEG_report/voxelpack_experimental/voxelpack/resources/pibs_alpha_v4.pt')
GENERIC = 'segment the lesion'
SPACING_MODE = {'mode': 'full'}


# same upstream voxarcs.enclosing_geometry fix as the batch B / mortality runs, plus the t1_spacing fallback
def _enclosing_geometry_fixed(geometries, spacing=None, orientation=None):
    geometries = [vx.cast_acquisition_geometry(geom) for geom in geometries]
    base = geometries[0]
    if len(geometries) == 1:
        return base if orientation is None else base.reorient(orientation)
    check = lambda x: torch.allclose(base.tensor, x.tensor, rtol=1e-3)
    if all(check(geom) for geom in geometries[1:]):
        return base if orientation is None else base.reorient(orientation)
    first = geometries[0]
    base = max(geometries, key=lambda x: x.fov.prod())
    device, dtype = base.tensor.device, base.tensor.dtype
    u, _, v = torch.linalg.svd(base[:3, :3])
    rotation = u @ v
    center = base.transform((torch.as_tensor(base.baseshape, device=device, dtype=dtype) - 1) / 2)
    extent = base.fov / 2
    bounds = vx.BoundingBox(extent=extent, rotation=rotation, center=center)
    points = torch.cat([geom.bounds().corner_points() for geom in geometries], dim=0)
    bounds = bounds.fit_extent(points)
    if spacing is None:
        if SPACING_MODE['mode'] == 'full':
            spacing = min([x.in_plane_spacing.min() for x in geometries])
        else:
            spacing = first.in_plane_spacing.min()
    orientation = orientation or geometries[0].orientation
    return bounds.geometry(spacing=spacing).reorient(orientation)


voxarcs.enclosing_geometry = _enclosing_geometry_fixed
voxarcs.utils.enclosing_geometry = _enclosing_geometry_fixed

model = Pibs.load(CKPT, device=args.device)
model.eval()


def pick_t1(files):
    t1 = sorted(f for f in files if os.path.basename(f).endswith('T1w.nii.gz') and 'FLAIR' not in os.path.basename(f))
    for pat in ['MPRAGE', 'SPGR', 'acq-SE', '']:
        hit = [f for f in t1 if pat in os.path.basename(f)]
        if hit:
            return hit[0]
    return None


def priority(f):
    n = os.path.basename(f)
    if 'angio' in n:
        return 4
    if 'FLAIR' in n:
        return 0
    if 'T2w' in n:
        return 1
    if 'T1w' in n:
        return 2
    return 3


def register_to_t1(other, t1):
    rigid = Rigid(loss=NCC(), scales=(4, 2), iterations=15, step=1e-2, min_shape=8)
    return other.transform(rigid(other, t1, verbose=False))


def load_inputs(t1_path, others):
    t1 = vx.load_volume(t1_path).to(args.device).float()
    vols, used, skipped, n_ok, n_failed = [t1], [os.path.basename(t1_path)], [], 0, 0
    for p in others:
        try:
            v = vx.load_volume(p)
        except Exception:
            n_failed += 1
            continue
        if v.tensor.ndim == 4 and v.tensor.shape[0] > 1:
            skipped.append(os.path.basename(p))
            continue
        try:
            vols.append(register_to_t1(v.to(args.device).float(), t1))
            used.append(os.path.basename(p))
            n_ok += 1
        except torch.cuda.OutOfMemoryError:
            raise
        except Exception:
            n_failed += 1
    return vols, used, skipped, n_ok, n_failed


def segment(images, prompt):
    with torch.no_grad():
        probs = model.segment(images, prompt, probs=True)
    t = probs.tensor
    aff = probs.geometry.tensor.detach().double().cpu()
    vox_ml = abs(torch.linalg.det(aff[:3, :3]).item()) / 1000
    res = {'max_prob': t.max().item(), 'n_vox': 0, 'volume_ml': 0.0, 'mean_prob_in_mask': '', 'x_mm': '', 'y_mm': '',
           'z_mm': '', 'side': ''}
    m = t > 0.5
    if m.any():
        idx = m.nonzero(as_tuple=False).double()
        c = idx[:, -3:].mean(dim=0).cpu()
        w = (aff @ torch.cat([c, torch.tensor([1.0], dtype=torch.double)]))[:3].tolist()
        res.update(n_vox=int(m.sum().item()), volume_ml=round(int(m.sum().item()) * vox_ml, 3),
                   mean_prob_in_mask=round(t[m].mean().item(), 4), x_mm=w[0], y_mm=w[1], z_mm=w[2],
                   side='right' if w[0] > 0 else 'left')
    probs = probs.cpu()
    del t
    return res, probs


def run_case(t1_path, others, prompts, viz):
    """Try full -> t1_spacing -> drop the lowest-priority sequences one by one until it fits on the GPU."""
    others = sorted(others, key=lambda f: (priority(f), os.path.basename(f)))
    plans = [('full', others), ('t1_spacing', others)]
    plans += [(f'drop_{k}', others[:len(others) - k]) for k in range(1, len(others) + 1)]
    for name, files in plans:
        SPACING_MODE['mode'] = 'full' if name == 'full' else 't1_spacing'
        try:
            vols, used, skipped, n_ok, n_failed = load_inputs(t1_path, files)
            images = vols[0] if len(vols) == 1 else vols
            out = []
            for pt, p in prompts:
                res, probs = segment(images, p)
                probs.save(os.path.join(viz, f'pibs_{pt}_prob.nii.gz'))
                out.append(res)
            for v, f in zip(vols[1:], used[1:]):
                v.cpu().save(os.path.join(viz, 'reg_' + f))
            meta = {'n_volumes_used': len(vols), 'n_registered_ok': n_ok, 'n_registered_failed': n_failed,
                    'fallback': name, 'files_used': '|'.join(used), 'skipped_multiframe': '|'.join(skipped)}
            del vols, images
            return meta, out
        except torch.cuda.OutOfMemoryError:
            for f in glob.glob(os.path.join(viz, 'pibs_*_prob.nii.gz')) + glob.glob(os.path.join(viz, 'reg_*')):
                os.remove(f)
        finally:
            torch.cuda.empty_cache()
    raise torch.cuda.OutOfMemoryError('OOM even with the T1 alone')


c = pd.read_csv(args.cases)
dxs = list(dict.fromkeys(c.diagnosis))[args.shard::args.nshards]
out_csv = os.path.join(args.out, f'pibs_shard{args.shard}.csv')
fields = ['case_id', 'diagnosis', 'rank', 'person_id', 'site', 'session_id', 'study_date', 'report_side', 'locations',
          'prompt_type', 'prompt', 't1_file', 'max_prob', 'n_vox', 'volume_ml', 'mean_prob_in_mask', 'x_mm', 'y_mm',
          'z_mm', 'side', 'n_volumes_used', 'n_registered_ok',
          'n_registered_failed', 'fallback', 'files_used', 'skipped_multiframe', 'error', 'seconds']
new = not os.path.exists(out_csv)
prev = pd.DataFrame(columns=fields) if new else pd.read_csv(out_csv)
fh = open(out_csv, 'a', newline='')
w = csv.DictWriter(fh, fieldnames=fields)
if new:
    w.writeheader()
t0 = time.time()
print(f'shard {args.shard}/{args.nshards}: {dxs}', flush=True)
for dx in dxs:
    n_ok = prev[(prev.diagnosis == dx) & prev.error.isna() & (prev.prompt_type == 'diagnosis')].case_id.nunique()
    done = set(prev[prev.diagnosis == dx].case_id)
    for r in c[c.diagnosis == dx].sort_values('rank').itertuples():
        if n_ok >= args.n_ok:
            break
        cid = f"{dx.replace(' ', '_')}_{int(r.rank):02d}"
        if cid in done:
            continue
        d = os.path.join(args.out, 'mri', cid)
        while not os.path.exists(os.path.join(d, '.done')):
            time.sleep(10)
        ts = time.time()
        base = {'case_id': cid, 'diagnosis': dx, 'rank': r.rank, 'person_id': r.person_id, 'site': r.site,
                'session_id': r.session_id, 'study_date': r.study_date, 'report_side': r.sides, 'locations': r.locations}
        prompts = [('diagnosis', r.prompt), ('generic', GENERIC)]
        files = sorted(glob.glob(os.path.join(d, '*.nii.gz')))
        t1_path = pick_t1(files)
        viz = os.path.join(args.out, 'viz', cid)
        if t1_path is None:
            rows = [dict(base, prompt_type=pt, prompt=p, error='no T1w file downloaded') for pt, p in prompts]
        else:
            os.makedirs(viz, exist_ok=True)
            shutil.copyfile(t1_path, os.path.join(viz, 't1.nii.gz'))
            others = [f for f in files if f != t1_path]
            try:
                meta, out = run_case(t1_path, others, prompts, viz)
                rows = [dict(base, prompt_type=pt, prompt=p, t1_file=os.path.basename(t1_path), **meta, **res, error='')
                        for (pt, p), res in zip(prompts, out)]
                n_ok += 1
            except Exception as e:
                rows = [dict(base, prompt_type=pt, prompt=p, t1_file=os.path.basename(t1_path),
                             error=f'{type(e).__name__}: {str(e)[:150]}') for pt, p in prompts]
        for row in rows:
            row['seconds'] = round(time.time() - ts, 1)
            w.writerow(row)
        fh.flush()
        print(f'{cid} fallback={rows[0].get("fallback", "-")} vols={rows[0].get("n_volumes_used", "-")} '
              f'side={rows[0].get("side", "")} report={r.sides} {time.time() - ts:.0f}s err={rows[0]["error"][:60]} '
              f'(ok {n_ok}/{args.n_ok} for {dx}, total {time.time() - t0:.0f}s)', flush=True)
    print(f'{dx}: {n_ok} ok', flush=True)
fh.close()
print('PIBS_DONE', flush=True)
