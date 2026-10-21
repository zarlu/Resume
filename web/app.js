'use strict';

// Working state lives here; the server rebuilds it in memory on every change and only writes
// resume.json when you press Save.

const $ = (sel) => document.querySelector(sel);
const clone = (x) => JSON.parse(JSON.stringify(x));

/** Tiny DOM builder. Text goes in via textContent, so resume text is never parsed as HTML. */
function h(tag, props = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === 'class') el.className = v;
    else if (k === 'text') el.textContent = v;
    else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else if (v === true) el.setAttribute(k, '');
    else if (v !== false && v != null) el.setAttribute(k, v);
  }
  for (const kid of kids.flat()) if (kid != null) el.append(kid);
  return el;
}

let META = null; // fonts, limits, defaults, outline (from /api/state)
let S = null; // working state: { style, sections }
let SAVED = ''; // snapshot of the last saved state, to know when there is something to save

const payload = () => ({ style: S.style, sections: S.sections });
const snapshot = () => JSON.stringify(payload());

// ------------------------------------------------------------------ api

async function api(path, body, signal) {
  const init = body === undefined
    ? { signal }
    : { method: 'POST', signal, headers: { 'Content-Type': 'application/json', 'X-Resume-UI': '1' }, body: JSON.stringify(body) };
  const res = await fetch(path, init);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = new Error(typeof data.detail === 'string' ? data.detail : res.statusText);
    err.status = res.status;
    throw err;
  }
  return data;
}

// ------------------------------------------------------------------ small widgets

const fmt = (v, unit) => `${+(+v).toFixed(2)}${unit}`;

function slider({ id, label, value, min, max, step, unit, dflt, onInput }) {
  const out = h('output', { for: id });
  const input = h('input', { type: 'range', id, min, max, step, value });
  const reset = h('button', { type: 'button', class: 'reset', title: `Reset to ${fmt(dflt, unit)}`, 'aria-label': `Reset ${label} to default` }, '↺');
  const sync = () => {
    out.textContent = fmt(input.value, unit);
    reset.hidden = Math.abs(+input.value - dflt) < 1e-9;
  };
  input.addEventListener('input', () => { sync(); onInput(+input.value); });
  reset.addEventListener('click', () => { input.value = dflt; sync(); onInput(dflt); });
  sync();
  return {
    el: h('div', { class: 'row' }, h('label', { for: id, text: label }), input, out, reset),
    set(v) { input.value = v; sync(); },
  };
}

/** One slider that moves several values together, with a checkbox to set each one separately. */
function linkedGroup({ id, title, items, bounds, step, unit, dflt, hint }) {
  const same = () => items.every((i) => Math.abs(i.get() - items[0].get()) < 1e-9);
  const perItem = h('input', { type: 'checkbox', id: `${id}-each` });
  perItem.checked = !same();

  const all = slider({
    id: `${id}-all`, label: 'All', value: items[0].get(), ...bounds, step, unit, dflt,
    onInput: (v) => { items.forEach((i) => i.set(v)); each.forEach((s) => s.set(v)); changed(); },
  });
  const each = items.map((i) => slider({
    id: `${id}-${i.key}`, label: i.label, value: i.get(), ...bounds, step, unit, dflt,
    onInput: (v) => { i.set(v); changed(); },
  }));
  const eachBox = h('div', { class: 'each' }, each.map((s) => s.el));

  const show = () => { all.el.hidden = perItem.checked; eachBox.hidden = !perItem.checked; };
  perItem.addEventListener('change', () => {
    if (!perItem.checked) { // back to one value: everything takes the first item's
      const v = items[0].get();
      items.forEach((i) => i.set(v));
      all.set(v);
      each.forEach((s) => s.set(v));
      changed();
    }
    show();
  });
  show();

  return h('section', { class: 'group' },
    h('h2', { text: title }), all.el, eachBox,
    h('label', { class: 'opt' }, perItem, ` Set each separately`),
    hint ? h('p', { class: 'hint', text: hint }) : null);
}

function checkRow({ checked, disabled, onChange, name, value, title }) {
  const box = h('input', { type: 'checkbox' });
  box.checked = checked;
  box.disabled = !!disabled;
  box.addEventListener('change', () => onChange(box.checked));
  return h('div', { class: 'fld', title: title || value || '' },
    h('label', {}, box, h('span', { class: 'n', text: name }), value ? h('span', { class: 'v', text: value }) : null));
}

const clip = (s, n = 46) => (s.length > n ? `${s.slice(0, n - 1)}…` : s);
const toggle = (arr, item, on) => { // `on` = keep it in the array
  const i = arr.indexOf(item);
  if (on && i < 0) arr.push(item);
  if (!on && i >= 0) arr.splice(i, 1);
};

