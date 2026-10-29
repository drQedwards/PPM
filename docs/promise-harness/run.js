#!/usr/bin/env node
/**
 * Run siphon + puzzle promise lineages under flat_for_N and early_break.
 * Compare loops / walk-steps / wall-time saved. Plain measured numbers only.
 */
const fs = require("fs");
const path = require("path");
const Q = require("q");
const { loadSiphon, reachablePairs } = require("./lib/graph");
const { runLineage, evaluateSiphon, DEFAULT_W } = require("./lib/harness");
const { runPuzzleLineage } = require("./lib/puzzle_harness");
const { randomWalk } = require("./lib/walk");
const { summarize, mean } = require("./lib/stats");

const ROOT = __dirname;
const OUT = path.join(ROOT, "out");
fs.mkdirSync(OUT, { recursive: true });

const SIPHON_OPTS = {
  maxGens: 8,
  flatN: 2,
  nTrials: 80,
  nEpisodes: 30,
  maxSteps: 3000,
  seedBase: 42,
};

const PUZZLE_OPTS = {
  maxGens: 8,
  flatN: 2,
  nTrials: 200,
  nEpisodes: 60,
  seedBase: 42,
};

function fmt(x, d = 4) {
  if (x == null || Number.isNaN(x)) return "—";
  return Number(x).toFixed(d);
}

function genTable(gens, vsBool = true) {
  const lines = [];
  if (vsBool) {
    lines.push(
      "| gen | status | parent | lastImproved | mean steps | stdev | vs parent | vs bool | flat |"
    );
    lines.push(
      "|----:|:-------|-------:|-------------:|-----------:|------:|----------:|--------:|:----:|"
    );
    for (const g of gens) {
      lines.push(
        `| ${g.id} | ${g.status} | ${g.parentId ?? "—"} | ${g.lastImprovedId ?? "—"} | ${fmt(g.meanSteps, 1)} | ${fmt(g.stdevSteps, 1)} | ${fmt(g.ratioVsParent)} | ${fmt(g.ratioVsBool)} | ${g.flat ? "Y" : "N"} |`
      );
    }
  } else {
    lines.push(
      "| gen | status | parent | lastImproved | mean steps | stdev | vs parent | vs rand | flat |"
    );
    lines.push(
      "|----:|:-------|-------:|-------------:|-----------:|------:|----------:|--------:|:----:|"
    );
    for (const g of gens) {
      lines.push(
        `| ${g.id} | ${g.status} | ${g.parentId ?? "—"} | ${g.lastImprovedId ?? "—"} | ${fmt(g.meanSteps, 0)} | ${fmt(g.stdevSteps, 0)} | ${fmt(g.ratioVsParent)} | ${fmt(g.ratioVsRand)} | ${g.flat ? "Y" : "N"} |`
      );
    }
  }
  return lines.join("\n");
}

function savings(flat, early) {
  return {
    loops_saved: flat.nGensRun - early.nGensRun,
    walk_steps_saved: flat.totalWalkSteps - early.totalWalkSteps,
    wall_ms_saved: flat.totalWallMs - early.totalWallMs,
    wall_ms_all_saved: flat.wallMsAll - early.wallMsAll,
    key_equiv_saved:
      (flat.totalKeyEquiv || 0) - (early.totalKeyEquiv || 0),
  };
}

