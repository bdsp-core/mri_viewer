"""
04_lesions_and_scenes.py
========================
After 03_run_pibs.py (run on the server, env torchenv): find the lesion in each Pibs probability map and write one FreeBrowse
scene (.nvd) per case.

Lesion = voxels with probability > 0.5; connected components (26-connectivity); the largest component is "the lesion"
(its volume, centroid in world RAS mm, side = sign of x). The side is compared with the side the radiology report
states (BIND finding laterality; 01_select_cases.py kept only one-sided cases).

Per case, in <out>/viz/<case_id>/:
  lesion_<prompt_type>.nii.gz   probability x 100 as uint8 (smaller than the float map, for the browser)
  <case_id>.nvd                 FreeBrowse scene: T1 (gray), registered FLAIR / T2 if present (hidden, opacity 0),
                                Pibs diagnosis-prompt map (red, shown from 50 = p 0.5), generic-prompt map (hidden);
                                the crosshair starts at the centre of the largest diagnosis-prompt component
                                (scene.crosshairPos = fraction of the T1's world-space bounding box)
Tables in <out>/results/: lesions.csv (one row per case and prompt), summary_by_diagnosis.csv, summary.txt

Usage:
  python 04_lesions_and_scenes.py --out /data/imaging_test/bind_10dx
"""
import argparse
import glob
import json
import os

import nibabel as nib
import numpy as np
import pandas as pd
from scipy import ndimage

ap = argparse.ArgumentParser()
ap.add_argument('--out', default='/data/imaging_test/bind_10dx')
ap.add_argument('--n_ok', type=int, default=10)
a = ap.parse_args()

res = pd.concat([pd.read_csv(f) for f in sorted(glob.glob(os.path.join(a.out, 'pibs_shard*.csv')))], ignore_index=True)
res['error'] = res.error.fillna('')
ok = res[res.error == ''].copy()
# the first n_ok successful cases per diagnosis (in rank order) are the study cases
first = (ok[ok.prompt_type == 'diagnosis'].sort_values(['diagnosis', 'rank']).groupby('diagnosis').head(a.n_ok).case_id)
ok = ok[ok.case_id.isin(first)]


def lesion(path):
    img = nib.load(path)
    p = np.asarray(img.dataobj, dtype=np.float32).squeeze()
    aff = img.affine
    u8 = np.clip(np.rint(p * 100), 0, 100).astype(np.uint8)
    out = nib.Nifti1Image(u8, aff)
    out.header.set_xyzt_units('mm')
    m = p > 0.5
    vox_ml = abs(np.linalg.det(aff[:3, :3])) / 1000
    r = {'max_prob': float(p.max()), 'mask_ml': round(float(m.sum()) * vox_ml, 3), 'n_components': 0,
         'largest_ml': 0.0, 'largest_x': np.nan, 'largest_y': np.nan, 'largest_z': np.nan, 'largest_side': '',
         'largest_mean_prob': np.nan}
    if m.any():
        lab, n = ndimage.label(m, structure=np.ones((3, 3, 3)))
        sizes = np.bincount(lab.ravel())[1:]
        k = int(sizes.argmax()) + 1
        c = np.argwhere(lab == k).mean(axis=0)
        x, y, z = (aff @ np.append(c, 1))[:3]
        r.update(n_components=int(n), largest_ml=round(float(sizes[k - 1]) * vox_ml, 3), largest_x=round(x, 1),
                 largest_y=round(y, 1), largest_z=round(z, 1), largest_side='right' if x > 0 else 'left',
                 largest_mean_prob=round(float(p[lab == k].mean()), 3))
    return r, out


rows = []
for r in ok.itertuples():
    viz = os.path.join(a.out, 'viz', r.case_id)
    src = os.path.join(viz, f'pibs_{r.prompt_type}_prob.nii.gz')
    les, img = lesion(src)
    nib.save(img, os.path.join(viz, f'lesion_{r.prompt_type}.nii.gz'))
    rows.append({**r._asdict(), **les})
