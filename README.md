# Centre-Embedding SAG Player

Play and check exported **Player-1 certificates** for the centre-embedding
square-achievement game (SAG): interactive human vs certificate, and batch
auto-play.

This repository is **stage 1** of a staged open-source release:

1. **Now** — playable certificates + interactive / auto-play tools (this repo)
2. **Next** — paper
3. **Later** — engine / prover / export source and the rest of the code

You do **not** need to re-prove anything to try the player: finite DAGs
(`6 ≤ n < 18`) and the merge certificate (`n ≥ 18`) are shipped under
`artifacts/`. **C++ engine source is not included in this stage** — play
uses a prebuilt Python extension `d11py`.

---

## Screencasts

Human vs certificate demos: the certificate plays first as P1 (X),
and the human plays second as P2 (O). Both demos use merge + Σ
(`n ≥ 18`) with the large-board viewport (`--board-view center`).

Play the videos below, or use the download links to watch them locally.

**n = 100 (merge + Σ)** — [Download video](media/n100.webm)

<video src="media/n100.webm" controls width="720">
  <a href="media/n100.webm">media/n100.webm</a>
</video>

**n = 1000 (merge + Σ)** — [Download video](media/n1000.webm)

<video src="media/n1000.webm" controls width="720">
  <a href="media/n1000.webm">media/n1000.webm</a>
</video>

Suggested matching commands:

```bash
cd scripts
./d11_interact.sh --n 100 --board-view center
./d11_interact.sh --n 1000 --board-view center
```

---

## What you get

| Path | Role |
|------|------|
| `scripts/d11_interact.sh` | Human vs certificate (ASCII board) |
| `scripts/d11_play.sh` | Single game / list certificates / custom P2 |
| `scripts/run_auto_play.sh` | Batch auto-play over shipped boards |
| `artifacts/finite/` | Finite-n proof DAGs |
| `artifacts/embed/merge/` | Merge DAG for all `n ≥ 18` |
| `build/d11py*.so` | Prebuilt Python extension (Linux x86_64) |
| `media/` | Screencast demos (`n100.webm`, `n1000.webm`) |

Players take turns placing one stone on an empty cell of an `n×n` board.
P1 moves first. The first player to occupy all four corners of an
axis-aligned square wins. Tilted squares do not count, and the smallest
winning square is a `2×2` block.

For `n ≥ 18`, certificate-controlled P1 plays only inside a fixed central
`6×6` block, while P2 may play anywhere on the board. The online map Σ
translates the real position into the merge-certificate view.

---

## Requirements

| Item | Notes |
|------|--------|
| OS | Linux **x86_64** |
| Python | **3.11** or **3.13** (must match the shipped ABI tag in the `.so` name) |
| pip packages | **None** for play |

Check:

```bash
python3 --version
ls build/d11py.cpython-*-x86_64-linux-gnu.so
python3 -c "import sys; sys.path.insert(0,'build'); import d11py; print('d11py OK', d11py.__file__)"
```

The bundled extensions require Linux x86_64 and a matching CPython
3.11 or 3.13 interpreter. They cannot be loaded by native Windows
or macOS Python. Windows users need a compatible Linux environment,
such as WSL.

Engine source and rebuild instructions are planned for a later
release stage.

With conda, create a matching Python and run (use `bash`, not `sh`):

```bash
conda create -n d11py311 python=3.11 -y
conda activate d11py311
cd scripts
bash ./d11_interact.sh --n 6
```

---

## Quick start

```bash
cd scripts

# Which certificates are present?
./d11_play.sh --list

# Human vs certificate (you = P2 / O, cert = P1 / X)
./d11_interact.sh --n 6
./d11_interact.sh --n 18          # merge + Σ; any n≥18 works (e.g. 25)
./d11_interact.sh --n 100 --board-view center   # large-board viewport
./d11_interact.sh --n 30 --timing               # stderr per-move timings

# Single auto game (JSON): P1=cert, P2=pruned-random
./d11_play.sh --n 6
./d11_play.sh --n 18 --seed 1

# Batch auto-play over all shipped boards
./run_auto_play.sh
./run_auto_play.sh --sizes 6,7,8 --games 3 --seed 0
```

### Move input

