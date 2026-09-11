# main-model-directed-v1 — reconstructed patches and evaluation

Claude Code series on the 12 v1 task instances (`main-20260906` sample),
SINGLE and MULTI, run 2026-09-11 05:00–07:53 UTC (first and last
orchestration-gate event).

## What was lost

Only `trace.jsonl` and `orchestration-gate/events.jsonl` survive per run —
exactly the files matched by `.gitignore:166 *.jsonl`. `patch.diff`,
`metrics.json`, `metadata.json`, `input/` and the rest were never committed
and are gone. Every affected directory has mtime 2026-09-11 15:29:57 +0300,
between `git pull` (15:29:34, shell history) and the start of a rebase
(15:30:23, reflog); the survivor pattern is what removing untracked files while
keeping ignored ones produces. The exact command was not recorded.

The MULTI treatment text is therefore not on disk for these runs. The
`multi-treatment.txt` committed when the series started is `a413433`
(07:43 +0300, "Enforce delegation before multi-agent completion"): lead agent,
substantive delegated problem solving required, model decides what and how to
delegate, post-hoc review-only delegation insufficient, gate enabled. This is
inferred from timing, not read from the run's own `input/treatment.txt`.

## Reconstruction

`experiment/execution/reconstruct_patch.py main-model-directed-v1` replays, in
a fresh container of each task image, every successful Edit/Write (parent and
subagents, in tool-result order) plus the hand-audited Bash commands with a net
effect on `/testbed` (`BASH_EFFECTS`), then collects the patch like
`runner.py` (`git add -A && git diff --cached <base> --binary`).

Checkpoints compare the replayed tree with what the agent saw at each
`git diff`, `git status` and Read of a `/testbed` file. Per run:
`reconstruction.json`, `patch-reconstructed.diff`.

- Replay failures: 0 edits/writes failed to apply. One benign Bash failure
  (pytest-5787/single op76: the second `git stash drop` found no entry; all
  later checkpoints match).
- 21/24 runs: the last checkpoint after the last change matches.
- 3/24 runs have no checkpoint after their final 1–2 edits
  (pylint-4551/single: ChangeLog ×2; scikit-learn-25102/single:
  `doc/whats_new/v1.3.rst`; sphinx-7757/single: `sphinx/util/inspect.py`);
  those edits applied to an exactly matching `old_string`, earlier checkpoints
  all match.
- Remaining checkpoint mismatches (2, pylint-4551/multi) concern `classes.dot`,
  a test artefact the agent later deleted, and a `grep`-filtered porcelain
  output; the following full porcelain checkpoint matches.
- Negative controls: dropping the last Edit (django-13449/multi) fails the final
  checkpoints; omitting the stash effects (pytest-5787/single) fails the
  intermediate ones.
- Untracked files produced only by commands that were not replayed (test
  artefacts) cannot be reproduced.

No reconstructed patch is byte-identical to the corresponding
`main-20260906` patch; 10/24 touch a different file set.

## Evaluation

```
swebench eval verified -p predictions-<cond>-reconstructed.jsonl \
  -r main-model-directed-v1-reconstructed-<cond> -j 2
```

Both exited 0; 0 infrastructure failures, 0 empty patches. Ran while an
OpenCode pilot was using the same host.

- SINGLE resolved 9/12, MULTI resolved 8/12 — the same per-instance pattern as
  `main-20260906` (only discordant pair: sympy-15017, SINGLE only).
- pylint-4551 is reported "ambiguous" in both conditions (as in
  `main-20260906`): the evaluation tests import `get_annotation` from
  `pylint.pyreverse.utils`, which neither patch defines, so collection fails.
- Tokens from `runner.token_accounting` on the traces (all `complete`): total
  23.41M SINGLE vs 22.73M MULTI; `modelUsage` cost $8.26 vs $9.40.

Per-run table: `results-reconstructed.tsv`. These outcomes rest on
reconstructed patches and must be reported as such.
