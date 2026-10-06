// Renders each case with tableskin.js and prints the markup as JSON, for
// test_parity.py to compare with tableskin.py. Usage: node parity.mjs '<cases json>'
import { readFileSync } from 'node:fs';
import { analyze, parseCSV, pick, render } from '../tableskin.js';

const cases = JSON.parse(process.argv[2]);
const out = cases.map(({ path, skin = 'auto', title = null, key = null, me = null }) => {
  const model = analyze(...parseCSV(readFileSync(path, 'utf8')));
  return { pick: pick(model), roles: model.columns.map((c) => c.role), html: render(model, { skin, title, key, me }) };
});
process.stdout.write(JSON.stringify(out));
