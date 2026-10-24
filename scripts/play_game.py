#!/usr/bin/env python3
"""Unified play interface against arbitrary Player-2 strategies.

Batch (JSON result):
  ./d11_play.sh --list
  ./d11_play.sh --n 6                         # P1=cert, P2=pruned-random
  python3 play_game.py --n 6 --p1 dag:PATH --p2 pruned-random

Interactive (ASCII board, you vs certificate):
  ./d11_interact.sh --n 6                     # you are P2, cert is P1
  ./d11_play.sh --n 6 --interactive
  ./d11_play.sh --n 6 --interactive --side p1 # you play P1, cert unused
  ./d11_play.sh --n 18 --interactive          # merge+Σ cert vs you
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional, Protocol, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
ARTIFACTS = ROOT / "artifacts"
sys.path.insert(0, str(BUILD))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import d11py  # noqa: E402

from run_merge import MergeInstance  # noqa: E402
from sigma import SigmaState, rebuild_ledger, update_arming  # noqa: E402
from play_support import PositionHistory, TerminalBoard, square_winner_after  # noqa: E402

P1, P2 = 0, 1
SYM = {0: ".", 1: "X", 2: "O"}  # empty / P1 / P2


def finite_dag_path(n: int) -> Path:
    return ARTIFACTS / "finite" / f"n{n:02d}" / "proof.dag"


def merge_dag_path() -> Path:
    return ARTIFACTS / "embed" / "merge" / "proof.dag"


def list_certificates() -> List[dict]:
    rows: List[dict] = []
    finite = ARTIFACTS / "finite"
    if finite.is_dir():
        for d in sorted(finite.glob("n*")):
            meta_p, dag_p = d / "meta.json", d / "proof.dag"
            if not (meta_p.exists() and dag_p.exists()):
                continue
            meta = json.loads(meta_p.read_text())
            rows.append(
                {
                    "kind": "finite",
                    "n": meta.get("n"),
                    "path": str(dag_p),
                    "raw_bytes": meta.get("raw_bytes", dag_p.stat().st_size),
                    "dag_nodes": meta.get("dag_nodes"),
                    "pinned": meta.get("pinned_root"),
                    "play": f"--n {meta.get('n')} --p1 cert --p2 pruned-random",
                }
            )
    mp, mm = merge_dag_path(), ARTIFACTS / "embed" / "merge" / "meta.json"
    if mp.exists() and mm.exists():
        meta = json.loads(mm.read_text())
        rows.append(
            {
                "kind": "merge",
                "n": ">=18",
                "path": str(mp),
                "raw_bytes": meta.get("raw_bytes", mp.stat().st_size),
                "dag_nodes": meta.get("dag_nodes"),
                "play": "--n 18 --p1 cert --p2 pruned-random",
            }
        )
    return rows


def resolve_cert_player(n: int) -> Player:
    """Auto P1 from exported artifacts: finite DAG if n<18, else embed/merge."""
    if n < 18:
        path = finite_dag_path(n)
        if not path.exists():
            raise SystemExit(
                f"no finite certificate for n={n} at {path}\n"
                f"expected shipped artifact under artifacts/finite/ "
                f"(see artifacts/VERIFY.md)"
            )
        meta_p = path.parent / "meta.json"
        pinned = None
        if meta_p.exists():
            pinned = json.loads(meta_p.read_text())["pinned_root"]["cell"]
        return DagPlayer(path, n, pinned=pinned)
    path = merge_dag_path()
    if not path.exists():
        raise SystemExit(
            f"no merge certificate at {path}\n"
            "expected shipped artifact under artifacts/embed/merge/ "
            "(see artifacts/VERIFY.md)"
        )
    return EmbedPlayer(path, n)


@dataclass
class GameView:
    n: int
    to_move: int
    board: Sequence[int]  # 0 empty, 1 P1, 2 P2
    legal: Sequence[int]
    history: Sequence[int]


@dataclass
class GameResult:
    winner: Optional[int]  # 1 / 2 / None draw
    reason: str
    history: List[int] = field(default_factory=list)
    plies: int = 0


class Player(Protocol):
    def choose(self, view: GameView) -> int: ...


class RandomPlayer:
    def __init__(self, seed: int = 0) -> None:
        self.rng = random.Random(seed)

    def choose(self, view: GameView) -> int:
        return self.rng.choice(list(view.legal))


class PrunedRandomPlayer:
    """Random among sound-pruned P2 replies (stays on proof DAG)."""

    def __init__(self, n: int, seed: int = 0) -> None:
        self.n = n
        self.rng = random.Random(seed)
        self.gs = d11py.GameSpec(n, n)
        self.cfg = d11py.VerifierConfig()
        self.cfg.game = self.gs
        self._position_sync = PositionHistory(lambda: d11py.Position(self.gs))

    def choose(self, view: GameView) -> int:
        pos = self._position_sync.sync((i % 2, mv) for i, mv in enumerate(view.history))
        moves = list(d11py.pruned_moves(pos, self.cfg))
        if not moves:
            moves = list(view.legal)
        return self.rng.choice(moves)

def cell_rc(n: int, cell: int) -> Tuple[int, int]:
    return divmod(cell, n)


def rc_cell(n: int, r: int, c: int) -> int:
    return r * n + c


def render_board(
    n: int,
    board: Sequence[int],
    *,
    last: Optional[int] = None,
    mark_cells: Optional[Sequence[int]] = None,
) -> str:
    """ASCII board; last move wrapped in []; optional mark_cells with *."""
    marks = set(mark_cells or ())
    # Each cell token is width 3; column labels centred over tokens.
    col_hdr = "   " + "".join(f"{c:^3d}" for c in range(n))
    rule = "  +" + ("---" * n) + "+"
    lines = [col_hdr, rule]
    for r in range(n):
        cells: List[str] = []
        for c in range(n):
            i = r * n + c
            ch = SYM[board[i]]
            if i == last:
                tok = f"[{ch}]"
            elif i in marks:
                tok = f"*{ch}"
            else:
                tok = f" {ch} "
            cells.append(tok)
        lines.append(f"{r:2d}|" + "".join(cells) + "|")
    lines.append(rule)
    lines.append("  X=P1  O=P2  .=empty  [ ]=last")
    return "\n".join(lines)


def parse_move_token(s: str, n: int, legal: Sequence[int]) -> Optional[int]:
    """Parse '12' | '2 3' | '2,3' | 'r2c3' into a legal cell, else None."""
    s = s.strip().lower().replace(",", " ")
    if not s:
        return None
    if s.startswith("r") and "c" in s:
        try:
            body = s[1:]
            r_s, c_s = body.split("c", 1)
            r, c = int(r_s), int(c_s)
            if not (0 <= r < n and 0 <= c < n):
                return None
            cell = rc_cell(n, r, c)
            return cell if cell in legal else None
        except ValueError:
            return None
    parts = s.split()
    if len(parts) == 1:
        try:
            cell = int(parts[0])
        except ValueError:
            return None
        return cell if cell in legal else None
    if len(parts) == 2:
        try:
            r, c = int(parts[0]), int(parts[1])
            if not (0 <= r < n and 0 <= c < n):
                return None
            cell = rc_cell(n, r, c)
        except ValueError:
            return None
        return cell if cell in legal else None
    return None


class HumanPlayer:
    """Terminal human: accepts cell / row col / quit (optional board redraw)."""

    def __init__(self, label: str = "you", *, show_board: bool = True) -> None:
        self.label = label
        self.show_board = show_board
        self.renderer = None

    def choose(self, view: GameView) -> int:
        if self.renderer is None:
            self.renderer = TerminalBoard()
        if self.show_board:
            last = view.history[-1] if view.history else None
            print()
            print(self.renderer.render(view.n, view.board, last=last))
        side = view.to_move + 1
        print(
            f"\n[{self.label}] P{side} to move | empties={len(view.legal)} | "
            f"plies={len(view.history)}"
        )
        print("  enter: <row> <col> | <cell> | view center | help | quit")
        while True:
            try:
                raw = input("move> ").strip()
            except EOFError:
                raise SystemExit("EOF — abort game") from None
            if not raw:
                continue
            cmd = raw.lower()
            if cmd in {"q", "quit", "exit"}:
                raise SystemExit("quit")
            if cmd in {"h", "help", "?"}:
                print("  row col   e.g. 2 3")
                print("  cell      flat index 0..n*n-1 (row-major)")
                print("  rXcY      e.g. r2c3")
                print("  legal     list legal cells")
                print("  hist      move history")
                print("  view auto|overview|center|last|full, or view ROW COL")
                print("  quit")
                continue
            if cmd == "view" or cmd.startswith("view "):
                try:
                    self.renderer.set_view(raw[4:].strip() or "auto", view.n)
                    print(self.renderer.render(view.n, view.board,
                        last=view.history[-1] if view.history else None))
                except ValueError as exc:
                    print(f"  {exc}")
                continue
            if cmd == "legal":
                coords = [f"{c}({c // view.n},{c % view.n})" for c in view.legal]
                print("  " + ", ".join(coords[:80]))
                if len(coords) > 80:
                    print(f"  ... +{len(coords) - 80} more")
                continue
            if cmd in {"hist", "history"}:
                print("  " + " ".join(str(x) for x in view.history) or "(empty)")
                continue
            cell = parse_move_token(raw, view.n, view.legal)
            if cell is None:
                print("  illegal / unreadable — try 'help' or 'legal'")
                continue
            return cell


class CallablePlayer:
    def __init__(self, fn: Callable[[GameView], int]) -> None:
        self.fn = fn

    def choose(self, view: GameView) -> int:
        return self.fn(view)


class DagPlayer:
    """P1 from a finite-n proof DAG. Fail-loud on hash miss."""

    def __init__(self, dag_path: Path, n: int, pinned: Optional[int] = None) -> None:
        self.dag = d11py.ProofDag.load_file(str(dag_path))
        if self.dag.n != n or self.dag.center != n:
            raise ValueError(
                f"DAG is G({self.dag.center},{self.dag.n}), play asked n={n}"
            )
        self.n = n
        self.gs = d11py.GameSpec(n, n)
        self.pos = d11py.Position(self.gs)
        self._position_sync = PositionHistory(lambda: d11py.Position(self.gs), self.pos)
        self.pinned = pinned
        self._plies = 0

    def choose(self, view: GameView) -> int:
        if view.n != self.n:
            raise RuntimeError("n mismatch")
        # History is authoritative; append only to an unchanged native prefix.
        self.pos = self._position_sync.sync((i % 2, mv) for i, mv in enumerate(view.history))
        self._plies = len(view.history)

        key = self.pos.hash()
        ans = self.dag.or_move(key)
        if ans is not None:
            move, _child = ans
            if move not in view.legal:
                raise RuntimeError(f"DagPlayer: DAG move {move} not legal")
            return int(move)

        # TW / fork leaf: DAG has no OR edge; synthesize the witnessing move.
        cfg = d11py.VerifierConfig()
        cfg.game = self.gs
        move = int(d11py.find_p1_certificate_move(self.pos, cfg))
        if move < 0 or move not in view.legal:
            raise RuntimeError(
                f"DagPlayer: position hash {key} not on proof DAG "
                f"(history={list(view.history)}) — no certificate / off-tree"
            )
        return move

class EmbedPlayer:
    """P1 for n>=18 via Σ + merge DAG. Fail-loud on merge-hash miss."""

    def __init__(self, dag_path: Path, n: int) -> None:
        if n < 18:
            raise ValueError("EmbedPlayer requires n>=18")
        self.n = n
        self.k = 6
        self.dag = d11py.ProofDag.load_file(str(dag_path))
        self.state = SigmaState(k=6, n=n, mi=MergeInstance(6))
        self.merge_gs = self.state.mi.game_spec(tokens=True, budget=True)
        self.merge_pos = d11py.Position(self.merge_gs)
        self._position_sync = PositionHistory(lambda: d11py.Position(self.merge_gs), self.merge_pos)
        self.real_gs = d11py.GameSpec(n, n)
        self.history: List[int] = []

    def _window_p2_locals(self, board: Sequence[int]):
        s = set()
        off = self.state.off
        w = self.state.w
        for r in range(off, off + w):
            for c in range(off, off + w):
                cell = r * self.n + c
                if board[cell] == 2:
                    s.add((r - off, c - off))
        return s

    def _rebuild_merge(self, view: GameView, board: List[int]) -> None:
        """Place history into merge_pos using the current Σ ledger."""
        mapped = []
        for i, cell in enumerate(view.history):
            side = P1 if (i % 2 == 0) else P2
            if side == P1:
                loc = self.state.window_local(cell)
                if loc is None or not (
                    self.state.k <= loc[0] < 2 * self.state.k
                    and self.state.k <= loc[1] < 2 * self.state.k
                ):
                    raise RuntimeError(f"P1 move {cell} outside centre C")
                mapped.append((P1, self.state.mi.g(loc)))
            elif self.state.in_window(cell):
                mcell = self.state.real_to_merge_window_cell(cell)
                assert mcell is not None
                mapped.append((P2, mcell))
            else:
                mcell = self.state.ledger.get(cell)
                if mcell is None:
                    raise RuntimeError(f"no ledger for outside cell {cell}")
                mapped.append((P2, mcell))

        # A changed Sigma ledger changes earlier mapped moves and therefore
        # forces a full rebuild; otherwise only new moves are appended.
        self.merge_pos = self._position_sync.sync(mapped)

    def _lookup_merge_move(self) -> Optional[int]:
        """OR-edge move, else TW/cert witnessing move; None if neither."""
        key = self.merge_pos.hash()
        ans = self.dag.or_move(key)
        if ans is not None:
            return int(ans[0])
        cfg = d11py.VerifierConfig()
        cfg.game = self.merge_gs
        syn = int(d11py.find_p1_certificate_move(self.merge_pos, cfg))
        return syn if syn >= 0 else None

    def choose(self, view: GameView) -> int:
        board = list(view.board)
        outs = [c for c in view.history if board[c] == 2 and not self.state.in_window(c)]
        self.state.outside_cells = outs
        update_arming(self.state, self._window_p2_locals(board))
        self._rebuild_merge(view, board)

        mcell = self._lookup_merge_move()
        # Pin/completable ledger rewrite can leave a geometrically justified
        # view that the pruned merge DAG never stored. Fall back to default
        # (outside → z/tokens), which is always a legal merge P2 reading.
        if mcell is None and self.state.mode != "default" and outs:
            self.state.mode = "default"
            self.state.armed_V = None
            self.state.armed_S = None
            rebuild_ledger(self.state)
            self._rebuild_merge(view, board)
            mcell = self._lookup_merge_move()

        if mcell is None:
            key = self.merge_pos.hash()
            raise RuntimeError(
                f"EmbedPlayer: merge hash {key} not on proof DAG "
                f"(Σ mode={self.state.mode}, outside={len(outs)}, "
                f"plies={len(view.history)}). "
                "Usually P2 played a sound-pruned window move, so the "
                "merge view left the exported certificate tree."
            )

        mr, mc = divmod(int(mcell), self.state.mi.N)
        lr, lc = mr - self.state.mi.off, mc - self.state.mi.off
        if not (self.state.k <= lr < 2 * self.state.k and self.state.k <= lc < 2 * self.state.k):
            raise RuntimeError(
                f"EmbedPlayer: merge move {mcell} maps to local {(lr, lc)} outside C"
            )
        rr, rc = lr + self.state.off, lc + self.state.off
        real = rr * self.n + rc
        if real not in view.legal:
            raise RuntimeError(f"EmbedPlayer: mapped move {real} not legal")
        return real


def terminal_winner(n: int, board: List[int]) -> Optional[int]:
    """Axis-aligned square win check (slow, fine for play)."""
    for s in range(1, n):
        for r in range(n - s):
            for c in range(n - s):
                cells = (
                    r * n + c,
                    r * n + (c + s),
                    (r + s) * n + c,
                    (r + s) * n + (c + s),
                )
                v = board[cells[0]]
                if v != 0 and all(board[x] == v for x in cells):
                    return v
    return None


def play(
    n: int,
    p1: Player,
    p2: Player,
    *,
    max_plies: Optional[int] = None,
    center_only_p1: bool = False,
    announce: bool = False,
    p1_name: str = "P1",
    p2_name: str = "P2",
    board_renderer: Optional[TerminalBoard] = None,
    report_timing: bool = False,
) -> GameResult:
    if n <= 0 or (max_plies is not None and max_plies < 0):
        raise ValueError("n must be positive and max_plies nonnegative")
    viewer = board_renderer or TerminalBoard()
    for player in (p1, p2):
        if isinstance(player, HumanPlayer):
            player.renderer = viewer
    board = [0] * (n * n)
    history: List[int] = []
    limit = max_plies if max_plies is not None else n * n
    names = (p1_name, p2_name)

    if announce:
        print(f"\n=== G({n},{n}) interactive ===")
        print(f"  {p1_name}=X (P1)   {p2_name}=O (P2)")
        if center_only_p1:
            off = (n - 6) // 2
            print(f"  P1 confined to centre 6×6 window [{off}..{off+5}]²")
        print(viewer.render(n, board))

    for ply in range(limit):
        side = P1 if ply % 2 == 0 else P2
        if center_only_p1 and side == P1:
            k = 6
            off = (n - k) // 2
            legal = [r*n+c for r in range(max(0, off), min(n, off+k))
                     for c in range(max(0, off), min(n, off+k)) if board[r*n+c] == 0]
        else:
            legal = [i for i, v in enumerate(board) if v == 0]
        if not legal:
            return GameResult(None, "no_moves", history, ply)

        view = GameView(n=n, to_move=side, board=board, legal=legal, history=history)
        mover = p1 if side == P1 else p2
        is_human = isinstance(mover, HumanPlayer)
        if announce and not is_human:
            print(f"\n... {names[side]} thinking ...", flush=True)
        started = time.perf_counter() if report_timing else 0.0
        mv = mover.choose(view)
        choose_s = time.perf_counter()-started if report_timing else 0.0
        if mv not in legal:
            return GameResult(3 - (side + 1), f"illegal_move_by_{side+1}", history, ply)
        board[mv] = side + 1
        history.append(mv)
        r, c = cell_rc(n, mv)
        if announce:
            print(f"\n{names[side]} plays cell {mv}  (row={r}, col={c})")
            print(viewer.render(n, board, last=mv))

        started = time.perf_counter() if report_timing else 0.0
        w = square_winner_after(n, board, mv)
        if report_timing:
            print(f"[timing] P{side+1} choose={choose_s:.6f}s "
                  f"win_check={time.perf_counter()-started:.6f}s", file=sys.stderr, flush=True)
        if w is not None:
            if announce:
                print(f"\n*** {names[w - 1]} wins by square ***")
            return GameResult(w, "square", history, ply + 1)

    if announce:
        print("\n*** draw (board full / max plies) ***")
    return GameResult(None, "max_plies", history, limit)


def parse_player(spec: str, n: int, seed: int) -> Player:
    if spec == "cert":
        return resolve_cert_player(n)
    if spec == "random":
        return RandomPlayer(seed)
    if spec == "pruned-random":
        return PrunedRandomPlayer(n, seed)
    if spec == "human":
        return HumanPlayer()
    if spec.startswith("dag:"):
        path = Path(spec[4:])
        meta = path.parent / "meta.json"
        pinned = None
        if meta.exists():
            pinned = json.loads(meta.read_text())["pinned_root"]["cell"]
        return DagPlayer(path, n, pinned=pinned)
    if spec.startswith("embed:"):
        return EmbedPlayer(Path(spec[6:]), n)
    if spec.startswith("script:"):
        # script:path.py defining choose(view)->int
        import importlib.util

        p = Path(spec[7:])
        u = importlib.util.spec_from_file_location("p2mod", p)
        assert u and u.loader
        mod = importlib.util.module_from_spec(u)
        u.loader.exec_module(mod)
        return CallablePlayer(mod.choose)
    raise SystemExit(
        f"unknown player spec: {spec}\n"
        "P1: cert|dag:PATH|embed:PATH|random|human\n"
        "P2: pruned-random|random|human|script:PATH"
    )


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--n", type=int, default=0, help="board size (required unless --list)")
    ap.add_argument(
        "--p1",
        default=None,
        help="cert|dag:PATH|embed:PATH|random|human (default: cert, or human if --side p1)",
    )
    ap.add_argument(
        "--p2",
        default=None,
        help="pruned-random|random|human|script:PATH "
        "(default: pruned-random batch / human interactive)",
    )
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--max-plies", type=int, default=0)
    ap.add_argument("--board-view", choices=TerminalBoard.MODES, default="auto",
                    help="interactive board: auto fits the terminal; full preserves the wide grid")
    ap.add_argument("--timing", action="store_true", help="report initialization and per-move timings on stderr")
    ap.add_argument(
        "--list",
        action="store_true",
        help="list exported certificates and suggested play commands",
    )
    ap.add_argument(
        "--interactive",
        "-i",
        action="store_true",
        help="ASCII interactive game (default: you=P2 vs certificate P1)",
    )
    ap.add_argument(
        "--side",
        choices=("p1", "p2"),
        default="p2",
        help="with --interactive: which seat you take (default p2)",
    )
    ap.add_argument(
        "--json",
        action="store_true",
        help="always print final JSON result (on by default unless --interactive)",
    )
    args = ap.parse_args()

    if args.list:
        rows = list_certificates()
        print(json.dumps(rows, indent=2))
        if not rows:
            print(
                "no certificates under artifacts/; see artifacts/VERIFY.md",
                file=sys.stderr,
            )
        return 0

    if args.n <= 0:
        ap.error("--n is required unless --list")
    if args.max_plies < 0:
        ap.error("--max-plies must be nonnegative")

    interactive = bool(args.interactive)
    # Resolve player specs: interactive defaults to cert (P1) vs you (P2).
    if interactive and args.p1 is None and args.p2 is None:
        if args.side == "p2":
            p1_spec, p2_spec = "cert", "human"
        else:
            p1_spec, p2_spec = "human", "pruned-random"
    else:
        p1_spec = args.p1 or "cert"
        p2_spec = args.p2 or ("human" if interactive else "pruned-random")

    if interactive:
        print("Loading players and certificates...", file=sys.stderr, flush=True)
    started = time.perf_counter()
    p1 = parse_player(p1_spec, args.n, args.seed)
    p2 = parse_player(p2_spec, args.n, args.seed + 1)
    if args.timing:
        print(f"[timing] initialization={time.perf_counter()-started:.6f}s", file=sys.stderr, flush=True)
    if interactive:
        for hp in (p1, p2):
            if isinstance(hp, HumanPlayer):
                hp.label = "you"
                hp.show_board = False  # play() already redraws after each ply

    center_only = isinstance(p1, EmbedPlayer)
    p1_name = "cert" if p1_spec in ("cert",) or p1_spec.startswith(("dag:", "embed:")) else p1_spec
    p2_name = p2_spec if not p2_spec.startswith("script:") else "script"
    if isinstance(p1, HumanPlayer):
        p1_name = "you"
    if isinstance(p2, HumanPlayer):
        p2_name = "you"
    if isinstance(p1, DagPlayer):
        p1_name = "cert-DAG"
    if isinstance(p1, EmbedPlayer):
        p1_name = "cert-Σ"

    res = play(
        args.n,
        p1,
        p2,
        max_plies=args.max_plies or None,
        center_only_p1=center_only,
        announce=interactive,
        p1_name=p1_name,
        p2_name=p2_name,
        board_renderer=TerminalBoard(args.board_view),
        report_timing=args.timing,
    )

    payload = {
        "n": args.n,
        "p1": p1_spec,
        "p2": p2_spec,
        "winner": res.winner,
        "reason": res.reason,
        "plies": res.plies,
        "history": res.history,
    }
    if interactive:
        print("\n--- result ---")
        if res.winner == 1:
            print(f"winner: {p1_name} (P1)  reason={res.reason}  plies={res.plies}")
        elif res.winner == 2:
            print(f"winner: {p2_name} (P2)  reason={res.reason}  plies={res.plies}")
        else:
            print(f"draw  reason={res.reason}  plies={res.plies}")
        print("history:", " ".join(str(x) for x in res.history))
        if args.json:
            print(json.dumps(payload))
    else:
        print(json.dumps(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