async function main() {
  console.log("promiseLib: q@" + "1.5.1");
  console.log("loading siphon graph…");
  const graph = loadSiphon(path.join(ROOT, "graph.json"));
  const pairs = reachablePairs(graph);
  console.log(
    `graph nodes=${graph.nodes.size} edges=${graph.n_edges} pairs=${pairs.length}`
  );

  // Baseline Boolean mean (for reporting vs prior 0.60x / 0.50x)
  // Already embedded in each gen's ratioVsBool via LOO.

  console.log("\n=== SIPHON: flat_for_N ===");
  const siphonFlat = await runLineage(graph, pairs, {
    ...SIPHON_OPTS,
    mode: "flat_for_N",
  });
  console.log(
    `stop=${siphonFlat.stopReason} gens=${siphonFlat.nGensRun} bestSteps=${fmt(siphonFlat.best.meanSteps, 1)} bestVsBool=${fmt(siphonFlat.best.ratioVsBool)} wallMs=${siphonFlat.totalWallMs}`
  );

  console.log("\n=== SIPHON: early_break ===");
  const siphonEarly = await runLineage(graph, pairs, {
    ...SIPHON_OPTS,
    mode: "early_break",
  });
  console.log(
    `stop=${siphonEarly.stopReason} gens=${siphonEarly.nGensRun} bestSteps=${fmt(siphonEarly.best.meanSteps, 1)} bestVsBool=${fmt(siphonEarly.best.ratioVsBool)} wallMs=${siphonEarly.totalWallMs}`
  );

  const siphonSave = savings(siphonFlat, siphonEarly);
  console.log("siphon savings (early vs flat_for_N):", siphonSave);

  console.log("\n=== PUZZLE: flat_for_N ===");
  const puzzleFlat = await runPuzzleLineage(path.join(ROOT, "export.csv"), {
    ...PUZZLE_OPTS,
    mode: "flat_for_N",
  });
  console.log(
    `stop=${puzzleFlat.stopReason} gens=${puzzleFlat.nGensRun} bestSteps=${fmt(puzzleFlat.best.meanSteps, 0)} bestVsRand=${fmt(puzzleFlat.best.ratioVsRand)} wallMs=${puzzleFlat.totalWallMs}`
  );

  console.log("\n=== PUZZLE: early_break ===");
  const puzzleEarly = await runPuzzleLineage(path.join(ROOT, "export.csv"), {
    ...PUZZLE_OPTS,
    mode: "early_break",
  });
  console.log(
    `stop=${puzzleEarly.stopReason} gens=${puzzleEarly.nGensRun} bestSteps=${fmt(puzzleEarly.best.meanSteps, 0)} bestVsRand=${fmt(puzzleEarly.best.ratioVsRand)} wallMs=${puzzleEarly.totalWallMs}`
  );

  const puzzleSave = savings(puzzleFlat, puzzleEarly);
  console.log("puzzle savings (early vs flat_for_N):", puzzleSave);

  const results = {
    promiseLib: "q@1.5.1",
    prior_best_siphon_adapt: 0.5,
    prior_static_rich: 0.6,
    siphon: {
      opts: SIPHON_OPTS,
      graph: {
        nodes: graph.nodes.size,
        edges: graph.n_edges,
        pairs: pairs.length,
      },
      flat_for_N: siphonFlat,
      early_break: siphonEarly,
      savings_early_vs_flat_for_N: siphonSave,
    },
    puzzle: {
      opts: PUZZLE_OPTS,
      flat_for_N: puzzleFlat,
      early_break: puzzleEarly,
      savings_early_vs_flat_for_N: puzzleSave,
    },
  };

  fs.writeFileSync(path.join(OUT, "results.json"), JSON.stringify(results, null, 2));

  // RESULTS.md
  const beatPrior =
    siphonEarly.best.ratioVsBool != null &&
    siphonEarly.best.ratioVsBool < 0.5 - 0.01;
  const lines = [
    "# Promise harness — ancestral prune with error feedback",
    "",
    `Promise library: **q@1.5.1** (npm \`q\`).`,
    "",
    "Each generation keeps `parentPtr` and `lastImprovedPtr`.",
    "`tryChild(parent)` is a Q promise: resolves only if the child beats the parent",
    "on the same data (mean steps, 1% margin); else rejects with",
    "`{loser, data, deltaSteps, errorMatrix}` and that error feeds the next child.",
    "",
    "Two stop modes on the same data/seeds:",
    "- **flat_for_N** — wait N consecutive rejections, then fall back to `lastImprovedPtr`.",
    "- **early_break** — on first flat error signal, the flatline is itself the pointer: jump to `lastImprovedPtr` immediately.",
    "",
    "## Siphon graph",
    "",
    `- Graph: ${graph.nodes.size} nodes, ${graph.n_edges} edges, ${pairs.length} reachable pairs.`,
    `- trials/LOO=${SIPHON_OPTS.nTrials}, train episodes/collector=${SIPHON_OPTS.nEpisodes}, maxGens=${SIPHON_OPTS.maxGens}, flatN=${SIPHON_OPTS.flatN}.`,
    `- Prior static rich RW: 0.60× Boolean; prior adaptive-prune best: 0.50×.`,
    "",
    "### flat_for_N",
    "",
    `- stop=${siphonFlat.stopReason}, prunedAt=${siphonFlat.prunedAt}, nGens=${siphonFlat.nGensRun}`,
    `- best gen=${siphonFlat.best.id} meanSteps=${fmt(siphonFlat.best.meanSteps, 1)} ± ${fmt(siphonFlat.best.stdevSteps, 1)} vsBool=${fmt(siphonFlat.best.ratioVsBool)}`,
    `- totalWalkSteps=${siphonFlat.totalWalkSteps}, totalWallMs=${siphonFlat.totalWallMs}`,
    "",
    genTable(siphonFlat.generations, true),
    "",
    "### early_break",
    "",
    `- stop=${siphonEarly.stopReason}, jumpedAt=${siphonEarly.jumpedAt}, nGens=${siphonEarly.nGensRun}`,
    `- best gen=${siphonEarly.best.id} meanSteps=${fmt(siphonEarly.best.meanSteps, 1)} ± ${fmt(siphonEarly.best.stdevSteps, 1)} vsBool=${fmt(siphonEarly.best.ratioVsBool)}`,
    `- finalAncestor gen=${siphonEarly.finalAncestor.id} (best fulfilled ancestor)`,
    `- totalWalkSteps=${siphonEarly.totalWalkSteps}, totalWallMs=${siphonEarly.totalWallMs}`,
    "",
    genTable(siphonEarly.generations, true),
    "",
    "### Savings (early_break vs flat_for_N)",
    "",
    `| metric | flat_for_N | early_break | saved |`,
    `|-------:|-----------:|------------:|------:|`,
    `| generations run | ${siphonFlat.nGensRun} | ${siphonEarly.nGensRun} | ${siphonSave.loops_saved} |`,
    `| walk steps | ${siphonFlat.totalWalkSteps} | ${siphonEarly.totalWalkSteps} | ${siphonSave.walk_steps_saved} |`,
    `| wall ms (sum gen) | ${siphonFlat.totalWallMs} | ${siphonEarly.totalWallMs} | ${siphonSave.wall_ms_saved} |`,
    `| wall ms (all) | ${siphonFlat.wallMsAll} | ${siphonEarly.wallMsAll} | ${siphonSave.wall_ms_all_saved} |`,
    "",
    siphonSave.loops_saved < 0
      ? `Note: miss-feature error matrix never flatlined (flat=N every gen), so early_break ran to maxGens while flat_for_N stopped after ${SIPHON_OPTS.flatN} consecutive rejections. Early break **cost** ${-siphonSave.loops_saved} generations / ${-siphonSave.walk_steps_saved} walk steps / ${-siphonSave.wall_ms_saved} ms here.`
      : `Note: early_break flatline jump saved ${siphonSave.loops_saved} generations / ${siphonSave.walk_steps_saved} walk steps / ${siphonSave.wall_ms_saved} ms vs flat_for_N.`,
    "",
    `**vs prior 0.50×:** this harness best vsBool = ${fmt(siphonEarly.best.ratioVsBool)}` +
      (beatPrior
        ? ` — beats prior best.`
        : ` — does **not** beat prior adaptive-prune best 0.50×.`),
    "",
    "## Puzzle keys (#1–#59 train → #60–#70 eval, S=2^20, 64 bins)",
    "",
    `- trials/puzzle=${PUZZLE_OPTS.nTrials}, train episodes=${PUZZLE_OPTS.nEpisodes}.`,
    "",
    "### flat_for_N",
    "",
    `- stop=${puzzleFlat.stopReason}, prunedAt=${puzzleFlat.prunedAt}, nGens=${puzzleFlat.nGensRun}`,
    `- best gen=${puzzleFlat.best.id} meanSteps=${fmt(puzzleFlat.best.meanSteps, 0)} vsRand=${fmt(puzzleFlat.best.ratioVsRand)}`,
    `- totalWalkSteps=${puzzleFlat.totalWalkSteps}, keyEquiv=${puzzleFlat.totalKeyEquiv}, totalWallMs=${puzzleFlat.totalWallMs}`,
    "",
    genTable(puzzleFlat.generations, false),
    "",
    "### early_break",
    "",
    `- stop=${puzzleEarly.stopReason}, jumpedAt=${puzzleEarly.jumpedAt}, nGens=${puzzleEarly.nGensRun}`,
    `- best gen=${puzzleEarly.best.id} meanSteps=${fmt(puzzleEarly.best.meanSteps, 0)} vsRand=${fmt(puzzleEarly.best.ratioVsRand)}`,
    `- totalWalkSteps=${puzzleEarly.totalWalkSteps}, keyEquiv=${puzzleEarly.totalKeyEquiv}, totalWallMs=${puzzleEarly.totalWallMs}`,
    "",
    genTable(puzzleEarly.generations, false),
    "",
    "### Savings (early_break vs flat_for_N)",
    "",
    `| metric | flat_for_N | early_break | saved |`,
    `|-------:|-----------:|------------:|------:|`,
    `| generations run | ${puzzleFlat.nGensRun} | ${puzzleEarly.nGensRun} | ${puzzleSave.loops_saved} |`,
    `| walk steps | ${puzzleFlat.totalWalkSteps} | ${puzzleEarly.totalWalkSteps} | ${puzzleSave.walk_steps_saved} |`,
    `| key-equiv | ${puzzleFlat.totalKeyEquiv} | ${puzzleEarly.totalKeyEquiv} | ${puzzleSave.key_equiv_saved} |`,
    `| wall ms (sum gen) | ${puzzleFlat.totalWallMs} | ${puzzleEarly.totalWallMs} | ${puzzleSave.wall_ms_saved} |`,
    `| wall ms (all) | ${puzzleFlat.wallMsAll} | ${puzzleEarly.wallMsAll} | ${puzzleSave.wall_ms_all_saved} |`,
    "",
    "**Puzzle:** ratios near 1.0 — flat prior; early_break is expected to fire immediately after gen 0's child if the miss-bin signal is flat.",
    "",
    "## Method notes",
    "",
    "- Beat rule: child mean steps < parent mean steps × 0.99 (same seeds/pairs).",
    "- Rejection error feeds next child via multiplicative weights (η=0.25), same as learn_walk.py.",
    "- Flat error = near-uniform miss-feature entropy or low CV (siphon); near-uniform miss bins (puzzle).",
    "- keyhunt / Cowcraft untouched; this process runs at nice 19.",
    "",
    "## Files",
    "",
    "- `run.js` — entry",
    "- `lib/harness.js` — siphon Q lineage + pointers",
    "- `lib/puzzle_harness.js` — puzzle Q lineage + pointers",
    "- `out/results.json` — full measured dump",
    "",
  ];
  fs.writeFileSync(path.join(ROOT, "RESULTS.md"), lines.join("\n") + "\n");
  console.log("\nWrote RESULTS.md and out/results.json");
  console.log(
    "SIPHON best vsBool early=",
    fmt(siphonEarly.best.ratioVsBool),
    "prior 0.50; beats?",
    beatPrior
  );
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
