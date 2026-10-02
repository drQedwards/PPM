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
```

`--offline` swaps the API client for a small local toy environment (TOY1 navigation, TOY2 click).
It needs no network access and no `ARC_API_KEY`, and it never opens a scorecard. On the toy, cold v2.1
levels up TOY2 at steps 7/8/9 and never solves TOY1. Warm-started from that run, it levels up TOY2 at
steps 1/2/3 and reaches TOY1 level 1 at step 143.
