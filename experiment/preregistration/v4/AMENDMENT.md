# v4 task-selection and treatment amendment

Date: 2026-09-11

Status: frozen before **v4 main runs under the final workstream-oriented
treatment**. Historical v3 trajectories exist for seven retained instances and
are disclosed below; therefore the v4 sample must not be described as fully
outcome-naive with respect to all prior experimental process information.

## Why v3 selection was amended

A post-v3 construct audit showed that several tasks that looked decomposable
from issue text or gold-patch spread did not satisfy the stronger construct used
by the v4 MULTI treatment: substantive workstreams should be natural from the
task/repository rather than mechanical propagation, and evaluator coverage
should require the relevant branches.

The audit was extended beyond SWE-bench Verified to the full SWE-bench task
collection. Non-Verified candidates were manually checked against the task
statement, accepted patch, evaluator tests, and workstream structure.

## Frozen orchestration-friendly arm

1. `sympy__sympy-19201` — Tier A, parallel implementation across
   str/pretty/LaTeX printer families.
2. `django__django-12508` — Tier A, backend-specific dbshell implementations
   after a shared API contract.
3. `astropy__astropy-13398` — Tier B, sequential/mixed location plumbing plus
   observed-frame/refraction work.
4. `sphinx-doc__sphinx-7590` — Tier B, lexical parsing plus AST/signature/ID
   support for C++ user-defined literals.
5. `django__django-11400` — Tier B-, two evaluator-covered ordering defects with
   a shared mechanism; retained as the weakest friendly slot, not claimed to be
   strict parallel implementation.

The first two are the cleanest early fan-out cases. The latter three represent
useful but more coupled orchestration rather than five equally clean parallel
tasks.

## Controls, risky stratum, and prior v3 exposure

The five v3 single-friendly controls were retained:

- `django__django-15957`
- `sphinx-doc__sphinx-11510`
- `sympy__sympy-17630`
- `django__django-15268`
- `django__django-15128`

The two v3 orchestration-risky tasks were retained:

- `sympy__sympy-16597`
- `django__django-16263`

After the local/uncommitted history was merged back into the repository, it
became clear that historical v3 SINGLE/MULTI trajectories from 2026-09-08 exist
for seven retained v4 instances:

- `astropy__astropy-13398`
- `sphinx-doc__sphinx-11510`
- `sympy__sympy-17630`
- `django__django-15268`
- `django__django-15128`
- `sympy__sympy-16597`
- `django__django-16263`

Those runs used an earlier treatment and are **not** part of the v4 analysis.
However, their existence means the v4 sample is not cleanly outcome-naive with
respect to all prior process information. The final v4 treatment, execution
order, freeze package and A0–A7 adherence rules were fixed before v4 main runs
under that final treatment. The report must disclose this as a limitation and
must not claim fully outcome-blind sample construction.

This gives 12 v4 instances and therefore 24 measured v4 runs at one run per
condition per instance.

## Pairing interpretation

The old v3 exact-matching optimum is not claimed for v4 because two accepted
friendly tasks come from outside the v3 annotation population.
`selection_v4.json` records descriptive control pairs only.

The primary paired comparison remains within-instance: every v4 instance is run
once in SINGLE and once in MULTI under the final treatment. Friendly-vs-single
comparisons are exploratory stratum-level heterogeneity analysis rather than
newly optimized exact matched causal contrasts.

## Benchmark-status limitation

The main sample is not exclusively SWE-bench Verified:
`sympy__sympy-19201` and `django__django-12508` are original SWE-bench instances
outside Verified. They were subjected to the same construct/evaluator audit but
do not carry the Verified engineer-verification label.

## MULTI treatment refinement

The v4 treatment follows task workstream structure rather than enforcing an
arbitrary minimum number of subagents.

An adversarial audit removed two confounds before v4 main runs:

1. the parent is not restricted to shallow inspection or forbidden from
   understanding implementation details before delegation; it may inspect
   deeply enough to identify workstreams, while production-code changes wait
   until workstreams have been identified;
2. delegation prompts may include relevant repository context and findings
   needed for a self-contained subtask, while solution design and implementation
   choices remain with the subagent.

