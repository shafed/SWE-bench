# v4 task-selection amendment

Date: 2026-09-11

Status: frozen before any main-series SINGLE/MULTI outcome for this sample.

## Why v3 selection was amended

A post-v3 construct audit showed that several tasks that looked decomposable from issue text or gold-patch spread did not satisfy the stronger requirement needed by the current MULTI treatment: substantive workstreams should be natural from the task/repository, not merely mechanical propagation, and the official evaluator should require the relevant branches.

The audit was extended beyond SWE-bench Verified to the full SWE-bench task collection. Non-Verified tasks were not accepted automatically; each selected candidate was manually checked against the task statement, accepted patch, evaluator tests, and workstream structure.

No task was selected using SINGLE/MULTI outcomes. Earlier v1 main tasks with known outcomes remain excluded.

## Frozen orchestration-friendly arm

1. `sympy__sympy-19201` — Tier A, parallel implementation across str/pretty/LaTeX printer families.
2. `django__django-12508` — Tier A, backend-specific dbshell implementations after a shared API contract.
3. `astropy__astropy-13398` — Tier B, sequential/mixed location plumbing plus observed-frame/refraction work.
4. `sphinx-doc__sphinx-7590` — Tier B, lexical parsing plus AST/signature/ID support for C++ user-defined literals.
5. `django__django-11400` — Tier B-, two evaluator-covered ordering defects with a shared mechanism; retained as the weakest friendly slot, not claimed to be strict parallel implementation.

The first two are the cleanest early fan-out cases. The latter three intentionally represent useful but more coupled orchestration rather than pretending that SWE-bench supplies five equally clean parallel tasks.

## Why other strong-looking candidates were not selected

- `sympy__sympy-14248`: strong printer fan-out, but too close in topic and orchestration structure to `sympy__sympy-19201`; kept as reserve to avoid same-topic duplication.
- `sympy__sympy-13878`: excellent logical fan-out, but FAIL_TO_PASS does not require the full distribution set.
- `sympy__sympy-13852`: two natural polylog lines, but evaluator coverage is concentrated on special values.
- `django__django-11138`: backend split is natural, but grader does not independently require all backend branches.
- `django__django-14631`: apparent BoundField split is not fully required by FAIL_TO_PASS.
- `django__django-16256`: evaluator coverage is good, but implementation is largely a mechanical async-wrapper sweep.
- `mwaskom__seaborn-3069`: several task-visible behaviors collapse to one cohesive implementation block.
- `matplotlib__matplotlib-25775`: structurally strong, but excluded because an earlier main series already exposed SINGLE/MULTI outcomes.

## Control and risky strata

The five v3 single-friendly controls are retained unchanged:

- `django__django-15957`
- `sphinx-doc__sphinx-11510`
- `sympy__sympy-17630`
- `django__django-15268`
- `django__django-15128`

The two v3 orchestration-risky tasks are also retained:

- `sympy__sympy-16597`
- `django__django-16263`

This gives 12 main instances and therefore 24 measured runs at one run per condition per instance.

## Pairing interpretation

The old v3 exact-matching optimum is not claimed for v4 because two accepted friendly tasks come from outside the v3 annotation population. `selection_v4.json` records descriptive control pairs only.

This does **not** affect the primary paired comparison: every instance is still run once in SINGLE and once in MULTI, so the treatment comparison remains within-instance. Friendly-vs-single comparisons should be interpreted as stratum-level heterogeneity analysis rather than as five newly optimized exact matched pairs.

## Benchmark-status limitation

The main sample is no longer exclusively SWE-bench Verified: `sympy__sympy-19201` and `django__django-12508` are original SWE-bench instances outside Verified. They were manually subjected to the same construct/evaluator audit, but they do not carry the SWE-bench Verified engineer-verification label. This must be reported as a limitation.

## Source of truth

Frozen task set: `experiment/preregistration/v4/selection_v4.json`.

The v3 files remain unchanged as historical preregistration records.
