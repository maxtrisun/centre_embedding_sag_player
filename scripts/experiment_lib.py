#!/usr/bin/env python3
"""Shared utilities for design11 paper experiments."""

from __future__ import annotations

import csv
import json
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Iterator, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
sys.path.insert(0, str(BUILD))

import d11py  # noqa: E402

EXPERIMENTS_DIR = ROOT / "experiments"
DATA_DIR = EXPERIMENTS_DIR / "data"

# Paper sweep sizes (user request; 9 and 10 are separate).
GNN_SIZES: Tuple[int, ...] = (5, 6, 7, 8, 9, 10, 13, 14)


def d4_map(cell: int, n: int, t: int) -> int:
    r, c = divmod(cell, n)
    if t == 0:
        nr, nc = r, c
    elif t == 1:
        nr, nc = c, n - 1 - r
    elif t == 2:
        nr, nc = n - 1 - r, n - 1 - c
    elif t == 3:
        nr, nc = n - 1 - c, r
    elif t == 4:
        nr, nc = r, n - 1 - c
    elif t == 5:
        nr, nc = n - 1 - r, c
    elif t == 6:
        nr, nc = c, r
    elif t == 7:
        nr, nc = n - 1 - c, n - 1 - r
    else:
        nr, nc = r, c
    return nr * n + nc


def d4_orbit(cell: int, n: int) -> Tuple[int, ...]:
    vals = {d4_map(cell, n, t) for t in range(8)}
    return tuple(sorted(vals))


def d4_representatives(n: int, cells: Optional[Sequence[int]] = None) -> List[int]:
    """One minimum-index cell per D4 orbit."""
    if cells is None:
        cells = range(n * n)
    seen: set[frozenset[int]] = set()
    reps: List[int] = []
    for c in cells:
        orb = frozenset(d4_orbit(c, n))
        if orb in seen:
            continue
        seen.add(orb)
        reps.append(min(orb))
    return sorted(reps)


def cell_hyperedge_counts(n: int) -> List[int]:
    """Incident axis-aligned square hyperedges per cell (matches C++ enumerate_axis_squares)."""
    counts = [0] * (n * n)
    for s in range(1, n):  # kMinSide = 1 → 2×2 corner squares
        for r in range(n - s):
            for c in range(n - s):
                corners = (
                    r * n + c,
                    r * n + (c + s),
                    (r + s) * n + c,
                    (r + s) * n + (c + s),
                )
                for cell in corners:
                    counts[cell] += 1
    return counts


def total_hyperedges(n: int) -> int:
    # Σ_{s=1}^{n-1} (n-s)²
    return sum((n - s) ** 2 for s in range(1, n))


def center_cells(center: int, n: int) -> List[int]:
    o = (n - center) // 2
    out: List[int] = []
    for r in range(o, o + center):
        for c in range(o, o + center):
            out.append(r * n + c)
    return out


def cell_coord(cell: int, n: int) -> Tuple[int, int]:
    return divmod(cell, n)


def make_config(
    center: int,
    n: int,
    *,
    mode: str = "decide",
    beam: int = 0,
    depth: int = 0,
    threads: int = 1,
    max_plies: Optional[int] = None,
    max_nodes: int = 0,
    parallel_or: bool = False,
    pinned: int = -1,
    iterative_beam: bool = True,
    **prune_flags: bool,
) -> d11py.VerifierConfig:
    cfg = d11py.VerifierConfig()
    cfg.game = d11py.GameSpec(n, center)
    cfg.mode = d11py.QueryMode.Decide if mode == "decide" else d11py.QueryMode.ProveP1
    cfg.or_beam_width = beam
    cfg.or_beam_depth = depth
    cfg.omp_threads = threads
    cfg.parallel_or = parallel_or
    cfg.max_nodes = max_nodes
    cfg.max_plies = max_plies if max_plies is not None else max(50, n * n)
    cfg.iterative_beam_widening = iterative_beam
    cfg.pinned_root_move = pinned
    for k, v in prune_flags.items():
        if hasattr(cfg, k):
            setattr(cfg, k, v)
    return cfg


@dataclass
class RunRecord:
    experiment: str
    n: int
    center: int
    cell: int
    row: int
    col: int
    hyperedges: int
    d4_orbit_size: int
    prove_count: int  # winning moves in D4 orbit (exact or sampled)
    prove_count_exact: bool
    verdict: str
    witness: int
    nodes: int
    tt_hits: int
    max_ply: int
    min_proven_ply: int
    proven_leaves: int
    time_s: float
    extra: dict = field(default_factory=dict)


def run_verify(cfg: d11py.VerifierConfig) -> Tuple[d11py.SearchResult, float]:
    t0 = time.perf_counter()
    res = d11py.verify(cfg)
    return res, time.perf_counter() - t0


def count_winning_in_orbit(
    n: int,
    center: int,
    rep: int,
    *,
    mode: str = "decide",
    beam: int = 0,
    depth: int = 0,
    threads: int = 1,
    max_nodes: int = 0,
    sample_limit: Optional[int] = None,
) -> Tuple[int, bool]:
    """Return (winning_count, is_exact) among cells in rep's D4 orbit."""
    orbit = d4_orbit(rep, n)
    if sample_limit is not None and len(orbit) > sample_limit:
        cfg = make_config(
            center,
            n,
            mode=mode,
            beam=beam,
            depth=depth,
            threads=threads,
            max_nodes=max_nodes,
            pinned=rep,
            iterative_beam=False,
        )
        res, _ = run_verify(cfg)
        if res.verdict == d11py.Verdict.Proven:
            return len(orbit), False
        return 0, False

    wins = 0
    for c in orbit:
        cfg = make_config(
            center,
            n,
            mode=mode,
            beam=beam,
            depth=depth,
            threads=threads,
            max_nodes=max_nodes,
            pinned=c,
            iterative_beam=False,
        )
        res, _ = run_verify(cfg)
        if res.verdict == d11py.Verdict.Proven:
            wins += 1
    return wins, True


def write_csv(path: Path, rows: Sequence[dict], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow(row)


def write_json(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        json.dump(obj, f, indent=2, sort_keys=True)


def append_jsonl(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(obj, sort_keys=True) + "\n")


def load_csv(path: Path) -> List[dict]:
    if not path.exists():
        return []
    with path.open() as f:
        return list(csv.DictReader(f))