// ------------------------------------------------------------------ panel

function buildPanel() {
  const panel = $('#panel');
  panel.replaceChildren();
  const st = S.style;
  const L = META.limits;

  // template
  const templateSelect = h('select', { id: 'template', 'aria-label': 'Template' },
    META.templates.map((t) => h('option', { value: t.key, text: t.label })));
  templateSelect.value = st.template;
  templateSelect.addEventListener('change', () => { st.template = templateSelect.value; changed(); });
  panel.append(h('section', { class: 'group' }, h('h2', { text: 'Template' }), templateSelect));

  // font
  const select = h('select', { id: 'font', 'aria-label': 'Font' });
  const groups = [['Bundled (builds anywhere)', true], ['Installed on this Mac', false]];
  for (const [label, portable] of groups) {
    select.append(h('optgroup', { label }, META.fonts.filter((f) => f.portable === portable).map(
      (f) => h('option', { value: f.key, text: f.label }))));
  }
  select.value = st.font;
  select.addEventListener('change', () => { st.font = select.value; changed(); });
  panel.append(h('section', { class: 'group' },
    h('h2', { text: 'Font' }), select,
    h('p', { class: 'hint', text: 'Macintosh fonts have no small caps, so section headings render in normal case.' })));

  // size
  const size = slider({
    id: 'size', label: 'Size', value: st.font_size, ...L.font_size, step: 0.05, unit: 'pt', dflt: META.defaults.font_size,
    onInput: (v) => { st.font_size = v; changed(); },
  });
  panel.append(h('section', { class: 'group' }, h('h2', { text: 'Text size' }), size.el));

  // margins and spacing
  const sides = ['top', 'bottom', 'left', 'right'].map((k) => ({
    key: k, label: k[0].toUpperCase() + k.slice(1), get: () => st.margins[k], set: (v) => { st.margins[k] = v; },
  }));
  panel.append(linkedGroup({ id: 'm', title: 'Margins', items: sides, bounds: L.margin, step: 0.05, unit: 'in', dflt: META.defaults.margins.top }));

  const gaps = [['section_gap', 'Sections'], ['entry_gap', 'Entries'], ['bullet_gap', 'Bullets']].map(([k, label]) => ({
    key: k, label, get: () => st[k], set: (v) => { st[k] = v; },
  }));
  panel.append(linkedGroup({
    id: 'g', title: 'Spacing', items: gaps, bounds: L.gap, step: 0.25, unit: 'pt', dflt: 0,
    hint: 'Extra space added to the template’s own. Negative tightens.',
  }));

  // fit
  const fit = h('input', { type: 'checkbox', id: 'fit' });
  fit.checked = st.fit_to_page;
  fit.addEventListener('change', () => { st.fit_to_page = fit.checked; changed(); });
  panel.append(h('section', { class: 'group' },
    h('h2', { text: 'One page' }),
    h('label', { class: 'opt', style: 'color: var(--ink); font-size: 14px' }, fit, ' Fit to one page'),
    h('p', { class: 'hint', text: `When the page overflows, shrink text, margins and spacing just enough (no further than ${META.fit_floor.font_size}pt / ${META.fit_floor.margin}in). Your sliders stay where you put them.` })));

  // visibility
  panel.append(buildTree());

  // checks
  panel.append(h('section', { class: 'group checks', id: 'checks' }));
}

