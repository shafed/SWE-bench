# v3 sample preregistration — task selection

Supersedes `../PROTOCOL.md` for *task selection only*. Everything else in the
v1 preregistration (paired running of both conditions, infrastructure-failure
rules, the freeze rule) continues to apply unchanged.

## Why v3 exists

v1 and v2 picked instances by structural proxies computed from the gold patch
— production files touched, directories spanned, identifier overlap between
files — and treated "the patch is dispersed" as a stand-in for "the task is
decomposable". The v1 main run showed that this does not hold: a multi-file
patch with a single root cause offers an agent nothing independent to hand
off, and MULTI degenerated into "solve the whole thing, then delegate the test
run". The v1 sample cannot support a claim about orchestration because it was
never established that the tasks admitted orchestration.

v3 keeps the mechanical part mechanical and moves the judgement to where it
belongs: a blind, rubric-driven annotation whose scores are recorded before
any category is assigned.

## What is being measured

The effect of **mandatory native subagent use** under an orchestrator treatment,
compared with the same model and harness with delegation disabled. A compliant
MULTI run must complete at least one subagent delegation. The experiment does
not prescribe which subtask must be delegated, how many delegations are used
beyond that minimum, or whether orchestration is sequential or parallel.

The sample's job is to guarantee that different forms of orchestration are
objectively meaningful for some tasks while being unnecessary or risky for
others; it does not force one particular orchestration pattern. If a task offers
clean fan-out and MULTI still solves most of the task itself and uses its required
delegation only for a reviewer, that is a valid behavioral result, not a sampling
defect. A MULTI run with zero completed delegations, however, is a protocol
violation rather than a valid MULTI observation.

The sample is therefore built from the structure of the work, not from
heuristics about how Claude Code delegates.

## Population

- Dataset `SWE-bench/SWE-bench_Verified`, split `test`, hub revision
  `78f471bf655a3137b2e8a75af1501690ec009ec3` (500 rows).
- `candidate_pool.py`, sha256 recorded in `candidates.json`.

## Exclusions (applied by code, before any draw)

| reason | rule | n |
| --- | --- | --- |
| `dev-instance` | `sympy__sympy-20590`, used to debug the pipeline | 1 |
| `v1-outcome-known` | the 12 v1 main instances; their SINGLE/MULTI outcomes are known to the experimenters, so leaving them in would let observed results steer the v3 sample | 12 |
| `no-production-python` | gold patch touches no non-test `.py` file | 0 |
| `degenerate-diff` | fewer than 2 changed production code lines | 22 |
| `trivial` | easiest difficulty bucket *and* fewer than 5 changed production code lines. Size alone is not triviality: a two-line fix that takes an hour to locate is exactly the local-but-hard task the single-friendly arm needs | 110 |
| `oversized` | more than 250 production code lines or more than 10 production files | 1 |
| `mechanical-sweep` | at least 6 production files averaging at most 3 changed code lines each | 0 |

354 of 500 instances remain eligible.

The remaining exclusions in the selection plan — unstable environment, external
services, ill-defined specification, patch dominated by documentation or
generated files — cannot be decided from metadata. They are annotation flags
(`env_risk`, `spec_clarity == 0`, `nonproduction_patch`, `unsolvable`) and
remove a candidate at classification time.

**No exclusion and no stratum uses file count, directory count or patch size as
a proxy for orchestration suitability.** That was the v1 mistake.

## Candidate pool

40 candidates, stratified over `repository × rough difficulty`.

Rough difficulty collapses the SWE-bench annotation into `easy`
(`<15 min fix`), `medium` (`15 min - 1 hour`) and `hard` (`1-4 hours`,
`>4 hours`).

Within each difficulty bucket, repositories are visited round-robin in a
seeded shuffled order, each contributing the next instance from its own
seeded shuffled queue. Buckets are interleaved on the fixed 8-slot pattern
`medium, hard, easy, medium, hard, medium, hard, easy`, giving
`easy:medium:hard = 2:3:3`.

Seed `"v3"`. Drawn mix: easy 10, medium 15, hard 15; at most 6 candidates from
any one repository, against django's 46% share of Verified.

