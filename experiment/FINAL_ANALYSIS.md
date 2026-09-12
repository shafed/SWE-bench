# Final analyzed experiment

Date: 2026-09-12

This file is the post-experiment source of truth for **which runs are included in the final analysis**. It does not modify or replace the frozen pre-run protocol files.

## Final empirical sample

The completed analysis uses the original 12-instance **v1 SWE-bench Verified sample** from `experiment/preregistration/tasks-main.txt`.

The final comparison is not the later 12-instance v4 orchestration-suitability sample. The attempted v4 main series was stopped because its resource/token cost was too high to finish within the project constraints.

## Conditions actually compared

One SINGLE baseline and three MULTI treatment variants are available on the same v1 task set.

### 1. Original MULTI treatment

Series: `experiment/runs/main-20260906`

- SINGLE + MULTI both completed.
- MULTI instruction: delegate at least one self-contained subtask; the model chooses what to delegate, how many subagents to use, and whether they run sequentially or in parallel.
- Result: SINGLE 9/12 resolved, MULTI 8/12 resolved.

### 2. Newer model-directed MULTI treatment

Series: `experiment/runs/main-model-directed-v1`

- SINGLE + MULTI completed, but `patch.diff`, `metrics.json`, `metadata.json` and `input/` were later lost.
- Patches were reconstructed from preserved traces; details and limitations are recorded in `RECONSTRUCTION.md`.
- MULTI treatment at run time is identified from commit `a413433`: substantive delegated problem solving is required before completion; the lead agent chooses decomposition, roles, count and scheduling; post-hoc review-only delegation is insufficient.
- Reconstructed result: SINGLE 9/12 resolved, MULTI 8/12 resolved.

### 3. v4 workstream-oriented prompt on the v1 sample

Series: `experiment/runs/main-v4prompt-v1`

- MULTI only.
- The treatment is the current `experiment/execution/multi-treatment.txt` (workstream-oriented orchestration).
- Result: MULTI 6/12 resolved.
- For descriptive comparison, this series is compared with the earlier SINGLE baseline from `main-20260906` on the same 12 tasks. It is **not** a same-session SINGLE/MULTI pair.

## Reported quality summary

| Condition | Resolved |
| --- | ---: |
| SINGLE baseline (`main-20260906`) | 9/12 |
| MULTI original prompt | 8/12 |
| MULTI newer model-directed prompt | 8/12 |
| MULTI v4 workstream-oriented prompt | 6/12 |

The two first MULTI variants have the same per-instance resolved pattern. The v4 prompt loses two additional tasks relative to those MULTI variants (`matplotlib__matplotlib-25775` and `pylint-dev__pylint-8898`) while `sympy__sympy-15017` remains unresolved in all three MULTI variants and resolved in the SINGLE baseline.

## Resource summary

The preserved analysis tables show increasing orchestration cost as the prompt becomes more prescriptive:

| Condition | Total tokens, sum / median | Output tokens, sum / median | Reported cost, USD | Wall-clock, sum / median |
| --- | ---: | ---: | ---: | ---: |
| SINGLE baseline | 18.17M / 1.48M | 147k / 13.8k | 6.74 | 44 min / 218 s |
| MULTI original prompt | 19.19M / 1.42M | 192k / 13.9k | 7.88 | 39 min / 165 s |
| SINGLE model-directed series | 23.41M / 1.67M | 178k / 13.6k | 8.26 | unavailable |
| MULTI model-directed | 22.73M / 1.91M | 254k / 21.5k | 9.40 | unavailable |
| MULTI v4 prompt | 25.93M / 1.96M | 298k / 24.2k | 10.73 | 73 min / 320 s |

Cost values are Claude Code/modelUsage estimates, not billing records.

## Status of `main-v4-20260911`

`experiment/runs/main-v4-20260911` is an **aborted partial attempt** at the later v4 sample and is excluded from final outcome analysis.

It contains completed runs for only the first part of the scheduled series plus several infrastructure/session-limit attempts. The series was not completed because the token/resource cost was too high for the project budget. It must not be described as the completed main experiment.

The frozen v4 selection, workstream treatment, adherence protocol and harness card remain useful as design history and as the source of the third prompt, but the final empirical evidence comes from applying the three MULTI prompt variants to the v1 sample.

## Interpretation boundary

The final study therefore supports a narrower claim than the planned v4 design:

- it compares **prompted subagent-orchestration policies** against a no-delegation SINGLE baseline on the same small SWE-bench Verified sample;
- it can describe how stronger orchestration instructions changed quality and resource use on those 12 tasks;
- it does **not** provide the planned v4 stratified test of orchestration-friendly vs single-friendly vs orchestration-risky tasks;
- with 12 tasks and one run per condition, findings are descriptive and should not be generalized as a universal effect of multi-agent systems.

## Source tables

- `experiment/runs/main-20260906/runs-table.tsv`
- `experiment/runs/main-model-directed-v1/RECONSTRUCTION.md`
- `experiment/runs/main-model-directed-v1/results-reconstructed.tsv`
- `experiment/runs/main-v4prompt-v1/runs-table.tsv`
- evaluator reports under `logs/evaluation/`
