"""Replay a finished run's frames.jsonl through the v2.2 GameOverTracker and
show how each GAME_OVER would be labeled (periodic vs attributed lethal)."""
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import persistence_self_talk as pst  # noqa: E402

path = sys.argv[1]
games = sys.argv[2].split(",") if len(sys.argv) > 2 else None
trk = {}
credit = defaultdict(lambda: defaultdict(int))   # game -> lethal key -> net support under v2.2
v21 = defaultdict(lambda: defaultdict(int))      # what v2.1 credited
rows = defaultdict(list)
for line in open(path):
    f = json.loads(line)
    g = f["game"]
    if games and g not in games:
        continue
    t = trk.setdefault(g, pst.GameOverTracker())
    if f["event"] == "reset":
        t.on_reset()
        continue
    o = f["outcome"]
    t.on_step(o["level_up"])
    if not o["game_over"]:
        continue
    key = "lethal:" + f["action"]["ekey"]
    v21[g][key] += 1
    periodic, retract = t.classify()
    for e in retract:
        for k in e["credited"]:
            credit[g][k] -= 1
        e["credited"] = []
    cred = [] if periodic else [key]
    for k in cred:
        credit[g][k] += 1
    ev = t.record(periodic, cred)
    rows[g].append([f["step"], t.since_reset, f["action"]["ekey"], ev])
for g in rows:
    print("==", g)
    for st, sr, ek, ev in rows[g]:
        label = "periodic (not lethal)" if ev["periodic"] else "ATTRIBUTED lethal"
        if ev["periodic"] and not ev["credited"] and st == rows[g][0][0]:
            label = "credited at the time, RETRACTED when the next game-over matched the interval"
        print("   step={0:3d} since_reset={1:3d} last={2:10s} -> {3}".format(st, sr, ek, label))
    print("   v2.1 lethal support:", dict(v21[g]))
    net = {k: v for k, v in credit[g].items() if v}
    print("   v2.2 lethal support:", net or "{}",
          "| penalizing (>= {0}):".format(pst.LETHAL_MIN_SUPPORT),
          [k for k, v in net.items() if v >= pst.LETHAL_MIN_SUPPORT] or "none")