function buildTree() {
  const root = h('section', { class: 'group' }, h('h2', { text: 'Show in PDF' }));
  for (const sec of META.sections) {
    const sv = S.sections[sec.key];
    if (!sec.entries.length) continue;
    const entriesBox = h('div', { class: 'entries' });
    entriesBox.classList.toggle('dim', sv.hidden);
    const secBox = h('input', { type: 'checkbox', 'aria-label': `Show ${sec.heading}` });
    secBox.checked = !sv.hidden;
    secBox.addEventListener('change', () => { sv.hidden = !secBox.checked; entriesBox.classList.toggle('dim', sv.hidden); changed(); });

    sec.entries.forEach((entry, ei) => {
      const ev = sv.entries[ei];
      const body = h('div');
      const entryBox = h('input', { type: 'checkbox', 'aria-label': `Show ${entry.name}` });
      entryBox.checked = !ev.hidden;
      entryBox.addEventListener('change', () => { ev.hidden = !entryBox.checked; body.classList.toggle('dim', ev.hidden); changed(); });
      body.classList.toggle('dim', ev.hidden);

      const bulletRows = [];
      for (const f of entry.fields) {
        const isBullets = f.name === 'bullets';
        body.append(checkRow({
          checked: !ev.hide.includes(f.name),
          name: isBullets ? 'all bullets' : f.name,
          value: clip(f.value),
          title: f.value,
          onChange: (on) => {
            toggle(ev.hide, f.name, !on);
            if (isBullets) bulletRows.forEach((r) => { r.querySelector('input').disabled = !on; });
            changed();
          },
        }));
      }
      entry.bullets.forEach((text, bi) => {
        const n = bi + 1;
        const row = checkRow({
          checked: !ev.hide_bullets.includes(n),
          disabled: ev.hide.includes('bullets'),
          name: `bullet ${n}`,
          value: clip(text.replace(/\*+/g, '')),
          title: text,
          onChange: (on) => { toggle(ev.hide_bullets, n, !on); changed(); },
        });
        bulletRows.push(row);
        body.append(row);
      });

      entriesBox.append(h('details', {}, h('summary', {}, entryBox, h('span', { text: clip(entry.name, 34), title: entry.name })), body));
    });

    root.append(h('details', { class: 'sec', open: true },
      h('summary', {}, secBox, h('span', { text: sec.heading }), h('span', { class: 'count', text: String(sec.entries.length) })),
      entriesBox));
  }
  return root;
}

// ------------------------------------------------------------------ status + checks

const chip = (text, kind, title) => h('span', { class: `chip ${kind}`, text, title: title || '' });

function renderStatus(r, ms) {
  const bar = $('#status');
  bar.replaceChildren();
  if (r.errors.length) { bar.append(chip('Build error', 'bad')); return; }
  const n = r.pages.count;
  bar.append(n === 1 ? chip('1 page', 'ok') : chip(`${n} pages: overflow`, 'bad'));
  const total = r.ats.checks.length;
  const passed = r.ats.checks.filter((c) => c.status === 'pass').length;
  bar.append(chip(`ATS ${passed}/${total}`, r.ats.ok ? 'ok' : 'bad', 'Name, email, headings and entry names found in PDF text, in reading order'));
  if (r.placeholders.length) bar.append(chip(`${r.placeholders.length} placeholders`, 'info', 'Text still in [brackets]'));
  if (r.fit) bar.append(chip(`Fitted ${Math.round(r.fit.squeeze * 100)}%`, 'info', r.fit.description));
  if (ms != null) bar.append(chip(`${ms} ms`, ''));
}

function renderChecks(r) {
  const box = $('#checks');
  if (!box) return;
  box.replaceChildren(h('h2', { text: 'Checks' }));
  if (r.errors.length) { box.append(h('ul', {}, r.errors.map((e) => h('li', { class: 'bad', text: e })))); return; }
  const lines = r.pages.lines.map((l) => l.trim()).filter(Boolean);
  if (r.fit) lines.unshift(r.fit.description);
  const items = [...lines.map((l) => [l.replace(/^(PASS|FAIL)\s+/, ''), /^FAIL/.test(l)])];
  box.append(h('ul', {}, items.map(([t, bad]) => h('li', { class: bad ? 'bad' : '', text: t }))));
  const failing = r.ats.checks.filter((c) => c.status !== 'pass');
  if (failing.length) {
    box.append(h('h3', { text: 'ATS problems' }), h('ul', {}, failing.map((c) => h('li', { class: 'bad', text: `${c.label}: ${c.text} (${c.why})` }))));
  }
  if (r.placeholders.length) {
    box.append(h('h3', { text: `Placeholders (${r.placeholders.length})` }),
      h('ul', {}, r.placeholders.map((p) => h('li', {}, h('code', { text: p.text }), ` ${p.where}`))));
  }
}

// ------------------------------------------------------------------ live preview

let reqId = 0;
const SESSION = (crypto.randomUUID && crypto.randomUUID()) || String(Math.random()).slice(2); // ids restart at 1 on reload
let timer = null;
let fitTimer = null;
let inflight = null;
let front = 0; // which iframe is showing

function changed() {
  updateDirty();
  clearTimeout(timer);
  clearTimeout(fitTimer);
  timer = setTimeout(() => refresh(false), 200);
}

function showBanner(msg, { info = false, reload = false } = {}) {
  const b = $('#banner');
  b.replaceChildren(h('div', { text: msg }));
  if (reload) b.append(h('button', { type: 'button', onclick: () => location.reload(), text: 'Reload page' }));
  b.classList.toggle('info', info);
  b.hidden = false;
}
const hideBanner = () => { $('#banner').hidden = true; };

