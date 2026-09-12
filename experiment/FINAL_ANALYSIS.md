# Final analyzed experiment

Date: 2026-09-12

This file is the post-experiment source of truth for **which runs are included in the final analysis**. It does not modify or replace the frozen pre-run protocol files.

## Final empirical sample

The completed analysis uses the original 12-instance **v1 SWE-bench Verified sample** from `experiment/preregistration/tasks-main.txt`.

The final comparison is not the later 12-instance v4 orchestration-suitability sample. The attempted v4 main series was stopped because its resource/token cost was too high to finish within the project constraints.

## Conditions actually compared

Two completed paired SINGLE/MULTI series and one MULTI-only treatment are available on the same v1 task set. The MULTI-only treatment is compared descriptively with the earlier SINGLE baseline; it is not a third same-session pair.

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

Resource results are interpreted metric by metric rather than as a single monotonic "orchestration cost" effect. The most stable observed pattern is increased **output-token** use in MULTI. Total-token and reported-cost comparisons are less clean because the SINGLE baseline itself changes substantially between the two completed paired series.

| Condition | Total tokens, sum / median | Output tokens, sum / median | Reported cost, USD |
| --- | ---: | ---: | ---: |
| SINGLE baseline | 18.17M / 1.48M | 147k / 13.8k | 6.74 |
| MULTI original prompt | 19.19M / 1.42M | 192k / 13.9k | 7.88 |
| SINGLE model-directed series | 23.41M / 1.67M | 178k / 13.6k | 8.26 |
| MULTI model-directed | 22.73M / 1.91M | 254k / 21.5k | 9.40 |
| MULTI v4 prompt | 25.93M / 1.96M | 298k / 24.2k | 10.73 |

Cost values are Claude Code/modelUsage estimates, not billing records.

Across the task-level comparisons, MULTI uses more output tokens in 10–12 of the 12 task pairs depending on the treatment comparison. By contrast, total tokens and reported cost should not be read as a clean monotonic treatment effect: the two SINGLE series differ by about 29% in total tokens and about 23% in reported cost. In the model-directed series, the lower aggregate total-token count for MULTI is also sensitive to the large `pytest-dev__pytest-5787` SINGLE run. The MULTI v4 resource comparison is additionally cross-series rather than a same-session pair.

## Status of `main-v4-20260911`

`experiment/runs/main-v4-20260911` is an **aborted partial attempt** at the later v4 sample and is excluded from final outcome analysis.

It contains completed runs for only the first part of the scheduled series plus several infrastructure/session-limit attempts. The series was not completed because the token/resource cost was too high for the project budget. It must not be described as the completed main experiment.

The frozen v4 selection, workstream treatment, adherence protocol and harness card remain useful as design history and as the source of the third prompt, but the final empirical evidence comes from applying the three MULTI prompt variants to the v1 sample.

## Interpretation boundary

The final study therefore supports a narrower claim than the planned v4 design:

- it compares a no-delegation baseline with three **different prompted subagent-orchestration treatments** on the same small SWE-bench Verified task set;
- it can describe how quality and resource use differed across those treatments, but the three MULTI variants are not a clean dose-response scale and differ in more than prompt wording;
- it does **not** provide the planned v4 stratified test of orchestration-friendly vs single-friendly vs orchestration-risky tasks;
- with 12 tasks and one run per task/condition, findings are descriptive and should not be generalized as a universal effect of multi-agent systems.

## Source tables

- `experiment/runs/main-20260906/runs-table.tsv`
- `experiment/runs/main-model-directed-v1/RECONSTRUCTION.md`
- `experiment/runs/main-model-directed-v1/results-reconstructed.tsv`
- `experiment/runs/main-v4prompt-v1/runs-table.tsv`
- evaluator reports under `logs/evaluation/`
