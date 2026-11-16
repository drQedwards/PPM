/**
 * Puzzle-key promise lineage with parent / lastImproved pointers.
 * Same contract as siphon harness; bins instead of feature weights.
 */
const Q = require("q");
const {
  S,
  N_BINS,
  ETA,
  loadPuzzleFracs,
  richWalkSteps,
  randomSteps,
  updateBinWeights,
  isFlatBins,
  densityPrior,
  mean,
} = require("./puzzle");
const { stdev } = require("./stats");

function cloneW(w) {
  return w.slice();
}

function genSnapshot(g) {
  return {
    id: g.id,
    parentId: g.parentPtr ? g.parentPtr.id : null,
    lastImprovedId: g.lastImprovedPtr ? g.lastImprovedPtr.id : null,
    meanSteps: g.meanSteps,
    stdevSteps: g.stdevSteps,
    meanRand: g.meanRand,
    ratioVsParent: g.ratioVsParent,
    ratioVsRand: g.ratioVsRand,
    status: g.status,
    flat: g.flat || false,
    flatStats: g.flatStats || null,
    entropy: g.entropy,
    walkSteps: g.walkSteps || 0,
    wallMs: g.wallMs || 0,
  };
}

function evaluatePuzzle(train, test, weights, opts) {
  const { nTrials, nEpisodes, seedBase } = opts;
  let walkSteps = 0;
  const missBins = Array(N_BINS).fill(0);

  for (let ep = 0; ep < nEpisodes; ep++) {
    const x = train[ep % train.length];
    const target = Math.min(S - 1, Math.floor(x.frac * S));
    const targetBin = Math.min(N_BINS - 1, Math.floor((target * N_BINS) / S));
    const remaining = [];
    for (let b = 0; b < N_BINS; b++) remaining.push(b);
    // seeded walk of bins
    let seed = (seedBase + ep * 17 + 100) >>> 0;
    // reuse richWalkSteps logic for miss recording
    const { mulberry32 } = require("./rng");
    const rng = mulberry32(seed);
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
      walkSteps += 1;
      if (b === targetBin) break;
      missBins[b] += 1;
    }
  }

  const Wnext = updateBinWeights(weights, missBins, ETA);
  const flatStats = isFlatBins(missBins);

  const richMeans = [];
  const randMeans = [];
  const ratios = [];
  const allRich = [];
  for (const x of test) {
    const target = Math.min(S - 1, Math.floor(x.frac * S));
    const richS = [];
    const randS = [];
    for (let t = 0; t < nTrials; t++) {
      const sb = (seedBase + 9000 + x.id * 400 + t) >>> 0;
      const rs = richWalkSteps(target, Wnext, sb);
      const us = randomSteps(target, sb);
      richS.push(rs);
      randS.push(us);
      allRich.push(rs);
      walkSteps += 1; // one bin-order trial counted as 1 unit; key-equiv separately
    }
    const rm = mean(richS);
    const um = mean(randS);
    richMeans.push(rm);
    randMeans.push(um);
    if (um) ratios.push(rm / um);
  }

  // key-equivalent overhead: miss bins * (S/N_BINS)
  const binSize = S / N_BINS;
  const keyEquiv = missBins.reduce((a, b) => a + b, 0) * binSize;

  return {
    meanSteps: mean(richMeans),
    stdevSteps: stdev(allRich),
    meanRand: mean(randMeans),
    ratioVsRand: mean(ratios),
    ratioSpread: stdev(ratios),
    Wnext,
    missBins,
    flat: flatStats.flat,
    flatStats,
    entropy: flatStats.entropy,
    walkSteps,
    keyEquiv,
  };
}

function tryChild(parent, train, test, opts) {
  const t0 = Date.now();
  let childW;
  if (parent._pendingError && parent._pendingError.missBins) {
    childW = updateBinWeights(parent.W, parent._pendingError.missBins, ETA);
  } else {
    childW = cloneW(parent.W);
  }
  const ev = evaluatePuzzle(train, test, childW, opts);
  const wallMs = Date.now() - t0;
  const child = {
    id: parent.id + 1,
    parentPtr: parent,
    lastImprovedPtr: parent.lastImprovedPtr || parent,
    W: ev.Wnext,
    meanSteps: ev.meanSteps,
    stdevSteps: ev.stdevSteps,
    meanRand: ev.meanRand,
    ratioVsRand: ev.ratioVsRand,
    ratioSpread: ev.ratioSpread,
    flat: ev.flat,
    flatStats: ev.flatStats,
    entropy: ev.entropy,
    walkSteps: ev.walkSteps,
    keyEquiv: ev.keyEquiv,
    wallMs,
    missBins: ev.missBins,
    status: "pending",
  };
  const parentSteps = parent.meanSteps;
  const childSteps = child.meanSteps;
  const deltaSteps =
    parentSteps != null && childSteps != null ? childSteps - parentSteps : null;
  child.ratioVsParent =
    parentSteps && childSteps ? childSteps / parentSteps : null;
  const beats =
    parentSteps != null &&
    childSteps != null &&
    childSteps < parentSteps * 0.99;

  if (beats) {
    child.status = "resolved";
    const prevBest = parent.lastImprovedPtr || parent;
    if (prevBest.meanSteps == null || child.meanSteps < prevBest.meanSteps) {
      child.lastImprovedPtr = child;
    } else {
      child.lastImprovedPtr = prevBest;
    }
    return Q.resolve(child);
  }
  child.status = "rejected";
  return Q.reject({
    loser: genSnapshot(child),
    data: {
      meanRand: ev.meanRand,
      ratioVsRand: ev.ratioVsRand,
      ratioSpread: ev.ratioSpread,
    },
    deltaSteps,
    errorMatrix: null,
    missBins: ev.missBins,
    flat: ev.flat,
    flatStats: ev.flatStats,
    walkSteps: ev.walkSteps,
    keyEquiv: ev.keyEquiv,
    wallMs,
    child,
  });
}

