// case_panel.js: floating panel on the FreeBrowse page (added by serve_freebrowse.py) that shows what the open BIND case
// is: target diagnosis, what the report states, the Pibs result and the layers. Reads /data/<case_id>/info.json and
// /data/index.json written by 05_case_info.py. The case is taken from ?nvd=... and from any .nvd the page fetches later
// (e.g. one opened from the NVD tab).
// Review: each reviewer (identified by the name typed in the panel, required) saves a review per case (POST /bind/review
// -> reviews.csv on the server) and can edit the Pibs lesion with FreeBrowse's own drawing tools: step 1 loads
// pibs_mask_diagnosis.nii.gz (or this reviewer's last saved edit) as the drawing layer of window.freebrowse.nv, step 3
// posts the drawing to /bind/mask/<case_id>?reviewer=<name> (edited_mask_<name>.nii.gz, one per reviewer; the Pibs output
// is never overwritten). See serve_freebrowse.py.
(function () {
  const css = `
#bcp { position: fixed; left: 12px; bottom: 12px; z-index: 9999; width: 430px; max-width: calc(100vw - 24px);
  max-height: 72vh; display: flex; flex-direction: column; background: rgba(22,24,28,.94); color: #e8e8e6;
  font: 13px/1.45 -apple-system, "Helvetica Neue", Arial, sans-serif; border: 1px solid #3a3d44; border-radius: 10px;
  box-shadow: 0 6px 24px rgba(0,0,0,.4); }
#bcp.min { max-height: none; }
#bcp.min .body { display: none; }
#bcp .head { display: flex; gap: 6px; align-items: center; padding: 8px 10px; border-bottom: 1px solid #3a3d44; }
#bcp .nav { display: flex; gap: 8px; align-items: center; padding: 10px 10px 0; }
#bcp .nav button { flex: 1; padding: 7px 10px; font-size: 14px; font-weight: 650; }
#bcp .nav #bcp-next { background: #2f5d9a; border-color: #4f7bb5; }
#bcp .nav #bcp-next:hover { background: #386cb2; }
#bcp .nav .pos { min-width: 64px; text-align: center; color: #9aa0aa; font-size: 12px; }
#bcp .head select { flex: 1; min-width: 0; background: #2a2d33; color: inherit; border: 1px solid #454952;
  border-radius: 6px; padding: 3px 4px; font: inherit; }
#bcp button { background: #2a2d33; color: inherit; border: 1px solid #454952; border-radius: 6px; padding: 2px 8px;
  font: inherit; cursor: pointer; }
#bcp button:hover { background: #363a42; }
#bcp .body { overflow-y: auto; padding: 8px 12px 12px; }
#bcp h3 { margin: 10px 0 4px; font-size: 11px; letter-spacing: .06em; text-transform: uppercase; color: #9aa0aa; }
#bcp .dx { font-size: 17px; font-weight: 650; margin: 2px 0; }
#bcp .muted { color: #9aa0aa; }
#bcp .ok { color: #7bd88f; } #bcp .bad { color: #ff7b72; }
#bcp table { border-collapse: collapse; width: 100%; }
#bcp td { padding: 3px 4px; border-top: 1px solid #33363d; vertical-align: top; }
#bcp tr.target td { background: rgba(255,90,90,.14); }
#bcp .tag { display: inline-block; padding: 0 5px; border-radius: 4px; background: #3a3d44; font-size: 11px; }
#bcp .sw { display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 6px; vertical-align: -1px; }
#bcp pre { white-space: pre-wrap; font: 12px/1.45 ui-monospace, Menlo, monospace; background: #15171a; padding: 8px;
  border-radius: 6px; margin: 4px 0 0; }
#bcp mark { background: #6b4b10; color: #fff; }
#bcp details summary { cursor: pointer; color: #9aa0aa; margin-top: 10px; }
#bcp .rev { margin-top: 10px; padding: 8px 10px; border: 1px solid #4a4f58; border-radius: 8px; background: #1d2025; }
#bcp .rev h3 { margin-top: 2px; }
#bcp .opts { display: flex; flex-wrap: wrap; gap: 4px 6px; margin: 2px 0 6px; }
#bcp .opts label { display: inline-flex; align-items: center; gap: 4px; padding: 2px 7px; border: 1px solid #454952;
  border-radius: 6px; cursor: pointer; }
#bcp .opts label:has(input:checked) { background: #2f4a6e; border-color: #4f7bb5; }
#bcp .opts input { margin: 0; }
#bcp textarea, #bcp input[type=text] { width: 100%; box-sizing: border-box; background: #2a2d33; color: inherit;
  border: 1px solid #454952; border-radius: 6px; padding: 4px 6px; font: inherit; }
#bcp textarea { height: 52px; resize: vertical; }
#bcp .row { display: flex; gap: 6px; align-items: center; margin-top: 6px; flex-wrap: wrap; }
#bcp button:disabled { opacity: .4; cursor: not-allowed; background: #2a2d33; border-color: #454952; }
#bcp .stp { display: flex; gap: 8px; padding: 6px 8px; margin-top: 6px; border: 1px solid #33363d; border-radius: 6px;
  opacity: .45; }
#bcp .stp .n { flex: none; width: 20px; height: 20px; border-radius: 50%; background: #3a3d44; text-align: center;
  font-weight: 700; line-height: 20px; font-size: 12px; }
#bcp .stp.active { opacity: 1; border-color: #4f7bb5; background: rgba(79,123,181,.12); }
#bcp .stp.active .n { background: #2f5d9a; }
#bcp .stp.done { opacity: .8; }
#bcp .stp.done .n { background: #2e6b3d; }
#bcp .stp .t { flex: 1; }
#bcp .primary { background: #2f5d9a; border-color: #4f7bb5; }
#bcp .primary:hover { background: #386cb2; }
#bcp .stat { font-size: 12px; }`;
  const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
  let index = [], current = null;

  const el = document.createElement('div');
  el.id = 'bcp';
  el.innerHTML = `<div class="nav"><button id="bcp-prev" title="previous case">◀ Previous case</button>
    <span class="pos" id="bcp-pos"></span><button id="bcp-next" title="next case">Next case ▶</button></div>
    <div class="head"><select id="bcp-sel" title="jump to a case"></select>
    <button id="bcp-min" title="collapse / expand the panel">–</button></div>
    <div class="body" id="bcp-body"><span class="muted">No case open.</span></div>`;
  const st = document.createElement('style');
  st.textContent = css;

  function open(cid) {  // reload the page on that case's scene
    location.href = `${location.pathname}?nvd=/data/${cid}/${cid}.nvd`;
  }
  function step(d) {
    const i = index.findIndex(c => c.case_id === current);
    if (index.length) open(index[(i + d + index.length) % index.length].case_id);
  }

  function side(p) {
    if (!p || !p.found) return '<span class="bad">no lesion (p &gt; 0.5 empty)</span>';
    const m = p.side_match ? '<span class="ok">✓ matches report</span>' : '<span class="bad">✗ differs from report</span>';
    return `largest component <b>${esc(p.largest_side)}</b>, ${(+p.largest_ml).toFixed(1)} ml
      <span class="muted">(${p.n_components} components)</span> ${m}`;
  }

  function render(d) {
    const t = d.target;
    const rows = d.findings.map(f => {
      const tgt = f.evidence && f.evidence === t.evidence;
      return `<tr class="${tgt ? 'target' : ''}"><td><b>${esc(f.finding)}</b>
        ${f.assertion === 'possible' ? '<span class="tag">possible</span>' : ''}
        ${f.acuity && f.acuity !== 'not stated' ? `<span class="tag">${esc(f.acuity)}</span>` : ''}
        <div class="muted">${esc([f.side !== 'not stated' ? f.side : '', f.location, f.size].filter(Boolean).join(' · '))}</div></td></tr>`;
    }).join('');
    let rep = esc(d.report_text);
    if (t.evidence) {
      const e = esc(t.evidence), k = rep.toLowerCase().indexOf(e.toLowerCase());
      if (k >= 0) rep = rep.slice(0, k) + '<mark>' + rep.slice(k, k + e.length) + '</mark>' + rep.slice(k + e.length);
    }
    const g = d.pibs.generic;
    el.querySelector('#bcp-body').innerHTML = `
      <div class="muted">${esc(d.case_id)} · ${esc(d.site)} · ${esc(d.exam)} · ${esc(d.study_date_shifted)} (shifted)</div>
      <div class="dx">${esc(d.diagnosis)}</div>
      <div>report: <b>${esc(t.side)}</b> ${esc(t.locations)}${t.size_mm ? ` · ${esc(t.size_mm)} mm` : ''}</div>
      <div class="muted" style="margin-top:2px">“${esc(t.evidence)}”</div>
      <h3>Pibs result</h3>
      <div><span class="sw" style="background:#ff4040"></span>${esc(d.pibs.diagnosis.prompt)}: ${side(d.pibs.diagnosis)}</div>
      ${g ? `<div><span class="sw" style="background:#4070ff"></span>${esc(g.prompt)}: ${side(g)}</div>` : ''}
      <div class="muted">${d.files_used.length} sequences used (${esc(d.fallback)})</div>
      <div id="bcp-review"></div>
      <h3>Layers</h3>
      ${d.layers.map(([n, s]) => `<div><b>${esc(n)}</b> <span class="muted">${esc(s)}</span></div>`).join('')}
      <h3>All findings in the report (${d.findings.length}, present / possible) · overall: ${esc(d.report_overall)}</h3>
      <table>${rows}</table>
      <details><summary>Radiology report (target sentence highlighted)</summary><pre>${rep}</pre></details>`;
  }

  function showPos() {  // "12 / 100" next to the buttons
    const i = index.findIndex(c => c.case_id === current);
    el.querySelector('#bcp-pos').textContent = i >= 0 ? `Case ${i + 1} / ${index.length}` : '';
  }

  async function load(cid) {
    if (!cid || cid === current) return;
    current = cid;
    const sel = el.querySelector('#bcp-sel');
    if (sel) sel.value = cid;
    showPos();
    try {
      const r = await fetch(`/data/${cid}/info.json`);
      if (!r.ok) throw new Error(r.status);
      render(await r.json());
      renderReview(cid);
    } catch (e) {
      el.querySelector('#bcp-body').innerHTML = `<span class="muted">No case info for ${esc(cid)}.</span>`;
    }
  }

  const VERDICTS = [['correct', 'Correct'], ['partial', 'Partially correct'], ['wrong_location', 'Wrong location'],
    ['false_positive', 'False positive'], ['missed', 'Missed']];
  const SIDE_OK = [['yes', 'Reliable'], ['no', 'Not reliable'], ['unsure', 'Unsure']];
  const store = {  // reviewer name, per browser only
    get: () => { try { return localStorage.getItem('bcp-reviewer') || ''; } catch (e) { return ''; } },
    set: v => { try { localStorage.setItem('bcp-reviewer', v); } catch (e) { /* ignore */ } },
  };
  const radios = (name, opts, val) => opts.map(([v, t]) =>
    `<label><input type="radio" name="${name}" value="${v}" ${v === val ? 'checked' : ''}>${t}</label>`).join('');

  async function renderReview(cid) {
    const box = el.querySelector('#bcp-review');
    const name = store.get();
    let st = {review: null, reviewers: [], mask_url: ''};
    try { st = await (await realFetch(`/bind/review/${cid}?reviewer=${encodeURIComponent(name)}`)).json(); } catch (e) { /* no server state */ }
    if (cid !== current || !box.isConnected) return;  // the case changed (or was re-rendered) meanwhile
    const r = st.review || {};
    const others = (st.reviewers || []).filter(n => n !== name);
    box.innerHTML = `<div class="rev">
      <h3>Review</h3>
      <div class="row" style="margin-top:0"><input type="text" id="bcp-who" placeholder="Your name (required)" style="flex:1"
        value="${esc(name)}"></div>
      <div class="stat" id="bcp-wstat">${name ? (r.time ? `<span class="muted">Your last review: ${esc(r.time)}</span>`
        : '<span class="muted">You have not reviewed this case yet.</span>') : '<span class="bad">Enter your name first; every save is recorded under it.</span>'}
        ${others.length ? `<span class="muted"> · also reviewed by ${others.map(esc).join(', ')}</span>` : ''}</div>
      <div class="muted" style="margin-top:6px">Pibs lesion</div><div class="opts">${radios('bcp-v', VERDICTS, r.pibs_verdict)}</div>
      <div class="muted">Report side</div><div class="opts">${radios('bcp-s', SIDE_OK, r.report_side_ok)}</div>
      <textarea id="bcp-note" placeholder="Note">${esc(r.note || '')}</textarea>
      <div class="row"><button class="primary" id="bcp-save" ${name ? '' : 'disabled'}>Save review</button>
        <span class="stat muted" id="bcp-rstat"></span></div>
      <h3 style="margin-top:12px">Edit lesion <span class="muted" style="text-transform:none">(optional, the Pibs output is never overwritten)</span></h3>
      <div class="stp active" id="bcp-st1"><span class="n">1</span><div class="t">Load the lesion as an editable drawing
        <div class="row"><button class="primary" id="bcp-edit" ${name ? '' : 'disabled'}>${st.mask_url ? 'Load my saved edit' : 'Load Pibs lesion'}</button></div>
        ${st.mask_url ? '<div class="muted">You saved an edited version of this case before; it is loaded instead of the Pibs output.</div>' : ''}</div></div>
      <div class="stp" id="bcp-st2"><span class="n">2</span><div class="t">In the drawing tools on the right set
        <b>Draw Mode → Pen</b> and paint on the image. Tick <b>Pen Erases</b> to erase, <b>Pen Fill</b> to fill a closed
        outline; <b>Undo</b> reverts. Each stroke paints only the current slice. Set Draw Mode back to <b>None</b> to move
        the crosshair without painting.
        <div class="row"><button id="bcp-tools" disabled>Open drawing tools</button><span class="stat" id="bcp-diff"></span></div></div></div>
      <div class="stp" id="bcp-st3"><span class="n">3</span><div class="t">Save
        <div class="row"><button class="primary" id="bcp-msave" disabled>Save edited lesion</button></div>
        <div class="stat muted" id="bcp-mstat">Enabled once the drawing differs from what was loaded.</div></div></div></div>`;
    const who = el.querySelector('#bcp-who');
    who.onchange = () => {  // a new name: show that reviewer's own review / edit (unless an edit is in progress)
      store.set(who.value.trim());
      if (!ed.snap) renderReview(cid);
    };
    el.querySelector('#bcp-save').onclick = async () => {
      const val = n => (el.querySelector(`input[name=${n}]:checked`) || {}).value || '';
      const stat = el.querySelector('#bcp-rstat');
      if (!who.value.trim()) { stat.innerHTML = '<span class="bad">Enter your name first.</span>'; return; }
      store.set(who.value.trim());
      try {
        const res = await realFetch('/bind/review', {method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({case_id: cid, reviewer: who.value.trim(), pibs_verdict: val('bcp-v'),
            report_side_ok: val('bcp-s'), note: el.querySelector('#bcp-note').value})});
        if (!res.ok) throw new Error(res.status);
        stat.innerHTML = `<span class="ok">Saved ${esc((await res.json()).saved)}</span>`;
      } catch (e) { stat.innerHTML = `<span class="bad">Save failed: ${esc(e.message)}</span>`; }
    };
    el.querySelector('#bcp-edit').onclick = () => editLesion(cid, st.mask_url);
    el.querySelector('#bcp-msave').onclick = () => saveLesion(cid);
    el.querySelector('#bcp-tools').onclick = openTools;
  }

  const viewer = () => (window.freebrowse && window.freebrowse.nv) || null;

  // Edit flow: 1 load -> 2 change -> 3 save. Save stays disabled until the drawing differs from the loaded snapshot.
  const ed = {snap: null, timer: null, saved: ''};  // saved: message of the last save, until the next change
  const bitmap = nv => nv && nv.drawingVolume && nv.drawingVolume.img;

  function steps(active, done) {
    [1, 2, 3].forEach(k => {
      const e = el.querySelector(`#bcp-st${k}`);
      e.classList.toggle('active', k === active);
      e.classList.toggle('done', done.includes(k));
    });
  }

  function diff() {  // voxels added / removed relative to the loaded snapshot
    const cur = bitmap(viewer());
    if (!cur || !ed.snap || cur.length !== ed.snap.length) return null;
    let add = 0, rem = 0;
    for (let i = 0; i < cur.length; i++) {
      const c = cur[i] !== 0, o = ed.snap[i] !== 0;
      if (c && !o) add++; else if (o && !c) rem++;
    }
    return {add, rem};
  }

  function watch() {
    const d = diff(), save = el.querySelector('#bcp-msave');
    if (!d || !save) return;
    const changed = d.add + d.rem > 0;
    el.querySelector('#bcp-diff').innerHTML = changed
      ? `<span class="ok">+${d.add} / −${d.rem} voxels</span>` : '<span class="muted">no change yet</span>';
    save.disabled = !changed;
    if (changed) ed.saved = '';
    const stat = el.querySelector('#bcp-mstat');
    if (ed.saved) { stat.innerHTML = ed.saved; steps(0, [1, 2, 3]); return; }
    stat.textContent = changed ? 'Ready to save.' : 'Enabled once the drawing differs from what was loaded.';
    steps(changed ? 3 : 2, changed ? [1, 2] : [1]);
  }

  function openTools() {  // the FreeBrowse sidebar's drawing tab (a Radix tab: activates on mousedown)
    const t = document.querySelector('button[role=tab][id$="-trigger-drawing"]');
    if (!t) return;
    t.dispatchEvent(new MouseEvent('mousedown', {bubbles: true, button: 0}));
    t.click();
  }

  async function editLesion(cid, maskUrl) {
    const nv = viewer(), stat = el.querySelector('#bcp-mstat');
    if (!nv || !nv.volumes.length) { stat.innerHTML = '<span class="bad">Images are still loading, try again in a moment.</span>'; return; }
    if (ed.snap && diff() && diff().add + diff().rem > 0 && !confirm('Discard the unsaved changes and reload?')) return;
    try {
      await nv.loadDrawing(maskUrl || `/data/${cid}/pibs_mask_diagnosis.nii.gz`);
      // hide the red Pibs map so the drawing (same voxels) is what is seen
      nv.volumes.forEach((v, i) => {
        if (/^Pibs: (?!generic)/.test(v.name || '')) nv.setVolume(i, {opacity: 0});
      });
      nv.drawIsEnabled = false;  // no painting until the reviewer picks Pen (FreeBrowse's Draw Mode shows None)
      ed.snap = bitmap(nv) ? bitmap(nv).slice() : null;
      ed.saved = '';
      el.querySelector('#bcp-edit').textContent = 'Reload (discard changes)';
      el.querySelector('#bcp-tools').disabled = false;
      clearInterval(ed.timer);
      ed.timer = setInterval(watch, 700);
      watch();
      openTools();
    } catch (e) { stat.innerHTML = `<span class="bad">Load failed: ${esc(e.message)}</span>`; }
  }

  async function saveLesion(cid) {
    const nv = viewer(), stat = el.querySelector('#bcp-mstat');
    const d = diff();
    if (!nv || !nv.drawingVolume || !d || d.add + d.rem === 0) return;  // button is disabled in these cases anyway
    try {
      const bytes = await nv.saveVolume({filename: '', isSaveDrawing: true, volumeByIndex: 0});
      if (!(bytes instanceof Uint8Array)) throw new Error('drawing export failed');
      const name = ((el.querySelector('#bcp-who') || {}).value || store.get()).trim();
      if (!name) { stat.innerHTML = '<span class="bad">Enter your name first.</span>'; return; }
      const who = encodeURIComponent(name);
      const res = await realFetch(`/bind/mask/${cid}?reviewer=${who}`, {method: 'POST',
        headers: {'Content-Type': 'application/octet-stream'}, body: bytes});
      if (!res.ok) throw new Error(res.status);
      const t = (await res.json()).saved;
      ed.snap = bitmap(nv).slice();  // further changes are needed before the next save
      ed.saved = `<span class="ok">Saved your edited lesion (${esc(t)}, +${d.add} / −${d.rem} voxels)</span>`;
      watch();
    } catch (e) { stat.innerHTML = `<span class="bad">Save failed: ${esc(e.message)}</span>`; }
  }

  const caseOf = u => (String(u).match(/([A-Za-z0-9_]+)\.nvd(\?|$)/) || [])[1];
  const realFetch = window.fetch.bind(window);
  window.fetch = function (input, init) {  // follow scenes opened inside the app
    const c = caseOf(typeof input === 'string' ? input : input && input.url);
    if (c) load(c);
    return realFetch(input, init);
  };

  // FreeBrowse's own "Save Drawing" only closes the drawing into an in-browser volume (nothing reaches the server), so it
  // is hidden here; step 3 of the panel is the only save.
  new MutationObserver(() => {
    document.querySelectorAll('button').forEach(x => {
      if (x.textContent.trim() === 'Save Drawing' && !x.hidden) { x.hidden = true; x.style.setProperty('display', 'none', 'important'); }
    });
  }).observe(document.documentElement, {childList: true, subtree: true});

  async function start() {
    document.head.appendChild(st);
    document.body.appendChild(el);
    el.querySelector('#bcp-min').onclick = () => el.classList.toggle('min');
    el.querySelector('#bcp-prev').onclick = () => step(-1);
    el.querySelector('#bcp-next').onclick = () => step(1);
    const sel = el.querySelector('#bcp-sel');
    sel.onchange = () => open(sel.value);
    try {
      index = await (await realFetch('/data/index.json')).json();
      sel.innerHTML = '<option value="">choose a case…</option>' + index.map(c => `<option value="${esc(c.case_id)}">
        ${esc(c.case_id)} — ${c.side_match === null ? 'no lesion' : c.side_match ? '✓' : '✗'}</option>`).join('');
    } catch (e) { /* no index: selector stays empty */ }
    const c = caseOf(new URLSearchParams(location.search).get('nvd') || '');
    if (c) load(c);
    if (current) sel.value = current;
    showPos();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
})();
