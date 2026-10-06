// tableskin.js: the browser twin of tableskin.py.
//
// Gives any table the hooks of CSSV's table model plus tableskin's extras,
// then a skin from tableskin.css. Two ways in:
//
//   import { skinTable, skinAll, fromCSV } from './tableskin.js';
//   skinTable(document.querySelector('table'));          // an existing table, in place
//   skinAll('main table', { skin: 'clean' });             // every match on the page
//   el.append(fromCSV(csvText, { title: 'Ports' }));      // a new table from CSV text
//
// The analysis and the markup must match tableskin.py byte for byte;
// tests/test_parity.py checks it. Change both together.
// The idea and several skins come from CSSV by Rodrigo Paiva (MIT; see NOTICE).

export const SKINS = ['clean', 'ledger', 'paper', 'splitflap', 'board', 'chat'];
export const MODIFIERS = ['heat', 'bars'];
const MEASURES = ['number', 'money', 'percent'];
const NUMBERED = ['number', 'money', 'percent', 'ordinal'];

// ---------------------------------------------------------------- values

const NA = new Set(['-', '--', '\u2013', '\u2014', 'n/a', 'na', 'null', 'none', 'nan', '?']);
const CUR = '$€£¥₹';
const NUM = new RegExp(
  '^([' + CUR + ']?)([+\\-−]?)([' + CUR + ']?)' +
  '([0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(\\.[0-9]+)?' +
  '(%|[kKMGTP]i?[Bb]?(?:ps)?|B|ms|s|min|h|hrs?|d|x|kg|g|km|m|mi|ft|USD|EUR|GBP)?$');
const SPACES = /[   ]/g;

// [value, hasCurrency, hasPercent] for a numeric-looking field, else null.
export function parseNumber(text) {
  let s = text.trim();
  const paren = s.length >= 3 && s[0] === '(' && s[s.length - 1] === ')';
  if (paren) s = s.slice(1, -1);
  const m = NUM.exec(s.replace(SPACES, ''));
  if (!m) return null;
  const [, c1, sign, c2, whole, frac, unit] = m;
  if ((c1 && c2) || (paren && sign)) return null;
  if (whole.length > 1 && whole[0] === '0') return null;
  let v = Number(whole.replaceAll(',', '') + (frac || ''));
  if (sign === '-' || sign === '−' || paren) v = -v;
  return [v, Boolean(c1 || c2 || unit === 'USD' || unit === 'EUR' || unit === 'GBP'), unit === '%'];
}