function showPdf(url) {
  const next = $(`#f${1 - front}`);
  const cur = $(`#f${front}`);
  next.onload = () => { next.onload = null; next.classList.add('on'); cur.classList.remove('on'); front = 1 - front; };
  next.src = `${url}#toolbar=0&navpanes=0&view=FitH`;
}

async function refresh(fit) {
  const id = ++reqId;
  inflight?.abort();
  inflight = new AbortController();
  $('#busy').textContent = fit ? 'Fitting to one page…' : 'Building…';
  $('#busy').hidden = false;
  try {
    const data = await api('/api/preview', { ...payload(), session: SESSION, id, fit }, inflight.signal);
    if (data.cancelled || data.id !== reqId) return; // a newer request is on its way
    $('#busy').hidden = true;
    const r = data.result;
    renderStatus(r, data.ms);
    renderChecks(r);
    if (r.errors.length) { showBanner(r.errors.join('\n')); return; }
    hideBanner();
    if (data.pdf) showPdf(data.pdf);
    // Overflowing: wait for the sliders to settle, then run the (slower) fit search once.
    if (!fit && r.pages.count > 1 && S.style.fit_to_page) fitTimer = setTimeout(() => refresh(true), 350);
  } catch (e) {
    if (e.name === 'AbortError') return;
    $('#busy').hidden = true;
    showBanner(e.message, { reload: e.status === 409 });
  }
}

// ------------------------------------------------------------------ save / export / revert

const dirty = () => snapshot() !== SAVED;
function updateDirty() {
  $('#save').disabled = !dirty();
  $('#revert').disabled = !dirty();
}

let toastTimer = null;
function toast(msg) {
  const t = $('#toast');
  t.textContent = msg;
  t.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove('show'), 3200);
}

async function save() {
  try {
    const r = await api('/api/save', payload());
    SAVED = snapshot();
    updateDirty();
    toast(`Saved style and visibility to ${r.path}`);
  } catch (e) {
    showBanner(`Could not save: ${e.message}`, { reload: e.status === 409 });
  }
}

async function exportPdf(download = false) {
  const btns = [$('#export'), $('#download')];
  btns.forEach((b) => { b.disabled = true; });
  try {
    const d = await api('/api/export', { ...payload(), final: $('#final').checked });
    if (d.exported) {
      hideBanner();
      if (download) {
        const name = d.path.split('/').pop();
        const res = await fetch('/api/download', { cache: 'no-store' });
        if (!res.ok) throw new Error(`download failed (${res.status}). Restart the server (Ctrl+C, then uv run build.py --serve) if it was started before this button existed`);
        const url = URL.createObjectURL(await res.blob());
        const a = h('a', { href: url, download: name });
        document.body.append(a);
        a.click();
        a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 10000);
        toast(`Downloaded ${name}`);
      } else {
        toast(`Exported ${d.path}`);
      }
      return;
    }
    const r = d.result;
    const why = [...r.errors];
    if (!r.pages.ok) why.push(...r.pages.lines.map((l) => l.trim()).filter(Boolean));
    why.push(...r.ats.checks.filter((c) => c.status !== 'pass').map((c) => `ATS: ${c.label}: ${c.text} (${c.why})`));
    if ($('#final').checked && r.placeholders.length) why.push(`${r.placeholders.length} [placeholder(s)] remain (Final is on)`);
    showBanner(`Not exported: dist/ left unchanged.\n${why.join('\n')}`);
  } catch (e) {
    showBanner(`Export failed: ${e.message}`, { reload: e.status === 409 });
  } finally {
    btns.forEach((b) => { b.disabled = false; });
  }
}

function revert() {
  S = JSON.parse(SAVED);
  buildPanel();
  updateDirty();
  refresh(false);
}

// ------------------------------------------------------------------ boot

function initState(meta) {
  META = meta;
  S = {
    style: clone(meta.style),
    sections: Object.fromEntries(meta.sections.map((s) => [s.key, {
      hidden: s.hidden,
      entries: s.entries.map((e) => ({ hidden: e.hidden, hide: [...e.hide], hide_bullets: [...e.hide_bullets] })),
    }])),
  };
  SAVED = snapshot();
}

async function boot() {
  $('#save').addEventListener('click', save);
  $('#export').addEventListener('click', () => exportPdf(false));
  $('#download').addEventListener('click', () => exportPdf(true));
  $('#revert').addEventListener('click', revert);
  try {
    initState(await api('/api/state'));
  } catch (e) {
    showBanner(`resume.json needs fixing before the UI can load it:\n${e.message}`, { reload: true });
    return;
  }
  document.title = `${META.name}: resume style`;
  $('#title').textContent = `${META.name}: style`;
  buildPanel();
  updateDirty();
  refresh(false);
}

boot();
