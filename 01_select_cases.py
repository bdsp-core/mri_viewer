"""
01_select_cases.py
==================
Pick 10 MRI studies (10 different patients) for each of 10 diagnoses from the BIND report package, for the Pibs
all-sequence (registered) run and FreeBrowse visualization. No EEG pairing.

Rules (BIND findings = what the radiology report states):
  - MR study, finding assertion 'present', laterality 'left' or 'right', and only one side stated for this diagnosis in
    the study (so the Pibs side can be checked)
  - the study has at least one non-derived T1w series (Pibs registers every other sequence onto a T1)
  - tumors (glioblastoma, meningioma): treatment 'none stated' and no present post-surgical change in the study
  - one study per patient, and a patient is used for one diagnosis only
  - random order (seed 20261027); first 10 kept, the rest are spares (in case a download or Pibs run fails)
Output: cases.csv (all candidates in random order with rank), selection_log.txt
"""
import os

import numpy as np
import pandas as pd

BIND = os.environ.get('BIND', '/Users/chenxisun/Documents/sshcode/EEG_report/mrigoth/mortality_mri_eeg/BIND_deidentified_2026-10-21/')
OUT = os.path.dirname(os.path.abspath(__file__))
SEED = 20261027

f = pd.read_parquet(BIND + 'findings.parquet')
s = pd.read_parquet(BIND + 'series.parquet', columns=['study_id', 'sequence_type', 'derived_image', 'path_in_collection', 'modality'])
f = f[(f.modality == 'MR') & (f.assertion == 'present')]

DX = {  # name -> (finding filter, prompt)
    'acute ischemic stroke': lambda x: (x.finding_type == 'ischemic infarct') & (x.acuity == 'acute'),
    'chronic ischemic stroke': lambda x: (x.finding_type == 'ischemic infarct') & (x.acuity == 'chronic'),
    'subdural hematoma': lambda x: x.finding_type == 'subdural hematoma',
    'glioblastoma': lambda x: x.tumor_subtype == 'glioma: glioblastoma',
    'meningioma': lambda x: x.tumor_subtype == 'meningioma',
    'hemorrhagic stroke': lambda x: x.finding_type == 'intraparenchymal hemorrhage',
    'subarachnoid hemorrhage': lambda x: x.finding_type == 'subarachnoid hemorrhage',
    'cavernous malformation': lambda x: x.finding_type == 'cavernous malformation',
    'arteriovenous malformation': lambda x: x.finding_type == 'arteriovenous malformation',
    'brain abscess': lambda x: (x.finding_type == 'infection') & (x.subtype == 'abscess'),
}
TUMOR = {'glioblastoma', 'meningioma'}

t1 = s[(s.modality == 'MR') & (s.sequence_type == 'T1w') & (s.derived_image == 'no')]
t1_prefix = t1.groupby('study_id').path_in_collection.first()
n_series = s[s.modality == 'MR'].groupby('study_id').size()
postop = set(f[f.finding_type == 'post-surgical change'].study_id)

rng = np.random.default_rng(SEED)
used, rows, log = set(), [], []
for dx, flt in DX.items():
    x = f[flt(f) & f.laterality.isin(['left', 'right'])]
    n0 = x.study_id.nunique()
    x = x[x.study_id.isin(t1_prefix.index)]
    n1 = x.study_id.nunique()
    if dx in TUMOR:
        x = x[(x.treatment == 'none stated') & ~x.study_id.isin(postop)]
    # one row per study: sides stated for this diagnosis in the study
    g = x.groupby('study_id').agg(person_id=('person_id', 'first'), site=('site', 'first'), session_id=('session_id', 'first'),
                                  study_date=('study_date', 'first'), sides=('laterality', lambda v: '|'.join(sorted(set(v)))),
                                  locations=('location', lambda v: '|'.join(sorted({str(j) for i in v if i is not None for j in (i if hasattr(i, '__len__') and not isinstance(i, str) else [i])}))),
                                  acuity=('acuity', lambda v: '|'.join(sorted(set(v)))),
                                  size_mm=('size_value', 'max'), evidence=('evidence_text', 'first')).reset_index()
    g = g[g.sides.isin(['left', 'right'])]
    g = g.iloc[rng.permutation(len(g))]
    g = g.drop_duplicates('person_id')
    g = g[~g.person_id.isin(used)].reset_index(drop=True)
    g['rank'] = np.arange(len(g))
    used |= set(g.person_id[:10])
    g.insert(0, 'diagnosis', dx)
    g['prompt'] = f'segment the {dx} lesion'
    g['s3_prefix'] = 'Imaging/' + g.study_id.map(t1_prefix)
    g['n_series'] = g.study_id.map(n_series)
    rows.append(g)
    log.append(f'{dx:28s} studies lateralized {n0:6d} | with T1w {n1:6d} | eligible patients {len(g):6d} | '
               f'top10 sides L/R {(g.sides[:10]=="left").sum()}/{(g.sides[:10]=="right").sum()} '
               f'site I0001 {(g.site[:10]=="I0001").sum()}')
c = pd.concat(rows, ignore_index=True)
c.to_csv(os.path.join(OUT, 'cases.csv'), index=False)
open(os.path.join(OUT, 'selection_log.txt'), 'w').write('\n'.join(log) + '\n')
print('\n'.join(log))
