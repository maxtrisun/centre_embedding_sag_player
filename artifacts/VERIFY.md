# Verifying play certificates

This repo ships exported P1 certificates used by the interactive / auto-play tools.

## Layout

```text
artifacts/
  VERIFY.md
  export_summary.json
  finite/nXX/{meta.json, proof.dag}   # 6 <= n < 18
  embed/merge/{meta.json, proof.dag}  # n >= 18 (merge + online Σ)
  embed/sigma_spec.md
```

## Check what is playable

```bash
cd scripts
./d11_play.sh --list
```

| Board size | P1 certificate |
|------------|----------------|
| `6 <= n < 18` | `artifacts/finite/nXX/proof.dag` |
| `n >= 18` | `artifacts/embed/merge/proof.dag` + online Σ (`scripts/sigma.py`) |

## Recommended play modes

P1 defaults to exported certificate (`cert`); batch P2 defaults to `pruned-random`
(stays on the proof DAG).

```bash
cd scripts
./d11_play.sh --n 6                          # P1=cert, P2=pruned-random
./d11_interact.sh --n 6                      # you vs cert
./d11_play.sh --n 18 --p2 pruned-random      # merge+Σ
./run_auto_play.sh --games 1                 # all shipped boards
```

## Notes

- Prefer `--p2 pruned-random` so P2 replies stay in the sound-pruned set stored in the DAG.
- Plain `--p2 random` (or free human moves) may leave the proof tree; `DagPlayer` fails loud.
- For `n >= 18`, P1 is confined to the centre `6×6` block; Σ maps the real board into the merge view.
- Full prover / export pipeline will arrive in a later open-source stage; this package is for play and certificate checks.
