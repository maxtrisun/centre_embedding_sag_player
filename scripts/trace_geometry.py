#!/usr/bin/env python3
"""Stage 1 of the trace-reduction lemma: the purely algebraic / geometric part.

This closes the *geometry* of Case 2 of the embedding theorem, i.e. every
axis-aligned square Q that is **not** contained in the window W.  Squares with
Q ⊆ W are Case 1 and are already hyperedges of the G(k,3k) certificate.

Setting (normalised to the window W, k = centre size):

    W = {0,...,3k-1}^2            the 3k x 3k window
    C = {k,...,2k-1}^2            the centre block P1 is confined to
    F = W \\ C                     the frame

    Q(a,b,d) = {(a,b),(a,b+d),(a+d,b),(a+d,b+d)},  d >= 1,  (a,b) in Z^2

Q ranges over axis-aligned squares of the *whole* n x n board for arbitrary
n >= 3k, i.e. over all of Z^2 (taking the union over n is the same as dropping
the board bound, which is a sound over-approximation).

This script machine-checks:

  L1  m = 0  <=>  X_Q ∩ I = {} or Y_Q ∩ I = {},  where X_Q = {a,a+d},
      Y_Q = {b,b+d}, I = {k,...,2k-1}, m = |Q ∩ C|; and for a single axis

          X_Q ∩ I = {}  <=>  a+d < k  or  a >= 2k  or  (a < k and a+d >= 2k).

      NOTE the third disjunct: the naive form "(a+d<k) or (a>2k-1)" is *wrong*.
      A square may straddle the centre band (one x-coordinate left of C, the
      other right of C) and still miss C entirely.  L1_naive_ok below records
      that the two-disjunct version fails.

  L1b Up to D4 there are therefore *two* canonical m=0 types, not one:
      the "one-sided" type (a+d < k, up to symmetry) and the "straddling"
      type (a < k and a+d >= 2k), the latter forcing d >= k+1.

  L2  r = |Q ∩ W| ∈ {0,1,2,4}; r = 3 is impossible (for *every* Q, not only m=0).

  L3  r = 2  =>  the two W-corners are *adjacent* corners of Q (share a row or
      a column), never a diagonal pair.

  L6  Q ⊄ W  =>  m <= 1.  A square that leaves the window touches the centre in
      at most one corner.  Together with L2/L3 this is what makes Case 2 a
      *finite* problem: the whole case is carried by traces of size <= 2, each
      of which contributes at most one centre cell.

  L4  The set of traces  V = Q ∩ W  over all Q ⊄ W is finite and is enumerated
      exactly:  r=0 gives V = {}, r=1 gives every cell of W, r=2 gives a
      computed finite family of chords of W.  Each trace is tagged with
      m = |V ∩ C| ∈ {0,1} so the m=0 sub-family (which has its own clean
      algebraic form L1) can still be reported separately.

  L5  (completion / filler test)  For which V does there exist an axis-aligned
      square S with V ⊆ S ⊆ W?  Whenever such an S exists the case is
      discharged by the plain G(k,3k) certificate alone (see the docstring of
      `window_completions`), so no new search is needed.  The residual traces
      are written out for Stage 2.

Outputs (under experiments/data/trace_reduction/):
  geometry_meta.json      counts + lemma check results
  traces_r1.csv           every r=1 trace, its D4 class, completion status
  traces_r2.csv           every r=2 trace, its D4 class, completion status
  residual_cases.json     D4 representatives that L5 does *not* discharge
"""

from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from experiment_lib import DATA_DIR, write_csv, write_json

Coord = Tuple[int, int]
Trace = Tuple[Coord, ...]


# ----------------------------------------------------------------------------
# basic geometry
# ----------------------------------------------------------------------------

def in_window(k: int, p: Coord) -> bool:
    r, c = p
    return 0 <= r < 3 * k and 0 <= c < 3 * k


def in_centre(k: int, p: Coord) -> bool:
    r, c = p
    return k <= r < 2 * k and k <= c < 2 * k


