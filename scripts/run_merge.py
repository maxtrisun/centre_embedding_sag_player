#!/usr/bin/env python3
"""Merge instance: one game whose PROVEN certificate is the embedding theorem.

doc/saturation.md §8.  Combines the three P2 win conditions that together cover
every axis-aligned square on every n x n board (n >= 3k):

  1. native W-squares          -- Case 1, including m in {2,3} inside W
  2. budget {outside 4}        -- every external m=0 square
  3. 32 residual m=1 edges     -- the only m=1 traces the filler lemma misses

Completable m=1 traces are *not* injected: by Lemma M1 the merge strategy is
already a G(k,3k) win, so the filler lemma discharges them.  Injecting them
with shared outside cells is the U model, already DISPROVEN.

Token layout matches the U model: one shared z plus one private y_V per
residual trace, all on a row strictly above W so no accidental geometric
square can touch them.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from functools import lru_cache
from typing import Dict, List, Tuple

from experiment_lib import DATA_DIR, write_json
from trace_geometry import (
    Coord,
    Trace,
    enumerate_traces,
    in_centre,
    square,
    window_completions,
)

import d11py


@lru_cache(maxsize=8)
def _residual_m1_traces(k: int) -> Tuple[Trace, ...]:
    out = []
    for r, vs in enumerate_traces(k).items():
        for V in vs:
            if sum(1 for p in V if in_centre(k, p)) != 1:
                continue
            if window_completions(k, V):
                continue
            out.append(tuple(sorted(V)))
    return tuple(out)


def residual_m1_traces(k: int) -> List[Trace]:
    # Each instance gets its own mutable list; cache only immutable geometry.
    return list(_residual_m1_traces(k))


class MergeInstance:
    def __init__(self, k: int):
        self.k = k
        self.w = 3 * k
        self.residuals = residual_m1_traces(k)
        assert all(len(V) == 2 for V in self.residuals), self.residuals[:3]

        # Carrier: all tokens on row 0 in columns 0..n_tokens-1, with
        # off >= n_tokens so they sit strictly left of W as well as above it.
        # Then no axis-aligned square through two tokens can land its other
        # corners inside W (same discipline as the U model).
        n_tokens = 1 + len(self.residuals)
        off = n_tokens
        N = self.w + 2 * off
        if (N - k) % 2:
            N += 2
            off = (N - self.w) // 2
        self.N = N
        self.off = off
        assert self.off >= n_tokens

        self.z = self.idx((0, 0))
        self.y = {V: self.idx((0, 1 + i)) for i, V in enumerate(self.residuals)}
        self.token_cells = [self.z] + [self.y[V] for V in self.residuals]
        assert max(c % N for c in self.token_cells) < self.off

        self.window = [(i, j) for i in range(self.w) for j in range(self.w)]
        self.p2_cells = sorted(
            {self.g(p) for p in self.window} | set(self.token_cells)
        )

        # Pin to the same local witness as G(6,18): (8,8) in window coords.
        self.root_local = (k + k // 2 - 1, k + k // 2 - 1)
        assert in_centre(k, self.root_local), self.root_local
        self.root_move = self.g(self.root_local)

    def idx(self, p: Coord) -> int:
        return p[0] * self.N + p[1]

    def g(self, p: Coord) -> int:
        return self.idx((p[0] + self.off, p[1] + self.off))

    def residual_edges(self) -> List[List[int]]:
        edges = []
        for V in self.residuals:
            cells = [self.g(p) for p in V] + [self.z, self.y[V]]
            assert len(cells) == 4 and len(set(cells)) == 4, cells
            edges.append(sorted(cells))
        return edges

    def game_spec(self, *, tokens: bool, budget: bool) -> "d11py.GameSpec":
        gs = d11py.GameSpec(self.N, self.k)
        if tokens:
            gs.p2_allowed = self.p2_cells
            gs.extra_p2_edges = self.residual_edges()
        else:
            gs.p2_allowed = sorted(self.g(p) for p in self.window)
        if budget:
            gs.p2_outside_centre_win = 4
        return gs

    def window_squares(self) -> set:
        out = set()
        for s in range(1, self.w):
            for r in range(self.w - s):
                for c in range(self.w - s):
                    out.add(frozenset(self.g(p) for p in square(r, c, s)))
        return out

    def audit(self, *, tokens: bool, budget: bool) -> Dict[str, object]:
        gs = self.game_spec(tokens=tokens, budget=budget)
        live = {frozenset(e) for e in d11py.live_hyperedges(gs)}
        want = self.window_squares()
        injected = {frozenset(e) for e in self.residual_edges()} if tokens else set()
        want_all = want | injected
        tok = set(self.token_cells)
        geometric_with_tok = [e for e in live if (e & tok) and e not in injected]
        return {
            "live_edges": len(live),
            "window_squares": len(want),
            "injected_edges": len(injected),
            "expected_edges": len(want_all),
            "spurious_edges": len(live - want_all),
            "missing_edges": len(want_all - live),
            "geometric_touching_tokens": len(geometric_with_tok),
            "edges_exact": live == want_all and not geometric_with_tok,
            "residual_traces": len(self.residuals),
            "tokens": len(self.token_cells) if tokens else 0,
            "budget": bool(budget),
        }


def solve(gs: d11py.GameSpec, *, beam: int, depth: int, max_plies: int,
          max_nodes: int, threads: int, pinned: int) -> Dict[str, object]:
    cfg = d11py.VerifierConfig()
    cfg.game = gs
    cfg.mode = d11py.QueryMode.ProveP1
    cfg.or_beam_width = beam
    cfg.or_beam_depth = depth
    cfg.omp_threads = threads
    cfg.parallel_or = threads != 1
    cfg.iterative_beam_widening = False
    cfg.max_plies = max_plies
    cfg.max_nodes = max_nodes
    if pinned >= 0:
        cfg.pinned_root_move = pinned

    t0 = time.perf_counter()
    res = d11py.verify(cfg)
    return {
        "verdict": d11py.verdict_str(res.verdict),
        "witness": res.witness,
        "nodes": res.nodes,
        "tt_hits": res.tt_hits,
        "max_ply": res.max_ply_reached,
        "min_proven_ply": res.min_proven_ply,
        "max_proven_ply": res.max_proven_ply,
        "proven_leaves": res.proven_leaf_count,
        "time_s": round(time.perf_counter() - t0, 3),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=6)
    ap.add_argument("--control", default="",
                    choices=["", "faithful", "canary", "budget_only"])
    ap.add_argument("--beam", type=int, default=16)
    ap.add_argument("--depth", type=int, default=2)
    ap.add_argument("--max-plies", type=int, default=120)
    ap.add_argument("--max-nodes", type=int, default=0)
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--audit-only", action="store_true")
    ap.add_argument("--tag", default="merge")
    args = ap.parse_args()

    k = 2 if args.control == "canary" else args.k
    tokens = args.control not in ("faithful", "budget_only")
    budget = args.control != "faithful"
    # canary keeps tokens+budget so the harness is the real one; k=2 must lose.

    inst = MergeInstance(k)
    print(f"[merge] k={k} W={inst.w} carrier={inst.N} residuals={len(inst.residuals)} "
          f"tokens={tokens} budget={budget} control={args.control or 'main'}",
          flush=True)

    aud = inst.audit(tokens=tokens, budget=budget)
    for key in ("live_edges", "window_squares", "injected_edges", "spurious_edges",
                "missing_edges", "geometric_touching_tokens", "edges_exact"):
        print(f"    {key}: {aud[key]}")
    if not aud["edges_exact"]:
        print("[merge] EDGE AUDIT FAILED", flush=True)
        sys.exit(1)
    if args.audit_only:
        write_json(DATA_DIR / args.tag / f"audit_k{k}.json", aud)
        return

    gs = inst.game_spec(tokens=tokens, budget=budget)
    rec = solve(gs, beam=args.beam, depth=args.depth, max_plies=args.max_plies,
                max_nodes=args.max_nodes, threads=args.threads,
                pinned=inst.root_move)
    out = {
        "k": k,
        "control": args.control or "main",
        "carrier_n": inst.N,
        "window": inst.w,
        "offset": inst.off,
        "residuals": len(inst.residuals),
        "tokens_enabled": tokens,
        "budget_enabled": budget,
        "root_move": inst.root_move,
        **aud,
        **rec,
    }
    print(f"[merge] verdict={rec['verdict']} nodes={rec['nodes']} "
          f"max_proven_ply={rec['max_proven_ply']} t={rec['time_s']}s",
          flush=True)

    path = DATA_DIR / args.tag / f"k{k}_{out['control']}.json"
    if path.exists():
        prev = json.loads(path.read_text())
        # keep a short history of prior runs under the same key
        hist = prev.get("_history", [])
        if isinstance(prev, dict) and "verdict" in prev:
            hist.append({k2: prev[k2] for k2 in ("verdict", "nodes", "time_s")
                         if k2 in prev})
        out["_history"] = hist[-5:]
    write_json(path, out)
    print(f"[merge] wrote {path}", flush=True)


if __name__ == "__main__":
    main()
