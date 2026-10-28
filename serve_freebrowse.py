"""
serve_freebrowse.py
===================
Serve FreeBrowse (github freesurfer/freebrowse, unmodified, cloned on the server at ~/Documents/EEG_report/freebrowse) for the
BIND 10-diagnosis Pibs cases. The upstream backend mounts the built frontend at /static, but `npm run build` emits
absolute /assets/... URLs, so the page does not load there; this wrapper imports the upstream app unchanged and also
mounts the build at / (after every upstream route). DATA_DIR (set by serve_freebrowse.sh) is the viz/ folder of the run,
so each case's volumes are at /data/<case_id>/... and its scene at /data/<case_id>/<case_id>.nvd.

The page at / is the built index.html with case_panel.js added: a floating panel that shows what the open case is (target
diagnosis, what the report states, Pibs result, layers), from /data/<case_id>/info.json written by 05_case_info.py.

Review (written by the panel; several reviewers, each identified by the name they type):
  GET  /bind/review/<case_id>?reviewer=<name>   this reviewer's latest review of the case, their edited mask (if any) and
                                                the names of everyone who has reviewed the case
  POST /bind/review             append one review row to REVIEW_DIR/reviews.csv (every save is kept; latest = last row)
  POST /bind/mask/<case_id>?reviewer=<name>
                                body = the FreeBrowse drawing as raw NIfTI; saved gzipped as
                                DATA_DIR/<case_id>/edited_mask_<reviewer>.nii.gz (one file per reviewer; the previous
                                version is kept in REVIEW_DIR/mask_history/), logged in REVIEW_DIR/mask_edits.csv.
                                The Pibs maps are never overwritten.
The upstream write endpoints (POST /data/nvd, POST /data/nii) are removed: they write any file name under DATA_DIR and are
not needed for review, and the server is reachable from the internal network.
"""
import csv
import datetime
import gzip
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.join(os.environ['FREEBROWSE'], 'backend', 'src'))
from fastapi import HTTPException, Request  # noqa: E402
from fastapi.responses import FileResponse, HTMLResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from server import app  # noqa: E402

app.router.routes[:] = [r for r in app.router.routes
                        if not (getattr(r, 'path', '') in ('/data/nvd', '/data/nii') and 'POST' in getattr(r, 'methods', ()))]

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ['DATA_DIR']
REVIEW = os.environ['REVIEW_DIR']
FIELDS = ['time', 'case_id', 'reviewer', 'pibs_verdict', 'report_side_ok', 'note']


def slug(name):
    """reviewer name -> file-name part; a name is required for every save"""
    s = re.sub(r'[^A-Za-z0-9_-]+', '_', str(name or '').strip())[:40].strip('_')
    if not s:
        raise HTTPException(400, 'reviewer name is required')
    return s


def case_dir(cid):
    d = os.path.join(DATA, cid)
    if not re.fullmatch(r'[a-z_]+_\d\d', cid) or not os.path.isfile(os.path.join(d, 'info.json')):
        raise HTTPException(404, f'unknown case {cid}')
    return d


def append(name, fields, row):
    os.makedirs(REVIEW, exist_ok=True)
    path = os.path.join(REVIEW, name)
    new = not os.path.exists(path)
    with open(path, 'a', newline='') as fh:
        w = csv.DictWriter(fh, fields)
        if new:
            w.writeheader()
        w.writerow(row)


def now():
    return datetime.datetime.now().isoformat(timespec='seconds')


@app.get('/bind/review/{cid}', include_in_schema=False)
def get_review(cid: str, reviewer: str = ''):
    d = case_dir(cid)
    me = re.sub(r'[^A-Za-z0-9_-]+', '_', reviewer.strip())[:40].strip('_')
    last, names = None, []
    path = os.path.join(REVIEW, 'reviews.csv')
    if os.path.exists(path):
        with open(path, newline='') as fh:
            for r in csv.DictReader(fh):
                if r['case_id'] != cid:
                    continue
                if r['reviewer'] not in names:
                    names.append(r['reviewer'])
                if me and slug(r['reviewer']) == me:
                    last = r
    mask = f'edited_mask_{me}.nii.gz' if me else ''
    return {'review': last, 'reviewers': names,
            'mask_url': f'/data/{cid}/{mask}' if mask and os.path.exists(os.path.join(d, mask)) else ''}


@app.post('/bind/review', include_in_schema=False)
async def post_review(request: Request):
    body = await request.json()
    case_dir(str(body.get('case_id', '')))
    slug(body.get('reviewer'))
    row = {k: str(body.get(k, '')).strip()[:2000] for k in FIELDS}
    row['time'] = now()
    append('reviews.csv', FIELDS, row)
    return {'saved': row['time']}


@app.post('/bind/mask/{cid}', include_in_schema=False)
async def post_mask(cid: str, request: Request):
    d = case_dir(cid)
    who = request.query_params.get('reviewer', '')
    me = slug(who)
    raw = await request.body()
    if len(raw) < 352 or raw[344:348] not in (b'n+1\0', b'ni1\0'):
        raise HTTPException(400, 'not a NIfTI-1 file')
    out = os.path.join(d, f'edited_mask_{me}.nii.gz')
    t = now()
    if os.path.exists(out):
        os.makedirs(os.path.join(REVIEW, 'mask_history'), exist_ok=True)
        shutil.copy2(out, os.path.join(REVIEW, 'mask_history', f'{cid}_{me}_{t.replace(":", "")}.nii.gz'))
    with gzip.open(out + '.tmp', 'wb') as fh:
        fh.write(raw)
    os.replace(out + '.tmp', out)
    append('mask_edits.csv', ['time', 'case_id', 'reviewer', 'file', 'bytes'],
           {'time': t, 'case_id': cid, 'reviewer': who.strip(), 'file': os.path.basename(out), 'bytes': len(raw)})
    return {'saved': t}


@app.get('/case_panel.js', include_in_schema=False)
def case_panel():
    return FileResponse(os.path.join(HERE, 'case_panel.js'), media_type='text/javascript',
                        headers={'Cache-Control': 'no-cache'})


@app.get('/', include_in_schema=False)
@app.get('/index.html', include_in_schema=False)
def index():
    page = open(os.path.join(os.environ['NIIVUE_BUILD_DIR'], 'index.html'), encoding='utf-8').read()
    return HTMLResponse(page.replace('</body>', '<script src="/case_panel.js"></script></body>', 1),
                        headers={'Cache-Control': 'no-cache'})


app.mount('/', StaticFiles(directory=os.environ['NIIVUE_BUILD_DIR'], html=True), name='root')