The authoritative prompt is `experiment/execution/multi-treatment.txt`.

The frozen policy is:

- identify substantive implementation workstreams and dependencies before
  production-code changes;
- delegate each substantive workstream that can be meaningfully separated;
- delegate independent workstreams to separate subagents in parallel;
- delegate distinct dependent workstreams sequentially as prerequisites become
  available;
- dependency alone is not a reason to collapse several substantive workstreams
  into one delegation;
- if there is genuinely one substantive workstream, one implementation
  delegation is sufficient;
- review-only, test-only, confirmation-only, or other post-hoc ceremonial
  delegation does not satisfy the treatment;
- provide sufficient repository context for independent work while leaving
  solution design and implementation choices to the subagent;
- the parent owns review, integration, conflict resolution, and final
  verification.

A local experimental branch briefly used a more permissive minimal prompt that
left decomposition, subagent count and scheduling to the lead agent. During the
2026-09-11 merge that text was accidentally concatenated with the v4 prompt.
The merge was resolved before v4 main runs: the minimal prompt is historical and
superseded; it must not be used for v4.

## Live orchestration gate

The merged runner also contains a MULTI-only admin-managed hook gate:
`experiment/execution/orchestration_gate.py` with
`orchestration-gate-settings.json`.

The gate observes `SubagentStart` and `Stop`. A Stop attempt is blocked until at
least one real subagent start is observed. This is only a **minimum mechanical
manipulation aid**. It does not prove pre-edit timing, substantive delegation,
workstream coverage, parallel fan-out, integration, or verification.

A model that solves the task first and delegates only after a rejected Stop
remains in the intention-to-treat analysis but fails relevant trajectory-level
adherence checks. The gate therefore cannot turn late ceremonial delegation
into full compliance.

## Executable v4 alignment

- `experiment/preregistration/v4/tasks-main-v4.txt` contains exactly the 12 v4
  tasks;
- `experiment/execution/run-order-v4.tsv` freezes task order and within-instance
  condition order;
- `experiment/execution/run_series.py` defaults to those v4 files;
- exactly six instances are SINGLE-first and six MULTI-first.

The order was generated once with Python `random.Random(20260911)` before v4
main inference under the final treatment.

## Frozen treatment-adherence check

Trajectory-level adherence is preregistered in
`experiment/preregistration/v4/ADHERENCE_PROTOCOL.md`.

Every MULTI run is coded on A0–A7:

- completed delegation;
- implementation delegation before the parent's first production-code
  modification;
- substantive implementation ownership rather than ceremonial review/test;
- coverage of materially distinct separable workstreams;
- parallel fan-out when independent workstreams exist;
- preservation of subagent solution independence;
- parent review/integration after delegated work;
- parent final verification.

Adherence is a process/manipulation result, not an exclusion criterion.
Non-compliant MULTI runs remain in the primary intention-to-treat comparison.

## Final pre-main freeze

`experiment/execution/FREEZE_V4.json` is the machine-checkable freeze. After the
2026-09-11 merge resolution it pins Git blob hashes for:

- `runner.py` and `runner.sha256`;
- `run_series.py` and `verify_freeze.py`;
- the authoritative MULTI treatment;
- orchestration gate code and managed settings;
- common prompt and v4 sample/order;
- quantitative analyzer;
- main network configuration;
- frozen failure-analysis and treatment-adherence protocols/validator.

`run_series.py` invokes `verify_freeze.py` before any reported v4 main
inference. The validation-only bypass must not be used for a reported main run.

## Source of truth

Frozen task set and provenance: `experiment/preregistration/v4/selection_v4.json`.

Executable task list: `experiment/preregistration/v4/tasks-main-v4.txt`.

Frozen execution order: `experiment/execution/run-order-v4.tsv`.

Authoritative MULTI treatment: `experiment/execution/multi-treatment.txt`.

Machine-checkable freeze: `experiment/execution/FREEZE_V4.json`.

Trajectory adherence protocol: `experiment/preregistration/v4/ADHERENCE_PROTOCOL.md`.

Current execution description: `experiment/execution/PROTOCOL.md` and
`experiment/execution/HARNESS_CARD.md`.