def square(a: int, b: int, d: int) -> Tuple[Coord, Coord, Coord, Coord]:
    return ((a, b), (a, b + d), (a + d, b), (a + d, b + d))


def d4_maps(k: int) -> List:
    """The 8 symmetries of the window W; each preserves C (C is central)."""
    m = 3 * k - 1

    def t0(p: Coord) -> Coord:
        return p

    def t1(p: Coord) -> Coord:
        r, c = p
        return (c, m - r)

    def t2(p: Coord) -> Coord:
        r, c = p
        return (m - r, m - c)

    def t3(p: Coord) -> Coord:
        r, c = p
        return (m - c, r)

    def t4(p: Coord) -> Coord:
        r, c = p
        return (r, m - c)

    def t5(p: Coord) -> Coord:
        r, c = p
        return (m - r, c)

    def t6(p: Coord) -> Coord:
        r, c = p
        return (c, r)

    def t7(p: Coord) -> Coord:
        r, c = p
        return (m - c, m - r)

    return [t0, t1, t2, t3, t4, t5, t6, t7]


def canonical_trace(k: int, V: Trace) -> Trace:
    """Lexicographically smallest D4 image of the trace (as a sorted tuple)."""
    best: Optional[Trace] = None
    for t in d4_maps(k):
        img = tuple(sorted(t(p) for p in V))
        if best is None or img < best:
            best = img
    assert best is not None
    return best


# ----------------------------------------------------------------------------
# L1 / L2 / L3 : exhaustive check on a bounded but generous range
# ----------------------------------------------------------------------------

def check_L1_L2_L3(k: int, margin: int) -> Dict[str, object]:
    """Exhaustively verify the three structural lemmas.

    `margin` is how far outside W the top-left corner and the side length are
    allowed to roam.  Anything beyond `margin` only repeats traces already
    seen (a corner outside W stays outside W), so a margin of 3k+2 is ample.
    """
    n = 3 * k
    lo, hi = -margin, n + margin
    bad_L1: List[Tuple[int, int, int]] = []
    bad_L1_naive: List[Tuple[int, int, int]] = []
    bad_L2: List[Tuple[int, int, int]] = []
    bad_L3: List[Tuple[int, int, int]] = []
    bad_L6: List[Tuple[int, int, int]] = []
    straddling = 0
    r_hist: Dict[int, int] = {}
    m_hist: Dict[int, int] = {}
    rm_hist: Dict[Tuple[int, int], int] = {}
    total = 0

    for a in range(lo, hi):
        for b in range(lo, hi):
            for d in range(1, hi - lo):
                corners = square(a, b, d)
                total += 1
                m = sum(1 for p in corners if in_centre(k, p))
                r = sum(1 for p in corners if in_window(k, p))
                m_hist[m] = m_hist.get(m, 0) + 1
                r_hist[r] = r_hist.get(r, 0) + 1
                rm_hist[(r, m)] = rm_hist.get((r, m), 0) + 1

                # L1: m == 0  <=>  x-interval or y-interval misses I = {k..2k-1}
                def misses(u: int) -> bool:
                    return (u + d < k) or (u >= 2 * k) or (u < k and u + d >= 2 * k)

                algebraic = misses(a) or misses(b)
                if (m == 0) != algebraic:
                    bad_L1.append((a, b, d))
                naive = (a + d < k) or (a > 2 * k - 1) or (b + d < k) or (b > 2 * k - 1)
                if (m == 0) != naive:
                    bad_L1_naive.append((a, b, d))
                if m == 0 and ((a < k <= 2 * k <= a + d) or (b < k <= 2 * k <= b + d)):
                    straddling += 1

                # L2: r != 3
                if r == 3:
                    bad_L2.append((a, b, d))

                # L3: r == 2  =>  the two W-corners share a row or a column
                if r == 2:
                    p, q = [x for x in corners if in_window(k, x)]
                    if p[0] != q[0] and p[1] != q[1]:
                        bad_L3.append((a, b, d))

                # L6: Q ⊄ W  =>  at most one corner in C
                if r < 4 and m > 1:
                    bad_L6.append((a, b, d))

    return {
        "k": k,
        "margin": margin,
        "squares_tested": total,
        "r_histogram": {str(kk): v for kk, v in sorted(r_hist.items())},
        "m_histogram": {str(kk): v for kk, v in sorted(m_hist.items())},
        "rm_histogram": {f"r{a}m{b}": v for (a, b), v in sorted(rm_hist.items())},
        "L1_counterexamples": bad_L1[:20],
        "L1_ok": not bad_L1,
        "L1_naive_ok": not bad_L1_naive,
        "L1_naive_counterexamples": bad_L1_naive[:20],
        "L1_naive_missed": len(bad_L1_naive),
        "m0_straddling_squares": straddling,
        "L2_counterexamples": bad_L2[:20],
        "L2_ok": not bad_L2,
        "L3_counterexamples": bad_L3[:20],
        "L3_ok": not bad_L3,
        "L6_counterexamples": bad_L6[:20],
        "L6_ok": not bad_L6,
    }


