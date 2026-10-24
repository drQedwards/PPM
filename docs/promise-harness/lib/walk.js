const { mulberry32, choice } = require("./rng");
const { FEATURE_KEYS } = require("./graph");

function richWeight(s, d, W, edgeFeat) {
  const f = edgeFeat.get(s + "\0" + d) || Object.fromEntries(FEATURE_KEYS.map((k) => [k, 0]));
  let score = 1e-6;
  score += W.same_sec * Math.log1p(f.same_sec);
  score += W.out_share * f.out_share;
  score += W.repeat * Math.log1p(f.repeat);
  score += W.delegation * f.delegation;
  score += W.near_zero * f.near_zero;
  return score;
}

/**
 * @returns {{steps: number|null, visited: string[], walkSteps: number}}
 * walkSteps counts every hop including teleports (for overhead accounting).
 */
function randomWalk(adj, edgeFeat, start, target, weighted, W, maxSteps, seed) {
  const rng = mulberry32(seed >>> 0);
  if (start === target) return { steps: 0, visited: [start], walkSteps: 0 };
  let u = start;
  const seen = new Set([u]);
  const visited = [u];
  let walkSteps = 0;
  for (let step = 1; step <= maxSteps; step++) {
    const outs = adj.get(u) || [];
    if (!outs.length) {
      u = start;
      walkSteps++;
      continue;
    }
    let v;
    if (weighted) {
      const ws = [];
      let total = 0;
      for (const e of outs) {
        let w = richWeight(u, e.dst, W, edgeFeat);
        if (seen.has(e.dst)) w *= 0.15;
        ws.push(w);
        total += w;
      }
      let r = rng() * total;
      let acc = 0;
      v = outs[outs.length - 1].dst;
      for (let i = 0; i < outs.length; i++) {
        acc += ws[i];
        if (acc >= r) {
          v = outs[i].dst;
          break;
        }
      }
    } else {
      v = choice(rng, outs).dst;
    }
    visited.push(v);
    walkSteps++;
    if (v === target) return { steps: step, visited, walkSteps };
    seen.add(v);
    u = v;
  }
  return { steps: null, visited, walkSteps };
}

function updateWeightsFromErrorMatrix(W, errorMatrix, eta, featureKeys) {
  const W2 = { ...W };
  const total = Object.values(errorMatrix).reduce((a, b) => a + b, 0) || 1;
  for (const k of featureKeys) {
    const missFrac = (errorMatrix[k] || 0) / total;
    W2[k] = Math.max(0.05, W2[k] * Math.exp(-eta * missFrac * 5.0));
  }
  return W2;
}

function isFlatErrorMatrix(errorMatrix, nKeys, entropyTol = 0.15, featureFlatCv = 0.25) {
  const vals = Object.values(errorMatrix);
  const s = vals.reduce((a, b) => a + Math.max(b, 0), 0);
  let H = 0;
  if (s > 0) {
    for (const v of vals) {
      if (v <= 0) continue;
      const p = v / s;
      H -= p * Math.log2(p);
    }
  }
  const Hmax = nKeys > 1 ? Math.log2(nKeys) : 0;
  const mean = vals.length ? s / vals.length : 0;
  let sd = 0;
  if (vals.length > 1 && mean > 0) {
    const varr = vals.reduce((a, b) => a + (b - mean) * (b - mean), 0) / vals.length;
    sd = Math.sqrt(varr);
  }
  const cv = mean > 1e-12 ? sd / mean : 0;
  const nearUniform = Hmax - H <= entropyTol;
  const lowCv = cv < featureFlatCv;
  return {
    flat: nearUniform || lowCv,
    entropy: H,
    entropy_max: Hmax,
    cv,
    near_uniform_entropy: nearUniform,
    low_cv: lowCv,
  };
}

module.exports = {
  richWeight,
  randomWalk,
  updateWeightsFromErrorMatrix,
  isFlatErrorMatrix,
};
