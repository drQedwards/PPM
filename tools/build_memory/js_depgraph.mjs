#!/usr/bin/env node
// js-depgraph.mjs — JS/TS import/export graph in the same unit + {nodes,edges} format as php-depgraph.php.
// Usage: node js-depgraph.mjs <repo> --out units.json --graph graph.json   (read-only, regex-based, no deps)
import fs from 'fs'; import path from 'path'; import crypto from 'crypto'; import { execSync } from 'child_process';
const a = process.argv.slice(2); let root, out = 'js_build_results.json', gout;
for (let i = 0; i < a.length; i++) a[i] === '--out' ? out = a[++i] : a[i] === '--graph' ? gout = a[++i] : root = a[i];
root = path.resolve(root);
const EXT = /\.(m?[jt]sx?|cjs)$/, SKIP = /(^|\/)(node_modules|\.git|dist|build|coverage|\.next|ios\/Pods)(\/|$)/;
const files = []; (function walk(d) { for (const e of fs.readdirSync(d, { withFileTypes: true })) { const p = path.join(d, e.name), r = path.relative(root, p);
  if (SKIP.test(r)) continue; e.isDirectory() ? walk(p) : EXT.test(e.name) && !e.name.endsWith('.d.ts') && files.push(r); } })(root);
files.sort();
// workspace packages: name -> dir
const pkgs = {}; (function walkPkg(d, depth) { if (depth > 4) return; for (const e of fs.readdirSync(d, { withFileTypes: true })) { const p = path.join(d, e.name);
  if (SKIP.test(path.relative(root, p))) continue; if (e.isDirectory()) walkPkg(p, depth + 1);
  else if (e.name === 'package.json') { try { const j = JSON.parse(fs.readFileSync(p)); if (j.name) pkgs[j.name] = { dir: path.relative(root, d) || '.', main: j.main || j.module || j.source }; } catch {} } } })(root, 0);
const nodes = new Map(), edges = new Map();
const node = (type, label, content, metadata = {}) => nodes.set(type + '\0' + label, { type, label, content, metadata });
const edge = (s, r, t) => edges.set(`${s}\0${r}\0${t}`, { source: s, relation: r, target: t });
const resolveRel = (from, spec) => { const b = path.join(path.dirname(path.join(root, from)), spec);
  for (const c of ['', '.ts', '.tsx', '.js', '.jsx', '.mjs', '/index.ts', '/index.tsx', '/index.js']) { const f = b + c; if (fs.existsSync(f) && fs.statSync(f).isFile()) return path.relative(root, f); } return null; };
