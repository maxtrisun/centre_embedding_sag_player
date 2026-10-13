# Online centre-embedding strategy Σ (paper Thm.lift)

Used by `EmbedPlayer` for all \(n\ge 18\). P1 answers only inside a fixed
central \(6\times 6\) block \(C\), reading the real board as a merge/window
view \(M\) and playing \(\sigma_M(M)\).

## Rules (priority order)

1. **Pin (overrides).** If two outside-\(W\) stones pin a unique \(W\)-meeting
   square \(Q^*\) (sharing lemma), arm residual or completable for \(Q^*\) and
   **rebuild** the outside-stone ledger so those stones occupy \(z,y_{V^*}\) or
   \(S^*\setminus V^*\). Occupancy inside \(W\) and P1 stones in \(C\) are
   unchanged.
2. **Residual armed.** Else if \(\mathrm{real}_{P2}\cap W\) already contains a
   residual trace \(V=\{c,f\}\), map first outside stone → \(z\), second →
   \(y_V\).
3. **Completable armed.** Else if a completable trace \(V\) with witness
   \(S\supseteq V\), \(S\subseteq W\) is present in \(W\), map outside stones to
   fillers on \(S\setminus V\) (then frame) and follow \(\sigma_0\) on that
   shadow. A second outside stone triggers (1) if the pinned trace differs.
4. **Default (pre-arm).** Map first outside stone → \(z\), further → unused
   tokens (budget/race reading).

This is **not** DFS search backtracking: real moves are never undone; only the
outside-stone ledger may be rewritten on pin rebuild.

## Implementation

See `scripts/sigma.py` and `scripts/play_game.py` (`EmbedPlayer`).
The merge certificate DAG supplies \(\sigma_M\) via hash lookup of the merge
view position.
