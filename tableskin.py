#!/usr/bin/env python3
"""tableskin: dress any table-like data in a stylesheet borrowed from CSSV.

The idea, and several of the stylesheets in skins/, come from CSSV by Rodrigo
Paiva (https://github.com/rhpaiva/cssv, MIT; see NOTICE). CSSV's trick is a
fixed HTML table model with hooks a stylesheet can rely on: data-col on every
cell, data-row on every row, and number/negative/zero/positive classes. This
module builds that model from a CSV file, a list of records or a DataFrame,
adds a few hooks CSSV leaves out on purpose (column roles, status tones,
per-column scale values, groups), and picks a skin that suits the data.

Stdlib only. tableskin.js is the browser twin and must produce identical
markup; tests/test_parity.py holds them to it.

    ./.venv/bin/python tableskin.py data.csv -o out.html     # auto-picked skin
    ./.venv/bin/python tableskin.py data.csv --explain       # roles and why
    ./.venv/bin/python tableskin.py --list
"""
from __future__ import annotations

import argparse
import csv
import io
import math
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKIN_DIR = HERE / "skins"
SKINS = ["clean", "ledger", "paper", "splitflap", "board", "chat"]
MODIFIERS = ["heat", "bars"]
MEASURES = ("number", "money", "percent")

# ---------------------------------------------------------------- values

NA = {"-", "--", "\u2013", "\u2014", "n/a", "na", "null", "none", "nan", "?"}
_CUR = "$€£¥₹"
_NUM = re.compile(
    r"^([" + _CUR + r"]?)([+\-−]?)([" + _CUR + r"]?)"
    r"([0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(\.[0-9]+)?"
    r"(%|[kKMGTP]i?[Bb]?(?:ps)?|B|ms|s|min|h|hrs?|d|x|kg|g|km|m|mi|ft|USD|EUR|GBP)?$"
)
_SPACES = re.compile(r"[   ]")


def parse_number(text):
    """(value, has_currency, has_percent) for a numeric-looking field, else None.

    More lenient than CSSV section 6.1 so real exports qualify: grouping
    commas, currency signs, a plus sign, percent and unit suffixes, and
    accounting parentheses. Leading zeros (007, 02134) stay text, as in CSSV.
    """
    s = text.strip()
    paren = len(s) >= 3 and s[0] == "(" and s[-1] == ")"
    if paren:
        s = s[1:-1]
    m = _NUM.fullmatch(_SPACES.sub("", s))
    if not m:
        return None
    c1, sign, c2, whole, frac, unit = m.groups()
    if (c1 and c2) or (paren and sign):
        return None
    if len(whole) > 1 and whole[0] == "0":
        return None
    v = float(whole.replace(",", "") + (frac or ""))
    if sign in ("-", "−") or paren:
        v = -v
    return v, bool(c1 or c2 or unit in ("USD", "EUR", "GBP")), unit == "%"


