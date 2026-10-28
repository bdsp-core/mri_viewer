"""
05_case_info.py
===============
After 04_lesions_and_scenes.py: write what each FreeBrowse case shows, for the case panel that serve_freebrowse.py adds
to the page (case_panel.js). Run where the BIND package is (local Mac); the output folder is then copied into the viz/
folder on the server (BIND data stays local / on the server only).

Per study case, <out>/<case_id>/info.json:
  target diagnosis and the report finding it was picked from (side, locations, evidence sentence),
  every finding the report states for this study (BIND findings, assertion present / possible; absent ones left out),
  the radiology report text and its overall impression category,
  the Pibs result (largest component of the diagnosis- and generic-prompt maps, side match, sequences used),
  the layers in the scene (same as 04: T1, registered FLAIR / T2, red = diagnosis prompt, blue = generic prompt).
<out>/index.json lists the cases (case_id, diagnosis, side match) for the panel's case selector.

Usage:
  python 05_case_info.py --out <dir>      then  scp -r <dir>/* <user>@<server>:/data/imaging_test/bind_10dx/viz/
"""
import argparse
import json
import os

import numpy as np
import pandas as pd

BIND = os.environ.get('BIND', '/Users/chenxisun/Documents/sshcode/EEG_report/mrigoth/mortality_mri_eeg/BIND_deidentified_2026-10-21/')
HERE = os.path.dirname(os.path.abspath(__file__))

ap = argparse.ArgumentParser()
ap.add_argument('--out', required=True)
a = ap.parse_args()

L = pd.read_csv(os.path.join(HERE, 'results', 'lesions.csv'))
C = pd.read_csv(os.path.join(HERE, 'cases.csv'))
L = L.merge(C[['diagnosis', 'rank', 'study_id', 'evidence', 'acuity', 'size_mm']], on=['diagnosis', 'rank'])
studies = set(L.study_id)
R = pd.read_parquet(BIND + 'reports.parquet', columns=['study_id', 'report_text', 'overall']).set_index('study_id')
S = pd.read_parquet(BIND + 'studies.parquet', columns=['study_id', 'exam_description', 'hospital']).set_index('study_id')
F = pd.read_parquet(BIND + 'findings.parquet')
F = F[F.study_id.isin(studies) & F.assertion.isin(['present', 'possible'])].sort_values(['study_id', 'finding_no'])


def clean(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return ''
    if hasattr(v, '__len__') and not isinstance(v, str):
        return ', '.join(str(x) for x in v)
    return str(v)


def finding(r):
    name = r.finding_type + (f' ({r.tumor_subtype or r.subtype})' if clean(r.tumor_subtype or r.subtype) else '')
    size = f'{r.size_value:g} {r.size_unit}' if clean(r.size_value) else ''
    return {'finding': name, 'assertion': r.assertion, 'acuity': clean(r.acuity), 'side': clean(r.laterality),
            'location': clean(r.location), 'size': size, 'treatment': clean(r.treatment), 'evidence': clean(r.evidence_text)}


def pibs(r):
    found = bool(r.found)
    return {'prompt': r.prompt, 'found': found, 'largest_side': clean(r.largest_side), 'largest_ml': r.largest_ml,
            'n_components': int(r.n_components), 'side_match': bool(r.side_match) if found else None,
            'max_prob': round(r.max_prob, 3)}


index = []
for cid, g in L.groupby('case_id', sort=True):
    d = g[g.prompt_type == 'diagnosis'].iloc[0]
    gen = g[g.prompt_type == 'generic']
    sid = d.study_id
    info = {
        'case_id': cid, 'diagnosis': d.diagnosis, 'site': d.site, 'study_date_shifted': d.study_date,
        'exam': clean(S.exam_description.get(sid)),
        'target': {'side': d.report_side, 'locations': clean(d.locations).replace('|', ', '), 'acuity': clean(d.acuity),
                   'size_mm': clean(d.size_mm), 'evidence': clean(d.evidence)},
        'findings': [finding(r) for r in F[F.study_id == sid].itertuples()],
        'report_overall': clean(R.overall.get(sid)), 'report_text': clean(R.report_text.get(sid)),
        'pibs': {'diagnosis': pibs(d), 'generic': pibs(gen.iloc[0]) if len(gen) else None},
        't1_file': d.t1_file, 'files_used': clean(d.files_used).split('|'), 'fallback': d.fallback,
        'layers': [['T1', 'base image (gray)'], ['FLAIR / T2', 'registered to T1, hidden (eye icon to show)'],
                   [f'Pibs: {d.diagnosis}', 'red, probability > 0.5'], ['Pibs: generic lesion', 'blue, hidden']],
    }
    os.makedirs(os.path.join(a.out, cid), exist_ok=True)
    with open(os.path.join(a.out, cid, 'info.json'), 'w') as fh:
        json.dump(info, fh, indent=1, default=float)
    index.append({'case_id': cid, 'diagnosis': d.diagnosis, 'report_side': d.report_side,
                  'pibs_side': clean(d.largest_side), 'side_match': info['pibs']['diagnosis']['side_match']})
with open(os.path.join(a.out, 'index.json'), 'w') as fh:
    json.dump(index, fh, indent=1)
print(len(index), 'cases ->', a.out)