L = pd.DataFrame(rows).drop(columns=['Index'])
L['found'] = L.largest_ml > 0
L['side_match'] = np.where(L.found, L.largest_side == L.report_side, np.nan)
os.makedirs(os.path.join(a.out, 'results'), exist_ok=True)
L.to_csv(os.path.join(a.out, 'results', 'lesions.csv'), index=False)


def crosshair(viz, xyz):
    """world RAS mm -> niivue scene fraction of the T1's axis-aligned world bounding box"""
    img = nib.load(os.path.join(viz, 't1.nii.gz'))
    corners = np.array([[i, j, k, 1] for i in (0, img.shape[0] - 1) for j in (0, img.shape[1] - 1)
                        for k in (0, img.shape[2] - 1)], dtype=float)
    w = (img.affine @ corners.T).T[:, :3]
    lo, hi = w.min(axis=0), w.max(axis=0)
    return [round(float(v), 4) for v in np.clip((np.asarray(xyz) - lo) / (hi - lo), 0, 1)]


def scene(case_id, dx, report_side, locations, xyz):
    viz = os.path.join(a.out, 'viz', case_id)
    regs = sorted(os.path.basename(f) for f in glob.glob(os.path.join(viz, 'reg_*.nii.gz')))
    pick = [f for f in regs if 'FLAIR' in f][:1] + [f for f in regs if 'T2w' in f and 'FLAIR' not in f][:1]
    vols = [{'url': f'data/{case_id}/t1.nii.gz', 'name': 'T1', 'colormap': 'gray', 'opacity': 1}]
    for f in pick:
        vols.append({'url': f'data/{case_id}/{f}', 'name': f[4:-7], 'colormap': 'gray', 'opacity': 0})
    vols.append({'url': f'data/{case_id}/lesion_diagnosis.nii.gz', 'name': f'Pibs: {dx}', 'colormap': 'red',
                 'opacity': 0.7, 'calMin': 50, 'calMax': 100})
    vols.append({'url': f'data/{case_id}/lesion_generic.nii.gz', 'name': 'Pibs: generic lesion', 'colormap': 'blue',
                 'opacity': 0, 'calMin': 50, 'calMax': 100})
    doc = {'version': 9, 'title': f'{case_id} | {dx} | report: {report_side} {locations}', 'volumes': vols}
    if not np.isnan(xyz).any():
        doc['scene'] = {'crosshairPos': crosshair(viz, xyz)}
    with open(os.path.join(viz, f'{case_id}.nvd'), 'w') as fh:
        json.dump(doc, fh, indent=1)


for r in L[L.prompt_type == 'diagnosis'].itertuples():
    scene(r.case_id, r.diagnosis, r.report_side, r.locations if isinstance(r.locations, str) else '',
          [r.largest_x, r.largest_y, r.largest_z])

S = []
for (dx, pt), g in L.groupby(['diagnosis', 'prompt_type'], sort=False):
    f = g[g.found]
    S.append({'diagnosis': dx, 'prompt_type': pt, 'cases': len(g), 'lesion_found': int(g.found.sum()),
              'side_match': int(f.side_match.sum()), 'side_match_pct': round(100 * f.side_match.mean(), 1) if len(f) else np.nan,
              'median_largest_ml': round(f.largest_ml.median(), 2) if len(f) else np.nan,
              'median_components': f.n_components.median() if len(f) else np.nan,
              'full_sequences': int((g.fallback == 'full').sum()), 'median_volumes_used': g.n_volumes_used.median()})
S = pd.DataFrame(S)
S.to_csv(os.path.join(a.out, 'results', 'summary_by_diagnosis.csv'), index=False)
tot = []
for pt, g in L.groupby('prompt_type'):
    f = g[g.found]
    tot.append(f'{pt}: {len(g)} cases, lesion found {g.found.sum()}, side match {int(f.side_match.sum())}/{len(f)} '
               f'({100 * f.side_match.mean():.1f}%)')
txt = S.to_string(index=False) + '\n\n' + '\n'.join(tot) + '\n'
open(os.path.join(a.out, 'results', 'summary.txt'), 'w').write(txt)
print(txt)
print('fallback', L[L.prompt_type == 'diagnosis'].fallback.value_counts().to_dict())
print('SCENES_DONE', flush=True)
