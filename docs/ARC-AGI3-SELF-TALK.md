# ARC-AGI-3: the persistence in memory, v2 "self-talk" claim loop

`lattice/scripts/persistence_self_talk.py` is a no-LLM, no-seed ARC-AGI-3 agent.
Its memory is a set of small falsifiable **claims** drawn from frame diffs
(never raw frames), kept in an iterable claim memory
(`lattice/scripts/claim_memory.py`: `__iter__`, `__len__`, PMLL-style `peek`).
Every step the memory talks to itself:

```python
for claim in self.peek(index=len(self)):   # recall(peek(self, len(self)))
    recall(claim)
```

then it acts to test the most uncertain useful claim (or exploits a confirmed
goal claim) and updates claims from the observed outcome. One policy and one
equal budget (250 actions) for all 25 games.

## Results (competition mode, all 25 games, 183 levels)

| Run | Budget | Seeds | Score | Levels | Actions | Scorecard |
|---|---|---|---|---|---|---|
| **v2 self-talk (cold)** | 250 / game, all games | none | **0.2209** | **7 / 183** | 6315 | [9494fcf1-f20f-4fca-8348-ab5bf63fa543](https://arcprize.org/scorecards/9494fcf1-f20f-4fca-8348-ab5bf63fa543) |
| v1 cold, fairness baseline | 250 / game, all games | none | 0.0248 | 1 / 183 | | [c8cabd6c-f0c2-4e20-9f7d-c7d0c7c0dd30](https://arcprize.org/scorecards/c8cabd6c-f0c2-4e20-9f7d-c7d0c7c0dd30) |
| v1 cold, default budgets | v1 defaults (bigger budgets for LP85/R11L/VC33 by name) | none | 0.1905 | 1 / 183 | | [29ebc8ea-f5c0-43f8-ad66-3e94ed69f6ae](https://arcprize.org/scorecards/29ebc8ea-f5c0-43f8-ad66-3e94ed69f6ae) |
| v1.5 seeded | v1 defaults | **yes** (LP85, R11L, VC33; disclosed) | | 3 / 183 | | [cfeeae13-dce8-457e-be23-a57725eeac91](https://arcprize.org/scorecards/cfeeae13-dce8-457e-be23-a57725eeac91) |

The like-for-like comparison is v2 vs the v1 fairness baseline (same 250-action
budget for every game, no seeds): 0.0248 -> 0.2209, 1 -> 7 levels.

v2 level-ups, rebuilt from the run's logs (`step` is the agent's action count;
the scorecard's per-level count can be one higher because it also counts RESETs):

| Game | Levels | Level-up | Step | Action | Claim that fired |
|---|---|---|---|---|---|
| VC33 | 2 | 0->1 | 95 | ACTION6 (62,34) | `goal:click:c9` |
| VC33 | | 1->2 | 132 | ACTION6 (2,46), "exploit goal" | `goal:click:c9` (re-used) |
| LF52 | 1 | 0->1 | 59 | ACTION6 (44,43) | `goal:click:c2` |
| LP85 | 1 | 0->1 | 24 | ACTION6 (5,33) | `goal:click:c8` |
| M0R0 | 1 | 0->1 | 108 | ACTION4 | `goal:key:A4` |
| R11L | 1 | 0->1 | 80 | ACTION6 (40,24) | `goal:click:c15` |
| TN36 | 1 | 0->1 | 56 | ACTION6 (36,55) | `goal:click:c9` |

By tag: click 6/55 levels (score 0.673), keyboard_click 1/93, keyboard 0/29.

## v2.2 and the warm-start runs

| Run | Code | Mode | Score | Levels | Actions | Scorecard |
|---|---|---|---|---|---|---|
| v2 cold | 2.0-self-talk | cold | 0.2209 | 7 / 183 | 6315 | [9494fcf1-f20f-4fca-8348-ab5bf63fa543](https://arcprize.org/scorecards/9494fcf1-f20f-4fca-8348-ab5bf63fa543) |
| warm1 | 2.1-self-talk-frames | **warm-start** | 0.1279 | 4 / 183 | 6319 | [6687986c-b9b5-4adb-ab69-7c845f69c137](https://arcprize.org/scorecards/6687986c-b9b5-4adb-ab69-7c845f69c137) |
| warm2 | 2.2-self-talk-periodic | **warm-start** | 0.3500 | 4 / 183 | 6320 | [5cc98e8d-6716-4177-b547-7a2eca60f25e](https://arcprize.org/scorecards/5cc98e8d-6716-4177-b547-7a2eca60f25e) |

All three runs: competition mode, all 25 games, 250 actions per game, no seeds, no LLM.

**Disclosure: warm1 and warm2 are NOT cold runs.** Both were warm-started from the v2 cold
run's rebuilt claims (`docs/arc-agi3-self-talk-v2-claims_final.json`, sha256
`6d7460f02f057de42403e07879ebccbfaa1825049bf88bcb17ffea4a4edac228`) with `--prior-weight 3`.
They carry knowledge from earlier plays of the same games. warm1's scorecard is tagged
`warm-start` and has the sha256 in `opaque`. warm2's is tagged `warm-start` and
`warm-start-sha256:6d7460f0…ad228` (full hash), and also has it in `opaque`.
Compare them with each other, not with cold results.

Level-ups (agent step; the scorecard per-level count includes RESETs; baseline is the scorecard's reference action count):

| Game | cold v2 | warm1 (v2.1) | warm2 (v2.2) | warm2 baseline |
|---|---|---|---|---|
| LP85 | 1 (click c8, step 24) | 1 (step 15) | 1 (click c8, step 5) | 17 |
| VC33 | 2 (click c9, steps 95, 132) | 0 | 1 (click c9, step 9) | 7 |
| R11L | 1 (click c15, step 80) | 1 (step 248) | 1 (click c6, step 25) | 22 |
| TN36 | 1 (click c9, step 56) | 1 (step 192) | 1 (click c9, step 170) | 32 |
| LF52 | 1 (click c2, step 59) | 0 | 0 | |
| M0R0 | 1 (ACTION4, step 108) | 1 (step 122) | 0 | |

Why warm1 lost to cold: GAME_OVERs in VC33, R11L and TN36 come at a fixed action count since
reset (50, 60 and 61), which looks like a per-life action limit. v2.1 blamed each one on the
last click, so the priors marked the goal colours as lethal, and the lethal penalty outweighed
the down-weighted goal prior.

v2.2 changes (`VERSION = "2.2-self-talk-periodic"`):

1. **Periodic game-overs.** `GameOverTracker` counts actions since the last RESET and since the
   last level-up. A GAME_OVER at the same count as an earlier one is periodic: it is not
   credited as lethal, and the earlier matching event's lethal credit is retracted. A lethal
   claim penalizes only at support >= 2 (`LETHAL_MIN_SUPPORT`). Frames carry
   `outcome.game_over_info`. `replay_lethal_check.py` replays a `frames.jsonl` through the tracker.
   On warm1's frames, every VC33, R11L and TN36 game-over is periodic (the first is retracted)
   and no lethal claim penalizes.
2. **Prior policy** (`prepare_priors`). Lethal priors that name the same click or key as a goal
   that caused a level-up are dropped. Other lethal priors are capped at support 1. Goal claims
   that caused a level-up load as confirmed at full weight (`s = prior_weight, c = 0`).
3. **Exploration floor.** With probability 0.15, or whenever "use effect" is over 60% of the last
   20 choices, a "use effect" pick is swapped for the least-known, least-tried candidate
   (`reason: "explore novelty"`). Goal exploitation and navigation are never swapped.
4. **Tags.** Warm-start runs tag `warm-start-sha256:<sha256>` in addition to `opaque`.

warm2 scores higher than cold because the first levels it reaches cost few actions
(LP85 in 5 vs a baseline of 17, VC33 in 9 vs 7). It completes **fewer** levels (4 vs 7).

### Known gaps

* **No second levels.** In warm2 every game stalls after level 1. VC33's cold level 2 was not repeated.
* **LF52 and M0R0 were lost in warm2.** LF52 clicked the goal colour (c2) 87 times without a
  level-up, so its win depends on position or order rather than colour. M0R0 looks like a navigation
  game, so a key-level goal claim (ACTION4) does not carry over. Colour-level claims cannot express either.
* The rebuilt `docs/arc-agi3-self-talk-v2-claims_final.json` was built with the v2.1 "confirmed"
  rule (lethal at support >= 1). v2.2 needs support >= 2 and drops conflicting lethal priors when loading.

## Decision / reasoning frames (v2.1)

v2.1 (`VERSION = "2.1-self-talk-frames"`) writes one JSON line per step to
`<out>/frames.jsonl`, plus `reset` events. No raw pixels are stored.

```json
{"game":"TOY2","event":"step","level":0,"step":7,"n_claims":19,
 "claims_before":[["goal:click:c7",0,1,0.333], ...],          // top 8: [key, support, contra, conf]
 "chosen":{"claim":"effect:click:c8","unc":1.0,"conf":0.5,"reason":"test effect",
           "score":2.068,"runner_up":["ACTION6",{"x":7,"y":11},"use effect",-0.306],"n_candidates":7},
 "action":{"name":"ACTION6","extra":{"x":11,"y":2},"ekey":"click:c8","color":8},
 "outcome":{"state":"NOT_FINISHED","lv_before":0,"lv_after":1,"level_up":true,"game_over":false,"http400":false,
            "diff":{"changed_cells":0,"frame_changed":false,"colors_changed":[],"moves":{},
                    "fh":["ccbb4404a0dbf9a0","ccbb4404a0dbf9a0"],"n_comps":[7,7]}},
 "update":{"confirmed":[],"refuted":[],"new":[["effect:click:c8",0,1],["goal:click:c8",1,0]]},
 "notes":["LEVEL_UP 0->1 via click:c8"]}
```

* `chosen.reason` is one of `test effect`, `use effect`, `exploit goal`, `approach cN`, `fallback`.
* `outcome.diff`: changed cell count (-1 = shape change), colors involved, per-color centroid moves,
  short frame hashes before/after, component counts.
* `update`: claims that gained support (`confirmed`), gained contra (`refuted`), or were created (`new`),
  each as `[key, support, contra]`.

At the end of a run `<out>/claims_final.json` holds, per game: best level, the confirmed claims
(goal: caused >= 1 level-up; lethal: support >= 1 and conf >= 0.5; effect/move: support >= 2 and
conf >= 0.6; static claims omitted), the lethal claims, and every level-up with the action, the
claim that fired and the confirmed claims at that moment.

`docs/arc-agi3-self-talk-v2-claims_final.json` is that file rebuilt offline from the v2 run
(`lattice/scripts/rebuild_from_log.py`). The v2 run predates frame logging, so its per-step frames are
only partly recoverable from `claims.log`: action, reason, state, level and the top-6 recalled claims
are there; the diff summary, the full claim set, the full claim update, candidate scores, RESET events,
and the clicked color on most ACTION6 steps were never logged. Those fields are `null` in the rebuilt
frames (`recovered: true`), not guessed.

## Warm start: NOT a cold run

```bash
python3 lattice/scripts/persistence_self_talk.py --out out-warm --warm-start out/claims_final.json
```

`--warm-start PATH` is opt-in; the default is cold. It loads a prior `claims_final.json` and seeds each
game's claim memory with its confirmed claims, capped at `--prior-weight` (default 3) total
observations per claim so new evidence can overturn them.

**A warm-started run is not a cold run.** It carries knowledge from earlier plays of the same games, and
it must be disclosed whenever its score is reported. The script prints a warning, tags the scorecard
`warm-start` (cold runs are tagged `cold`), and records `mode`, `warm_start_sha256` and
`warm_start_prior_weight` in the scorecard's `opaque` field and in `claims_final.json` `meta`. Never put a
warm-start score in the same column as cold results.

## Testing without a scorecard

```bash
python3 lattice/scripts/test_persistence_self_talk.py            # unit + offline cold/warm runs
python3 lattice/scripts/persistence_self_talk.py --offline --out /tmp/dry
python3 lattice/scripts/replay_lethal_check.py out/frames.jsonl VC33,R11L,TN36   # v2.2 game-over replay
```

`--offline` swaps the API client for a small local toy environment: TOY1 (navigation), TOY2 (click),
and, since v2.2, TOY3 (click-only, decoys only, a GAME_OVER every 6 actions of a life). It needs no
network access and no `ARC_API_KEY`, and it never opens a scorecard. The toy runs are deterministic.
With the current script and the default 250-action budget:

* **Cold** (`--offline --out /tmp/cold`): TOY2 is won in 3 actions (level-ups at steps 1, 2, 3).
  TOY1 reaches level 2 (level-ups at steps 210 and 244) but is not won. In TOY3, 40 of 41
  game-overs are classed periodic, the first one's credit is retracted, and no lethal claim survives.
* **Warm** (`--warm-start /tmp/cold/claims_final.json`, default `--prior-weight 3`): TOY1 is won in
  100 actions (level-ups at steps 26, 62, 100). TOY2 and TOY3 are the same as cold.

`--prior-weight N` caps support + contra for every seeded claim at N; `--prior-weight 0` seeds no
priors. Figures quoted in earlier versions of this page (v2.1: cold TOY2 at steps 7/8/9, warm TOY1
level 1 at step 143; first v2.2 write-up: 24 of 25 TOY3 game-overs periodic, warm TOY1 at steps
100/124/144) were recorded with earlier commits and are not reproduced by the current script.
