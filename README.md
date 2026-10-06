# tableskin

> Built on [CSSV](https://github.com/rhpaiva/cssv) by Rodrigo Paiva: its
> table model and six of its stylesheets, reworked to apply to any table.
> MIT, like the original; see [Credit](#credit) and `NOTICE`.

A hammer for the day a table shows up that deserves better than default HTML.
Feed it a CSV file, a list of records or a DataFrame. It works out what each
column is (money, dates, statuses, people, ids, long text), marks up the table
with hooks a stylesheet can rely on, and picks a skin that suits the data:

| Skin | Picked when | Looks like |
| --- | --- | --- |
| `clean` | nothing more specific fits | hairline rules, quiet headers, status and category dots |
| `ledger` | money, or signed amounts over dates | a bank statement: credits green with `+`, balance muted |
| `paper` | money with Subtotal/Tax/Total rows | an invoice on warm paper, serif, total in the accent color |
| `splitflap` | a short list of short values with times or statuses | an airport departures board, flaps and all |
| `board` | a status column (2–6 values) and long titles | a kanban board, one lane per status |
| `chat` | a person, long text and timestamps | message bubbles, runs grouped, `--me` on the right |
| `heat` (modifier) | 3+ measure columns, half the table or more | cells shaded by where they sit in their column |
| `bars` (modifier) | a few measure columns | a thin bar under each value |

Modifiers stack on a skin: `clean heat`, `ledger bars`.

**[See the gallery](https://charles-hood.github.io/tableskin/gallery.html)**: every sample in
its picked skin, with a menu to try the others and a light/dark toggle. It is
`gallery.html` in this repo, rebuilt by `tableskin.py --gallery`.

## Use

Python, stdlib only (`.venv` exists for the tests' Pillow and nothing else):

```
./.venv/bin/python tableskin.py data.csv -o out.html             # whole page, skin picked for you
./.venv/bin/python tableskin.py data.csv -s "clean heat" -t "Ports" -o out.html
./.venv/bin/python tableskin.py data.csv --fragment              # <style> + table, to paste in
./.venv/bin/python tableskin.py data.csv --explain               # column roles and why that skin
./.venv/bin/python tableskin.py chat.csv --me Sam                # chat: whose bubbles go right
./.venv/bin/python tableskin.py --list
```

```python
import tableskin as ts
html = ts.page(df, title="Fabric A")                # DataFrame, records, list of lists, CSV path or text
frag = ts.fragment("ports.csv", skin="clean heat")
model = ts.analyze(*ts.load(records)); print(ts.explain(model))
```

Browser, for tables that already exist on a page. `tableskin.js` is an ES
module and loads `tableskin.css` from beside itself:

```html
<script type="module">
  import { skinAll, skinTable, fromCSV } from './tableskin.js';
  skinAll('main table');                                  // every table, skin picked per table
  skinTable(document.querySelector('#q3'), { skin: 'ledger' });
  document.body.append(fromCSV(csvText, { title: 'Ports' }));
</script>
```

`skinTable` keeps the cells and whatever is in them (links, icons), moves a
header row into `<thead>` if it has to, adds the hooks and wraps the table.
`skinAll` skips tables with merged cells.

## The hooks

Every skin is written against this markup and nothing else, so any skin works
on any table. The first group is CSSV's table model (SPEC sections 6 and 7);
the rest are tableskin's additions, several of which CSSV leaves out on
purpose (it never copies cell content into attributes).

| Hook | On | Meaning |
| --- | --- | --- |
| `data-col` | `col`, `th`, `td` | the column name, exactly as written |
| `data-row` | `tr` | record number, header = 1 |
| `class="number negative\|zero\|positive"` | `td` (`th`: `number`) | numeric cells and their sign |
| `data-key` | `tr` | the key column's value (`--key`; else the first id column, or the person for chat) |
| `data-role` | `col`, `th`, `td` | `number money percent ordinal id date datetime time status person label prose text url email empty` |
| `data-primary` | `th`, `td` | the column that names the row (first prose, else text) |
| `data-signed` | `th`, `td` | a measure column with negatives in it |
| `data-tone` | `td` | `good warn bad neutral`, for known status words |
| `data-tag`, `--hue` | `td` | slug and a golden-angle hue for status, label and person cells |
| `data-group`, `data-group-start`, `--group` | `tr` | the row's lane: status column, else first label column |
| `data-run="start"`, `--hue` | `tr` | first row of a run with the same key; hue per key |
| `data-me` | `tr` | the key equals `--me` |
| `data-total` | `tr` | the first or second cell reads Total, Subtotal, Tax and so on |
| `data-na` | `td` | a placeholder such as `-`, `--`, `n/a`, `null` or a lone dash |
| `--t`, `--mag` | `td` | for measures: 0–1 position in the column's range, and size against its largest absolute value |
| `--i`, `--j` | `tr`, cells | row and column index, for staggered animation |
| `--rows`, `--cols`, `--groups` | `table` | counts, for grid layouts |

Each skin is scoped to `[data-skin~="name"]` on the wrapper and lives in a
cascade layer, so several skins can share a page and any plain rule on the page
overrides them. The wrapper has `contain: paint`, so a skin cannot draw outside
its box. `--t` and `--mag` are what make heat maps and bars possible, which
CSSV cannot do because CSS cannot compare numbers.

## Adding a skin

Write `skins/<name>.css` in `@layer tableskin.skin` (or `tableskin.mod` for a
modifier), scoped to `[data-skin~="<name>"]`, against the hooks above. Add the
name to `SKINS` or `MODIFIERS` in both `tableskin.py` and `tableskin.js`, give
`pick()` a rule in both if it should be chosen automatically, then
`tableskin.py --bundle` and `--gallery`.

## Tests

```
./.venv/bin/python -m unittest discover tests
```

Unit tests for the analysis and the markup, plus two parity checks:
`tableskin.js` under Node must write exactly the string `tableskin.py` writes
for every sample and fixture, and `skinTable()` run on a plain table in
headless Chrome must produce the same markup. Each parity check skips itself
if Node or Chrome is missing. The test suite also fails if `tableskin.css` is
older than `skins/`.

## Limits

- Numbers are written with `.` for decimals. In semicolon files `1.200` reads
  as 1.2, not 1200 (CSSV has the same limit).
- Values display as written: no locale formatting, no rounding.
- `splitflap` and `board` are tuned for a screenful: the picker only reaches
  for them on small tables.
- Browser support is whatever handles CSS nesting, `light-dark()`,
  `color-mix()` and `:has()`: current Chrome, Safari and Firefox.

## Credit

The table-model idea and the skins `clean`, `ledger`, `paper`, `splitflap`,
`board` and `chat` are adapted from [CSSV](https://github.com/rhpaiva/cssv) by
Rodrigo Paiva, MIT licensed; see `NOTICE`. The originals name their columns;
these find them by role.