At the `move>` prompt, rows and columns are zero-based: the top-left
cell is `(0, 0)`. For example, `2 3` selects the third row and fourth
column. Input always uses these real board coordinates (never overview
tile indices).

| Input | Meaning |
|-------|---------|
| `row col` | place a stone, e.g. `2 3` |
| `cell` | flat index `0 … n²-1` (row-major) |
| `rXcY` | e.g. `r2c3` |
| `legal` | list legal cells |
| `hist` | move history |
| `help` | list commands |
| `quit` | exit |

Legend: `X`=P1, `O`=P2, `.`=empty, `[ ]`=last move.

### Board views (large `n`)

Large boards do not fit a terminal as a full cell grid. Prefer a
**viewport** of real cells around the centre or last move; avoid relying
on the aggregated overview unless you want a whole-board summary.

Start with a viewport:

```bash
./d11_interact.sh --n 100 --board-view center
./d11_interact.sh --n 100 --board-view last
./d11_interact.sh --n 30 --timing          # choose / win-check timings on stderr
```

Or switch at `move>` (redraw only; does **not** consume a turn):

| Command | Display |
|---------|---------|
| `view auto` | full grid if it fits; otherwise overview tiles |
| `view overview` | whole board as aggregated tiles |
| `view center` | real cells around the board centre |
| `view last` | real cells around the last move |
| `view 12 13` | real cells around row 12, column 13 |
| `view full` | force full grid (may overflow the terminal) |

- `12 13` places a stone; `view 12 13` only changes the camera.
- Cell views label the visible row/column range and count hidden stones.
- Overview tiles may cover many cells: `X` = P1 only, `O` = P2 only,
  `*` = both, `.` = empty; brackets mark the tile that contains the last
  move. Row labels are ranges; column labels are tile starts.

`--board-view` choices: `auto` (default), `full`, `overview`, `center`,
`last`. Details: [`doc/play.md`](doc/play.md).

---

## Player strategies

The shipped certificates provide strategies for P1 (the first player).
By default, interactive mode uses certificate-controlled P1 against
a human P2. Batch mode uses certificate-controlled P1 against
a pruned-random P2.

Both sides implement `choose(view) -> legal_cell`. CLI specs:

| Spec | Typical seat | Behaviour |
|------|--------------|-----------|
| `cert` | P1 (default) | Finite DAG if `n<18`, else merge+Σ |
| `dag:PATH` | P1 | Explicit finite `proof.dag` |
| `embed:PATH` | P1 | Explicit merge DAG (`n≥18`) |
| `pruned-random` | P2 (batch default) | Random among engine-pruned replies; falls back to legal moves if none are returned |
| `random` | P2 | Uniform legal (may leave proof tree) |
| `human` | either | Terminal input |
| `script:PATH.py` | usually P2 | Module exporting `choose(view) -> int` |

Examples:

```bash
./d11_play.sh --n 6 --p2 random --seed 2
./d11_play.sh --n 10 --p1 cert --p2 script:./my_p2.py
./d11_interact.sh --n 6 --side p1    # you play P1; P2 = pruned-random
```

Custom P2 plugin:

```python
# my_p2.py
def choose(view) -> int:
    return list(view.legal)[0]
```

**Certificate coverage:** use `--p2 pruned-random` for certificate-oriented
replay. Unrestricted random or human moves may reach positions outside
the exported DAG. If the certificate player cannot provide a move,
play stops with an error. This error is not a win or loss under the
game rules.

More detail: [`doc/play.md`](doc/play.md), [`artifacts/VERIFY.md`](artifacts/VERIFY.md),
[`doc/sigma_spec.md`](doc/sigma_spec.md).

---

## Repository layout

```text
centre_embedding_sag_player/   # open-source repo root (stage 1)
  README.md
  requirements.txt
  artifacts/                   # shipped certificates
  build/                       # prebuilt d11py*.so only
  doc/                         # play + Σ notes
  media/                       # screencast demos
  scripts/                     # interact / play / auto-play
```

---

## Roadmap (staged release)

| Stage | Contents |
|-------|----------|
| **1 (this repo)** | Interactive + auto-play, certificates, prebuilt `d11py` |
| **2** | Paper |
| **3** | Engine / export / search source and remaining code |

Issues and discussion welcome once the remote is public; please keep play
questions tied to a concrete `--n`, seed, and whether you used `pruned-random`
or free play.
