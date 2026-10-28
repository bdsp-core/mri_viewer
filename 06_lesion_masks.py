"""
06_lesion_masks.py
==================
After 04_lesions_and_scenes.py (run on the server, env torchenv): write each case's Pibs diagnosis-prompt lesion as a 0/1 mask,
viz/<case_id>/pibs_mask_diagnosis.nii.gz (uint8, p > 0.5, on the voxel grid of t1.nii.gz). A FreeBrowse drawing must
be on the grid of the background volume, and about half of the Pibs maps are not (axes reordered / other spacing), so the
probability map is resampled into the T1 grid through the two affines (trilinear) before thresholding; the lesion volume
before and after is printed as a check. The case panel (case_panel.js) loads it
as the FreeBrowse drawing layer when a reviewer edits the lesion; each reviewer's edited mask is saved next to it as
edited_mask_<reviewer>.nii.gz by serve_freebrowse.py (the Pibs output is never overwritten).

Usage:
  python 06_lesion_masks.py --out /data/imaging_test/bind_10dx
"""
import argparse
import json
import os

import nibabel as nib
import numpy as np
from scipy import ndimage

ap = argparse.ArgumentParser()
ap.add_argument('--out', default='/data/imaging_test/bind_10dx')
a = ap.parse_args()

viz = os.path.join(a.out, 'viz')
cases = [c['case_id'] for c in json.load(open(os.path.join(viz, 'index.json')))]
for cid in cases:
    d = os.path.join(viz, cid)
    t1 = nib.load(os.path.join(d, 't1.nii.gz'))
    p = nib.load(os.path.join(d, 'pibs_diagnosis_prob.nii.gz'))
    prob = np.asarray(p.dataobj, dtype=np.float32).squeeze()
    ml_src = (prob > 0.5).sum() * abs(np.linalg.det(p.affine[:3, :3])) / 1000
    if prob.shape != t1.shape[:3] or not np.allclose(p.affine, t1.affine, atol=1e-3):
        # T1 voxel -> world -> Pibs voxel
        ijk = np.indices(t1.shape[:3], dtype=np.float32).reshape(3, -1)
        m2p = np.linalg.inv(p.affine) @ t1.affine
        src = m2p[:3, :3] @ ijk + m2p[:3, 3:]
        prob = ndimage.map_coordinates(prob, src, order=1, cval=0).reshape(t1.shape[:3])
    ml = (prob > 0.5).sum() * abs(np.linalg.det(t1.affine[:3, :3])) / 1000
    print(f'{cid:30s} lesion {ml_src:8.2f} ml -> {ml:8.2f} ml on the T1 grid', flush=True)
    m = nib.Nifti1Image((prob > 0.5).astype(np.uint8), t1.affine)
    m.header.set_xyzt_units('mm')
    nib.save(m, os.path.join(d, 'pibs_mask_diagnosis.nii.gz'))
print(len(cases), 'cases', 'MASKS_DONE')