const pkgOf = f => { let best = '.'; for (const { dir } of Object.values(pkgs)) if ((dir === '.' || f.startsWith(dir + '/')) && dir.length > best.length) best = dir; return best; };
const IMP = /(?:import|export)\s+(?:type\s+)?(?:[\w*{}\s,$]+?\s+from\s+)?['"]([^'"]+)['"]|require\(\s*['"]([^'"]+)['"]\s*\)|import\(\s*['"]([^'"]+)['"]\s*\)/g;
const EXP = /export\s+(?:default\s+)?(?:declare\s+)?(?:abstract\s+)?(class|function\*?|const|let|interface|type|enum)\s+([\w$]+)/g;
const units = {}; let iterCount = 0;
for (const f of files) {
  const src = fs.readFileSync(path.join(root, f), 'utf8'); const pk = pkgOf(f); const fl = `js:file:${f}`;
  node('file', fl, `js file ${f}`); edge(`js:pkg:${pk}`, 'contains', fl);
  const u = units[pk] ??= { path: pk, files: [], deps: new Set() }; u.files.push(f);
  for (const m of src.matchAll(EXP)) { const [_, kind, name] = m; const l = `js:sym:${f}#${name}`; node('concept', l, `export ${kind} ${name}`, { kind }); edge(fl, 'exports', l);
    if (kind === 'function*') { node('concept', `js:iter:${f}#${name}`, `generator ${name}`, { iterator: true }); edge(`js:iter:${f}#${name}`, 'references', l); iterCount++; } }
  for (const m of src.matchAll(/(?:async\s+)?\*\s*\[Symbol\.(async)?[iI]terator\]|function\*\s*([\w$]+)/g)) if (m[0].includes('Symbol')) { node('concept', `js:iter:${f}#Symbol.${m[1] ? 'asyncIterator' : 'iterator'}`, 'iterator protocol impl', { iterator: true }); edge(fl, 'contains', `js:iter:${f}#Symbol.${m[1] ? 'asyncIterator' : 'iterator'}`); }
  for (const m of src.matchAll(IMP)) { const spec = m[1] || m[2] || m[3];
    if (spec.startsWith('.')) { const t = resolveRel(f, spec); if (t) { edge(fl, 'imports', `js:file:${t}`); const tp = pkgOf(t); if (tp !== pk) u.deps.add(tp); } }
    else { const name = spec.startsWith('@') ? spec.split('/').slice(0, 2).join('/') : spec.split('/')[0];
      if (pkgs[name]) { edge(fl, 'imports', `js:pkg:${pkgs[name].dir}`); if (pkgs[name].dir !== pk) u.deps.add(pkgs[name].dir); }
      else { node('concept', `js:ext:${name}`, `external package ${name}`, { external: true }); edge(fl, 'imports', `js:ext:${name}`); } } }
}
for (const [n, { dir }] of Object.entries(pkgs)) node('concept', `js:pkg:${dir}`, `package ${n}`, { name: n });
node('concept', 'js:pkg:.', 'repo root package');
const rootPkg = pkgs[JSON.parse(fs.readFileSync(path.join(root, 'package.json'))).name];
const entry = rootPkg?.main && fs.existsSync(path.join(root, rootPkg.main)) ? rootPkg.main : null;
const rootLabel = `js:root:${path.basename(root)}`; node('note', rootLabel, `root ${entry || 'package.json'}`); edge(rootLabel, 'references', entry ? `js:file:${entry}` : 'js:pkg:.');
for (const e of edges.values()) for (const l of [e.source, e.target]) if (![...['file', 'concept', 'note']].some(t => nodes.has(t + '\0' + l))) node('concept', l, `ref ${l}`);
const sha = f => crypto.createHash('sha256').update(fs.readFileSync(path.join(root, f))).digest('hex');
const fsha = fl => { const h = crypto.createHash('sha256'); for (const r of [...new Set(fl)].sort()) h.update(`${r}\0${sha(r)}\n`); return h.digest('hex'); };
let head = ''; try { head = execSync(`git -C ${JSON.stringify(root)} rev-parse HEAD`).toString().trim(); } catch {}
const meta = { repo: path.basename(root), head, generated_at: new Date().toISOString(), parser: 'regex', root_entry: entry || 'package.json' };
const U = Object.values(units).map(u => ({ path: u.path, sha256: fsha(u.files), files: u.files, includes: [], depends_on_units: [...u.deps].sort(), kind: 'js', required: false, ok: null, warnings: 0, first_errors: [] }));
fs.writeFileSync(out, JSON.stringify({ units: U, required_failures: 0, meta }, null, 1));
if (gout) fs.writeFileSync(gout, JSON.stringify({ meta, root: rootLabel, nodes: [...nodes.values()], edges: [...edges.values()] }, null, 1));
const nk = {}, ek = {}; for (const n of nodes.values()) nk[n.label.split(':')[1]] = (nk[n.label.split(':')[1]] || 0) + 1; for (const e of edges.values()) ek[e.relation] = (ek[e.relation] || 0) + 1;
console.error(`files=${files.length} packages=${U.length} nodes=${nodes.size} edges=${edges.size}\nnode kinds: ${JSON.stringify(nk)}\nedge kinds: ${JSON.stringify(ek)}`);