# ----------------------------------------------------------------------------
# L4 : the exact finite family of m=0 traces
# ----------------------------------------------------------------------------

def squares_through_pair(p: Coord, q: Coord) -> List[Tuple[int, int, int]]:
    """Every axis-aligned square having both p and q as corners, as (a,b,d).

    Two corners of an axis-aligned square are either in the same row, in the
    same column, or diagonally opposite. A shared row (or column) leaves the
    square's side pinned but its other edge free to sit on either side, giving
    two candidates; a diagonal pair pins the square outright. Anything else is
    not part of any square.
    """
    (r1, c1), (r2, c2) = p, q
    if p == q:
        return []
    if r1 == r2:
        d = abs(c2 - c1)
        b = min(c1, c2)
        return [(r1 - d, b, d), (r1, b, d)]
    if c1 == c2:
        d = abs(r2 - r1)
        a = min(r1, r2)
        return [(a, c1 - d, d), (a, c1, d)]
    if abs(r2 - r1) == abs(c2 - c1):
        return [(min(r1, r2), min(c1, c2), abs(r2 - r1))]
    return []


def check_sharing_lemma(k: int, margin: int) -> Dict[str, object]:
    """L7: two cells outside W lie on at most one W-meeting square.

    This is what bounds how far P2 can reuse a move played outside the window.
    Every external square has at least two corners outside W (r <= 2), and by
    this lemma *any two* of them already pin the square uniquely among the
    squares that reach W at all.  So P2 cannot keep several external targets
    alive on shared outside stones: the second outside stone commits it.

    Proof (mirrored by the sweep below).  Let p, q lie outside W and share a
    row a, at columns b and b+d.  The two candidate squares put their other
    edge at row a-d and a+d.  If a < 0 then a-d < 0, so only the a+d square can
    reach W; if a > 3k-1 then symmetrically only a-d can.  If instead a is a
    row of W, then b and b+d must both be outside W's columns (else p or q
    would lie in W), and the other two corners repeat those columns, so neither
    candidate meets W.  Columns are symmetric, and a diagonal pair pins one
    square outright.
    """
    n = 3 * k
    lo, hi = -margin, n + margin
    cells = [(i, j) for i in range(lo, hi) for j in range(lo, hi)
             if not in_window(k, (i, j))]
    worst = 0
    counterexamples: List[Tuple[Coord, Coord]] = []
    pairs = 0
    for idx, p in enumerate(cells):
        for q in cells[idx + 1:]:
            cands = squares_through_pair(p, q)
            if not cands:
                continue
            pairs += 1
            meeting = [t for t in cands
                       if any(in_window(k, x) for x in square(*t))]
            if len(meeting) > worst:
                worst = len(meeting)
            if len(meeting) > 1:
                counterexamples.append((p, q))
    return {
        "outside_cells_swept": len(cells),
        "pairs_on_a_common_square": pairs,
        "max_W_meeting_squares_per_pair": worst,
        "L7_ok": not counterexamples,
        "L7_counterexamples": [[list(a), list(b)] for a, b in counterexamples[:20]],
    }


