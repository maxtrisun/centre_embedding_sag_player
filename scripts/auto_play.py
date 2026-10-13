#!/usr/bin/env python3
"""Batch auto-play: P1=exported certificate vs P2 for every available n.

Default P2 is pruned-random (stays on the proof DAG). Reports win/loss/error.

Examples:
  python3 auto_play.py                     # all finite n + merge(n=18)
  python3 auto_play.py --sizes 6,7,8       # subset
  python3 auto_play.py --games 5 --seed 1
  python3 auto_play.py --p2 random         # may leave proof tree
  python3 auto_play.py --skip-merge
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from play_game import (  # noqa: E402
    ARTIFACTS,
    list_certificates,
    parse_player,
    play,
    EmbedPlayer,
)


def available_boards(*, skip_merge: bool) -> List[int]:
    """Finite n with certificates, plus 18 if merge exists (stands for n>=18)."""
    ns: List[int] = []
    for row in list_certificates():
        if row["kind"] == "finite":
            ns.append(int(row["n"]))
        elif row["kind"] == "merge" and not skip_merge:
            ns.append(18)
    return sorted(set(ns))


def run_one(n: int, *, p2_spec: str, seed: int, max_plies: int) -> Dict[str, Any]:
    t0 = time.time()
    try:
        p1 = parse_player("cert", n, seed)
        p2 = parse_player(p2_spec, n, seed + 1)
        res = play(
            n,
            p1,
            p2,
            max_plies=max_plies or None,
            center_only_p1=isinstance(p1, EmbedPlayer),
        )
        return {
            "n": n,
            "ok": True,
            "winner": res.winner,
            "reason": res.reason,
            "plies": res.plies,
            "p1_win": res.winner == 1,
            "time_s": round(time.time() - t0, 3),
            "history": res.history,
            "error": None,
        }
    except Exception as e:  # noqa: BLE001 — collect per-game failures
        return {
            "n": n,
            "ok": False,
            "winner": None,
            "reason": "exception",
            "plies": 0,
            "p1_win": False,
            "time_s": round(time.time() - t0, 3),
            "history": [],
            "error": f"{type(e).__name__}: {e}",
        }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--sizes",
        default="all",
        help="Comma list of n, or 'all' (finite certs + 18 if merge present)",
    )
    ap.add_argument("--games", type=int, default=1, help="games per board")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--p2", default="pruned-random")
    ap.add_argument("--max-plies", type=int, default=0)
    ap.add_argument("--skip-merge", action="store_true")
    ap.add_argument(
        "--out",
        type=Path,
        default=ARTIFACTS / "auto_play_summary.json",
        help="JSON summary path",
    )
    args = ap.parse_args()

    if args.sizes.strip().lower() == "all":
        boards = available_boards(skip_merge=args.skip_merge)
    else:
        boards = [int(x) for x in args.sizes.split(",") if x.strip()]

    if not boards:
        print("no certificates found under artifacts/", file=sys.stderr)
        print("list: python3 play_game.py --list", file=sys.stderr)
        return 2

    print(
        f"auto-play boards={boards} games/board={args.games} p1=cert p2={args.p2}",
        flush=True,
    )

    rows: List[Dict[str, Any]] = []
    for n in boards:
        for g in range(args.games):
            seed = args.seed + 1000 * n + g
            print(f"[n={n} game={g+1}/{args.games} seed={seed}] …", flush=True)
            row = run_one(n, p2_spec=args.p2, seed=seed, max_plies=args.max_plies)
            row["game"] = g
            row["seed"] = seed
            rows.append(row)
            if row["ok"]:
                print(
                    f"  -> winner={row['winner']} reason={row['reason']} "
                    f"plies={row['plies']} t={row['time_s']}s",
                    flush=True,
                )
            else:
                print(f"  -> FAIL {row['error']}", flush=True)
                # short traceback for debug
                traceback.print_exc() if False else None

    # per-n aggregate
    by_n: Dict[int, Dict[str, Any]] = {}
    for r in rows:
        n = int(r["n"])
        agg = by_n.setdefault(
            n, {"n": n, "games": 0, "p1_wins": 0, "fails": 0, "errors": []}
        )
        agg["games"] += 1
        if not r["ok"]:
            agg["fails"] += 1
            agg["errors"].append(r["error"])
        elif r["p1_win"]:
            agg["p1_wins"] += 1

    summary = {
        "p1": "cert",
        "p2": args.p2,
        "games_per_board": args.games,
        "seed_base": args.seed,
        "boards": boards,
        "per_game": rows,
        "per_n": [by_n[n] for n in sorted(by_n)],
        "totals": {
            "games": len(rows),
            "p1_wins": sum(1 for r in rows if r.get("p1_win")),
            "fails": sum(1 for r in rows if not r.get("ok")),
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=2) + "\n")

    print("\n=== summary ===", flush=True)
    for agg in summary["per_n"]:
        print(
            f"n={agg['n']:2d}  P1_wins={agg['p1_wins']}/{agg['games']}  "
            f"fails={agg['fails']}",
            flush=True,
        )
    t = summary["totals"]
    print(
        f"TOTAL  P1_wins={t['p1_wins']}/{t['games']}  fails={t['fails']}",
        flush=True,
    )
    print(f"wrote {args.out}", flush=True)

    # exit 0 only if every finished game is a P1 win and no fails
    if t["fails"] or t["p1_wins"] != t["games"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
