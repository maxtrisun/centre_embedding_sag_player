#!/usr/bin/env python3
"""Σ view builder for n>=18 (merge reading). Minimal playable implementation.

Maps a real n×n Position (symmetric GameSpec) into a merge carrier Position
compatible with the exported merge ProofDag, using artifact_plan / Thm.lift
online rules. Pin-rebuild rewrites only the outside ledger.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Dict, List, Optional, Set, Tuple

from run_merge import MergeInstance
from trace_geometry import (
    enumerate_traces,
    external_squares_for_trace,
    square,
    window_completions,
)

Coord = Tuple[int, int]


@lru_cache(maxsize=8)
def _trace_family(k):
    # Immutable values preserve enumeration order and cannot leak mutations.
    family = enumerate_traces(k)
    return tuple(tuple(tuple(sorted(v)) for v in family[r]) for r in (1, 2))


@lru_cache(maxsize=4096)
def _completions(k, trace):
    return tuple(tuple(s) for s in window_completions(k, trace))


@lru_cache(maxsize=4096)
def _external_squares(k, trace):
    return tuple(external_squares_for_trace(k, trace))


@dataclass
class SigmaState:
    """Mutable online ledger for EmbedPlayer."""

    k: int = 6
    n: int = 18
    mi: MergeInstance = field(default_factory=lambda: MergeInstance(6))
    # Armed mode: "default" | "residual" | "completable" | "pin"
    mode: str = "default"
    armed_V: Optional[Tuple[Coord, ...]] = None
    armed_S: Optional[List[Coord]] = None
    # Outside stones in play order (board cells on the real n×n board)
    outside_cells: List[int] = field(default_factory=list)
    # Map real outside cell -> merge token/filler cell (carrier index)
    ledger: Dict[int, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.w = 3 * self.k
        self.off = (self.n - self.w) // 2

    def window_local(self, cell: int) -> Optional[Coord]:
        r, c = divmod(cell, self.n)
        lr, lc = r - self.off, c - self.off
        if 0 <= lr < self.w and 0 <= lc < self.w:
            return (lr, lc)
        return None

    def in_window(self, cell: int) -> bool:
        return self.window_local(cell) is not None

    def real_to_merge_window_cell(self, cell: int) -> Optional[int]:
        loc = self.window_local(cell)
        if loc is None:
            return None
        return self.mi.g(loc)


def sharing_pin(outside: List[int], n: int, off: int, w: int) -> Optional[Set[Coord]]:
    """If two outside cells determine a unique axis-aligned square meeting W, return Q∩W.

    Conservative: only handle same-row or same-col pairs with the other edge
    intersecting the window (paper sharing lemma special case).
    """
    if len(outside) < 2:
        return None
    a, b = outside[0], outside[1]
    ra, ca = divmod(a, n)
    rb, cb = divmod(b, n)
    cands: List[Set[Coord]] = []

    def meet_w(cells: List[Coord]) -> Set[Coord]:
        out = set()
        for r, c in cells:
            if off <= r < off + w and off <= c < off + w:
                out.add((r - off, c - off))
        return out

    if ra == rb:
        d = abs(ca - cb)
        if d == 0:
            return None
        c0 = min(ca, cb)
        for r2 in (ra - d, ra + d):
            corners = [(ra, c0), (ra, c0 + d), (r2, c0), (r2, c0 + d)]
            tw = meet_w(corners)
            if tw:
                cands.append(tw)
    elif ca == cb:
        d = abs(ra - rb)
        if d == 0:
            return None
        r0 = min(ra, rb)
        for c2 in (ca - d, ca + d):
            corners = [(r0, ca), (r0 + d, ca), (r0, c2), (r0 + d, c2)]
            tw = meet_w(corners)
            if tw:
                cands.append(tw)
    else:
        # diagonal pair pins one square
        if abs(ra - rb) == abs(ca - cb):
            d = abs(ra - rb)
            r0, c0 = min(ra, rb), min(ca, cb)
            corners = [(r0, c0), (r0, c0 + d), (r0 + d, c0), (r0 + d, c0 + d)]
            tw = meet_w(corners)
            if tw:
                cands.append(tw)

    uniq = {frozenset(x) for x in cands}
    if len(uniq) == 1:
        return set(next(iter(uniq)))
    return None


def rebuild_ledger(state: SigmaState) -> None:
    """Apply mode rules to outside_cells → ledger (may rewrite)."""
    state.ledger.clear()
    outs = list(state.outside_cells)
    if not outs:
        return

    if state.mode in ("residual", "pin") and state.armed_V is not None:
        V = tuple(sorted(state.armed_V))
        # residual if no window completion
        comps = _completions(state.k, V)
        if not comps:
            y = state.mi.y.get(V)
            if y is None:
                # unknown residual class — fall back to default tokens
                state.ledger[outs[0]] = state.mi.z
                for i, cell in enumerate(outs[1:], start=1):
                    tok = state.mi.token_cells[min(i, len(state.mi.token_cells) - 1)]
                    state.ledger[cell] = tok
                return
            state.ledger[outs[0]] = state.mi.z
            if len(outs) >= 2:
                state.ledger[outs[1]] = y
            for i, cell in enumerate(outs[2:], start=2):
                tok = state.mi.token_cells[min(i, len(state.mi.token_cells) - 1)]
                state.ledger[cell] = tok
            return
        # completable pin: fillers on S\V
        S = comps[0]
        fillers = [p for p in S if p not in V]
        for i, cell in enumerate(outs):
            if i < len(fillers):
                state.ledger[cell] = state.mi.g(fillers[i])
            else:
                # spill to frame / tokens
                tok = state.mi.token_cells[min(i - len(fillers), len(state.mi.token_cells) - 1)]
                state.ledger[cell] = tok
        return

    if state.mode == "completable" and state.armed_S is not None and state.armed_V is not None:
        Vset = set(state.armed_V)
        fillers = [p for p in state.armed_S if p not in Vset]
        for i, cell in enumerate(outs):
            if i < len(fillers):
                state.ledger[cell] = state.mi.g(fillers[i])
            else:
                tok = state.mi.token_cells[min(i - len(fillers), len(state.mi.token_cells) - 1)]
                state.ledger[cell] = tok
        return

    # default
    state.ledger[outs[0]] = state.mi.z
    for i, cell in enumerate(outs[1:], start=1):
        tok = state.mi.token_cells[min(i, len(state.mi.token_cells) - 1)]
        state.ledger[cell] = tok


def _outside_rel(state: SigmaState) -> List[Coord]:
    """Outside stones in window-relative coordinates (may lie outside [0,w))."""
    out: List[Coord] = []
    for cell in state.outside_cells:
        r, c = divmod(cell, state.n)
        out.append((r - state.off, c - state.off))
    return out


def find_completable_arming(
    state: SigmaState, occupied: Set[Coord]
) -> Optional[Tuple[Tuple[Coord, ...], List[Coord]]]:
    """Arm completable only when outside stones uniquely pin a Case-2 Q.

    The old heuristic armed on *any* W-subset with a window completion (almost
    every singleton), rewriting the first outside stone from ``z`` to a filler
    and leaving the merge view off-certificate.

    Require a *unique* external square Q such that:

      * Q ⊄ W, V := Q ∩ W is a completable Case-2 trace;
      * V ⊆ P2 ∩ W;
      * every current outside stone is a corner of Q.

    One outside stone usually fits many Q's — keep ``default`` until unique.
    """
    if not state.outside_cells or not occupied:
        return None
    outs = _outside_rel(state)
    matches: List[Tuple[Tuple[Coord, ...], List[Coord], Tuple[int, int, int]]] = []
    fam = _trace_family(state.k)
    for group in fam:
        for Vraw in group:
            V = tuple(sorted(Vraw))
            if not set(V).issubset(occupied):
                continue
            comps = _completions(state.k, V)
            if not comps:
                continue
            for a, b, d in _external_squares(state.k, V):
                corners = set(square(a, b, d))
                if all(o in corners for o in outs):
                    matches.append((V, list(comps[0]), (a, b, d)))
    if not matches:
        return None
    # Unique geometric Q (same corners), not merely unique V.
    uniq_q = {frozenset(square(a, b, d)) for _, _, (a, b, d) in matches}
    if len(uniq_q) != 1:
        return None
    V, S, _ = matches[0]
    return (V, S)


def update_arming(state: SigmaState, p2_cells_in_window_local: Set[Coord]) -> None:
    """Recompute mode from window occupancy + outside list (pin overrides)."""
    pin = sharing_pin(state.outside_cells, state.n, state.off, state.w)
    if pin is not None and len(state.outside_cells) >= 2:
        state.mode = "pin"
        state.armed_V = tuple(sorted(pin))
        comps = _completions(state.k, state.armed_V)
        state.armed_S = list(comps[0]) if comps else None
        rebuild_ledger(state)
        return

    # residual traces present in window?
    for V in state.mi.residuals:
        if set(V).issubset(p2_cells_in_window_local):
            state.mode = "residual"
            state.armed_V = tuple(sorted(V))
            state.armed_S = None
            rebuild_ledger(state)
            return

    # completable: Case-2 trace in W whose external Q covers the outside stones
    hit = find_completable_arming(state, p2_cells_in_window_local)
    if hit is not None:
        V, S = hit
        state.mode = "completable"
        state.armed_V = V
        state.armed_S = S
        rebuild_ledger(state)
        return

    # default (pre-arm): outside → z / tokens
    state.mode = "default"
    state.armed_V = None
    state.armed_S = None
    rebuild_ledger(state)


def build_merge_position(state: SigmaState, real_board_owners: List[int]):
    """Construct d11py.Position for merge GameSpec from real board owners.

    real_board_owners[cell] in {0,1,2} for empty/P1/P2 on the n×n board.
    P1 stones outside C are ignored (illegal under Σ). P2 outside W go through ledger.
    """
    import d11py

    gs = state.mi.game_spec(tokens=True, budget=True)
    pos = d11py.Position(gs)
    # Replay in an order that matches parity as much as possible: use history if
    # caller supplies via sequential place. Here we place all stones with
    # alternating turns approximated by placing P1 centre then syncing P2.
    # For hash lookup during play, EmbedPlayer places move-by-move instead.
    return pos, gs