The draw is a single deterministic ordering, so extending the pool is
`--size 50`, `--size 60`, … : the earlier candidates are unchanged and the new
block is drawn by the identical method. **The pool is only ever extended
because a category could not be filled — never by loosening the rubric.**

The pool *was* extended: block 1 produced no `orchestration-risky` candidates
and only one fan-out task, and all three friendly candidates came from the
`hard` bucket. The extension appended every remaining eligible `hard` instance
(24), exhausting that stratum — see **amendment 1** in `AMENDMENTS.md`. Final
pool: 64 candidates, all annotated.

## Annotation

Rubric: `RUBRIC.md`, fixed before any candidate was read.

Two passes, separate sessions:

1. **Pass 1, without the gold patch** — problem statement plus the repository
   at `base_commit` (checkouts under `~/.cache/nir-v3-worktrees`, no test
   patch present). Scores `spec_clarity`, `discoverability`, `early_fanout`,
   `fanout_kind`, `env_risk`. These scores are final and are never revised
   after the gold patch is seen.
2. **Pass 2, with the gold patch** — scores `n_subtasks`, `independence`,
   `integration_cost`, `global_context`, `locality`, `difficulty_overall`,
   `investigation_volume`, `change_type`, `nonproduction_patch`, `unsolvable`.

Annotators receive the rubric and one candidate bundle. They never receive:
SINGLE/MULTI results, the SWE-bench difficulty label, the target category
counts, which category is currently short, or the other candidates' scores.
The dataset difficulty label is withheld specifically so that
`difficulty_overall` is an independent estimate.

Annotators output features only. Categories are derived from the feature
profile by `classify.py`, using the table in `RUBRIC.md`. A profile that
matches nothing is `borderline` and never enters the main 12.

## Final sample

`match.py`, run once on the classified pool:

- 5 `orchestration-friendly`, of which at least 2 are `fan-out` (plan target
  was 3; the pool contains exactly 2 and the stratum is exhausted — see
  **amendment 2**). None of the remaining three is the
  `implement, then delegate a review` pattern the plan caps at two: all three
  are two dependent implementation lines, so the classifier's non-fan-out
  bucket is named `sequential`, not `pipeline`;
- each paired 1:1 with a `single-friendly` task;
- 2 `orchestration-risky`, each reported against the nearest of the 5 chosen
  friendly tasks as a reference. Risky tasks do not get their own single-arm
  partners.

All 12 run under **both** SINGLE and MULTI — 24 measured runs.

### Pairing metric

`3·|Δdifficulty_overall| + 2·[change_type differs] + 2·|Δinvestigation_volume|
+ 0.5·|Δlog2(1+production lines)| + 0.5·min(|Δproduction files|, 2)`,
minus `1.5` when the pair shares a repository.

Set-level penalties: `+1.0` per repeated `fanout_kind` among the chosen fan-out
tasks (the plan asks the three to represent different situations), and `+1.0`
per task beyond 3 from any single repository across the 10 paired tasks.

**Orchestration features are excluded from the metric.** They are the
dimension the pairs must differ on; matching on them would erase the contrast.

Selection is exact rather than greedy: every admissible 5-subset of the
friendly group is enumerated, each optimally assigned against the
single-friendly group (Jonker-Volgenant), and the cheapest whole configuration
wins. Ties are broken by instance id, so the result is reproducible.

## Outcome

| category | of 64 candidates |
| --- | --- |
| orchestration-friendly | 5 (fan-out 2, sequential 3) |
| orchestration-risky | 2 |
| single-friendly | 30 |
| borderline | 25 |
| excluded | 2 |

Selected: `tasks-main.txt` (12 instances), pairing in `selection_v3.json`.

Four limitations of this sample — the friendly/single split coinciding with a
feature/bugfix split, the difficulty ceiling of the single-friendly pool,
repository concentration, and the absence of an inter-annotator agreement
figure — are stated in `AMENDMENTS.md` and must be carried into any report of
the result.

## Freeze

Once `selection_v3.json` is committed, the rubric, the pool script, the
classification rules and the matching weights are frozen. They must not be
changed on the basis of observed SINGLE/MULTI outcomes.
