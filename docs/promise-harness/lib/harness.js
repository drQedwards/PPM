/**
 * Promise-based ancestral walk harness (Dr. Q prune rule + error feedback).
 *
 * Each Generation keeps:
 *   parentPtr        — pointer to its parent generation
 *   lastImprovedPtr  — pointer to the last generation that beat its parent
 *
 * tryChild(parent) returns a Q promise that:
 *   resolves with the child if it measurably beats the parent on the same data
 *   rejects with {loser, data, deltaSteps, errorMatrix, ...} otherwise
 *
 * On rejection the error feeds the next child (multiplicative-weights update).
 * Modes:
 *   flat_for_N  — wait N consecutive non-improvements, then fall back
 *   early_break — on first flat error signal, jump via lastImprovedPtr immediately
 */
const Q = require("q");
const { FEATURE_KEYS, DEFAULT_W } = require("./graph");
const {
  randomWalk,
  updateWeightsFromErrorMatrix,
  isFlatErrorMatrix,
} = require("./walk");
const { summarize, mean, stdev } = require("./stats");

const ETA = 0.25;

function hashStr(s) {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

function cloneW(W) {
  return { ...W };
}

function genSnapshot(g) {
  return {
    id: g.id,
    parentId: g.parentPtr ? g.parentPtr.id : null,
    lastImprovedId: g.lastImprovedPtr ? g.lastImprovedPtr.id : null,
    W: cloneW(g.W),
    meanSteps: g.meanSteps,
    stdevSteps: g.stdevSteps,
    meanBool: g.meanBool,
    ratioVsParent: g.ratioVsParent,
    ratioVsBool: g.ratioVsBool,
    status: g.status,
    flat: g.flat || false,
    flatStats: g.flatStats || null,
    errorMatrix: g.errorMatrix || null,
    walkSteps: g.walkSteps || 0,
    wallMs: g.wallMs || 0,
  };
}

/**
 * Evaluate a weight vector W on all LOO folds. Returns aggregate stats + error matrix from train.
 */
function evaluateSiphon(g, pairs, W, opts) {
  const { nTrials, nEpisodes, maxSteps, seedBase } = opts;
  const collectors = [...new Set(pairs.map((p) => p.collector))].sort();
  const looRatios = [];
  const richMeans = [];
  const boolMeans = [];
  const allRich = [];
  const allBool = [];
  let walkSteps = 0;
  const errorMatrix = Object.fromEntries(FEATURE_KEYS.map((k) => [k, 0]));
  let missNodes = 0;
  const foldWs = [];

  for (const held of collectors) {
    const train = pairs.filter((p) => p.collector !== held);
    const test = pairs.filter((p) => p.collector === held);
    if (!train.length || !test.length) continue;

    // Train error matrix
    const localEM = Object.fromEntries(FEATURE_KEYS.map((k) => [k, 0]));
    for (const { seed, collector, path } of train) {
      for (let ep = 0; ep < nEpisodes; ep++) {
        const seedN =
          (seedBase +
            1000 * hashStr(held) +
            37 * hashStr(seed + "|" + collector) +
            ep * 17) >>>
          0;
        const r = randomWalk(
          g.adj,
          g.edgeFeat,
          seed,
          collector,
          true,
          W,
          maxSteps,
          seedN
        );
        walkSteps += r.walkSteps;
        for (const n of r.visited) {
          if (path.has(n)) continue;
          missNodes++;
          const nf = g.nodeFeat.get(n) || Object.fromEntries(FEATURE_KEYS.map((k) => [k, 0]));
          for (const k of FEATURE_KEYS) {
            localEM[k] += nf[k];
            errorMatrix[k] += nf[k];
          }
        }
      }
    }
    const Wfold = updateWeightsFromErrorMatrix(W, localEM, ETA, FEATURE_KEYS);
    foldWs.push(Wfold);

    for (const { seed, collector } of test) {
      const boolSteps = [];
      const richSteps = [];
      for (let i = 0; i < nTrials; i++) {
        const sb = (seedBase + 5000 + i * 31 + hashStr(collector)) >>> 0;
        const b = randomWalk(
          g.adj,
          g.edgeFeat,
          seed,
          collector,
          false,
          Wfold,
          maxSteps,
          sb
        );
        const r = randomWalk(
          g.adj,
          g.edgeFeat,
          seed,
          collector,
          true,
          Wfold,
          maxSteps,
          sb
        );
        boolSteps.push(b.steps);
        richSteps.push(r.steps);
        walkSteps += b.walkSteps + r.walkSteps;
      }
      const be = summarize(boolSteps, nTrials);
      const re = summarize(richSteps, nTrials);
      if (be.mean != null) {
        boolMeans.push(be.mean);
        allBool.push(...boolSteps.filter((x) => x != null));
      }
      if (re.mean != null) {
        richMeans.push(re.mean);
        allRich.push(...richSteps.filter((x) => x != null));
      }
      if (be.mean && re.mean) looRatios.push(re.mean / be.mean);
    }
  }

  const Wnext =
    foldWs.length > 0
      ? Object.fromEntries(
          FEATURE_KEYS.map((k) => [k, mean(foldWs.map((w) => w[k]))])
        )
      : cloneW(W);

  const flatStats = isFlatErrorMatrix(errorMatrix, FEATURE_KEYS.length);
  return {
    meanSteps: mean(richMeans),
    stdevSteps: stdev(allRich),
    meanBool: mean(boolMeans),
    ratioVsBool: mean(looRatios),
    ratioSpread: stdev(looRatios),
    Wnext,
    errorMatrix,
    missNodes,
    flat: flatStats.flat,
    flatStats,
    walkSteps,
    n_loo: looRatios.length,
  };
}

/**
 * tryChild: Promise that resolves iff child beats parent on mean steps (lower is better)
 * with a minimum relative margin, else rejects with the error object.
 */
function tryChild(parent, graph, pairs, opts) {
  const t0 = Date.now();
  // Child weights: if parent has a pending error, apply it; else start from parent.W
  let childW;
  if (parent._pendingError && parent._pendingError.errorMatrix) {
    childW = updateWeightsFromErrorMatrix(
      parent.W,
      parent._pendingError.errorMatrix,
      ETA,
      FEATURE_KEYS
    );
  } else {
    childW = cloneW(parent.W);
  }

  const ev = evaluateSiphon(graph, pairs, childW, opts);
  const wallMs = Date.now() - t0;

  const child = {
    id: parent.id + 1,
    parentPtr: parent,
    lastImprovedPtr: parent.lastImprovedPtr || parent, // inherit until proven
    W: ev.Wnext, // store the LOO-averaged next weights for lineage
    _evalW: childW, // weights actually used for this eval
    meanSteps: ev.meanSteps,
    stdevSteps: ev.stdevSteps,
    meanBool: ev.meanBool,
    ratioVsBool: ev.ratioVsBool,
    ratioSpread: ev.ratioSpread,
    errorMatrix: ev.errorMatrix,
    flat: ev.flat,
    flatStats: ev.flatStats,
    walkSteps: ev.walkSteps,
    wallMs,
    missNodes: ev.missNodes,
    status: "pending",
  };

  const parentSteps = parent.meanSteps;
  const childSteps = child.meanSteps;
  const deltaSteps =
    parentSteps != null && childSteps != null ? childSteps - parentSteps : null;
  // Beat = strictly fewer mean steps (margin 1% to avoid noise)
  const beats =
    parentSteps != null &&
    childSteps != null &&
    childSteps < parentSteps * 0.99;

  child.ratioVsParent =
    parentSteps && childSteps ? childSteps / parentSteps : null;

  if (beats) {
    child.status = "resolved";
    // Advance lastImproved only if this fulfilled child is the best ancestor so far
    const prevBest = parent.lastImprovedPtr || parent;
    if (prevBest.meanSteps == null || child.meanSteps < prevBest.meanSteps) {
      child.lastImprovedPtr = child;
    } else {
      child.lastImprovedPtr = prevBest;
    }
    return Q.resolve(child);
  }

  child.status = "rejected";
  const err = {
    loser: genSnapshot(child),
    data: {
      n_loo: ev.n_loo,
      meanBool: ev.meanBool,
      ratioVsBool: ev.ratioVsBool,
      ratioSpread: ev.ratioSpread,
    },
    deltaSteps,
    errorMatrix: ev.errorMatrix,
    flat: ev.flat,
    flatStats: ev.flatStats,
    walkSteps: ev.walkSteps,
    wallMs,
    child, // keep live pointer for lineage chaining
  };
  return Q.reject(err);
}

/**
 * Run ancestral line under a prune mode.
 * @param {'flat_for_N'|'early_break'} mode
 * @param {number} flatN — consecutive non-improvements before prune (flat_for_N only)
 */
function runLineage(graph, pairs, opts) {
  const {
    mode = "flat_for_N",
    flatN = 2,
    maxGens = 8,
    nTrials = 80,
    nEpisodes = 30,
    maxSteps = 3000,
    seedBase = 42,
  } = opts;

  const tAll = Date.now();
  const evalOpts = { nTrials, nEpisodes, maxSteps, seedBase };

  // Generation 0 = static rich walk (DEFAULT_W), evaluated once
  const t0 = Date.now();
  const ev0 = evaluateSiphon(graph, pairs, DEFAULT_W, evalOpts);
  const gen0 = {
    id: 0,
    parentPtr: null,
    lastImprovedPtr: null, // filled after self
    W: cloneW(DEFAULT_W),
    meanSteps: ev0.meanSteps,
    stdevSteps: ev0.stdevSteps,
    meanBool: ev0.meanBool,
    ratioVsBool: ev0.ratioVsBool,
    ratioSpread: ev0.ratioSpread,
    ratioVsParent: null,
    errorMatrix: ev0.errorMatrix,
    flat: ev0.flat,
    flatStats: ev0.flatStats,
    walkSteps: ev0.walkSteps,
    wallMs: Date.now() - t0,
    status: "resolved", // baseline is the fulfilled ancestor
    missNodes: ev0.missNodes,
  };
  gen0.lastImprovedPtr = gen0;

  const history = [genSnapshot(gen0)];
  let current = gen0;
  let best = gen0;
  let consecutiveRejects = 0;
  let prunedAt = null;
  let jumpedAt = null;
  let totalWalkSteps = gen0.walkSteps;
  let totalWallMs = gen0.wallMs;

  const deferred = Q.defer();

  function step() {
    if (current.id >= maxGens - 1) {
      finish("max_gens");
      return;
    }

    tryChild(current, graph, pairs, evalOpts).then(
      (child) => {
        // Fulfilled: child beats parent
        consecutiveRejects = 0;
        totalWalkSteps += child.walkSteps;
        totalWallMs += child.wallMs;
        history.push(genSnapshot(child));
        current = child;
        if (child.meanSteps < best.meanSteps) best = child;
        // Continue lineage from the fulfilled child
        setImmediate(step);
      },
      (err) => {
        // Rejected: feed error into next attempt from current parent
        consecutiveRejects++;
        const child = err.child;
        totalWalkSteps += err.walkSteps || 0;
        totalWallMs += err.wallMs || 0;
        history.push(genSnapshot(child));

        // Attach pending error so the NEXT child of current learns from it
        // After reject we still advance current to the loser (ancestral line continues)
        // but lastImprovedPtr stays pointing at last win.
        child.lastImprovedPtr = current.lastImprovedPtr || current;
        child._pendingError = err;

        const flatNow = !!err.flat;

        if (mode === "early_break" && flatNow) {
          // Flatline IS the pointer: jump back to last-improving generation
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

        // Continue from rejected child (with error fed forward)
        current = child;
        setImmediate(step);
      }
    );
  }

  function finish(reason) {
    const ancestor = best; // best fulfilled ancestor (global)
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
      totalWallMs,
      wallMsAll: Date.now() - tAll,
      promiseLib: "q@1.5.1",
    });
  }

  setImmediate(step);
  return deferred.promise;
}

module.exports = {
  tryChild,
  runLineage,
  evaluateSiphon,
  genSnapshot,
  ETA,
  DEFAULT_W,
  FEATURE_KEYS,
};