def enumerate_traces(k: int) -> Dict[int, List[Trace]]:
    """All traces V = Q ∩ W of squares Q ⊄ W, grouped by r = |V|.

    r = 4 is deliberately excluded: it means Q ⊆ W, i.e. Q is an ordinary
    W-hyperedge, already covered by the G(k,3k) certificate (Case 1).

    r = 1: every cell of W occurs (take d larger than the whole window).
    r = 2: {(i,j),(i,j+d)} with the opposite edge row i-d or i+d outside W
           (and the column-transposed family).

    Cells of C are *not* excluded: a trace may contain one centre cell, which
    is exactly the m = 1 sub-family.  By L6 it can never contain two.
    """
    n = 3 * k
    out: Dict[int, List[Trace]] = {0: [()], 1: [], 2: []}

    for i in range(n):
        for j in range(n):
            out[1].append(((i, j),))

    seen2 = set()
    for i in range(n):
        for j in range(n):
            for d in range(1, n - j):
                # the other edge of Q must leave the window entirely
                if not (i - d < 0 or i + d > n - 1):
                    continue
                for V in (((i, j), (i, j + d)), ((j, i), (j + d, i))):
                    V = tuple(sorted(V))
                    if V not in seen2:
                        seen2.add(V)
                        out[2].append(V)
    return out


def trace_m(k: int, V: Trace) -> int:
    """m = |Q ∩ C| for any Q realising the trace V (= |V ∩ C| by L6)."""
    return sum(1 for p in V if in_centre(k, p))


def verify_trace_family(k: int, margin: int, fam: Dict[int, List[Trace]]) -> Dict[str, object]:
    """Cross-check `enumerate_traces` against brute force over Q(a,b,d)."""
    n = 3 * k
    lo, hi = -margin, n + margin
    brute: Dict[int, set] = {0: set(), 1: set(), 2: set(), 4: set()}
    for a in range(lo, hi):
        for b in range(lo, hi):
            for d in range(1, hi - lo):
                corners = square(a, b, d)
                V = tuple(sorted(p for p in corners if in_window(k, p)))
                brute[len(V)].add(V)
    return {
        "r0_match": brute[0] == set(fam[0]),
        "r1_match": brute[1] == set(fam[1]),
        "r2_match": brute[2] == set(fam[2]),
        "r1_brute": len(brute[1]),
        "r2_brute": len(brute[2]),
        "r4_brute": len(brute[4]),
    }


# ----------------------------------------------------------------------------
# L5 : frame completion (the "filler" discharge)
# ----------------------------------------------------------------------------

def window_completions(k: int, V: Trace) -> List[Tuple[Coord, ...]]:
    """All axis-aligned squares S with V ⊆ S ⊆ W.

    Why this discharges the case (the *filler* argument).  Let sigma be a P1
    winning strategy for G(k,3k) on W and suppose such an S exists.  On the
    n x n board P1 plays sigma against a *shadow* W-game maintained as
    follows: shadow_P1 = real_P1, and shadow_P2 = (real_P2 ∩ W) ∪ Phi, where
    every P2 move outside W adds one *filler* stone Phi, taken from S \\ V
    while any of those is still shadow-empty.

      * The shadow play is a legal G(k,3k) game (fillers are only ever put on
        shadow-empty cells, one per P2 move, preserving parity).
      * P1's replies stay legal in the real game: sigma only plays shadow-empty
        cells of C, and shadow occupancy contains real occupancy, so such a
        cell is real-empty too.  In particular P1 never occupies a filler cell,
        even when that filler lies in C.
      * P1's own stones coincide in the two games, so P1 completes its C-square
        at exactly the same move index in both.

    Now suppose P2 completed the external square Q on its move t of the real
    game.  Then real_P2 ⊇ Q, so shadow_P2 ⊇ V; and P2 made |Q \\ W| = |S \\ V|
    moves outside W, each producing a filler, so shadow_P2 ⊇ S \\ V by move t.
    Hence shadow_P2 ⊇ S, a completed W-square, contradicting that sigma wins
    unless P1 finished strictly earlier.  So P1 finishes first.

    Note S is only required to lie in W, not in the frame F: filler cells
    inside C are harmless by the third bullet above.
    """
    n = 3 * k
    if not V:
        return [square(0, 0, 1)]
    if len(V) == 1:
        (i, j) = V[0]
        out = []
        for d in range(1, n):
            for a in (i - d, i):
                for b in (j - d, j):
                    S = square(a, b, d)
                    if all(in_window(k, p) for p in S):
                        out.append(S)
        return out
    (i1, j1), (i2, j2) = V
    out = []
    if i1 == i2:
        d = abs(j2 - j1)
        for i3 in (i1 - d, i1 + d):
            S = square(min(i1, i3), min(j1, j2), d)
            if all(in_window(k, p) for p in S):
                out.append(S)
    else:
        d = abs(i2 - i1)
        for j3 in (j1 - d, j1 + d):
            S = square(min(i1, i2), min(j1, j3), d)
            if all(in_window(k, p) for p in S):
                out.append(S)
    return out


