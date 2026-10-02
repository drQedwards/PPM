#!/usr/bin/env python3
"""Rebuild claims_final.json (and partial per-step frames) from a finished
v2.0 run that predates frame logging: out/claims.log + out/claims/*.jsonl
(+ results.json / scorecard.json). Nothing is invented: fields the v2.0 run
never logged are null and listed under meta.not_recoverable."""
import ast
import json
import re
import sys
from pathlib import Path

_here = Path(__file__).resolve().parent
sys.path[:0] = [str(_here), str(_here.parent)]  # claim_memory.py beside this file or one level up
from claim_memory import Claim, VALUE  # noqa: E402

ACT = re.compile(r"^\[(\w+)\] step=(\d+) ACT (ACTION\d) (.*?) ?\((.+?)\) -> (\S+) lv=(\d+)$")
CLM = re.compile(r"^\[(\w+)\] step=(\d+) CLAIM (\w+) \| (.*) s=(\d+) c=(\d+) conf=([\d.]+)$")
NOTE = re.compile(r"^\[(\w+)\] (LEVEL_UP (\d+)->(\d+) via (\S+)|GAME_OVER via (\S+) touched=(.*))$")


def text_to_key(kind, text):
    m = re.match(r"levels_completed rises after player c\d+ touches c(\d+)$", text)
    if m:
        return "goal:touch:c" + m.group(1)
    m = re.match(r"GAME_OVER follows contact between c\d+ and c(\d+)$", text)
    if m:
        return "lethal:touch:c" + m.group(1)
    m = re.match(r"levels_completed rises after (\S+)$", text)
    if m:
        return "goal:" + m.group(1)
    m = re.match(r"GAME_OVER follows (\S+)$", text)
    if m:
        return "lethal:" + m.group(1)
    m = re.match(r"(\S+) changes the frame$", text)
    if m:
        return "effect:" + m.group(1)
    m = re.match(r"color (\d+) is static$", text)
    if m:
        return "static:c" + m.group(1)
    m = re.match(r"ACTION(\d) moves color (\d+) by", text)
    if m:
        return "move:A{0}:c{1}".format(m.group(1), m.group(2))
    return "{0}:?{1}".format(kind, text)


def claim_from_row(r):
    cl = Claim(r["key"], r["kind"], r["text"], VALUE.get(r["kind"], 1.0), r.get("data"))
    cl.s, cl.c = r["support"], r["contra"]
    return cl


