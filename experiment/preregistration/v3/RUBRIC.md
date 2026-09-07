# v3 rubric — experimenter's copy

Feature definitions live in **`RUBRIC_ANNOTATOR.md`**, which is the only rubric
document an annotator ever sees. This file adds the parts that must be kept
away from them: why the features exist, and how a category is derived from a
feature profile.

## What the sample has to guarantee

The experiment measures the effect of *having subagents available* on solving
programming tasks. The MULTI arm is free to fan out, delegate sequentially,
run implementation → debug/review/test, or do none of that. The sample's job
is to guarantee that several forms of orchestration are objectively
*available* — not to force the model to use them, and not to be tuned to any
particular model's delegation heuristics.

That is why `RUBRIC_ANNOTATOR.md` never mentions agents, subagents, this
study, or its conditions. It asks about a second engineer, because the
property being measured is a property of the work, not of a product.

## What annotators are not given

- the category names and the profile table below;
- the target counts, and which category is currently short;
- SINGLE/MULTI results from any run;
- the SWE-bench difficulty label — withheld so that `difficulty_overall` is an
  independent estimate;
- the other candidates' scores;
- in pass 1, the accepted fix, and any git history that would reveal it (the
  checkouts are `git archive` exports, with no `.git` at all).

Pass-1 scores are final. They are never revised once the fix has been seen,
and pass-2 annotators do not see them.

## Derived categories

Applied by `classify.py` from the recorded features. Never chosen by the
annotator, never adjusted to fill a quota.

Hard exclusion first: `spec_clarity == 0`, or `env_risk`, or
`nonproduction_patch`, or `unsolvable` → `excluded`.

| category | rule |
| --- | --- |
| `orchestration-friendly` | `n_subtasks == 2` and `independence >= 1` and `integration_cost <= 1` and `global_context <= 1` and `locality <= 1` |
| ├ `fan-out` | friendly, and `early_fanout == 2` and `discoverability == 2` |
| └ `sequential` | friendly, and not fan-out |
| `orchestration-risky` | `n_subtasks == 2` and (`integration_cost == 2` or `global_context == 2` or `independence == 0`) |
| `single-friendly` | `n_subtasks == 0` and `locality == 2` and `early_fanout == 0` and `discoverability <= 1` |
| `borderline` | everything else — never enters the main 12 |

`borderline` is a real outcome, not a failure. If the categories cannot be
filled, the pool is extended by one more block of 10 from the same script
(`--size 50`, `--size 60`, …) and the new block is annotated the same way.
**The rubric is never loosened to make a category fill.**