# ----------------------------------------------------------------------------
# realisable external squares for a residual trace (input for Stage 2)
# ----------------------------------------------------------------------------

def external_squares_for_trace(k: int, V: Trace) -> List[Tuple[int, int, int]]:
    """All (a,b,d) with Q(a,b,d) ⊄ W and Q(a,b,d) ∩ W = V.

    Constructed directly rather than by sweeping Z^2: the trace pins the
    square except for the choice of which side the missing corners sit on.
    Side lengths are capped at 3k (a longer Q has the same trace as the
    capped one, since its extra corners are outside W either way).
    """
    n = 3 * k
    cand: List[Tuple[int, int, int]] = []
    if not V:
        # any square entirely outside W; the canonical one sits above-left
        cand = [(-2, -2, 1)]
    elif len(V) == 1:
        (i, j) = V[0]
        for d in range(1, 2 * n + 1):
            for a in (i - d, i):
                for b in (j - d, j):
                    cand.append((a, b, d))
    else:
        (i1, j1), (i2, j2) = sorted(V)
        if i1 == i2:
            d = abs(j2 - j1)
            for a in (i1 - d, i1):
                cand.append((a, min(j1, j2), d))
        else:
            d = abs(i2 - i1)
            for b in (j1 - d, j1):
                cand.append((min(i1, i2), b, d))

    out = []
    want = tuple(sorted(V))
    for (a, b, d) in cand:
        corners = square(a, b, d)
        if tuple(sorted(p for p in corners if in_window(k, p))) == want:
            out.append((a, b, d))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=6)
    ap.add_argument("--margin", type=int, default=None,
                    help="how far outside W the brute-force sweep goes (default 3k+2)")
    ap.add_argument("--share-margin", type=int, default=9,
                    help="margin for the L7 pair sweep (quadratic in the cell count)")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    k = args.k
    n = 3 * k
    margin = args.margin if args.margin is not None else n + 2
    out_dir = args.out or (DATA_DIR / "trace_reduction")

    print(f"[geometry] k={k} W={n}x{n} C=[{k},{2*k-1}]^2 margin={margin}")

    struct = check_L1_L2_L3(k, margin)
    print(f"  L1 (m=0 algebraic form)   ok={struct['L1_ok']}")
    print(f"  L2 (r != 3)               ok={struct['L2_ok']}")
    print(f"  L3 (r=2 => adjacent pair) ok={struct['L3_ok']}")
    print(f"  L6 (Q not in W => m<=1)   ok={struct['L6_ok']}")
    print(f"  squares tested: {struct['squares_tested']}")

    share = check_sharing_lemma(k, args.share_margin)
    print(f"  L7 (outside pair pins <=1 W-meeting square) ok={share['L7_ok']}"
          f"  max={share['max_W_meeting_squares_per_pair']}"
          f"  pairs={share['pairs_on_a_common_square']}"
          f"  cells={share['outside_cells_swept']}")

    fam = enumerate_traces(k)
    cross = verify_trace_family(k, margin, fam)
    print(f"  L4 trace family: r0={len(fam[0])} r1={len(fam[1])} r2={len(fam[2])}"
          f"  (brute-force match: r0={cross['r0_match']} r1={cross['r1_match']} r2={cross['r2_match']})")

    rows: Dict[int, List[dict]] = {1: [], 2: []}
    classes: Dict[Trace, dict] = {}
    for r in (0, 1, 2):
        for V in fam[r]:
            comps = window_completions(k, V)
            canon = canonical_trace(k, V)
            m = trace_m(k, V)
            assert m == trace_m(k, canon), (V, canon)   # D4 preserves C
            info = classes.setdefault(canon, {
                "r": r,
                "m": m,
                "canonical": canon,
                "members": 0,
                "completable": True,
            })
            info["members"] += 1
            if not comps:
                info["completable"] = False
            if r in rows:
                rows[r].append({
                    "r": r,
                    "m": m,
                    "cells": ";".join(f"{p[0]},{p[1]}" for p in V),
                    "canonical": ";".join(f"{p[0]},{p[1]}" for p in canon),
                    "n_completions": len(comps),
                    "completion": (";".join(f"{p[0]},{p[1]}" for p in comps[0]) if comps else ""),
                    "discharged_by_completion": bool(comps),
                })

    by_rm: Dict[Tuple[int, int], Dict[str, int]] = {}
    residual: List[dict] = []
    for canon, info in sorted(classes.items(), key=lambda kv: (kv[1]["r"], kv[1]["m"], kv[0])):
        r, m = info["r"], info["m"]
        st = by_rm.setdefault((r, m), {"classes": 0, "traces": 0, "residual_classes": 0,
                                       "residual_traces": 0})
        st["classes"] += 1
        st["traces"] += info["members"]
        if not info["completable"]:
            st["residual_classes"] += 1
            st["residual_traces"] += info["members"]
            residual.append({
                "r": r,
                "m": m,
                "cells": [list(p) for p in canon],
                "orbit_members": info["members"],
                "external_squares": [list(t) for t in external_squares_for_trace(k, canon)[:8]],
            })

    for (r, m) in sorted(by_rm):
        st = by_rm[(r, m)]
        print(f"  r={r} m={m}: {st['traces']} traces / {st['classes']} D4 classes; "
              f"needing search: {st['residual_traces']} traces / {st['residual_classes']} classes")
    tot_cls = sum(st["classes"] for st in by_rm.values())
    tot_res = sum(st["residual_classes"] for st in by_rm.values())
    print(f"  TOTAL: {tot_cls} D4 classes, {tot_res} residual")

    meta = {
        "k": k,
        "window": n,
        "structural_lemmas": struct,
        "sharing_lemma": share,
        "trace_family_crosscheck": cross,
        "trace_counts": {str(r): len(v) for r, v in fam.items()},
        "d4_summary": {f"r{r}m{m}": v for (r, m), v in by_rm.items()},
        "d4_class_total": tot_cls,
        "residual_class_count": len(residual),
    }
    write_json(out_dir / "geometry_meta.json", meta)
    for r in (1, 2):
        write_csv(out_dir / f"traces_r{r}.csv", rows[r],
                  ["r", "m", "cells", "canonical", "n_completions", "completion",
                   "discharged_by_completion"])
    write_json(out_dir / "residual_cases.json", residual)
    print(f"[geometry] wrote {out_dir}")

    failed = [name for name in ("L1_ok", "L2_ok", "L3_ok", "L6_ok") if not struct[name]]
    failed += [name for name in ("r0_match", "r1_match", "r2_match") if not cross[name]]
    if not share["L7_ok"]:
        failed.append("L7_ok")
    if failed:
        print(f"[geometry] FAILED: {', '.join(failed)}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
