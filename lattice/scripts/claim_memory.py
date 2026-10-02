"""Claim memory: the iterable self-talk primitive behind persistence_self_talk.py.

A claim is a small falsifiable hypothesis ("click:c9 raises levels_completed")
with Beta(1,1) support/contra counts. The memory is iterable (`__iter__`),
sized (`__len__`) and readable with a PMLL-style `peek`, so a step can run

    for claim in memory.peek(index=len(memory)):   # peek(self, len(self))
        recall(claim)

Extras for frame logging and warm starts:
  * `snapshot()` / `delta(before)` report which claims were confirmed,
    refuted or newly created by one step.
  * `confirmed()` lists claims the evidence backs.
  * `load_priors(rows, weight)` seeds the memory from a prior
    claims_final.json. A warm-started memory is NOT a cold run.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple

VALUE = {"effect": 1.0, "move": 1.5, "goal": 3.0, "lethal": 2.0, "static": 0.3}


class Claim:
    __slots__ = ("key", "kind", "text", "s", "c", "value", "data", "prior")

    def __init__(self, key: str, kind: str, text: str, value: float, data: Optional[dict] = None) -> None:
        self.key, self.kind, self.text, self.value = key, kind, text, value
        self.s = 0
        self.c = 0
        self.data = data or {}
        self.prior = False  # True when seeded by --warm-start

    @property
    def conf(self) -> float:
        return (self.s + 1.0) / (self.s + self.c + 2.0)

    @property
    def unc(self) -> float:
        return 1.0 / (1.0 + self.s + self.c)

    def line(self) -> str:
        return "CLAIM {0} | {1} s={2} c={3} conf={4:.2f}".format(self.kind, self.text, self.s, self.c, self.conf)

    def compact(self) -> list:
        return [self.key, self.s, self.c, round(self.conf, 3)]

    def is_confirmed(self) -> bool:
        if self.kind == "goal":
            return self.s >= 1  # it produced at least one level-up
        if self.kind == "lethal":
            return self.s >= 2 and self.conf >= 0.5  # >=2 independent (non-periodic) game-overs
        if self.kind == "static":
            return self.s >= 8 and self.conf >= 0.9
        return self.s >= 2 and self.conf >= 0.6

    def to_json(self) -> dict:
        row = {"key": self.key, "kind": self.kind, "text": self.text, "support": self.s,
               "contra": self.c, "conf": round(self.conf, 4), "value": self.value, "data": self.data}
        if self.prior:
            row["prior"] = True
        return row


class ClaimMemory:
    """Iterable claim store. peek mirrors PMLL.c peek(silo, key, index, ...):
    a key does an exact lookup, an index in range returns that slot, and
    index -1 or len(self) returns the whole current state (latest snapshot)."""

    VALUE = VALUE

    def __init__(self) -> None:
        self.slots: Dict[str, Claim] = {}

    def __len__(self) -> int:
        return len(self.slots)

    def __iter__(self) -> Iterator[Claim]:
        # priority: value of knowing it x how unsure we still are, confirmed goals first
        return iter(sorted(self.slots.values(),
                           key=lambda c: -(c.value * (c.unc + (1.0 if c.kind == "goal" and c.s else 0.0)))))

    def peek(self, key: Optional[str] = None, index: int = -1):
        if key is not None:
            return self.slots.get(key)
        if index == -1 or index == len(self):
            return list(self)
        ordered = list(self)
        return ordered[index] if 0 <= index < len(ordered) else None

    def get(self, key: str, kind: str, text: str, data: Optional[dict] = None) -> Claim:
        cl = self.slots.get(key)
        if cl is None:
            cl = Claim(key, kind, text, self.VALUE.get(kind, 1.0), data)
            self.slots[key] = cl
        return cl

    def observe(self, key: str, kind: str, text: str, ok: bool, data: Optional[dict] = None) -> Claim:
        cl = self.get(key, kind, text, data)
        if ok:
            cl.s += 1
        else:
            cl.c += 1
        return cl

    # recall: the memory reads itself back into a working belief
    def self_talk(self, log, step: int, top: int = 6) -> Dict[str, Any]:
        belief: Dict[str, Any] = {"effect": {}, "move": {}, "goal": {}, "lethal": {}, "static": {}}
        spoken = 0
        for claim in self.peek(index=len(self)):
            belief.setdefault(claim.kind, {})[claim.key] = claim
            if spoken < top:
                log("step={0} {1}".format(step, claim.line()))
                spoken += 1
        return belief

    # ---- frame logging helpers
    def snapshot(self) -> Dict[str, Tuple[int, int]]:
        return {k: (cl.s, cl.c) for k, cl in self.slots.items()}

    def delta(self, before: Dict[str, Tuple[int, int]]) -> Dict[str, List[list]]:
        """Claims confirmed (+support), refuted (+contra) or new since `before`."""
        out: Dict[str, List[list]] = {"confirmed": [], "refuted": [], "new": []}
        for k, cl in self.slots.items():
            s0, c0 = before.get(k, (None, None))
            if s0 is None:
                out["new"].append([k, cl.s, cl.c])
                continue
            if cl.s > s0:
                out["confirmed"].append([k, cl.s, cl.c])
            if cl.c > c0:
                out["refuted"].append([k, cl.s, cl.c])
        return out

    def compact(self, top: int = 8) -> List[list]:
        return [cl.compact() for cl in list(self)[:top]]

    def confirmed(self, include_static: bool = False) -> List[Claim]:
        return [cl for cl in self if cl.is_confirmed() and (include_static or cl.kind != "static")]

    # ---- persistence
    def dump(self, path: Path, game: str, tag: str) -> None:
        with path.open("a") as fh:
            for cl in self.slots.values():
                row = cl.to_json()
                row.update({"game": game, "at": tag})
                fh.write(json.dumps(row, separators=(",", ":")) + "\n")

    def load_priors(self, rows: Iterable[dict], weight: int = 3) -> int:
        """Seed claims from a prior run. Counts are capped at `weight` (keeping
        the support/contra ratio) so fresh evidence can overturn a prior."""
        n = 0
        for r in rows:
            s, c = int(r.get("support", 0)), int(r.get("contra", 0))
            tot = s + c
            if tot <= 0:
                continue
            scale = min(1.0, float(weight) / tot)
            cl = self.get(r["key"], r["kind"], r.get("text", r["key"]), dict(r.get("data") or {}))
            cl.s = max(1 if s else 0, int(round(s * scale)))
            cl.c = int(round(c * scale))
            cl.prior = True
            n += 1
        return n
