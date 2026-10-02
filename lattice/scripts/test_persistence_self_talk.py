"""Offline tests: frame logging, claims_final.json, and opt-in warm start.
No network, no ARC_API_KEY, no scorecard. Run: python3 test_persistence_self_talk.py"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from claim_memory import ClaimMemory  # noqa: E402

SCRIPT = HERE / "persistence_self_talk.py"
STEP_KEYS = {"game", "level", "step", "claims_before", "chosen", "action", "outcome", "update"}


def run(out, *extra):
    env = {k: v for k, v in os.environ.items() if k != "ARC_API_KEY"}
    r = subprocess.run([sys.executable, str(SCRIPT), "--offline", "--budget", "150", "--out", str(out), *extra],
                       capture_output=True, text=True, env=env, timeout=300)
    assert r.returncode == 0, r.stderr
    return r.stdout


class ClaimMemoryTest(unittest.TestCase):
    def test_iter_len_peek_delta(self):
        m = ClaimMemory()
        snap = m.snapshot()
        m.observe("goal:click:c9", "goal", "levels rise after click:c9", True)
        m.observe("effect:key:A1", "effect", "A1 changes", False)
        self.assertEqual(len(m), 2)
        self.assertEqual(len(list(m)), 2)
        self.assertEqual(len(m.peek(index=len(m))), 2)
        self.assertEqual(m.peek(key="goal:click:c9").s, 1)
        d = m.delta(snap)
        self.assertEqual({r[0] for r in d["new"]}, {"goal:click:c9", "effect:key:A1"})
        snap = m.snapshot()
        m.observe("goal:click:c9", "goal", "", True)
        m.observe("effect:key:A1", "effect", "", False)
        d = m.delta(snap)
        self.assertEqual([r[0] for r in d["confirmed"]], ["goal:click:c9"])
        self.assertEqual([r[0] for r in d["refuted"]], ["effect:key:A1"])

    def test_priors_are_capped(self):
        m = ClaimMemory()
        n = m.load_priors([{"key": "goal:click:c9", "kind": "goal", "support": 2, "contra": 44}], weight=3)
        cl = m.peek(key="goal:click:c9")
        self.assertEqual(n, 1)
        self.assertTrue(cl.prior)
        self.assertGreaterEqual(cl.s, 1)
        self.assertLessEqual(cl.s + cl.c, 4)


class OfflineRunTest(unittest.TestCase):
    def test_cold_then_warm(self):
        with tempfile.TemporaryDirectory() as td:
            cold, warm = Path(td) / "cold", Path(td) / "warm"
            out = run(cold)
            self.assertIn("mode cold", out)
            frames = [json.loads(l) for l in (cold / "frames.jsonl").read_text().splitlines()]
            steps = [f for f in frames if f.get("event") == "step"]
            self.assertTrue(steps)
            for f in steps:
                self.assertTrue(STEP_KEYS <= set(f), f)
                self.assertIn("diff", f["outcome"])
                self.assertNotIn("frame", f["outcome"])  # no raw pixels
            self.assertTrue(any(f["outcome"]["level_up"] for f in steps))
            cf = json.loads((cold / "claims_final.json").read_text())
            self.assertEqual(cf["meta"]["mode"], "cold")
            leveled = [t for t, g in cf["games"].items() if g["level_ups"]]
            self.assertTrue(leveled)  # TOY2 (click) levels up; TOY1 (navigation) may not
            for t in leveled:
                self.assertTrue(any(c["kind"] == "goal" for c in cf["games"][t]["confirmed"]))

            out = run(warm, "--warm-start", str(cold / "claims_final.json"))
            self.assertIn("NOT a cold run", out)
            self.assertIn("mode warm-start", out)
            wf = json.loads((warm / "claims_final.json").read_text())
            self.assertEqual(wf["meta"]["mode"], "warm-start")
            self.assertTrue(wf["meta"]["warm_start_sha256"])
            for t in leveled:
                g = wf["games"][t]
                self.assertTrue(g["level_ups"], t)
                first_cold = cf["games"][t]["level_ups"][0]["step"]
                first_warm = g["level_ups"][0]["step"]
                self.assertLessEqual(first_warm, first_cold, t)
            res = json.loads((warm / "results.json").read_text())
            self.assertTrue(all(r["warm_start_priors"] > 0 for r in res))


if __name__ == "__main__":
    unittest.main(verbosity=2)
