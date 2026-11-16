function mean(xs) {
  if (!xs.length) return null;
  return xs.reduce((a, b) => a + b, 0) / xs.length;
}

function stdev(xs) {
  if (xs.length < 2) return 0;
  const m = mean(xs);
  const v = xs.reduce((a, b) => a + (b - m) * (b - m), 0) / (xs.length - 1);
  return Math.sqrt(v);
}

function summarize(xs, nTrials) {
  const hit = xs.filter((x) => x != null);
  if (!hit.length) {
    return { n_hit: 0, n_miss: nTrials, mean: null, stdev: 0, hit_rate: 0 };
  }
  return {
    n_hit: hit.length,
    n_miss: nTrials - hit.length,
    mean: mean(hit),
    stdev: stdev(hit),
    hit_rate: hit.length / nTrials,
  };
}

function entropy(vals) {
  const s = vals.reduce((a, b) => a + Math.max(b, 0), 0);
  if (s <= 0) return 0;
  let h = 0;
  for (const v of vals) {
    if (v <= 0) continue;
    const p = v / s;
    h -= p * Math.log2(p);
  }
  return h;
}

module.exports = { mean, stdev, summarize, entropy };