function runPuzzleLineage(csvPath, opts) {
  const {
    mode = "flat_for_N",
    flatN = 2,
    maxGens = 8,
    nTrials = 200,
    nEpisodes = 60,
    seedBase = 42,
  } = opts;

  const fracs = loadPuzzleFracs(csvPath);
  const train = fracs.filter((x) => x.id >= 1 && x.id <= 59);
  const test = fracs.filter((x) => x.id >= 60 && x.id <= 70);
  const dens = densityPrior(train);
  const evalOpts = { nTrials, nEpisodes, seedBase };

  const tAll = Date.now();
  const t0 = Date.now();
  const ev0 = evaluatePuzzle(train, test, dens, evalOpts);
  const gen0 = {
    id: 0,
    parentPtr: null,
    lastImprovedPtr: null,
    W: dens,
    meanSteps: ev0.meanSteps,
    stdevSteps: ev0.stdevSteps,
    meanRand: ev0.meanRand,
    ratioVsRand: ev0.ratioVsRand,
    ratioSpread: ev0.ratioSpread,
    ratioVsParent: null,
    flat: ev0.flat,
    flatStats: ev0.flatStats,
    entropy: ev0.entropy,
    walkSteps: ev0.walkSteps,
    keyEquiv: ev0.keyEquiv,
    wallMs: Date.now() - t0,
    status: "resolved",
    missBins: ev0.missBins,
  };
  gen0.lastImprovedPtr = gen0;

  const history = [genSnapshot(gen0)];
  let current = gen0;
  let best = gen0;
  let consecutiveRejects = 0;
  let prunedAt = null;
  let jumpedAt = null;
  let totalWalkSteps = gen0.walkSteps;
  let totalKeyEquiv = gen0.keyEquiv;
  let totalWallMs = gen0.wallMs;

  const deferred = Q.defer();

  function step() {
    if (current.id >= maxGens - 1) {
      finish("max_gens");
      return;
    }
    tryChild(current, train, test, evalOpts).then(
      (child) => {
        consecutiveRejects = 0;
        totalWalkSteps += child.walkSteps;
        totalKeyEquiv += child.keyEquiv || 0;
        totalWallMs += child.wallMs;
        history.push(genSnapshot(child));
        current = child;
        if (child.meanSteps < best.meanSteps) best = child;
        setImmediate(step);
      },
      (err) => {
        consecutiveRejects++;
        const child = err.child;
        totalWalkSteps += err.walkSteps || 0;
        totalKeyEquiv += err.keyEquiv || 0;
        totalWallMs += err.wallMs || 0;
        history.push(genSnapshot(child));
        child.lastImprovedPtr = current.lastImprovedPtr || current;
        child._pendingError = err;

        if (mode === "early_break" && err.flat) {
          jumpedAt = child.id;
          const target = child.lastImprovedPtr || gen0;
          best = target.meanSteps <= best.meanSteps ? target : best;
          current = target;
          finish("early_break_flatline");
          return;
        }
        if (mode === "flat_for_N" && consecutiveRejects >= flatN) {
          prunedAt = child.id;
          const target = child.lastImprovedPtr || gen0;
          best = target.meanSteps <= best.meanSteps ? target : best;
          current = target;
          finish("flat_for_N");
          return;
        }
        current = child;
        setImmediate(step);
      }
    );
  }

  function finish(reason) {
    const ancestor = best;
    deferred.resolve({
      mode,
      flatN,
      maxGens,
      stopReason: reason,
      prunedAt,
      jumpedAt,
      generations: history,
      best: genSnapshot(best),
      finalAncestor: genSnapshot(ancestor),
      nGensRun: history.length,
      totalWalkSteps,
      totalKeyEquiv,
      totalWallMs,
      wallMsAll: Date.now() - tAll,
      train_n: train.length,
      test_ids: test.map((x) => x.id),
      S,
      n_bins: N_BINS,
      promiseLib: "q@1.5.1",
    });
  }

  setImmediate(step);
  return deferred.promise;
}

module.exports = { runPuzzleLineage, evaluatePuzzle, genSnapshot };
