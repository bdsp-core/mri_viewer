# mri_viewer: BIND 10-diagnosis Pibs lesion review

We picked 100 brain MRI studies from the BIND report package, 10 for each of 10 diagnoses:
- acute ischemic stroke
- chronic ischemic stroke
- subdural hematoma
- glioblastoma
- meningioma
- hemorrhagic stroke
- subarachnoid hemorrhage
- cavernous malformation
- arteriovenous malformation
- brain abscess

Pibs segmented each lesion using all of the study's sequences, after they had been registered to its T1. Experts review the results in a web viewer. For each case they record whether the Pibs lesion is right and whether the report can be trusted, and they can correct the lesion by hand.

This repository contains code only. The MRIs, the report text and the Pibs outputs are BIND data and stay on the group server (see [Data policy](#data-policy)).

## What we added to FreeBrowse

**Base.** The viewer is **FreeBrowse**, <https://github.com/freesurfer/freebrowse> (commit `2eae89e`, 2026-10-27). It is a React + NiiVue frontend with a FastAPI backend.

FreeBrowse already provides:
- the multi-planar and 3D MRI display;
- the layer list (show/hide, opacity, contrast, colormap);
- loading `.nvd` scenes;
- the drawing tools (Pen, Pen Erases, Pen Fill, Undo).

FreeBrowse itself is used **unmodified**. It is cloned and built on the server (`npm ci && npm run build` in `frontend/`, `pixi install` in `backend/`), and nothing in that clone is edited. Everything below is added around it at start-up by the files in this repository.

### 1. Case panel (`case_panel.js`)

A floating panel over the FreeBrowse page, at the bottom left.
- **Case navigation.** "Previous case / Next case" buttons with a `Case k / 100` counter, and a list to jump to any case. Each case in the list is marked ✓, ✗ or "no lesion" (Pibs side vs report side).
- **What the case shows:**
  - the target diagnosis;
  - the side and locations the report gives;
  - the report sentence the case was selected from.
- **Pibs result for both prompts.** The diagnosis prompt and the generic "segment the lesion" prompt. For each: the side and volume of the largest component, the number of components, whether the side matches the report, and how many sequences Pibs used.
- **All report findings for the study** (present or possible), with the target finding highlighted.
- **The full radiology report**, with the target sentence highlighted.
- **A legend of the scene's layers.**

### 2. Expert review (`case_panel.js` + `serve_freebrowse.py`)

- **Reviewer name.** It is required before anything can be saved, and the browser remembers it. Several reviewers can review the same case independently.
- **Review form:**
  - the Pibs verdict: Correct / Partially correct / Wrong location / False positive / Missed;
  - the report-side rating: Reliable / Not reliable / Unsure;
  - a free-text note.
- **Where reviews are saved.** Each save appends a row to `reviews.csv` on the server; a reviewer's latest row is their current review.
- **Reopening a case.** The panel restores that reviewer's last review and lists who else has reviewed the case.

### 3. Guided lesion editing (`case_panel.js` + `serve_freebrowse.py` + `06_lesion_masks.py`)

- **Starting drawing.** The Pibs lesion is loaded as an editable FreeBrowse drawing. It is first resampled onto the T1 voxel grid, because about half of the Pibs maps are on a different grid (`06_lesion_masks.py`). If the reviewer has saved an edit before, that edit is loaded instead.
- **Three steps in a fixed order: load, edit, save.** The current step is highlighted, and the panel shows how many voxels were added and removed.
- **Painting starts off.** Painting stays off until the reviewer chooses Draw Mode → Pen, so moving the crosshair never paints by accident.
- **"Save edited lesion" is disabled until the drawing actually differs from what was loaded.**
- **Each reviewer's edit is a separate file:** `edited_mask_<reviewer>.nii.gz`, with earlier versions kept and every save logged. The Pibs output is never overwritten.
- **FreeBrowse's own "Save Drawing" button is hidden.** It only turns the drawing into an in-browser volume and saves nothing to the server.

### 4. Server changes (`serve_freebrowse.py`, `serve_freebrowse.sh`)

- **The page is served at `/`.** Upstream mounts the built frontend at `/static`, but the build requests `/assets/...`, so the page is blank there. `case_panel.js` is injected into the page.
- **New endpoints:**
  - `GET/POST /bind/review`: reviews;
  - `POST /bind/mask/<case_id>`: edited lesions.
  - Both need a reviewer name.
- **Removed upstream endpoints:** `POST /data/nvd` and `POST /data/nii`. They can write any file name under the data folder, and review does not need them.
- **Start-up.** `serve_freebrowse.sh` starts the server on port 8765 with the case data folder; FreeBrowse's AI features are off.

### 5. Data prepared for the viewer (scripts 04 to 06)

- **One FreeBrowse scene (`.nvd`) per case:**
  - the T1;
  - the registered FLAIR/T2, hidden;
  - the Pibs diagnosis-prompt lesion in red;
  - the generic-prompt lesion in blue, hidden.
  - The crosshair starts at the largest lesion component.
- **Case information.** `info.json` per case and `index.json` for the case list: report findings, report text and the Pibs result.

Pibs is `pibs_alpha_v4`. It is run in all-sequence mode: every sequence is rigidly registered onto the T1, and the T1 plus the registered sequences are the input.

## Expert review guide

### 1. Open the viewer

The viewer runs on the group server and is opened in a browser, preferably Chrome.

- **Through an SSH tunnel (works now).** Run `ssh -N -L 8765:127.0.0.1:8765 <review account>@<server>` (ask the group for the account and password), leave it running, then go to <http://localhost:8765/>.
- **Directly at `http://<server>:8765/`.** This works only once IT opens port 8765 to the internal network. At present the network passes only SSH (port 22) to the server.

To open a specific case, use `http://localhost:8765/?nvd=/data/<case_id>/<case_id>.nvd`, for example `glioblastoma_00`. If you open the bare address, choose a case from the panel's case list.

### 2. The screen

- **Centre: the images.** Axial, coronal and sagittal slices, plus a 3D view.
  - The crosshair starts at the centre of the largest Pibs lesion.
  - Left-click or drag on an image to move the crosshair. The scroll wheel changes the slice.
  - Right-drag changes the contrast, or pans and zooms; the choice is at the top, under "Right drag".
  - The "View" buttons at the top switch the layout, for example a single large Axial view.
- **Right: the FreeBrowse sidebar.** The first tab, "Volumetric Details", lists the layers. The eye icon shows or hides a layer, and opacity and contrast are set below.

| Layer | Meaning | At start |
|---|---|---|
| `T1` | Base image. Everything is aligned to it. | shown |
| `sub-..._FLAIR`, `sub-..._T2w` | The study's FLAIR / T2, registered to the T1 | hidden |
| `Pibs: <diagnosis>` | Pibs lesion for the prompt "segment the &lt;diagnosis&gt; lesion" (probability > 0.5) | shown, red |
| `Pibs: generic lesion` | Pibs lesion for the prompt "segment the lesion", for comparison | hidden, blue |

- **Bottom left: the case panel.** The "–" button collapses or expands it.
  - **Previous case / Next case**, with `Case k / 100` between them. The list below the buttons jumps to any case. Each entry is marked ✓ (Pibs side matches the report), ✗ (it does not) or "no lesion".
  - **What the case shows:**
    - the target diagnosis, with the side and locations the report gives;
    - the report sentence the case was selected from;
    - the Pibs result for both prompts: the side and size of the largest component, and whether the side matches the report;
    - how many sequences Pibs used.
  - **Review:** your name, your verdict and a note (section 3).
  - **Edit lesion:** optional correction of the Pibs lesion (section 4).
  - **Below:** every finding the report states for this study (present or possible), with the target finding highlighted, and the full radiology report under "Radiology report". The target sentence is highlighted there too.

### 3. Review a case

1. **Type your name** in "Your name (required)" at the top of the Review box.
   - Every save is recorded under this name.
   - The browser remembers it, so you type it once.
   - Use the same name every time.
2. **Read the panel:** the target diagnosis, the side and location, and the report sentence. Open "Radiology report" if you need the context, for example a history of surgery or a lesion described as resolved.
3. **Look at the images.**
   - Turn on FLAIR and/or T2 with the eye icon, and compare the red Pibs lesion with the lesion you see.
   - Scroll through all slices that contain the lesion, not only the crosshair slice.
   - Toggle the red layer on and off to see the tissue underneath.
4. **Choose "Pibs lesion":**

| Choice | Use when |
|---|---|
| **Correct** | The red area covers the lesion named in the target diagnosis, with no important extra regions. |
| **Partially correct** | The red area overlaps the lesion but misses a substantial part of it, or also marks substantial unrelated tissue. |
| **Wrong location** | The lesion is visible, but the red area is mainly somewhere else. |
| **False positive** | There is no such lesion on these images, for example because it has resolved or was resected, yet Pibs marks something. |
| **Missed** | The lesion is visible, but Pibs marks nothing or almost nothing of it. |

5. **Choose "Report side":**
   - **Reliable:** the images agree with the report's side and description of the target lesion.
   - **Not reliable:** they do not. For example the side is wrong, the lesion has resolved or been treated, or it is a different diagnosis.
   - **Unsure:** you cannot tell.
6. **Note** (optional): anything worth recording, for example "lesion resected, cavity only" or "Pibs also marks the contralateral ventricle".
7. **Click "Save review."** The time of the save appears next to the button.
   - Saving again replaces your earlier review of that case, but the old row is kept in the log.
   - Other reviewers' reviews are kept separately. The panel lists who else has reviewed the case.

### 4. Correct the lesion (optional)

Do this when Pibs is close but not right and a corrected mask is useful. The three steps are done in order; the current step is outlined in blue, and finished steps get a green number.

1. **Load.** Click "Load Pibs lesion".
   - The Pibs lesion becomes an editable red drawing, and the original red Pibs layer is hidden.
   - The drawing tools open in the right sidebar.
   - If you saved an edit of this case before, the button reads "Load my saved edit" and loads your edit instead.
2. **Edit.** In the right sidebar, set **Draw Mode → Pen** and paint on the image.
   - **Pen Erases** (tick it): the pen erases instead of painting.
   - **Pen Fill** (on by default): a closed outline is filled. Untick it to draw thin lines.
   - **Undo:** reverts the last stroke.
   - **Each stroke paints only the slice you draw on.** For a lesion that spans many slices, edit it slice by slice.
   - Set **Draw Mode → None** whenever you want to move the crosshair or change slices without painting. While Draw Mode is None, clicks do not paint.
   - The panel shows how much has changed, for example `+641 / −0 voxels`.
3. **Save.** "Save edited lesion" becomes clickable only once the drawing differs from what was loaded. Click it.
   - Your edit is stored as your own file for this case. The Pibs output is never changed.
   - Saving again keeps the previous version as history.
   - "Reload (discard changes)" in step 1 throws away unsaved changes and starts again from your last save, or from Pibs if you have not saved yet.

Save both the review and any edit before you move to another case. Changing case reloads the page, and anything unsaved is lost.

### 5. Suggested routine per case

1. Read the panel.
2. Look at T1 + red, then at FLAIR/T2, scrolling through the lesion.
3. Choose the Pibs verdict and the report-side rating, and add a note if needed.
4. Click **Save review**.
5. If needed, correct the lesion (steps 1 to 3 above).
6. Click **Next case**.

### 6. Known issues to look out for

- **Report labels.** The BIND report labels were extracted automatically and can be wrong. A case can be labelled "present" or "untreated" although the report says the lesion has resolved or was already resected. Rate these with "Report side: Not reliable" and say why in the note.
- **Large fields of view.** When the scan extends into the neck, the largest Pibs component can be outside the brain.
- **Partial T1 coverage.** About 4 cases lose roughly 10% of the Pibs lesion when it is put on the T1 grid for editing, because Pibs saw tissue beyond the T1's coverage. Those voxels cannot be edited.

## What is recorded (on the server, `/data/imaging_test/bind_10dx/`)

| File | Content |
|---|---|
| `review/reviews.csv` | One row per "Save review": `time, case_id, reviewer, pibs_verdict, report_side_ok, note`. A reviewer's latest row for a case is their current review. |
| `viz/<case_id>/edited_mask_<reviewer>.nii.gz` | A reviewer's corrected lesion: uint8 0/1 on the voxel grid of `viz/<case_id>/t1.nii.gz`. |
| `review/mask_edits.csv` | One row per "Save edited lesion": `time, case_id, reviewer, file, bytes`. |
| `review/mask_history/` | Earlier versions of each edited mask. |

## Pipeline (how the cases were made)

All scripts are in this folder. Steps 02 to 04 and 06 run on the server.

| Step | Script | What it does |
|---|---|---|
| 01 | `01_select_cases.py` | Selects cases from the BIND parquet tables: `findings` and `series`. |
| | | Rules: an MR study; the finding is asserted present; the report gives a single side, left or right; the study has a non-derived T1w series. |
| | | For glioblastoma and meningioma, the treatment must be "none stated" and the study must have no post-surgical change. |
| | | One study per patient, and each patient is used for one diagnosis only. The order is random (seed 20261027); the first 10 per diagnosis plus 3 spares are kept. |
| | | Output: `cases.csv`. |
| 02 | `02_download.py` | Downloads all anatomical sequences of each case from S3 (`bdsp-opendata-repository`). The credentials are read at run time from a file on the server, never stored here. |
| 03 | `03_run_pibs.py` | Runs Pibs (env `pibs_reg`). |
| | | Picks the T1 in the order MPRAGE > SPGR > SE > other, and registers every other sequence onto it. |
| | | Runs a diagnosis prompt and a generic prompt. If the GPU runs out of memory, it falls back first to the T1 spacing and then to dropping sequences; `files_used` records what was used. |
| | | Continues each diagnosis until 10 cases succeed. |
| 04 | `04_lesions_and_scenes.py` | (env `torchenv`) Finds the lesion: probability > 0.5, the largest 26-connected component, its side, and whether the side matches the report. |
| | | Writes `results/lesions.csv` and the summaries, plus one FreeBrowse scene (`.nvd`) per case. |
| 05 | `05_case_info.py` | (run where the BIND package is) Writes `viz/<case_id>/info.json` and `viz/index.json`, which the panel reads: the report findings, the report text and the Pibs result. |
| 06 | `06_lesion_masks.py` | Writes `pibs_mask_diagnosis.nii.gz`, the Pibs lesion resampled onto the T1 grid. It is the starting drawing for edits. |
| — | `serve_freebrowse.sh` | Starts the viewer. |

Start or restart the viewer on the server:

```
pkill -f '[u]vicorn serve_freebrowse'
nohup bash serve_freebrowse.sh > /data/imaging_test/bind_10dx/freebrowse_server.log 2>&1 &
```

Run the stop command and the start command separately. `serve_freebrowse.sh` expects the FreeBrowse clone at `~/Documents/EEG_report/freebrowse` (or set `FREEBROWSE`), already built.

## Data policy

The BIND report package must stay within the group: do not pass it on. **No patient data goes into this repository.** That rules out:
- the MRIs;
- the report text, and any CSV holding report sentences, such as `cases.csv`;
- Pibs outputs, `results/`, and review files.

`.gitignore` excludes these. Data and review records stay on the server.
