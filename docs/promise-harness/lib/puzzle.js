const fs = require("fs");
const { mulberry32, randint } = require("./rng");
const { mean, entropy } = require("./stats");

const S = 1 << 20;
const N_BINS = 64;
const ETA = 0.25;

function loadPuzzleFracs(csvPath) {
  const text = fs.readFileSync(csvPath, "utf8").trim().split("\n");
  const header = text[0].split(",");
  const idI = header.indexOf("id");
  const loI = header.indexOf("range_min");
  const hiI = header.indexOf("range_max");
  const pkI = header.indexOf("private_key");
  const out = [];
  for (let i = 1; i < text.length; i++) {
    const cols = text[i].split(",");
    if (!cols[pkI]) continue;
    const id = parseInt(cols[idI], 10);
    const lo = parseInt(cols[loI], 16);
    const hi = parseInt(cols[hiI], 16);
    if (hi <= lo) continue;
    const k = parseInt(cols[pkI], 16);
    out.push({ id, frac: (k - lo) / (hi - lo) });
  }
  return out;
}

function richWalkSteps(target, weights, seed) {
  const rng = mulberry32(seed >>> 0);
  const nBins = weights.length;
  const binSize = Math.floor(S / nBins);
  const targetBin = Math.min(nBins - 1, Math.floor((target * nBins) / S));
  const lo = targetBin * binSize;
  const hi = targetBin === nBins - 1 ? S : (targetBin + 1) * binSize;
  const binLen = hi - lo;
  const remaining = [];
  for (let b = 0; b < nBins; b++) remaining.push(b);
  let steps = 0;
  while (remaining.length) {
    let total = 0;
    for (const b of remaining) total += weights[b];
    let r = rng() * total;
    let acc = 0;
    let choiceI = 0;
    for (let i = 0; i < remaining.length; i++) {
      acc += weights[remaining[i]];
      if (acc >= r) {
        choiceI = i;
        break;
      }
    }
    const b = remaining.splice(choiceI, 1)[0];
    if (b !== targetBin) {
      const bl = b === nBins - 1 ? S - b * binSize : binSize;
      steps += bl;
    } else {
      steps += randint(rng, 1, binLen);
      return steps;
    }
  }
  return steps;
}

function randomSteps(target, seed) {
  const rng = mulberry32(seed >>> 0);
  return randint(rng, 1, S);
}

function updateBinWeights(weights, missBins, eta = ETA) {
  const w = weights.slice();
  const total = missBins.reduce((a, b) => a + b, 0) || 1;
  for (let b = 0; b < w.length; b++) {
    const missFrac = missBins[b] / total;
    w[b] = Math.max(1e-6, w[b] * Math.exp(-eta * missFrac * 3.0));
  }
  const s = w.reduce((a, b) => a + b, 0);
  return w.map((x) => x / s);
}

function isFlatBins(missBins, entropyTol = 0.15) {
  const H = entropy(missBins);
  const Hmax = Math.log2(missBins.length);
  const flat = Hmax - H <= entropyTol || missBins.every((v) => v === 0);
  return { flat, entropy: H, entropy_max: Hmax };
}

function densityPrior(train) {
  const dens = Array(N_BINS).fill(1.0);
  for (const x of train) {
    dens[Math.min(N_BINS - 1, Math.floor(x.frac * N_BINS))] += 1.0;
  }
  const s = dens.reduce((a, b) => a + b, 0);
  return dens.map((v) => v / s);
}

module.exports = {
  S,
  N_BINS,
  ETA,
  loadPuzzleFracs,
  richWalkSteps,
  randomSteps,
  updateBinWeights,
  isFlatBins,
  densityPrior,
  entropy,
  mean,
};
