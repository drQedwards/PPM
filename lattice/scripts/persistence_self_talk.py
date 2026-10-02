#!/usr/bin/env python3
"""the persistence in memory, v2: self-talk claim memory for ARC-AGI-3.

The memory stores small hypotheses (claims) drawn from frame diffs, not raw
frames. Each step the memory iterates over itself, reads its whole state with
a PMLL-style peek (`for claim in self.peek(index=len(self)): recall(claim)`),
logs each recalled claim as a `CLAIM ...` line, picks the action that best
tests the most uncertain useful claim (or exploits a confirmed goal claim),
acts, and updates claims from the observed diff.

No LLM, no neural net, no per-game seeds, no hardcoded coordinates. One policy
and one equal action budget for every game. Sequential, paced, 429 backoff.
ARC_API_KEY is read from the environment only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


ROOT = "https://three.arcprize.org"
AGENT = "the persistence in memory"
VERSION = "2.2-self-talk-periodic"
SOURCE_URL = "https://github.com/drQedwards/pmll"
MIN_INTERVAL = 0.11
DIRS = (1, 2, 3, 4)
LETHAL_MIN_SUPPORT = 2      # a lethal claim penalizes only after >=2 independent (non-periodic) game-overs
EXPLORE_EPS = 0.15          # chance to swap a "use effect" pick for a novelty pick
USE_EFFECT_CAP = 0.6        # max share of "use effect" picks in the recent window
USE_WINDOW = 20

# ---------------------------------------------------------------- frames


def last_grid(frame: Any) -> Optional[List[List[int]]]:
    if not frame:
        return None
    g = frame
    if isinstance(frame, list) and frame and isinstance(frame[0], list) and frame[0] and isinstance(frame[0][0], list):
        g = frame[-1]
    if not g or not g[0]:
        return None
    return g


def frame_hash(g: Optional[List[List[int]]]) -> str:
    if not g:
        return "empty"
    return hashlib.sha256(json.dumps(g, separators=(",", ":")).encode()).hexdigest()[:16]


def components(g: List[List[int]], bg: int) -> List[Dict[str, Any]]:
    h, w = len(g), len(g[0])
    seen = [[False] * w for _ in range(h)]
    out: List[Dict[str, Any]] = []
    for y in range(h):
        for x in range(w):
            if seen[y][x] or int(g[y][x]) == bg:
                continue
            color = int(g[y][x])
            stack = [(x, y)]
            seen[y][x] = True
            cells = []
            while stack:
                cx, cy = stack.pop()
                cells.append((cx, cy))
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = cx + dx, cy + dy
                    if 0 <= nx < w and 0 <= ny < h and not seen[ny][nx] and int(g[ny][nx]) == color:
                        seen[ny][nx] = True
                        stack.append((nx, ny))
            sx = sum(c[0] for c in cells) / len(cells)
            sy = sum(c[1] for c in cells) / len(cells)
            # click point: the member cell closest to the centroid
            px, py = min(cells, key=lambda c: (c[0] - sx) ** 2 + (c[1] - sy) ** 2)
            out.append({"color": color, "n": len(cells), "cx": sx, "cy": sy, "px": px, "py": py, "cells": cells})
    return out


class View:
    """One decoded frame: grid, background, per-color stats, components."""

    def __init__(self, frame: Any) -> None:
        self.g = last_grid(frame)
        self.fh = frame_hash(self.g)
        self.colors: Dict[int, Dict[str, float]] = {}
        self.bg = 0
        self.comps: List[Dict[str, Any]] = []
        if not self.g:
            return
        cnt: Counter = Counter()
        sums: Dict[int, List[float]] = {}
        for y, row in enumerate(self.g):
            for x, v in enumerate(row):
                v = int(v)
                cnt[v] += 1
                s = sums.setdefault(v, [0.0, 0.0])
                s[0] += x
                s[1] += y
        self.bg = cnt.most_common(1)[0][0]
        for c, n in cnt.items():
            self.colors[c] = {"n": n, "cx": sums[c][0] / n, "cy": sums[c][1] / n}
        self.comps = components(self.g, self.bg)

    def at(self, x: int, y: int) -> int:
        return int(self.g[y][x]) if self.g else -1


def diff(a: View, b: View) -> Dict[str, Any]:
    out = {"changed": 0, "colors_changed": set(), "moves": {}}
    if not a.g or not b.g or len(a.g) != len(b.g) or len(a.g[0]) != len(b.g[0]):
        out["changed"] = -1
        return out
    for y in range(len(a.g)):
        ra, rb = a.g[y], b.g[y]
        for x in range(len(ra)):
            if ra[x] != rb[x]:
                out["changed"] += 1
                out["colors_changed"].add(int(ra[x]))
                out["colors_changed"].add(int(rb[x]))
    # a color "moved" if its cell count is (nearly) preserved and its centroid shifted
    for c, sa in a.colors.items():
        sb = b.colors.get(c)
        if not sb or c == a.bg or sa["n"] > 400:
            continue
        if abs(sb["n"] - sa["n"]) <= max(1, sa["n"] // 10):
            dx, dy = sb["cx"] - sa["cx"], sb["cy"] - sa["cy"]
            if abs(dx) >= 0.5 or abs(dy) >= 0.5:
                out["moves"][c] = (int(round(dx)), int(round(dy)))
    return out


def touching(v: View, color: int) -> List[int]:
    """Colors 4-adjacent to any cell of `color` (excluding bg and itself)."""
    if not v.g:
        return []
    h, w = len(v.g), len(v.g[0])
    hit = set()
    for y in range(h):
        row = v.g[y]
        for x in range(w):
            if int(row[x]) != color:
                continue
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if 0 <= nx < w and 0 <= ny < h:
                    k = int(v.g[ny][nx])
                    if k != color and k != v.bg:
                        hit.add(k)
    return sorted(hit)


# ---------------------------------------------------------------- claims
# Claim / ClaimMemory live in claim_memory.py (the self-talk primitive).
import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parent))
from claim_memory import Claim, ClaimMemory  # noqa: E402,F401  (Claim re-exported)


# ---------------------------------------------------------------- policy


def click_key(color: int) -> str:
    return "click:c{0}".format(color)


def candidates(v: View, avail: List[int]) -> List[Tuple[str, dict, str, Optional[int]]]:
    """(action, extra, effect-key, color) tuples."""
    out: List[Tuple[str, dict, str, Optional[int]]] = []
    for a in avail:
        if a in (1, 2, 3, 4, 5, 7):
            out.append(("ACTION{0}".format(a), {}, "key:A{0}".format(a), None))
    if 6 in avail and v.comps:
        comps = [c for c in v.comps if c["n"] <= 600]
        comps.sort(key=lambda c: c["n"])
        for c in comps[:48]:
            out.append(("ACTION6", {"x": int(c["px"]), "y": int(c["py"])}, click_key(c["color"]), c["color"]))
    return out


def player_model(belief: Dict[str, Any]) -> Tuple[Optional[int], Dict[int, Tuple[int, int]]]:
    """Most-supported moving color and its per-action displacement."""
    best: Dict[int, int] = Counter()
    for cl in belief["move"].values():
        if cl.conf >= 0.6:
            best[cl.data["color"]] += cl.s
    if not best:
        return None, {}
    p = max(best, key=lambda k: best[k])
    dirs = {}
    for cl in belief["move"].values():
        if cl.data["color"] == p and cl.conf >= 0.6:
            a = cl.data["action"]
            if a not in dirs or cl.s > dirs[a][1]:
                dirs[a] = (tuple(cl.data["d"]), cl.s)
    return p, {a: d for a, (d, _) in dirs.items()}


def choose(mem: ClaimMemory, belief: Dict[str, Any], v: View, avail: List[int],
           tried: Dict[Tuple[str, str], int], rng: random.Random,
           info: Optional[dict] = None, explore: bool = False) -> Tuple[str, dict, str, Optional[int], str]:
    """Pick an action. If `info` is a dict it is filled with the claim the
    action tests (key, uncertainty, conf, score, runner-up) for frame logging."""
    cands = candidates(v, avail)
    if not cands:
        a = avail[0] if avail else 1
        if info is not None:
            info.update({"claim": "effect:key:A{0}".format(a), "unc": 1.0, "conf": 0.5, "score": None})
        return "ACTION{0}".format(a), {}, "key:A{0}".format(a), None, "fallback"
    player, dirs = player_model(belief)
    nav_target: Optional[Tuple[float, float, int, float]] = None
    if player is not None and player in v.colors and dirs:
        px, py = v.colors[player]["cx"], v.colors[player]["cy"]
        best = None
        for c in v.comps:
            if c["color"] == player or c["n"] > 600:
                continue
            g = mem.peek(key="goal:touch:c{0}".format(c["color"]))
            l = mem.peek(key="lethal:touch:c{0}".format(c["color"]))
            st = mem.peek(key="static:c{0}".format(c["color"]))
            gain = 1.0 * (g.unc if g else 1.0) + (3.0 if g and g.s else 0.0)
            gain -= 2.5 * (l.conf if l and l.s >= LETHAL_MIN_SUPPORT else 0.0)
            gain -= 0.3 * (st.conf if st and st.s > 8 else 0.0)
            dist = abs(c["cx"] - px) + abs(c["cy"] - py)
            if dist < 1.5:
                continue
            sc = gain - 0.01 * dist
            if best is None or sc > best[3]:
                best = (c["cx"], c["cy"], c["color"], sc)
        nav_target = best

    scored = []
    for name, extra, ekey, color in cands:
        eff = mem.peek(key="effect:" + ekey)
        p_change = eff.conf if eff else 0.5
        u = eff.unc if eff else 1.0
        sc = 1.0 * u + 0.8 * p_change
        why = "test effect" if u > 0.5 else "use effect"
        if color is not None:
            g = mem.peek(key="goal:" + ekey)
            if g and g.s:
                sc += 3.0 * g.conf
                why = "exploit goal"
            else:
                sc += 1.2 * (g.unc if g else 1.0) * p_change
        else:
            g = mem.peek(key="goal:" + ekey)
            if g and g.s:
                sc += 1.5 * g.conf
        lth = mem.peek(key="lethal:" + ekey)
        if lth and lth.s >= LETHAL_MIN_SUPPORT:
            sc -= 2.0 * lth.conf
        if nav_target and name in ("ACTION1", "ACTION2", "ACTION3", "ACTION4"):
            a = int(name[-1])
            if a in dirs:
                dx, dy = dirs[a]
                px, py = v.colors[player]["cx"], v.colors[player]["cy"]
                before = abs(nav_target[0] - px) + abs(nav_target[1] - py)
                after = abs(nav_target[0] - px - dx) + abs(nav_target[1] - py - dy)
                if after < before:
                    sc += 1.0 + max(0.0, nav_target[3])
                    why = "approach c{0}".format(nav_target[2])
        k = (v.fh, name + json.dumps(extra, sort_keys=True))
        n_tried = tried.get(k, 0)
        sc -= 1.5 * n_tried
        sc += rng.random() * 0.25
        scored.append((sc, name, extra, ekey, color, why))
    scored.sort(key=lambda t: -t[0])
    best_sc, name, extra, ekey, color, why = scored[0]
    if explore and why == "use effect" and len(scored) > 1:
        # novelty floor: test the least-known, least-tried candidate instead of re-using a known effect
        nov = []
        for _, n2, e2, k2, c2, _w in scored:
            eff = mem.peek(key="effect:" + k2)
            lth = mem.peek(key="lethal:" + k2)
            if lth and lth.s >= LETHAL_MIN_SUPPORT:
                continue
            t2 = tried.get((v.fh, n2 + json.dumps(e2, sort_keys=True)), 0)
            nsc = (eff.unc if eff else 1.0) + 1.0 / (1.0 + t2) + rng.random() * 0.25
            nov.append((nsc, n2, e2, k2, c2))
        if nov:
            nov.sort(key=lambda t: -t[0])
            best_sc, name, extra, ekey, color = nov[0]
            why = "explore novelty"
    if info is not None:
        if why == "exploit goal":
            ck = "goal:" + ekey
        elif why.startswith("approach c"):
            ck = "goal:touch:" + why.split()[-1]
        else:
            ck = "effect:" + ekey
        cl = mem.peek(key=ck)
        info.update({"claim": ck, "unc": round(cl.unc, 4) if cl else 1.0,
                     "conf": round(cl.conf, 4) if cl else 0.5, "score": round(best_sc, 3),
                     "n_candidates": len(scored),
                     "runner_up": ([scored[1][1], scored[1][2], scored[1][5], round(scored[1][0], 3)]
                                   if len(scored) > 1 else None)})
    return name, extra, ekey, color, why


def update(mem: ClaimMemory, before: View, after: View, name: str, ekey: str, color: Optional[int],
           lv0: int, lv1: int, state: str, lethal_ok: bool = True,
           credited: Optional[List[str]] = None) -> List[str]:
    """`lethal_ok=False` means this GAME_OVER matched an action-limit pattern:
    it is not credited as lethal to the last action. Keys that do get lethal
    support are appended to `credited` so a later pattern match can retract them."""
    notes = []
    d = diff(before, after)
    changed = d["changed"] != 0
    mem.observe("effect:" + ekey, "effect", "{0} changes the frame".format(ekey), changed)
    level_up = lv1 > lv0
    if name in ("ACTION1", "ACTION2", "ACTION3", "ACTION4") and not level_up:
        a = int(name[-1])
        for c, dd in d["moves"].items():
            mem.observe("move:A{0}:c{1}".format(a, c), "move",
                        "ACTION{0} moves color {1} by {2}".format(a, c, dd), True,
                        {"action": a, "color": c, "d": list(dd)})
        for cl in list(mem.slots.values()):
            if cl.kind == "move" and cl.data.get("action") == a and cl.data["color"] not in d["moves"] \
                    and cl.data["color"] in before.colors and d["changed"] >= 0:
                cl.c += 1
    if before.g and after.g and not level_up and d["changed"] >= 0:
        for c in before.colors:
            if c == before.bg:
                continue
            if len(mem) < 4000 or ("static:c{0}".format(c) in mem.slots):
                mem.observe("static:c{0}".format(c), "static", "color {0} is static".format(c),
                            c not in d["colors_changed"])
    touched: List[int] = []
    player, _ = player_model({"move": {k: v for k, v in mem.slots.items() if v.kind == "move"}})
    if player is not None:
        touched = touching(after if not level_up else before, player)
    if color is not None:
        mem.observe("goal:" + ekey, "goal", "levels_completed rises after {0}".format(ekey), level_up)
    else:
        if level_up or mem.peek(key="goal:" + ekey):
            mem.observe("goal:" + ekey, "goal", "levels_completed rises after {0}".format(ekey), level_up)
    for k in touched:
        mem.observe("goal:touch:c{0}".format(k), "goal",
                    "levels_completed rises after player c{0} touches c{1}".format(player, k), level_up)
    over = state == "GAME_OVER"
    if over and not lethal_ok:
        notes.append("GAME_OVER periodic (action limit), not credited to {0}".format(ekey))
        return notes
    if over or mem.peek(key="lethal:" + ekey):
        mem.observe("lethal:" + ekey, "lethal", "GAME_OVER follows {0}".format(ekey), over)
        if over and credited is not None:
            credited.append("lethal:" + ekey)
    for k in touched:
        if over or mem.peek(key="lethal:touch:c{0}".format(k)):
            mem.observe("lethal:touch:c{0}".format(k), "lethal",
                        "GAME_OVER follows contact between c{0} and c{1}".format(player, k), over)
            if over and credited is not None:
                credited.append("lethal:touch:c{0}".format(k))
    if level_up:
        notes.append("LEVEL_UP {0}->{1} via {2}".format(lv0, lv1, ekey))
    if over:
        notes.append("GAME_OVER via {0} touched={1}".format(ekey, touched))
    return notes


# ---------------------------------------------------------------- API


class Client:
    def __init__(self, key: str) -> None:
        import requests  # lazy: offline dry runs and tests need no network stack
        self._rq = requests
        self.s = requests.Session()
        self.s.headers.update({"X-API-Key": key, "Accept": "application/json", "Content-Type": "application/json"})
        self.last = 0.0
        self.n429 = 0

    def req(self, method: str, path: str, body: Optional[dict] = None, timeout: int = 30) -> Tuple[int, Any]:
        backoff = 2.0
        for _ in range(10):
            wait = MIN_INTERVAL - (time.time() - self.last)
            if wait > 0:
                time.sleep(wait)
            self.last = time.time()
            try:
                if method == "GET":
                    r = self.s.get(ROOT + path, timeout=timeout)
                else:
                    r = self.s.post(ROOT + path, json=body or {}, timeout=timeout)
            except self._rq.RequestException:
                time.sleep(backoff)
                backoff = min(backoff * 2, 40)
                continue
            if r.status_code == 429:
                self.n429 += 1
                time.sleep(backoff)
                backoff = min(backoff * 2, 40)
                continue
            try:
                data = r.json() if r.content else {}
            except Exception:
                data = {"raw": r.text[:240]}
            return r.status_code, data
        return 429, {"error": "RATE_LIMIT_EXCEEDED"}

    def cmd(self, action: str, body: dict) -> dict:
        status, data = self.req("POST", "/api/cmd/{0}".format(action), body)
        if status == 400:
            data = dict(data or {})
            data["_http"] = 400
            return data
        if status != 200:
            raise RuntimeError("{0} {1} {2}".format(action, status, json.dumps(data)[:240]))
        return data


# ---------------------------------------------------------------- offline toy client


class OfflineClient:
    """Deterministic toy environment for dry runs and tests. It never touches
    the network and never opens a scorecard. TOY1: a player (color 3) moved by
    ACTION1-4 must reach a goal tile (color 9); a lava tile (color 2) is
    GAME_OVER. TOY2: click-only; clicking the 3-cell button (color 8) completes
    a level, the single-cell decoys do nothing. TOY3: click-only, ten one-cell
    decoys and an action limit: every 6th action of a life is GAME_OVER
    (periodic, so it must not be learned as lethal)."""

    GAMES = [{"game_id": "toy1-offline", "title": "TOY1", "tags": ["keyboard_click"]},
             {"game_id": "toy2-offline", "title": "TOY2", "tags": ["click"]},
             {"game_id": "toy3-offline", "title": "TOY3", "tags": ["click"]}]
    LIMIT = {"toy3": 6}  # TOY3: action limit -> GAME_OVER every 6 actions per life

    def __init__(self) -> None:
        self.n429 = 0
        self.st: Dict[str, dict] = {}

    def req(self, method: str, path: str, body: Optional[dict] = None, timeout: int = 30) -> Tuple[int, Any]:
        if path == "/api/games":
            return 200, [dict(g) for g in self.GAMES]
        if path.startswith("/api/scorecard"):
            return 200, {"card_id": "offline-dry-run", "score": None, "offline": True}
        return 404, {}

    def _new(self, gid: str, level: int = 0) -> dict:
        return {"gid": gid, "lv": level, "p": [2, 2 + level], "state": "NOT_FINISHED", "guid": "g-" + gid, "n": 0}

    def _frame(self, st: dict) -> List[List[List[int]]]:
        g = [[0] * 16 for _ in range(16)]
        if st["gid"].startswith("toy1"):
            g[12][12] = 9
            g[8][4] = 2
        elif st["gid"].startswith("toy2"):
            for x in range(10, 13):
                g[2][x] = 8
            for x, y, c in ((5, 5, 4), (7, 11, 6), (13, 13, 7), (1, 9, 1)):
                g[y][x] = c
        else:  # toy3: one-cell decoys only, 6-action limit per life (no way to level up)
            for x, y, c in ((5, 5, 4), (7, 11, 6), (13, 13, 7), (1, 9, 1), (3, 13, 10), (9, 7, 11),
                            (14, 5, 12), (6, 3, 13), (11, 10, 14), (4, 8, 15)):
                g[y][x] = c
        g[14][1] = 5
        px, py = st["p"]
        g[py][px] = 3
        return [g]

    def _resp(self, st: dict) -> dict:
        avail = [1, 2, 3, 4] if st["gid"].startswith("toy1") else [6]
        if st["gid"].startswith("toy3"):
            avail = [6]
        return {"guid": st["guid"], "frame": self._frame(st), "state": st["state"],
                "levels_completed": st["lv"], "available_actions": avail}

    def cmd(self, action: str, body: dict) -> dict:
        gid = body["game_id"]
        if action == "RESET":
            old = self.st.get(gid)
            self.st[gid] = self._new(gid, old["lv"] if old else 0)
            return self._resp(self.st[gid])
        st = self.st[gid]
        if action in ("ACTION1", "ACTION2", "ACTION3", "ACTION4") and gid.startswith("toy1"):
            dx, dy = {"ACTION1": (0, -1), "ACTION2": (0, 1), "ACTION3": (-1, 0), "ACTION4": (1, 0)}[action]
            st["p"] = [min(15, max(0, st["p"][0] + dx)), min(15, max(0, st["p"][1] + dy))]
            if tuple(st["p"]) == (12, 12):
                st["lv"] += 1
                st["p"] = [2, 2]
            elif tuple(st["p"]) == (4, 8):
                st["state"] = "GAME_OVER"
        elif action == "ACTION6" and gid[:4] in ("toy2", "toy3"):
            x, y = int(body.get("x", -1)), int(body.get("y", -1))
            st["n"] += 1
            if y == 2 and (10 <= x <= 12 if gid.startswith("toy2") else x == 10):
                st["lv"] += 1
                st["p"] = [2, 2]
                st["n"] = 0
            elif gid[:4] in self.LIMIT and st["n"] >= self.LIMIT[gid[:4]]:
                st["state"] = "GAME_OVER"
        if st["lv"] >= 3:
            st["state"] = "WIN"
        return self._resp(st)


# ---------------------------------------------------------------- frame log


def diff_summary(d: Dict[str, Any], a: View, b: View) -> Dict[str, Any]:
    return {"changed_cells": d["changed"], "frame_changed": d["changed"] != 0 or a.fh != b.fh,
            "colors_changed": sorted(d["colors_changed"]),
            "moves": {str(c): list(v) for c, v in d["moves"].items()},
            "fh": [a.fh, b.fh], "n_comps": [len(a.comps), len(b.comps)]}


class FrameLog:
    """Per-step decision/reasoning frames as JSONL (no raw pixels)."""

    def __init__(self, path: Optional[Path]) -> None:
        self.fh = path.open("a") if path else None

    def write(self, row: dict) -> None:
        if self.fh:
            self.fh.write(json.dumps(row, separators=(",", ":"), default=str) + "\n")

    def flush(self) -> None:
        if self.fh:
            self.fh.flush()

    def close(self) -> None:
        if self.fh:
            self.fh.close()


# ---------------------------------------------------------------- periodic game-over detection


class GameOverTracker:
    """Detects action-limit GAME_OVERs. Counts agent actions since the last
    RESET and since the last level-up. A GAME_OVER whose count matches an
    earlier GAME_OVER's count (either measure, within `tol`) is periodic: it is
    not credited as lethal, and the lethal support credited by the earlier
    matching event(s) is retracted."""

    def __init__(self, tol: int = 0) -> None:
        self.tol = tol
        self.since_reset = 0
        self.since_level = 0
        self.events: List[dict] = []   # {"r": int, "l": int, "credited": [...], "periodic": bool}
        self.periods: set = set()

    def on_reset(self) -> None:
        self.since_reset = 0
        self.since_level = 0

    def on_step(self, level_up: bool) -> None:
        self.since_reset += 1
        self.since_level += 1
        if level_up:
            self.since_level = 0

    def _match(self, a: int, b: int) -> bool:
        return abs(a - b) <= self.tol

    def classify(self) -> Tuple[bool, List[dict]]:
        """Call on a GAME_OVER (after on_step). Returns (periodic, earlier events to retract)."""
        r, lv = self.since_reset, self.since_level
        known = any(self._match(r, p) or self._match(lv, p) for p in self.periods)
        matches = [e for e in self.events if self._match(e["r"], r) or self._match(e["l"], lv)]
        periodic = known or bool(matches)
        if periodic:
            for e in matches:
                self.periods.add(e["r"] if self._match(e["r"], r) else e["l"])
                e["periodic"] = True
        retract = [e for e in matches if e["credited"]]
        return periodic, retract

    def record(self, periodic: bool, credited: List[str]) -> dict:
        ev = {"r": self.since_reset, "l": self.since_level, "credited": list(credited), "periodic": periodic}
        self.events.append(ev)
        return ev


def retract_lethal(mem: ClaimMemory, events: List[dict]) -> List[str]:
    out = []
    for e in events:
        for k in e["credited"]:
            cl = mem.peek(key=k)
            if cl and cl.s > 0:
                cl.s -= 1
                cl.data["retracted_periodic"] = cl.data.get("retracted_periodic", 0) + 1
                out.append(k)
        e["credited"] = []
    return out


# ---------------------------------------------------------------- game loop


def play_game(client: Any, game: dict, card_id: str, budget: int, out: Path, log,
              frames: Optional[FrameLog] = None, priors: Optional[dict] = None,
              prior_weight: int = 3) -> dict:
    gid = game["game_id"]
    title = game.get("title") or gid
    rng = random.Random(gid)
    mem = ClaimMemory()
    frames = frames or FrameLog(None)
    n_priors = 0
    prior_rep: Optional[dict] = None
    if priors:
        prow = priors.get(title) or priors.get(gid)
        if prow:
            rows, prior_report = prepare_priors(prow, prior_weight)
            n_priors = mem.load_priors(rows, prior_weight)
            for r in rows:  # level-up goal claims: confirmed prior at full weight
                if r.get("_levelup_goal"):
                    cl = mem.peek(key=r["key"])
                    cl.s, cl.c = max(prior_weight, 1), 0
            prior_rep = prior_report
    claims_path = out / "claims" / "{0}.jsonl".format(title)
    claims_path.write_text("")
    summary = {"game_id": gid, "title": title, "tags": game.get("tags"), "best_levels": 0,
               "state": "NOT_PLAYED", "actions": 0, "resets": 0, "claims": 0, "error": None,
               "warm_start_priors": n_priors, "prior_report": prior_rep, "level_ups": [], "game_overs": []}

    def say(msg: str) -> None:
        log("[{0}] {1}".format(title, msg))

    gotr = GameOverTracker()
    recent: List[str] = []
    summary["game_overs_periodic"] = 0
    try:
        data = client.cmd("RESET", {"game_id": gid, "card_id": card_id})
        summary["resets"] += 1
        gotr.on_reset()
        frames.write({"game": title, "event": "reset", "step": 0, "level": int(data.get("levels_completed") or 0),
                      "priors": n_priors})
        guid = data.get("guid")
        view = View(data.get("frame"))
        tried: Dict[Tuple[str, str], int] = {}
        idle = 0
        steps = 0
        while steps < budget:
            state = data.get("state")
            lv = int(data.get("levels_completed") or 0)
            summary["best_levels"] = max(summary["best_levels"], lv)
            if state:
                summary["state"] = state
            if state == "WIN":
                break
            if data.get("_http") == 400 or state in ("GAME_OVER",) or idle >= 40:
                why_reset = "http400" if data.get("_http") == 400 else ("game_over" if state == "GAME_OVER" else "idle40")
                data = client.cmd("RESET", {"game_id": gid, "card_id": card_id, "guid": guid})
                summary["resets"] += 1
                guid = data.get("guid") or guid
                view = View(data.get("frame"))
                idle = 0
                tried.clear()
                gotr.on_reset()
                frames.write({"game": title, "event": "reset", "step": steps, "reason": why_reset,
                              "level": int(data.get("levels_completed") or 0), "state": data.get("state")})
                if data.get("_http") == 400 or data.get("state") == "NOT_PLAYED":
                    say("reset refused: {0}".format(json.dumps(data)[:160]))
                    break
                continue
            avail = [int(a) for a in (data.get("available_actions") or [1, 2, 3, 4])]
            belief = mem.self_talk(say, steps)  # for claim in self: recall(peek(self, len(self)))
            before_compact = mem.compact(8)
            snap = mem.snapshot()
            info: Dict[str, Any] = {}
            use_share = (sum(1 for w in recent if w == "use effect") / len(recent)) if recent else 0.0
            explore = rng.random() < EXPLORE_EPS or (len(recent) >= USE_WINDOW // 2 and use_share > USE_EFFECT_CAP)
            name, extra, ekey, color, why = choose(mem, belief, view, avail, tried, rng, info, explore)
            recent.append(why)
            if len(recent) > USE_WINDOW:
                recent.pop(0)
            body = {"game_id": gid, "guid": guid}
            body.update(extra)
            nxt = client.cmd(name, body)
            guid = nxt.get("guid") or guid
            steps += 1
            summary["actions"] += 1
            nview = View(nxt.get("frame"))
            k = (view.fh, name + json.dumps(extra, sort_keys=True))
            tried[k] = tried.get(k, 0) + 1
            lv1 = int(nxt.get("levels_completed") or 0)
            gotr.on_step(lv1 > lv)
            go_info = None
            lethal_ok, credited, retracted = True, [], []
            if nxt.get("state") == "GAME_OVER":
                periodic, to_retract = gotr.classify()
                lethal_ok = not periodic
                retracted = retract_lethal(mem, to_retract)
                go_info = {"periodic": periodic, "since_reset": gotr.since_reset, "since_level": gotr.since_level,
                           "periods": sorted(gotr.periods), "retracted": retracted}
                if periodic:
                    summary["game_overs_periodic"] += 1
            notes = update(mem, view, nview, name, ekey, color, lv, lv1, nxt.get("state") or "",
                           lethal_ok=lethal_ok, credited=credited)
            if go_info is not None:
                gotr.record(go_info["periodic"], credited)
                go_info["credited"] = credited
                if retracted:
                    notes.append("RETRACT lethal {0} (periodic GAME_OVER every {1})".format(
                        retracted, sorted(gotr.periods)))
            dsum = diff_summary(diff(view, nview), view, nview)
            frames.write({
                "game": title, "event": "step", "level": lv, "step": steps,
                "n_claims": len(snap), "claims_before": before_compact,
                "chosen": {"claim": info.get("claim"), "unc": info.get("unc"), "conf": info.get("conf"),
                           "reason": why, "score": info.get("score"), "runner_up": info.get("runner_up"),
                           "n_candidates": info.get("n_candidates")},
                "action": {"name": name, "extra": extra, "ekey": ekey, "color": color},
                "outcome": {"state": nxt.get("state"), "lv_before": lv, "lv_after": lv1,
                            "level_up": lv1 > lv, "game_over": nxt.get("state") == "GAME_OVER",
                            "http400": nxt.get("_http") == 400, "diff": dsum, "game_over_info": go_info},
                "update": mem.delta(snap), "notes": notes,
            })
            say("step={0} ACT {1} {2} ({3}) -> {4} lv={5}".format(steps, name, extra or "", why, nxt.get("state"), lv1))
            for n in notes:
                say(n)
            if lv1 > lv:
                gc = mem.peek(key="goal:" + ekey)
                summary["level_ups"].append({
                    "from": lv, "to": lv1, "step": steps, "action": name, "extra": extra, "ekey": ekey,
                    "reason": why, "claim": info.get("claim"),
                    "goal_claim": gc.to_json() if gc else None,
                    "confirmed_at_levelup": [c.to_json() for c in mem.confirmed()][:24]})
                mem.dump(claims_path, title, "level_up:{0}".format(lv1))
                tried.clear()
                idle = 0
            elif nview.fh == view.fh:
                idle += 1
            else:
                idle = 0 if nview.fh not in {t[0] for t in tried} else idle + 1
            if nxt.get("state") == "GAME_OVER":
                summary["game_overs"].append({"step": steps, "ekey": ekey, "level": lv,
                                              "periodic": go_info["periodic"] if go_info else None,
                                              "since_reset": go_info["since_reset"] if go_info else None})
            data, view = nxt, nview
        summary["best_levels"] = max(summary["best_levels"], int(data.get("levels_completed") or 0))
        summary["state"] = data.get("state") or summary["state"]
    except Exception as e:
        summary["error"] = "{0}: {1}".format(type(e).__name__, e)[:240]
    mem.dump(claims_path, title, "final")
    frames.flush()
    summary["claims"] = len(mem)
    summary["confirmed"] = [c.to_json() for c in mem.confirmed()]
    print("[{0}] state={1} levels={2} acts={3} resets={4} claims={5} priors={6} err={7}".format(
        title, summary["state"], summary["best_levels"], summary["actions"], summary["resets"],
        summary["claims"], n_priors, summary["error"]), flush=True)
    return summary


def prepare_priors(prow: dict, weight: int) -> Tuple[List[dict], dict]:
    """v2.2 prior policy. Goal claims that caused a level-up are kept as
    confirmed priors at full weight. Lethal priors that name the same action/
    color as such a goal are dropped (they came from action-limit GAME_OVERs);
    other lethal priors are discounted to support<=1, below LETHAL_MIN_SUPPORT,
    so they cannot penalize until fresh evidence confirms them."""
    rows = [dict(r) for r in prow.get("confirmed", []) + prow.get("refuted_priors", [])]
    goal_ekeys = {lu.get("ekey") for lu in prow.get("level_ups", []) if lu.get("ekey")}
    goal_ekeys |= {r["key"][len("goal:"):] for r in rows if r["kind"] == "goal" and r.get("support", 0) >= 1}
    out, dropped, discounted, boosted = [], [], [], []
    for r in rows:
        if r["kind"] == "lethal":
            ek = r["key"][len("lethal:"):]
            if ek in goal_ekeys:
                dropped.append(r["key"])
                continue
            r["support"] = min(int(r.get("support", 0)), 1)
            discounted.append(r["key"])
        elif r["kind"] == "goal" and r["key"][len("goal:"):] in goal_ekeys:
            r["_levelup_goal"] = True
            boosted.append(r["key"])
        out.append(r)
    return out, {"dropped_lethal": dropped, "discounted_lethal": discounted, "boosted_goal": boosted}


def claims_final(results: List[dict], meta: dict) -> dict:
    """Per-game confirmed claims plus what led to each level-up."""
    games = {}
    for r in results:
        games[r["title"]] = {
            "game_id": r["game_id"], "best_levels": r["best_levels"], "actions": r["actions"],
            "state": r["state"], "level_ups": r.get("level_ups", []),
            "confirmed": r.get("confirmed", []),
            "lethal": [c for c in r.get("confirmed", []) if c["kind"] == "lethal"],
        }
    return {"meta": meta, "games": games}


def load_warm_start(path: str) -> Tuple[dict, str]:
    raw = Path(path).read_bytes()
    doc = json.loads(raw)
    return doc.get("games", doc), hashlib.sha256(raw).hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget", type=int, default=250, help="non-RESET actions per game (same for every game)")
    ap.add_argument("--out", default="/tmp/arc-self-talk")
    ap.add_argument("--games", default="", help="comma list of titles (default: all)")
    ap.add_argument("--warm-start", default="", metavar="PATH",
                    help="OPT-IN: load a prior claims_final.json as priors. A warm-started run is NOT a cold run "
                         "and must be disclosed (it is tagged 'warm-start' on the scorecard). Default: cold.")
    ap.add_argument("--prior-weight", type=int, default=3, help="cap on support+contra per prior claim")
    ap.add_argument("--offline", action="store_true",
                    help="dry run against a local toy environment; no network, no scorecard")
    ap.add_argument("--no-frames", action="store_true", help="disable out/frames.jsonl")
    args = ap.parse_args()
    out = Path(args.out)
    (out / "claims").mkdir(parents=True, exist_ok=True)
    priors, prior_sha = (None, None)
    if args.warm_start:
        priors, prior_sha = load_warm_start(args.warm_start)
        print("WARM START from {0} sha256={1} games={2} -- NOT a cold run; disclose it.".format(
            args.warm_start, prior_sha[:16], len(priors)), flush=True)
    if args.offline:
        client: Any = OfflineClient()
    else:
        key = os.environ.get("ARC_API_KEY")
        if not key:
            raise SystemExit("ARC_API_KEY is not set")
        client = Client(key)
    trace = (out / "claims.log").open("w")
    frames_path = out / "frames.jsonl"
    if not args.no_frames:
        frames_path.write_text("")
    frames = FrameLog(None if args.no_frames else frames_path)

    def log(line: str) -> None:
        trace.write(line + "\n")

    status, games = client.req("GET", "/api/games")
    if status != 200 or not isinstance(games, list):
        raise SystemExit("games list failed {0}".format(status))
    games.sort(key=lambda g: g.get("title") or g["game_id"])
    if args.games:
        want = set(args.games.upper().split(","))
        games = [g for g in games if (g.get("title") or "").upper() in want]
    mode = "warm-start" if priors else "cold"
    tags = [AGENT, "pmll", "self-talk", "competition", VERSION, mode]
    if priors:
        tags.append("warm-start-sha256:" + prior_sha)
    opaque = {"agent": AGENT, "version": VERSION, "budget_per_game": args.budget, "mode": mode,
              "method": "claim memory self-talk loop; no seeds; no LLM"
                        + ("; WARM START from prior claims_final.json" if priors else ""),
              "code": SOURCE_URL + "/blob/main/lattice/scripts/persistence_self_talk.py"}
    if priors:
        opaque.update({"warm_start_sha256": prior_sha, "warm_start_prior_weight": args.prior_weight})
    status, opened = client.req("POST", "/api/scorecard/open", {
        "source_url": SOURCE_URL, "tags": tags, "opaque": opaque, "competition_mode": True,
    })
    if priors and status in (400, 422):
        # tag too long or rejected: retry with a short sha tag (full sha stays in opaque)
        tags[-1] = "warm-start-sha256:" + prior_sha[:16]
        status, opened = client.req("POST", "/api/scorecard/open", {
            "source_url": SOURCE_URL, "tags": tags, "opaque": opaque, "competition_mode": True,
        })
    print("TAGS", tags, flush=True)
    if status != 200 or not isinstance(opened, dict) or not opened.get("card_id"):
        raise SystemExit("open failed {0} {1}".format(status, opened))
    card_id = opened["card_id"]
    print("OPENED", card_id, "budget", args.budget, "mode", mode, flush=True)
    (out / "card_id.txt").write_text(card_id)
    results = []
    for g in games:
        results.append(play_game(client, g, card_id, args.budget, out, log, frames, priors, args.prior_weight))
        trace.flush()
        (out / "results.json").write_text(json.dumps(results, indent=2))
    meta = {"agent": AGENT, "version": VERSION, "card_id": card_id, "budget": args.budget, "mode": mode,
            "warm_start": args.warm_start or None, "warm_start_sha256": prior_sha, "offline": args.offline,
            "written": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    (out / "claims_final.json").write_text(json.dumps(claims_final(results, meta), indent=2))
    status, summary = client.req("POST", "/api/scorecard/close", {"card_id": card_id}, timeout=60)
    if status != 200:
        time.sleep(5)
        status, summary = client.req("GET", "/api/scorecard/{0}".format(card_id), timeout=60)
    (out / "scorecard.json").write_text(json.dumps(summary, indent=2) if isinstance(summary, dict) else str(summary))
    frames.close()
    trace.close()
    print("CLOSE status", status, "429s", client.n429, flush=True)
    if isinstance(summary, dict):
        print("SCORE", summary.get("score"), "levels", summary.get("total_levels_completed"), "/",
              summary.get("total_levels"), "actions", summary.get("total_actions"), flush=True)
    if not args.offline:
        print("URL https://arcprize.org/scorecards/{0}".format(card_id), flush=True)


if __name__ == "__main__":
    main()