const DATES = [
  ['date', /^[0-9]{4}-[0-9]{2}-[0-9]{2}$/],
  ['datetime', /^[0-9]{4}-[0-9]{2}-[0-9]{2}[T ][0-9]{1,2}:[0-9]{2}(:[0-9]{2}(\.[0-9]+)?)?(Z|[+-][0-9]{2}:?[0-9]{2})?$/],
  ['date', /^[0-9]{1,2}[/.][0-9]{1,2}[/.][0-9]{2,4}$/],
  ['datetime', /^[0-9]{1,2}[/.][0-9]{1,2}[/.][0-9]{2,4},? [0-9]{1,2}:[0-9]{2}(:[0-9]{2})?( ?[AaPp][Mm])?$/],
  ['date', /^[0-9]{1,2}[/ -][A-Za-z]{3}[/ -][0-9]{2,4}$/],
  ['datetime', /^[0-9]{1,2}[/ -][A-Za-z]{3}[/ -][0-9]{2,4} [0-9]{1,2}:[0-9]{2}(:[0-9]{2})?( ?[AaPp][Mm])?$/],
  ['date', /^[A-Za-z]{3,9}\.? [0-9]{1,2},? [0-9]{4}$/],
  ['time', /^[0-9]{1,2}:[0-9]{2}(:[0-9]{2})?( ?[AaPp][Mm])?$/],
];
const URL_RE = /^https?:\/\/\S+$/;
const EMAIL = /^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$/;
const CODE = /^(?=.*[0-9])[A-Za-z0-9][A-Za-z0-9_\-:./#]{2,39}$|^[A-Z]{1,4} [0-9]{1,6}$/;

export function dateKind(text) {
  for (const [kind, rx] of DATES) if (rx.test(text)) return kind;
  return null;
}

const words = (...names) => new RegExp('(^|[^a-z])(' + names.join('|') + ')([^a-z]|$)');
const ID_H = words('id', 'key', 'sku', 'code', 'ref', 'hash', 'commit', 'sha', 'serial', 'wwn', 'wwpn',
  'uuid', 'guid', 'ticket', 'account', 'acct', 'invoice', 'po', 'asset', 'mac', 'ip', 'vin', 'flight');
const YEAR_H = /^(year|yr|fy|fiscal year)$/;
const ORD_H = /^(#|no\.?|num|number|index|idx|slot|port|port ?#|port index|rank|pos|position|row|line|seq|step|order)$/;
const MONEY_H = words('amount', 'price', 'cost', 'costs', 'subtotal', 'balance', 'revenue', 'sales', 'usd',
  'eur', 'gbp', 'fee', 'fees', 'paid', 'budget', 'salary', 'spend', 'spent', 'income', 'expense', 'expenses',
  'tax', 'vat', 'profit', 'payment', 'debit', 'credit', 'charge', 'mrr', 'arr');
const PCT_H = /%|(^|[^a-z])(pct|percent|percentage|util|utilization|utilisation|ratio|share)([^a-z]|$)/;
const STATUS_H = words('status', 'state', 'result', 'health', 'phase', 'stage', 'severity', 'priority',
  'outcome', 'condition', 'verdict');
const PERSON_H = words('owner', 'assignee', 'assigned to', 'sender', 'from', 'author', 'user', 'username',
  'who', 'reporter', 'contact', 'employee', 'customer', 'client', 'member', 'player', 'driver', 'agent',
  'manager', 'full name', 'first name', 'last name', 'person', 'staff', 'speaker');
const LABEL_H = words('category', 'categories', 'type', 'kind', 'group', 'tag', 'tags', 'label', 'labels',
  'class', 'department', 'dept', 'team', 'region', 'segment', 'tier', 'channel', 'source', 'vendor', 'model',
  'platform', 'site');
const TOTAL = /^(sub ?-?total|total|totals|grand total|sum|balance due|amount due|total due|net total|tax|vat|sales tax|discount|shipping)\b/i;

const TONE_WORDS = {
  good: 'done, ok, okay, pass, passed, passing, success, successful, succeeded, complete, completed, ' +
    'healthy, online, up, active, on time, resolved, closed, green, yes, y, true, enabled, approved, ' +
    'paid, delivered, shipped, in stock, valid, connected, available, ready, merged, live, running, ' +
    'normal, good, accepted, won, departed, landed, arrived',
  warn: 'pending, in progress, in review, review, waiting, warning, warn, degraded, partial, delayed, ' +
    'at risk, yellow, amber, queued, draft, late, maintenance, paused, on hold, unknown, marginal, ' +
    'low stock, expiring, needs review, stale, busy, retrying, boarding, final call',
  bad: 'failed, fail, failing, failure, error, errored, errors, critical, down, offline, cancelled, ' +
    'canceled, blocked, red, no, n, false, disabled, rejected, overdue, unpaid, expired, missing, ' +
    'invalid, disconnected, outage, lost, broken, faulty, faulted, out of stock, declined, denied, ' +
    'dead, gate closed',
  neutral: 'to do, todo, open, new, backlog, planned, scheduled, not started, idle, info',
};
export const TONES = new Map();
for (const [tone, list] of Object.entries(TONE_WORDS)) for (const w of list.split(',')) TONES.set(w.trim(), tone);
const TONE_RANK = { neutral: 0, warn: 1, bad: 2, good: 3 };

export const toneOf = (text) => TONES.get(text.trim().toLowerCase().replace(/[\s_\-]+/g, ' ')) ?? null;
export function isBlank(text) {
  const s = text.trim();
  return s === '' || NA.has(s.toLowerCase());
}
const slug = (text) => text.trim().toLowerCase().replace(/[^\p{L}\p{N}]+/gu, '-').replace(/^-+|-+$/g, '');
const hue = (k) => Math.floor(210 + k * 137.508 + 0.5) % 360;
const fmt3 = (x) => (Math.floor(x * 1000 + 0.5) / 1000).toFixed(3).replace(/0+$/, '').replace(/\.$/, '') || '0';
const cplen = (text) => [...text].length;

// ---------------------------------------------------------------- input

// [header, rows]. Delimiter is , ; or tab, detected from the header record.
export function parseCSV(text) {
  if (text.startsWith('﻿')) text = text.slice(1);
  const counts = { ',': 0, ';': 0, '\t': 0 };
  let inside = false;
  for (const ch of text) {
    if (ch === '"') inside = !inside;
    else if (!inside && (ch === '\r' || ch === '\n')) break;
    else if (!inside && ch in counts) counts[ch]++;
  }
  let delim = ',';
  for (const d of [';', '\t']) if (counts[d] > counts[delim]) delim = d;

  const records = [];
  let record = [], field = '', quoted = false, i = 0, started = false;
  const endField = () => { record.push(field); field = ''; };
  const endRecord = () => {
    endField();
    if (!(record.length === 1 && record[0] === '' && !started)) records.push(record);
    record = []; started = false;
  };
  while (i < text.length) {
    const ch = text[i];
    if (quoted) {
      if (ch === '"') {
        if (text[i + 1] === '"') { field += '"'; i += 2; continue; }
        quoted = false;
      } else field += ch;
      i++;
      continue;
    }
    if (ch === '"' && field === '') { quoted = true; started = true; }
    else if (ch === delim) { endField(); started = true; }
    else if (ch === '\r' || ch === '\n') {
      endRecord();
      if (ch === '\r' && text[i + 1] === '\n') i++;
    } else { field += ch; started = true; }
    i++;
  }
  if (field !== '' || record.length || started) endRecord();
  if (!records.length) return [[], []];
  return [records[0], records.slice(1)];
}

// ---------------------------------------------------------------- analysis

function role(name, values) {
  const h = name.trim().toLowerCase();
  const vals = values.filter((v) => !isBlank(v));
  const info = { role: 'empty', numeric: false, signed: false, lo: null, hi: null, maxabs: 0,
    distinct: new Set(vals).size, avglen: 0 };
  if (!vals.length) return info;
  info.avglen = vals.reduce((a, v) => a + cplen(v), 0) / vals.length;
  const nums = vals.map(parseNumber);
  if (nums.every(Boolean)) {
    const xs = nums.map((n) => n[0]);
    Object.assign(info, { numeric: true, lo: Math.min(...xs), hi: Math.max(...xs),
      maxabs: Math.max(...xs.map(Math.abs)), signed: xs.some((x) => x < 0) });
    const integers = xs.every(Number.isInteger);
    if (ID_H.test(h)) info.role = 'id';
    else if (YEAR_H.test(h) && integers) info.role = 'date';
    else if (ORD_H.test(h) && integers) info.role = 'ordinal';
    else if (nums.some((n) => n[1]) || MONEY_H.test(h)) info.role = 'money';
    else if (nums.some((n) => n[2]) || PCT_H.test(h)) info.role = 'percent';
    else info.role = 'number';
    return info;
  }
  const n = vals.length, { distinct, avglen } = info;
  const count = (f) => vals.reduce((a, v) => a + (f(v) ? 1 : 0), 0);
  const kinds = vals.map(dateKind);
  if (kinds.filter(Boolean).length >= 0.8 * n) {
    info.role = kinds.includes('datetime') ? 'datetime'
      : kinds.filter(Boolean).every((k) => k === 'time') ? 'time' : 'date';
  } else if (count((v) => URL_RE.test(v)) >= 0.8 * n) info.role = 'url';
  else if (count((v) => EMAIL.test(v)) >= 0.8 * n) info.role = 'email';
  else if (distinct <= 12 && (count(toneOf) >= 0.6 * n || (STATUS_H.test(h) && avglen <= 24))) info.role = 'status';
  else if ((ID_H.test(h) || count((v) => CODE.test(v)) >= 0.8 * n) && distinct >= 0.8 * n && avglen <= 40) info.role = 'id';
  else if (PERSON_H.test(h) && avglen < 40) info.role = 'person';
  else if (avglen >= 32 || vals.some((v) => v.includes('\n'))) info.role = 'prose';
  else if (n >= 3 && distinct <= 12 && avglen <= 24 && (LABEL_H.test(h) || distinct <= Math.ceil(0.6 * n))) info.role = 'label';
  else info.role = 'text';
  return info;
}

// The table model: columns with roles, rows of cells, primary and group columns.
export function analyze(header, rows) {
  const width = Math.max(header.length, ...rows.map((r) => r.length));
  header = [...header, ...Array(width - header.length).fill('')];
  rows = rows.filter((r) => r.some((f) => f !== '')).map((r) => [...r, ...Array(width - r.length).fill('')]);
  const cols = header.map((name, j) => ({ name, index: j, ...role(name, rows.map((r) => r[j])) }));
  const first = (...roles) => { const c = cols.find((c) => roles.includes(c.role)); return c ? c.index : null; };
  let primary = first('prose');
  if (primary === null) primary = first('text');
  if (primary === null) primary = first('person', 'label');
  let group = first('status');
  if (group === null) group = first('label');

  let groups = [];
  if (group !== null) {
    const seen = [];
    for (const r of rows) if (!isBlank(r[group]) && !seen.includes(r[group])) seen.push(r[group]);
    groups = cols[group].role === 'status'
      ? [...seen].sort((a, b) => (TONE_RANK[toneOf(a) ?? 'neutral'] - TONE_RANK[toneOf(b) ?? 'neutral']) || (seen.indexOf(a) - seen.indexOf(b)))
      : seen;
  }
  return { columns: cols, rows, primary, group, groups };
}

const isTotal = (row, cols) => {
  for (let j = 0; j < Math.min(2, cols.length); j++) if (!cols[j].numeric && TOTAL.test(row[j].trim())) return true;
  return false;
};

// [skin tokens, reason]: the first rule that fits wins.
export function pick(model) {
  const cols = model.columns, rows = model.rows;
  const roles = cols.map((c) => c.role), has = (r) => roles.includes(r);
  const measures = cols.filter((c) => MEASURES.includes(c.role));
  let longest = 0;
  for (const r of rows) for (const v of r) longest = Math.max(longest, cplen(v));
  const totals = rows.some((r) => isTotal(r, cols));
  const { primary, group } = model;

  if (has('person') && has('prose') && (has('time') || has('datetime') || has('date')) && rows.length >= 4)
    return [['chat'], 'a person column, a long-text column and timestamps read as a conversation'];
  if (group !== null && cols[group].role === 'status' && model.groups.length >= 2 && model.groups.length <= 6 &&
      primary !== null && cols[primary].role === 'prose' && rows.length >= 4 && rows.length <= 80)
    return [['board'], `a status column with ${model.groups.length} values and long titles make a board`];
  if (rows.length <= 16 && cols.length >= 3 && cols.length <= 6 && longest <= 18 &&
      (has('time') || (has('status') && has('id'))))
    return [['splitflap'], 'a short list of short values with times or statuses fits a departures board'];
  if (totals && has('money')) return [['paper'], 'money with total rows reads as an invoice or statement'];
  if (has('money') || (has('date') && measures.some((c) => c.signed)))
    return [['ledger'], 'money or signed amounts over dates read as a ledger'];
  if (measures.length >= 3 && measures.length * 2 >= cols.length)
    return [['clean', 'heat'], `${measures.length} of ${cols.length} columns are measures, so shade them as a heat map`];
  if (measures.length && rows.length >= 3) return [['clean', 'bars'], 'a few measure columns get in-cell bars'];
  return [['clean'], 'nothing more specific fits'];
}

// ---------------------------------------------------------------- markup plan
// plan() decides every attribute once; toHTML() writes it as a string (the
// same string tableskin.py writes) and applyPlan() sets it on live elements.

function keyIndex(model, skin, key) {
  if (key != null) {
    const c = model.columns.find((c) => c.name === key);
    if (!c) throw new Error(`no column named ${JSON.stringify(key)}`);
    return c.index;
  }
  const want = skin.includes('chat') ? ['person'] : ['id'];
  const c = model.columns.find((c) => want.includes(c.role));
  return c ? c.index : null;
}

export function plan(model, { skin = 'auto', title = null, key = null, me = null } = {}) {
  skin = skin === 'auto' ? pick(model)[0] : typeof skin === 'string' ? skin.split(/\s+/).filter(Boolean) : [...skin];
  const cols = model.columns, rows = model.rows, groups = model.groups;
  const kj = keyIndex(model, skin, key), gj = model.group, pj = model.primary;
  const catSeen = new Map(cols.filter((c) => ['status', 'label', 'person'].includes(c.role)).map((c) => [c.index, []]));
  const keySeen = [];

  let tstyle = `--rows:${rows.length};--cols:${cols.length}`;
  if (groups.length) tstyle += `;--groups:${groups.length}`;
  const flags = (c, a) => {
    if (c.index === pj) a.push(['data-primary', true]);
    if (c.index === gj) a.push(['data-grouping', true]);
  };

  const head = cols.map((c) => {
    const a = [['data-col', c.name], ['data-role', c.role]];
    if (c.numeric && NUMBERED.includes(c.role)) a.push(['class', 'number']);
    if (c.signed && MEASURES.includes(c.role)) a.push(['data-signed', true]);
    flags(c, a);
    a.push(['style', `--j:${c.index}`]);
    return { attrs: a, text: c.name };
  });

  let prevKey = null;
  const started = new Set();
  const body = rows.map((r, i) => {
    const a = [['data-row', String(i + 2)]];
    let style = `--i:${i}`;
    const k = kj !== null && !isBlank(r[kj]) ? r[kj] : null;
    if (k !== null) {
      a.push(['data-key', k]);
      if (me != null && k === me) a.push(['data-me', true]);
      if (k !== prevKey) a.push(['data-run', 'start']);
      if (!keySeen.includes(k)) keySeen.push(k);
    }
    prevKey = k;
    if (gj !== null && groups.includes(r[gj])) {
      const g = r[gj];
      a.push(['data-group', g]);
      if (!started.has(g)) { a.push(['data-group-start', true]); started.add(g); }
      style += `;--group:${groups.indexOf(g) + 1}`;
    }
    if (isTotal(r, cols)) a.push(['data-total', true]);
    if (k !== null) style += `;--hue:${hue(keySeen.indexOf(k))}`;
    a.push(['style', style]);

    const cells = cols.map((c) => {
      const v = r[c.index];
      const ca = [['data-col', c.name], ['data-role', c.role]];
      let cs = `--j:${c.index}`;
      const n = c.numeric ? parseNumber(v) : null;
      if (n && NUMBERED.includes(c.role)) ca.push(['class', 'number ' + (n[0] === 0 ? 'zero' : n[0] < 0 ? 'negative' : 'positive')]);
      if (c.signed && MEASURES.includes(c.role)) ca.push(['data-signed', true]);
      if (v !== '' && isBlank(v)) ca.push(['data-na', true]);
      flags(c, ca);
      if (!isBlank(v)) {
        if (c.role === 'status' && toneOf(v)) ca.push(['data-tone', toneOf(v)]);
        if (catSeen.has(c.index)) {
          ca.push(['data-tag', slug(v)]);
          const seen = catSeen.get(c.index);
          if (!seen.includes(v)) seen.push(v);
          cs += `;--hue:${hue(seen.indexOf(v))}`;
        }
      }
      if (n && MEASURES.includes(c.role)) {
        const span = c.hi - c.lo;
        const t = span ? (n[0] - c.lo) / span : 1;
        const mag = c.maxabs ? Math.abs(n[0]) / c.maxabs : 0;
        cs += `;--t:${fmt3(t)};--mag:${fmt3(mag)}`;
      }
      ca.push(['style', cs]);
      return { attrs: ca, text: v };
    });
    return { attrs: a, cells };
  });

  return {
    skin: skin.join(' '),
    table: [['data-rows', String(rows.length)], ['data-cols', String(cols.length)], ['style', tstyle]],
    title,
    cols: cols.map((c) => [['data-col', c.name], ['data-role', c.role]]),
    head,
    body,
  };
}

const escText = (s) => s.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;');
const escAttr = (s) => escText(s).replaceAll('"', '&quot;');
// Flag attributes carry true and are written bare, as tableskin.py writes them.
const attrs = (list) => list.map(([k, v]) => (v === true ? ` ${k}` : ` ${k}="${escAttr(v)}"`)).join('');

export function toHTML(p) {
  let out = `<div class="tableskin" data-skin="${escAttr(p.skin)}"><table${attrs(p.table)}>`;
  if (p.title) out += `<caption>${escText(p.title)}</caption>`;
  out += '<colgroup>' + p.cols.map((a) => `<col${attrs(a)}>`).join('') + '</colgroup>';
  out += '<thead><tr data-row="1">' + p.head.map((h) => `<th${attrs(h.attrs)}>${escText(h.text)}</th>`).join('') + '</tr></thead>';
  out += '<tbody>' + p.body.map((r) => `<tr${attrs(r.attrs)}>` + r.cells.map((c) => `<td${attrs(c.attrs)}>${escText(c.text)}</td>`).join('') + '</tr>').join('');
  return out + '</tbody></table></div>';
}

export function render(model, opts = {}) {
  return toHTML(plan(model, opts));
}

// ---------------------------------------------------------------- DOM

let stylesAdded = false;
// Adds tableskin.css (next to this module) to the page once. Pass false to skip.
export function ensureStyles(href = new URL('./tableskin.css', import.meta.url).href) {
  if (stylesAdded || href === false || typeof document === 'undefined') return;
  stylesAdded = true;
  const link = document.createElement('link');
  link.rel = 'stylesheet';
  link.href = href;
  document.head.append(link);
}

// A new wrapper element holding a table built from CSV text.
export function fromCSV(text, opts = {}) {
  ensureStyles(opts.styles);
  const [header, rows] = parseCSV(text);
  const t = document.createElement('template');
  t.innerHTML = render(analyze(header, rows), opts);
  return t.content.firstElementChild;
}

// textContent, not innerText: innerText would pick up the page's text-transform.
const cellText = (el) => el.textContent.replace(/\s+/g, ' ').trim();

// Skins an existing <table> in place: keeps its cells and their content,
// moves a header row into <thead> when needed, adds the hooks, and wraps it.
export function skinTable(table, opts = {}) {
  ensureStyles(opts.styles);
  let headRow = table.tHead?.rows[0];
  if (!headRow) {
    headRow = table.rows[0];
    if (!headRow) return null;
    table.createTHead().append(headRow);
  }
  // Skins style header cells as th; a promoted first row usually holds td.
  for (const cell of [...headRow.cells]) {
    if (cell.tagName === 'TH') continue;
    const th = document.createElement('th');
    for (const { name, value } of cell.attributes) th.setAttribute(name, value);
    th.append(...cell.childNodes);
    cell.replaceWith(th);
  }
  const bodyRows = [...table.tBodies].flatMap((b) => [...b.rows]);
  const header = [...headRow.cells].map(cellText);
  const rows = bodyRows.map((tr) => [...tr.cells].map(cellText));
  const model = analyze(header, rows);
  const p = plan(model, opts);

  const set = (el, list) => { for (const [k, v] of list) el.setAttribute(k, v === true ? '' : v); };
  set(table, p.table);
  if (p.title) (table.caption ?? table.createCaption()).textContent = p.title;
  table.querySelector(':scope > colgroup')?.remove();
  const cg = document.createElement('colgroup');
  for (const a of p.cols) { const col = document.createElement('col'); set(col, a); cg.append(col); }
  table.insertBefore(cg, table.tHead);
  headRow.setAttribute('data-row', '1');
  [...headRow.cells].forEach((cell, j) => p.head[j] && set(cell, p.head[j].attrs));
  // analyze() drops rows that are entirely empty; match the rest in order.
  const kept = bodyRows.filter((tr) => [...tr.cells].some((c) => cellText(c) !== ''));
  kept.forEach((tr, i) => {
    set(tr, p.body[i].attrs);
    [...tr.cells].forEach((cell, j) => p.body[i].cells[j] && set(cell, p.body[i].cells[j].attrs));
  });

  let wrap = table.parentElement;
  if (!wrap?.classList.contains('tableskin')) {
    wrap = document.createElement('div');
    wrap.className = 'tableskin';
    table.replaceWith(wrap);
    wrap.append(table);
  }
  wrap.dataset.skin = p.skin;
  return wrap;
}

// Skins every table matching selector. Tables with merged cells are skipped.
export function skinAll(selector = 'table', opts = {}) {
  return [...document.querySelectorAll(selector)]
    .filter((t) => !t.querySelector('[rowspan]:not([rowspan="1"]), [colspan]:not([colspan="1"])'))
    .map((t) => skinTable(t, opts))
    .filter(Boolean);
}