_DATES = [
    ("date", r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$"),
    ("datetime", r"^[0-9]{4}-[0-9]{2}-[0-9]{2}[T ][0-9]{1,2}:[0-9]{2}(:[0-9]{2}(\.[0-9]+)?)?(Z|[+-][0-9]{2}:?[0-9]{2})?$"),
    ("date", r"^[0-9]{1,2}[/.][0-9]{1,2}[/.][0-9]{2,4}$"),
    ("datetime", r"^[0-9]{1,2}[/.][0-9]{1,2}[/.][0-9]{2,4},? [0-9]{1,2}:[0-9]{2}(:[0-9]{2})?( ?[AaPp][Mm])?$"),
    ("date", r"^[0-9]{1,2}[/ -][A-Za-z]{3}[/ -][0-9]{2,4}$"),
    ("datetime", r"^[0-9]{1,2}[/ -][A-Za-z]{3}[/ -][0-9]{2,4} [0-9]{1,2}:[0-9]{2}(:[0-9]{2})?( ?[AaPp][Mm])?$"),
    ("date", r"^[A-Za-z]{3,9}\.? [0-9]{1,2},? [0-9]{4}$"),
    ("time", r"^[0-9]{1,2}:[0-9]{2}(:[0-9]{2})?( ?[AaPp][Mm])?$"),
]
_DATES = [(kind, re.compile(rx)) for kind, rx in _DATES]
_URL = re.compile(r"^https?://\S+$")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
_CODE = re.compile(r"^(?=.*[0-9])[A-Za-z0-9][A-Za-z0-9_\-:./#]{2,39}$|^[A-Z]{1,4} [0-9]{1,6}$")


def date_kind(text):
    for kind, rx in _DATES:
        if rx.fullmatch(text):
            return kind
    return None


# Header names, matched against the lowercased header.
def _words(*names):
    return re.compile(r"(^|[^a-z])(" + "|".join(names) + r")([^a-z]|$)")


_ID_H = _words("id", "key", "sku", "code", "ref", "hash", "commit", "sha", "serial", "wwn", "wwpn",
               "uuid", "guid", "ticket", "account", "acct", "invoice", "po", "asset", "mac", "ip",
               "vin", "flight")
_YEAR_H = re.compile(r"^(year|yr|fy|fiscal year)$")
_ORD_H = re.compile(r"^(#|no\.?|num|number|index|idx|slot|port|port ?#|port index|rank|pos|position|row|line|seq|step|order)$")
_MONEY_H = _words("amount", "price", "cost", "costs", "subtotal", "balance", "revenue", "sales", "usd",
                  "eur", "gbp", "fee", "fees", "paid", "budget", "salary", "spend", "spent", "income",
                  "expense", "expenses", "tax", "vat", "profit", "payment", "debit", "credit", "charge",
                  "mrr", "arr")
_PCT_H = re.compile(r"%|(^|[^a-z])(pct|percent|percentage|util|utilization|utilisation|ratio|share)([^a-z]|$)")
_STATUS_H = _words("status", "state", "result", "health", "phase", "stage", "severity", "priority",
                   "outcome", "condition", "verdict")
_PERSON_H = _words("owner", "assignee", "assigned to", "sender", "from", "author", "user", "username",
                   "who", "reporter", "contact", "employee", "customer", "client", "member", "player",
                   "driver", "agent", "manager", "full name", "first name", "last name", "person",
                   "staff", "speaker")
_LABEL_H = _words("category", "categories", "type", "kind", "group", "tag", "tags", "label", "labels",
                  "class", "department", "dept", "team", "region", "segment", "tier", "channel", "source",
                  "vendor", "model", "platform", "site")
_TOTAL = re.compile(r"^(sub ?-?total|total|totals|grand total|sum|balance due|amount due|total due|net total|tax|vat|sales tax|discount|shipping)\b", re.I)

# Status words and the tone a skin should give them.
_TONE_WORDS = {
    "good": "done, ok, okay, pass, passed, passing, success, successful, succeeded, complete, completed, "
            "healthy, online, up, active, on time, resolved, closed, green, yes, y, true, enabled, approved, "
            "paid, delivered, shipped, in stock, valid, connected, available, ready, merged, live, running, "
            "normal, good, accepted, won, departed, landed, arrived",
    "warn": "pending, in progress, in review, review, waiting, warning, warn, degraded, partial, delayed, "
            "at risk, yellow, amber, queued, draft, late, maintenance, paused, on hold, unknown, marginal, "
            "low stock, expiring, needs review, stale, busy, retrying, boarding, final call",
    "bad": "failed, fail, failing, failure, error, errored, errors, critical, down, offline, cancelled, "
           "canceled, blocked, red, no, n, false, disabled, rejected, overdue, unpaid, expired, missing, "
           "invalid, disconnected, outage, lost, broken, faulty, faulted, out of stock, declined, denied, "
           "dead, gate closed",
    "neutral": "to do, todo, open, new, backlog, planned, scheduled, not started, idle, info",
}
TONES = {w.strip(): tone for tone, words in _TONE_WORDS.items() for w in words.split(",")}
_TONE_RANK = {"neutral": 0, "warn": 1, "bad": 2, "good": 3}


def _norm(text):
    return re.sub(r"[\s_\-]+", " ", text.strip().lower())


def tone_of(text):
    return TONES.get(_norm(text))


def is_blank(text):
    s = text.strip()
    return s == "" or s.lower() in NA


def slug(text):
    return re.sub(r"[\W_]+", "-", text.strip().lower()).strip("-")


def hue(k):
    """Golden-angle hues, so the first few categories land far apart."""
    return int(math.floor(210 + k * 137.508 + 0.5)) % 360


def fmt3(x):
    s = "%.3f" % (math.floor(x * 1000 + 0.5) / 1000)
    return s.rstrip("0").rstrip(".") or "0"


def _cplen(text):
    return len(text)  # code points, as [...text].length in JS

# ---------------------------------------------------------------- input


def parse_csv(text):
    """(header, rows). Delimiter is , ; or tab, detected from the header record."""
    if text.startswith("﻿"):
        text = text[1:]
    counts, inside = {",": 0, ";": 0, "\t": 0}, False
    for ch in text:
        if ch == '"':
            inside = not inside
        elif not inside and ch in "\r\n":
            break
        elif not inside and ch in counts:
            counts[ch] += 1
    delim = max([",", ";", "\t"], key=lambda d: (counts[d], d == ","))
    records = [r for r in csv.reader(io.StringIO(text, newline=""), delimiter=delim) if r]
    if not records:
        return [], []
    return records[0], records[1:]


def _cell(v):
    if v is None:
        return ""
    if isinstance(v, float) and math.isnan(v):
        return ""
    return str(v)


def load(source):
    """(header, rows) from a CSV path or text, records, a list of lists, or a DataFrame."""
    if hasattr(source, "columns") and hasattr(source, "itertuples"):
        header = [str(c) for c in source.columns]
        return header, [[_cell(v) for v in row] for row in source.itertuples(index=False)]
    if isinstance(source, Path) or (isinstance(source, str) and "\n" not in source and Path(source).is_file()):
        return parse_csv(Path(source).read_text(encoding="utf-8"))
    if isinstance(source, str):
        return parse_csv(source)
    rows = list(source)
    if rows and isinstance(rows[0], dict):
        header = []
        for r in rows:
            header += [k for k in r if k not in header]
        return [str(h) for h in header], [[_cell(r.get(h)) for h in header] for r in rows]
    return [_cell(v) for v in rows[0]], [[_cell(v) for v in r] for r in rows[1:]]

# ---------------------------------------------------------------- analysis


def _role(name, values):
    """Role of one column and the facts the skins and the picker use."""
    h = name.strip().lower()
    vals = [v for v in values if not is_blank(v)]
    info = {"role": "empty", "numeric": False, "signed": False, "lo": None, "hi": None, "maxabs": 0.0,
            "distinct": len(set(vals)), "avglen": 0.0}
    if not vals:
        return info
    info["avglen"] = sum(_cplen(v) for v in vals) / len(vals)
    nums = [parse_number(v) for v in vals]
    if all(nums):
        xs = [n[0] for n in nums]
        info.update(numeric=True, lo=min(xs), hi=max(xs), maxabs=max(abs(x) for x in xs),
                    signed=any(x < 0 for x in xs))
        integers = all(x == int(x) for x in xs)
        if _ID_H.search(h):
            info["role"] = "id"
        elif _YEAR_H.fullmatch(h) and integers:
            info["role"] = "date"
        elif _ORD_H.fullmatch(h) and integers:
            info["role"] = "ordinal"
        elif any(n[1] for n in nums) or _MONEY_H.search(h):
            info["role"] = "money"
        elif any(n[2] for n in nums) or _PCT_H.search(h):
            info["role"] = "percent"
        else:
            info["role"] = "number"
        return info
    n, distinct, avglen = len(vals), info["distinct"], info["avglen"]
    kinds = [date_kind(v) for v in vals]
    if sum(1 for k in kinds if k) >= 0.8 * n:
        info["role"] = "datetime" if "datetime" in kinds else "time" if all(k == "time" for k in kinds if k) else "date"
    elif sum(1 for v in vals if _URL.fullmatch(v)) >= 0.8 * n:
        info["role"] = "url"
    elif sum(1 for v in vals if _EMAIL.fullmatch(v)) >= 0.8 * n:
        info["role"] = "email"
    elif distinct <= 12 and (sum(1 for v in vals if tone_of(v)) >= 0.6 * n or (_STATUS_H.search(h) and avglen <= 24)):
        info["role"] = "status"
    elif (_ID_H.search(h) or sum(1 for v in vals if _CODE.fullmatch(v)) >= 0.8 * n) and distinct >= 0.8 * n and avglen <= 40:
        info["role"] = "id"
    elif _PERSON_H.search(h) and avglen < 40:
        info["role"] = "person"
    elif avglen >= 32 or any("\n" in v for v in vals):
        info["role"] = "prose"
    elif n >= 3 and distinct <= 12 and avglen <= 24 and (_LABEL_H.search(h) or distinct <= math.ceil(0.6 * n)):
        info["role"] = "label"
    else:
        info["role"] = "text"
    return info


def analyze(header, rows):
    """The table model: columns with roles, rows of typed cells, primary and group columns."""
    width = max([len(header)] + [len(r) for r in rows])
    header = list(header) + [""] * (width - len(header))
    rows = [list(r) + [""] * (width - len(r)) for r in rows if any(f != "" for f in r)]
    cols = []
    for j, name in enumerate(header):
        info = _role(name, [r[j] for r in rows])
        cols.append({"name": name, "index": j, **info})

    def first(*roles):
        return next((c["index"] for c in cols if c["role"] in roles), None)

    primary = first("prose")
    if primary is None:
        primary = first("text")
    if primary is None:
        primary = first("person", "label")
    group = first("status")
    if group is None:
        group = first("label")

    groups = []
    if group is not None:
        seen = []
        for r in rows:
            v = r[group]
            if not is_blank(v) and v not in seen:
                seen.append(v)
        if cols[group]["role"] == "status":
            seen = sorted(seen, key=lambda v: (_TONE_RANK[tone_of(v) or "neutral"], seen.index(v)))
        groups = seen
    return {"columns": cols, "rows": rows, "primary": primary, "group": group, "groups": groups}


def pick(model):
    """(skin tokens, reasons): the first rule that fits wins."""
    cols, rows = model["columns"], model["rows"]
    roles = [c["role"] for c in cols]
    measures = [c for c in cols if c["role"] in MEASURES]
    has = roles.__contains__
    longest = max((_cplen(v) for r in rows for v in r), default=0)
    totals = any(_is_total(r, cols) for r in rows)
    primary = model["primary"]
    group = model["group"]

    if has("person") and has("prose") and (has("time") or has("datetime") or has("date")) and len(rows) >= 4:
        return ["chat"], "a person column, a long-text column and timestamps read as a conversation"
    if (group is not None and cols[group]["role"] == "status" and 2 <= len(model["groups"]) <= 6
            and primary is not None and cols[primary]["role"] == "prose" and 4 <= len(rows) <= 80):
        return ["board"], "a status column with %d values and long titles make a board" % len(model["groups"])
    if (len(rows) <= 16 and 3 <= len(cols) <= 6 and longest <= 18
            and (has("time") or (has("status") and has("id")))):
        return ["splitflap"], "a short list of short values with times or statuses fits a departures board"
    if totals and has("money"):
        return ["paper"], "money with total rows reads as an invoice or statement"
    if has("money") or (has("date") and any(c["signed"] for c in measures)):
        return ["ledger"], "money or signed amounts over dates read as a ledger"
    if len(measures) >= 3 and len(measures) * 2 >= len(cols):
        return ["clean", "heat"], "%d of %d columns are measures, so shade them as a heat map" % (len(measures), len(cols))
    if measures and len(rows) >= 3:
        return ["clean", "bars"], "a few measure columns get in-cell bars"
    return ["clean"], "nothing more specific fits"


def _is_total(row, cols):
    for j in range(min(2, len(cols))):
        if not cols[j]["numeric"] and _TOTAL.match(row[j].strip()):
            return True
    return False

# ---------------------------------------------------------------- markup


def _text(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _attr(s):
    return _text(s).replace('"', "&quot;")


def _key_index(model, skin, key):
    cols = model["columns"]
    if key is not None:
        for c in cols:
            if c["name"] == key:
                return c["index"]
        raise ValueError("no column named %r" % key)
    want = ("person",) if "chat" in skin else ("id",)
    return next((c["index"] for c in cols if c["role"] in want), None)


def render(model, skin="auto", title=None, key=None, me=None):
    """The wrapper div and the table, with no styles. skin is "auto", a name or a list."""
    if skin == "auto":
        skin = pick(model)[0]
    elif isinstance(skin, str):
        skin = skin.split()
    cols, rows = model["columns"], model["rows"]
    kj, gj, pj = _key_index(model, skin, key), model["group"], model["primary"]
    groups = model["groups"]

    # Per-column hue indexes for categorical cells, and per-key hues for rows.
    cat_seen = {c["index"]: [] for c in cols if c["role"] in ("status", "label", "person")}
    key_seen = []

    out = ['<div class="tableskin" data-skin="%s">' % _attr(" ".join(skin))]
    style = "--rows:%d;--cols:%d" % (len(rows), len(cols))
    if groups:
        style += ";--groups:%d" % len(groups)
    out.append('<table data-rows="%d" data-cols="%d" style="%s">' % (len(rows), len(cols), style))
    if title:
        out.append("<caption>%s</caption>" % _text(title))
    out.append("<colgroup>%s</colgroup>" % "".join(
        '<col data-col="%s" data-role="%s">' % (_attr(c["name"]), c["role"]) for c in cols))

    def flags(c):
        a = ""
        if c["index"] == pj:
            a += " data-primary"
        if c["index"] == gj:
            a += " data-grouping"
        return a

    numbered = ("number", "money", "percent", "ordinal")
    head = []
    for c in cols:
        a = '<th data-col="%s" data-role="%s"' % (_attr(c["name"]), c["role"])
        if c["numeric"] and c["role"] in numbered:
            a += ' class="number"'
        if c["signed"] and c["role"] in MEASURES:
            a += " data-signed"
        a += flags(c)
        head.append('%s style="--j:%d">%s</th>' % (a, c["index"], _text(c["name"])))
    out.append('<thead><tr data-row="1">%s</tr></thead>' % "".join(head))

    out.append("<tbody>")
    prev_key, group_started = None, set()
    for i, r in enumerate(rows):
        a = '<tr data-row="%d"' % (i + 2)
        style = "--i:%d" % i
        k = r[kj] if kj is not None and not is_blank(r[kj]) else None
        if k is not None:
            a += ' data-key="%s"' % _attr(k)
            if me is not None and k == me:
                a += " data-me"
            if k != prev_key:
                a += ' data-run="start"'
            if k not in key_seen:
                key_seen.append(k)
        prev_key = k
        if gj is not None and r[gj] in groups:
            g = r[gj]
            a += ' data-group="%s"' % _attr(g)
            if g not in group_started:
                a += " data-group-start"
                group_started.add(g)
            style += ";--group:%d" % (groups.index(g) + 1)
        if _is_total(r, cols):
            a += " data-total"
        if k is not None:
            style += ";--hue:%d" % hue(key_seen.index(k))
        cells = []
        for c in cols:
            v = r[c["index"]]
            ca = '<td data-col="%s" data-role="%s"' % (_attr(c["name"]), c["role"])
            cs = "--j:%d" % c["index"]
            n = parse_number(v) if c["numeric"] else None
            if n is not None and c["role"] in numbered:
                sign = "zero" if n[0] == 0 else "negative" if n[0] < 0 else "positive"
                ca += ' class="number %s"' % sign
            if c["signed"] and c["role"] in MEASURES:
                ca += " data-signed"
            if v != "" and is_blank(v):
                ca += " data-na"
            ca += flags(c)
            if not is_blank(v):
                if c["role"] == "status" and tone_of(v):
                    ca += ' data-tone="%s"' % tone_of(v)
                if c["index"] in cat_seen:
                    ca += ' data-tag="%s"' % _attr(slug(v))
                    seen = cat_seen[c["index"]]
                    if v not in seen:
                        seen.append(v)
                    cs += ";--hue:%d" % hue(seen.index(v))
            if n is not None and c["role"] in MEASURES:
                span = c["hi"] - c["lo"]
                t = (n[0] - c["lo"]) / span if span else 1.0
                mag = abs(n[0]) / c["maxabs"] if c["maxabs"] else 0.0
                cs += ";--t:%s;--mag:%s" % (fmt3(t), fmt3(mag))
            cells.append('%s style="%s">%s</td>' % (ca, cs, _text(v)))
        out.append('%s style="%s">%s</tr>' % (a, style, "".join(cells)))
    out.append("</tbody></table></div>")
    return "".join(out)


def css(skin):
    """The base stylesheet plus each named skin, in cascade order."""
    names = skin.split() if isinstance(skin, str) else list(skin)
    parts = [(SKIN_DIR / "base.css").read_text(encoding="utf-8")]
    for name in names:
        path = SKIN_DIR / ("%s.css" % name)
        if not path.is_file():
            raise ValueError("no skin named %r (have: %s)" % (name, ", ".join(SKINS + MODIFIERS)))
        parts.append(path.read_text(encoding="utf-8"))
    return "\n".join(parts)


def bundle():
    """Every skin in one file, for pages that use tableskin.js."""
    return css(SKINS + MODIFIERS)


def fragment(source, skin="auto", title=None, key=None, me=None):
    """A <style> and the table, ready to paste into a page. Styles are scoped by data-skin."""
    model = analyze(*load(source))
    names = pick(model)[0] if skin == "auto" else (skin.split() if isinstance(skin, str) else list(skin))
    return "<style>\n%s</style>\n%s" % (css(names), render(model, names, title, key, me))


def page(source, skin="auto", title=None, key=None, me=None):
    """A standalone HTML page."""
    return PAGE % {"title": _text(title or "Table"), "body": fragment(source, skin, title, key, me)}


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>%(title)s</title>
<style>
:root { color-scheme: light dark; --page: light-dark(#f6f5f2, #161615); --ink: light-dark(#1d1d1b, #e8e6e1); }
body { margin: 0; padding: 32px 16px; background: var(--page); color: var(--ink); font: 15px/1.5 system-ui, sans-serif; }
main { max-width: 1040px; margin: 0 auto; }
</style>
</head>
<body><main>
%(body)s
</main></body>
</html>
"""


def explain(model):
    lines = []
    w = max([len(c["name"]) for c in model["columns"]] + [6])
    for c in model["columns"]:
        extra = []
        if c["index"] == model["primary"]:
            extra.append("primary")
        if c["index"] == model["group"]:
            extra.append("groups: " + ", ".join(model["groups"]))
        if c["signed"]:
            extra.append("signed")
        lines.append("  %-*s  %-8s %s" % (w, c["name"] or "(empty)", c["role"], "  ".join(extra)))
    skin, why = pick(model)
    lines.append("skin: %s  (%s)" % (" ".join(skin), why))
    return "\n".join(lines)

# ---------------------------------------------------------------- gallery


def gallery(out=HERE / "gallery.html"):
    """Every sample with its picked skin and a menu to try the others."""
    samples = [
        ("transactions.csv", "September transactions", {}),
        ("invoice.csv", "Invoice 2026-114", {}),
        ("departures.csv", "Departures", {}),
        ("sprint.csv", "Sprint 15", {}),
        ("chat.csv", None, {"me": "Sam"}),
        ("ports.csv", "Fabric A port utilization", {}),
        ("cities.csv", "Largest cities", {}),
    ]
    options = "".join('<option>%s</option>' % s for s in SKINS + ["clean heat", "clean bars", "ledger bars"])
    blocks = []
    for name, title, kw in samples:
        model = analyze(*load(HERE / "samples" / name))
        skin, why = pick(model)
        blocks.append(
            '<section><header><h2>%s</h2><p>Picked <b>%s</b>: %s.</p>'
            '<label>Try <select data-for="%s">%s</select></label></header>%s</section>'
            % (name, " ".join(skin), why, name, options.replace(
                "<option>%s</option>" % " ".join(skin), "<option selected>%s</option>" % " ".join(skin)),
               render(model, skin, title, **kw)))
    html = GALLERY % {"css": bundle(), "body": "\n".join(blocks)}
    Path(out).write_text(html, encoding="utf-8")
    return out


GALLERY = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Tableskin Gallery</title>
<style>
:root { color-scheme: light dark; --page: light-dark(#f6f5f2, #161615); --ink: light-dark(#1d1d1b, #e8e6e1); --muted: light-dark(#6b6a65, #9d9b94); }
:root[data-theme="light"] { color-scheme: light; }
:root[data-theme="dark"] { color-scheme: dark; }
body { margin: 0; padding: 32px 16px 80px; background: var(--page); color: var(--ink); font: 15px/1.5 system-ui, sans-serif; }
main { max-width: 1040px; margin: 0 auto; }
h1 { margin: 0 0 4px; font-size: 28px; letter-spacing: -0.02em; }
.lede { margin: 0 0 24px; color: var(--muted); max-width: 68ch; }
.theme { position: fixed; top: 12px; right: 12px; font: inherit; }
section { margin: 0 0 56px; }
section header { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 16px; margin-bottom: 14px; }
h2 { margin: 0; font: 600 13px ui-monospace, Menlo, monospace; }
section header p { margin: 0; color: var(--muted); font-size: 13px; flex: 1; }
label { font-size: 13px; color: var(--muted); }
</style>
<style>
%(css)s
</style>
</head>
<body>
<button class="theme" type="button">Theme: auto</button>
<main>
<h1>Tableskin gallery</h1>
<p class="lede">Sample tables, each in the skin tableskin.py picked for it. The menu swaps the skin on the same markup. Skins and the table-model idea are adapted from CSSV by Rodrigo Paiva (MIT).</p>
%(body)s
</main>
<script>
for (const sel of document.querySelectorAll('select[data-for]')) {
  sel.addEventListener('change', () => { sel.closest('section').querySelector('.tableskin').dataset.skin = sel.value; });
}
const btn = document.querySelector('.theme'), modes = ['auto', 'light', 'dark'];
btn.addEventListener('click', () => {
  const next = modes[(modes.indexOf(btn.textContent.slice(7)) + 1) %% 3];
  btn.textContent = 'Theme: ' + next;
  if (next === 'auto') delete document.documentElement.dataset.theme; else document.documentElement.dataset.theme = next;
});
</script>
</body>
</html>
"""

# ---------------------------------------------------------------- cli


def main(argv=None):
    ap = argparse.ArgumentParser(description="Render table-like data with a CSSV-style skin.")
    ap.add_argument("source", nargs="?", help="a CSV file (comma, semicolon or tab), or - for stdin")
    ap.add_argument("-s", "--skin", default="auto", help='"auto", or skin names such as "ledger" or "clean heat"')
    ap.add_argument("-t", "--title", help="caption shown above the table")
    ap.add_argument("-o", "--out", help="write here instead of stdout")
    ap.add_argument("--key", help="column whose values become data-key")
    ap.add_argument("--me", help='for the chat skin: whose messages go on the right')
    ap.add_argument("--fragment", action="store_true", help="a <style> and the table, not a whole page")
    ap.add_argument("--explain", action="store_true", help="print column roles and the picked skin")
    ap.add_argument("--list", action="store_true", help="list skins")
    ap.add_argument("--bundle", action="store_true", help="rewrite tableskin.css from skins/")
    ap.add_argument("--gallery", action="store_true", help="rewrite gallery.html from samples/")
    a = ap.parse_args(argv)

    if a.list:
        print("skins:     " + "  ".join(SKINS))
        print("modifiers: " + "  ".join(MODIFIERS) + "   (combine: \"clean heat\")")
        return 0
    if a.bundle:
        (HERE / "tableskin.css").write_text(bundle(), encoding="utf-8")
        print(HERE / "tableskin.css")
        return 0
    if a.gallery:
        print(gallery())
        return 0
    if not a.source:
        ap.error("give a CSV file, or --list, --bundle or --gallery")
    source = sys.stdin.read() if a.source == "-" else Path(a.source)
    if a.explain:
        print(explain(analyze(*load(source))))
        return 0
    result = (fragment if a.fragment else page)(source, a.skin, a.title, a.key, a.me)
    if a.out:
        Path(a.out).write_text(result, encoding="utf-8")
        print(a.out)
    else:
        sys.stdout.write(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
