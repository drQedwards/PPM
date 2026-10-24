/** Load siphon graph + structural features (port of siphon-walk/learn_walk). */
const fs = require("fs");
const path = require("path");

const FEATURE_KEYS = ["same_sec", "out_share", "repeat", "delegation", "near_zero"];
const DEFAULT_W = {
  same_sec: 3.0,
  out_share: 2.0,
  repeat: 1.0,
  delegation: 5.0,
  near_zero: 2.0,
};

function norm(a) {
  if (!a) return null;
  if (typeof a === "string" && (a.startsWith("0x") || a.startsWith("0X"))) return a.toLowerCase();
  return a;
}

function loadSiphon(graphPath) {
  const G = JSON.parse(fs.readFileSync(graphPath, "utf8"));
  const collectors = [
    "0xeeeee90971b6264c53175d3af6840a8dd5dc7b6c",
    "0xf111122404b8c2fc01dff89c65d3104fbb608008",
    "0x8566263047ead285194b2e8feb53f312cf8cb463",
    "0x09cbc0d92aabe6f53ac7e84f0ba0fbfd05eb80f2",
    "FncazAs6omJJjtLVzquzT9KoyXn6tFixr9kGjr42ktLj",
    "5qmtDCvUreD8G59M5FosdpV8Gqdd3kFgdH1Vv7HKXUKq",
    "7jNPvxGzQ5wG5NMYZD1GGLAvCyYF7v1Ai5PV9whYt9AN",
  ];
  const collectors_n = collectors.map((c) => (c.startsWith("0x") ? norm(c) : c));
  const seeds = G.seeds.ethereum.map(norm).concat(G.seeds.solana);
  const delegation = {};
  for (const [k, v] of Object.entries(G.delegation || {})) {
    delegation[norm(k)] = norm(v);
  }

  const edges = [];
  for (const e of G.edges) {
    const s = norm(e.src);
    const d = norm(e.dst);
    if (!s || !d || s === d) continue;
    edges.push({ ...e, src: s, dst: d });
  }

  const adj = new Map();
  for (const e of edges) {
    if (!adj.has(e.src)) adj.set(e.src, []);
    adj.get(e.src).push(e);
  }

  const nodes = new Set();
  for (const e of edges) {
    nodes.add(e.src);
    nodes.add(e.dst);
  }

  const byNodeTs = new Map();
  function pushEv(n, ev) {
    if (!byNodeTs.has(n)) byNodeTs.set(n, []);
    byNodeTs.get(n).push(ev);
  }
  for (const e of edges) {
    let ts = e.ts;
    if (ts == null) continue;
    ts = parseInt(ts, 10);
    if (Number.isNaN(ts)) continue;
    pushEv(e.dst, [ts, "in", e.src]);
    pushEv(e.src, [ts, "out", e.dst]);
  }

  const sameSecond = new Map(); // key "src\0dst" -> count
  for (const [node, evs] of byNodeTs) {
    const inByT = new Map();
    for (const [t, d, o] of evs) {
      if (d === "in") {
        if (!inByT.has(t)) inByT.set(t, []);
        inByT.get(t).push(o);
      }
    }
    for (const [t, d, o] of evs) {
      if (d === "out" && inByT.has(t)) {
        const k = node + "\0" + o;
        sameSecond.set(k, (sameSecond.get(k) || 0) + 1);
      }
    }
  }

  const outValue = new Map();
  const inValue = new Map();
  const edgeValue = new Map();
  const repeatCount = new Map();
  for (const e of edges) {
    const v = Math.max(parseFloat(e.value) || 0, 0);
    outValue.set(e.src, (outValue.get(e.src) || 0) + v);
    inValue.set(e.dst, (inValue.get(e.dst) || 0) + v);
    const ek = e.src + "\0" + e.dst;
    edgeValue.set(ek, (edgeValue.get(ek) || 0) + v);
    repeatCount.set(ek, (repeatCount.get(ek) || 0) + 1);
  }

  function outflowShare(s, d) {
    const tot = outValue.get(s) || 0;
    if (tot <= 0) return 0;
    return (edgeValue.get(s + "\0" + d) || 0) / tot;
  }

  function nearZero(s, d) {
    const inn = inValue.get(s) || 0;
    const out = outValue.get(s) || 0;
    if (out <= 0) return 0;
    if (inn <= 0) return outflowShare(s, d) >= 0.5 ? 1 : 0;
    const residual = Math.max(inn - out, 0) / inn;
    if (residual < 0.05 && outflowShare(s, d) >= 0.1) return 1;
    return 0;
  }

  const edgeFeat = new Map();
  for (const e of edges) {
    const ek = e.src + "\0" + e.dst;
    edgeFeat.set(ek, {
      same_sec: sameSecond.get(ek) || 0,
      out_share: outflowShare(e.src, e.dst),
      repeat: repeatCount.get(ek) || 0,
      delegation: delegation[e.src] === e.dst ? 1 : 0,
      near_zero: nearZero(e.src, e.dst),
    });
  }

  const nodeFeat = new Map();
  for (const n of nodes) {
    const outs = adj.get(n) || [];
    if (!outs.length) {
      nodeFeat.set(n, Object.fromEntries(FEATURE_KEYS.map((k) => [k, 0])));
      continue;
    }
    const acc = Object.fromEntries(FEATURE_KEYS.map((k) => [k, 0]));
    for (const e of outs) {
      const f = edgeFeat.get(e.src + "\0" + e.dst);
      for (const k of FEATURE_KEYS) acc[k] += f[k];
    }
    for (const k of FEATURE_KEYS) acc[k] /= outs.length;
    nodeFeat.set(n, acc);
  }

  return {
    adj,
    nodes,
    seeds,
    collectors_n,
    edgeFeat,
    nodeFeat,
    n_edges: edges.length,
    FEATURE_KEYS,
    DEFAULT_W,
  };
}

function bfsPath(adj, start, target, maxExpand = 50000) {
  if (start === target) return new Set([start]);
  const q = [start];
  const parent = new Map([[start, null]]);
  let expanded = 0;
  while (q.length) {
    const u = q.shift();
    expanded++;
    if (expanded > maxExpand) return null;
    for (const e of adj.get(u) || []) {
      const v = e.dst;
      if (parent.has(v)) continue;
      parent.set(v, u);
      if (v === target) {
        const path = new Set();
        let cur = v;
        while (cur != null) {
          path.add(cur);
          cur = parent.get(cur);
        }
        return path;
      }
      q.push(v);
    }
  }
  return null;
}

function reachablePairs(g) {
  const pairs = [];
  for (const seed of g.seeds) {
    if (!g.nodes.has(seed) && !g.adj.has(seed)) continue;
    for (const c of g.collectors_n) {
      if (!g.nodes.has(c)) continue;
      const seedEth = typeof seed === "string" && seed.startsWith("0x");
      const cEth = typeof c === "string" && c.startsWith("0x");
      if (seedEth !== cEth) continue;
      const path = bfsPath(g.adj, seed, c);
      if (path) pairs.push({ seed, collector: c, path });
    }
  }
  return pairs;
}

module.exports = {
  FEATURE_KEYS,
  DEFAULT_W,
  loadSiphon,
  bfsPath,
  reachablePairs,
  norm,
};