def main(out):
    out = Path(out)
    results = {r["title"]: r for r in json.loads((out / "results.json").read_text())}
    sc = json.loads((out / "scorecard.json").read_text())
    envs = {e["id"]: e for e in sc.get("environments", [])}
    card = (out / "card_id.txt").read_text().strip()

    frames = []
    level_ups = {}
    game_overs = {}
    top6 = {}          # (game, step) -> list of [key, s, c, conf]
    last_lv = {}
    cur = None
    for line in (out / "claims.log").read_text().splitlines():
        m = ACT.match(line)
        if m:
            g, step, name, extra, why, state, lv = m.groups()
            step, lv = int(step), int(lv)
            extra = ast.literal_eval(extra) if extra.strip() else {}
            lv0 = last_lv.get(g, 0)
            ekey = "key:A" + name[-1] if name != "ACTION6" else None
            cur = {"game": g, "event": "step", "recovered": True, "level": lv0, "step": step,
                   "claims_before_top6": top6.get((g, step - 1), []),
                   "chosen": {"claim": None, "unc": None, "reason": why},
                   "action": {"name": name, "extra": extra, "ekey": ekey},
                   "outcome": {"state": state, "lv_before": lv0, "lv_after": lv, "level_up": lv > lv0,
                               "game_over": state == "GAME_OVER", "diff": None},
                   "update": None, "notes": []}
            frames.append(cur)
            last_lv[g] = lv
            continue
        m = NOTE.match(line)
        if m and cur is not None and cur["game"] == m.group(1):
            cur["notes"].append(m.group(2))
            via = m.group(5) or m.group(6)
            cur["action"]["ekey"] = via
            if m.group(5):
                level_ups.setdefault(m.group(1), []).append({
                    "from": int(m.group(3)), "to": int(m.group(4)), "step": cur["step"],
                    "action": cur["action"]["name"], "extra": cur["action"]["extra"], "ekey": via,
                    "reason": cur["chosen"]["reason"]})
            else:
                game_overs.setdefault(m.group(1), []).append({"step": cur["step"], "ekey": via,
                                                               "touched": ast.literal_eval(m.group(7))})
            continue
        m = CLM.match(line)
        if m:
            g, step, kind, text, s, c, conf = m.groups()
            top6.setdefault((g, int(step)), []).append([text_to_key(kind, text), int(s), int(c), float(conf)])

    # second pass: claim under test (when derivable), its uncertainty, visible claim deltas
    for f in frames:
        g, st = f["game"], f["step"]
        why, ekey = f["chosen"]["reason"], f["action"]["ekey"]
        ck = None
        if why.startswith("approach c"):
            ck = "goal:touch:" + why.split()[-1]
        elif ekey:
            ck = ("goal:" if why == "exploit goal" else "effect:") + ekey
        f["chosen"]["claim"] = ck
        before = {r[0]: r for r in f["claims_before_top6"]}
        if ck in before:
            s, c = before[ck][1], before[ck][2]
            f["chosen"]["unc"] = round(1.0 / (1 + s + c), 4)
        elif ck and not f["claims_before_top6"]:
            f["chosen"]["unc"] = None
        after = {r[0]: r for r in top6.get((g, st), [])}
        vis = {"confirmed": [], "refuted": [], "partial": True}
        for k in set(before) & set(after):
            if after[k][1] > before[k][1]:
                vis["confirmed"].append([k, after[k][1], after[k][2]])
            if after[k][2] > before[k][2]:
                vis["refuted"].append([k, after[k][1], after[k][2]])
        f["update"] = vis

    games = {}
    for p in sorted((out / "claims").glob("*.jsonl")):
        rows = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
        title = p.stem
        final = [claim_from_row(r) for r in rows if r["at"] == "final"]
        snaps = {}
        for r in rows:
            if r["at"].startswith("level_up:"):
                snaps.setdefault(int(r["at"].split(":")[1]), []).append(claim_from_row(r))
        res = results.get(title, {})
        env = envs.get(res.get("game_id"), {})
        run0 = (env.get("runs") or [{}])[0]
        lus = []
        for lu in level_ups.get(title, []):
            snap = snaps.get(lu["to"], [])
            gc = next((c for c in snap if c.key == "goal:" + lu["ekey"]), None)
            lu = dict(lu)
            lu["goal_claim"] = gc.to_json() if gc else None
            lu["confirmed_at_levelup"] = [c.to_json() for c in snap if c.is_confirmed() and c.kind != "static"]
            la = run0.get("level_actions") or []
            lu["scorecard_level_actions"] = la[lu["from"]] if lu["from"] < len(la) else None
            lu["scorecard_baseline_actions"] = (run0.get("level_baseline_actions") or [None] * 99)[lu["from"]]
            lus.append(lu)
        conf = [c for c in final if c.is_confirmed() and c.kind != "static"]
        conf.sort(key=lambda c: (-VALUE.get(c.kind, 1), -c.s))
        games[title] = {"game_id": res.get("game_id"), "best_levels": res.get("best_levels"),
                        "actions": res.get("actions"), "state": res.get("state"),
                        "level_ups": lus, "confirmed": [c.to_json() for c in conf],
                        "lethal": [c.to_json() for c in conf if c.kind == "lethal"],
                        "game_overs_logged": len(game_overs.get(title, [])),
                        "n_claims_final": len(final)}
    meta = {"agent": "the persistence in memory", "version": "2.0-self-talk", "card_id": card,
            "scorecard": "https://arcprize.org/scorecards/" + card, "budget": 250, "mode": "cold",
            "score": sc.get("score"), "levels": sc.get("total_levels_completed"), "total_levels": sc.get("total_levels"),
            "total_actions": sc.get("total_actions"),
            "source": "rebuilt offline from out/claims.log + out/claims/*.jsonl + results.json + scorecard.json",
            "confirmed_rule": "goal: support>=1 (caused a level-up); lethal: support>=1 & conf>=0.5; "
                              "effect/move: support>=2 & conf>=0.6; static claims omitted",
            "frames_recovered": len(frames),
            "not_recoverable": ["per-step diff summary (changed cells, colors, moves)",
                                "full claim set before each step (only top-6 recalled claims were logged)",
                                "complete per-step claim update (only deltas of claims visible in two consecutive top-6 lists)",
                                "ACTION6 target color for steps without a LEVEL_UP/GAME_OVER note",
                                "chosen-claim uncertainty when that claim was not in the top-6",
                                "candidate scores / runner-up", "RESET events (not logged by v2.0)"]}
    (out / "claims_final.json").write_text(json.dumps({"meta": meta, "games": games}, indent=2))
    with (out / "frames_recovered.jsonl").open("w") as fh:
        for f in frames:
            fh.write(json.dumps(f, separators=(",", ":")) + "\n")
    print("frames", len(frames), "games", len(games), "level_ups", sum(len(v) for v in level_ups.values()))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "out")
