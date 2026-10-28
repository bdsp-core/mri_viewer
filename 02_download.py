"""
02_download.py
==============
Download every anatomical sequence (all *.nii.gz in the study's anat/ folder) of the first --n_per_dx candidates of each
diagnosis in cases.csv (01_select_cases.py; the first 10 plus spares). Run on the server, env torchenv.

  <out>/mri/<case_id>/*.nii.gz     case_id = <diagnosis slug>_<rank>
  <out>/mri/<case_id>/.done        written when the folder is complete (03_run_pibs.py waits for it)
  <out>/download_status.csv

Credentials are not stored here: parsed at run time from --creds_py.

Usage:
  python 02_download.py --cases cases.csv --out /data/imaging_test/bind_10dx --n_per_dx 13
"""
import argparse
import os
import re
from concurrent.futures import ThreadPoolExecutor

import boto3
import pandas as pd

ap = argparse.ArgumentParser()
ap.add_argument('--cases', default='cases.csv')
ap.add_argument('--out', default='/data/imaging_test/bind_10dx')
ap.add_argument('--n_per_dx', type=int, default=13)
ap.add_argument('--bucket', default='bdsp-opendata-repository')
ap.add_argument('--creds_py', default=os.path.expanduser('~/Documents/EEG_report/Morgoth2_repo/download_from_aws.py'))
ap.add_argument('--workers', type=int, default=8)
a = ap.parse_args()

src = open(a.creds_py).read()
s3 = boto3.client('s3', aws_access_key_id=re.search(r'aws_access_key_id="([^"]+)"', src).group(1),
                  aws_secret_access_key=re.search(r'aws_secret_access_key="([^"]+)"', src).group(1))


def case_id(r):
    return f"{r.diagnosis.replace(' ', '_')}_{int(r.rank):02d}"


def one(r):
    d = os.path.join(a.out, 'mri', case_id(r))
    res = {'case_id': case_id(r), 'diagnosis': r.diagnosis, 'rank': r.rank, 'person_id': r.person_id}
    if os.path.exists(os.path.join(d, '.done')):
        return dict(res, status='ok', n_files=len([f for f in os.listdir(d) if f.endswith('.nii.gz')]))
    try:
        keys = []
        kw = {'Bucket': a.bucket, 'Prefix': r.s3_prefix}
        while True:
            resp = s3.list_objects_v2(**kw)
            keys += [o['Key'] for o in resp.get('Contents', []) if o['Key'].endswith('.nii.gz')]
            if not resp.get('IsTruncated'):
                break
            kw['ContinuationToken'] = resp['NextContinuationToken']
        if not keys:
            raise FileNotFoundError(f'no .nii.gz under {r.s3_prefix}')
        os.makedirs(d, exist_ok=True)
        for k in keys:
            dst = os.path.join(d, os.path.basename(k))
            if not os.path.exists(dst):
                s3.download_file(a.bucket, k, dst + '.part')
                os.replace(dst + '.part', dst)
        status = 'ok'
    except Exception as e:
        os.makedirs(d, exist_ok=True)
        status = f'{type(e).__name__}: {str(e)[:150]}'
        keys = []
    open(os.path.join(d, '.done'), 'w').write(status)
    return dict(res, status=status, n_files=len(keys))


c = pd.read_csv(a.cases)
c = c[c['rank'] < a.n_per_dx]
os.makedirs(os.path.join(a.out, 'mri'), exist_ok=True)
with ThreadPoolExecutor(a.workers) as ex:
    st = pd.DataFrame(list(ex.map(one, c.itertuples())))
st.to_csv(os.path.join(a.out, 'download_status.csv'), index=False)
print('status', st.status.value_counts().to_dict(), '| files per case', st.n_files.describe().round(1).to_dict())
print('DOWNLOAD_DONE', flush=True)
