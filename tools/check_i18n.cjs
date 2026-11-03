// Validate translation coverage and numbered placeholders without modifying source.
const fs = require('node:fs'), path = require('node:path'), ts = require('typescript');
const root = path.resolve(__dirname, '..'), dictionary = JSON.parse(fs.readFileSync(path.join(root, 'locales/en.json'), 'utf8'));
const errors = [], keys = new Set();
for (const folder of ['src', 'electron']) for (const name of fs.readdirSync(path.join(root, folder))) {
  if (!/\.(?:ts|tsx|cjs)$/.test(name)) continue;
  const file = path.join(root, folder, name), source = ts.createSourceFile(file, fs.readFileSync(file, 'utf8'), ts.ScriptTarget.Latest, true, name.endsWith('.tsx') ? ts.ScriptKind.TSX : name.endsWith('.ts') ? ts.ScriptKind.TS : ts.ScriptKind.JS);
  function visit(node) {
    if (ts.isCallExpression(node) && node.expression.getText(source) === 'tr' && node.arguments[0] && ts.isStringLiteralLike(node.arguments[0])) keys.add(node.arguments[0].text);
    ts.forEachChild(node, visit);
  }
  visit(source);
}
const slots = value => [...value.matchAll(/\{\d+\}/g)].map(m => m[0]).sort().join(',');
for (const key of keys) if (/\p{Script=Han}/u.test(key) && !dictionary[key]) errors.push('Missing translation: ' + key);
for (const [key, value] of Object.entries(dictionary)) {
  if (typeof value !== 'string' || !value.trim()) errors.push('Invalid translation: ' + key);
  else if (slots(key) !== slots(value)) errors.push('Placeholder mismatch: ' + key);
}
if (errors.length) { console.error(errors.join('\n')); process.exitCode = 1; }
else console.log(`Validated ${keys.size} UI keys and ${Object.keys(dictionary).length} English translations.`);
