# Centre-Embedding SAG Player

人机 / 自动对弈入口：用已导出的 **P1 证书**（有限 DAG 与 merge+Σ）体验与校验。

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

Human vs certificate (you = P2). Open the files locally if your Markdown viewer
does not embed video.

**n = 6 (finite DAG)** — [`media/n6.webm`](media/n6.webm)

<video src="media/n6.webm" controls width="720">
  <a href="media/n6.webm">media/n6.webm</a>
</video>

**n = 30 (merge + Σ)** — [`media/n30.webm`](media/n30.webm)

<video src="media/n30.webm" controls width="720">
  <a href="media/n30.webm">media/n30.webm</a>
</video>

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
| `media/` | Screencast demos (`n6.webm`, `n30.webm`) |

Game (short): `n×n` board; axis-aligned squares only (no tilted); smallest win is
the four corners of a `2×2` block. For `n ≥ 18`, certificate P1 only plays inside
a fixed centre `6×6` block and reads the board through an online map Σ onto the
merge certificate.

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

If import fails (wrong Python version, macOS, or non-x86_64), this stage-1
binary package will not run on your machine. Engine source and rebuild
instructions will arrive in a later open-source stage.

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

# Single auto game (JSON): P1=cert, P2=pruned-random
./d11_play.sh --n 6
./d11_play.sh --n 18 --seed 1

# Batch auto-play over all shipped boards
./run_auto_play.sh
./run_auto_play.sh --sizes 6,7,8 --games 3 --seed 0
```

Move input at `move>`:

| Input | Meaning |
|-------|---------|
| `row col` | e.g. `2 3` |
| `cell` | flat index `0 … n²-1` (row-major) |
| `rXcY` | e.g. `r2c3` |
| `legal` / `hist` / `quit` | helpers |

Legend: `X`=P1, `O`=P2, `.`=empty, `[ ]`=last move.

---

## Player strategies

Both sides implement `choose(view) -> legal_cell`. CLI specs:

| Spec | Typical seat | Behaviour |
|------|--------------|-----------|
| `cert` | P1 (default) | Finite DAG if `n<18`, else merge+Σ |
| `dag:PATH` | P1 | Explicit finite `proof.dag` |
| `embed:PATH` | P1 | Explicit merge DAG (`n≥18`) |
| `pruned-random` | P2 (batch default) | Random among sound-pruned replies (stays on DAG) |
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

**Review tip:** use `--p2 pruned-random` so play stays on the exported certificate
tree. Free `random` / aggressive human moves can leave the DAG; finite `DagPlayer`
then fails loud (by design). That means “off the checkable certificate path”, not
a silent rewrite of the theorem.

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
