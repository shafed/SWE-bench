# Execution protocol

## Fixed sample

The v4 main sample contains 12 frozen SWE-bench instances selected for
orchestration suitability:

- 5 `orchestration-friendly`;
- 5 `single-friendly` controls;
- 2 `orchestration-risky` tasks.

The authoritative selection is recorded in
`../preregistration/v4/selection_v4.json`; the executable instance list is
`../preregistration/v4/tasks-main-v4.txt`.

Ten instances are from SWE-bench Verified. Two orchestration-friendly instances
(`sympy__sympy-19201` and `django__django-12508`) are original SWE-bench
instances outside Verified and were manually audited against the task statement,
accepted patch, evaluator tests, and workstream structure. This benchmark-status
difference is a declared limitation.

The five control pairs in `selection_v4.json` are descriptive rather than exact
matched pairs. The primary comparison is within-instance: every one of the 12
instances is evaluated once under SINGLE and once under MULTI.

Earlier v1/v3 sample files remain historical records and are not inputs to the
v4 main-series driver.

## Conditions

SINGLE:
- Claude Code 2.1.261
- model: claude-sonnet-5
- Task disallowed
- WebFetch and WebSearch disallowed

MULTI:
- Claude Code 2.1.261
- orchestrator model: claude-sonnet-5
- subagent model: claude-sonnet-5
- Task available
- the authoritative treatment is `multi-treatment.txt`
- WebFetch and WebSearch disallowed

The MULTI treatment requires workstream-oriented orchestration. Before making
production-code changes, the parent inspects the task and repository enough to
identify substantive implementation workstreams and dependencies. Every
substantive implementation workstream that can be meaningfully separated is
delegated. Independent workstreams are delegated to separate subagents in
parallel; distinct dependent workstreams are delegated sequentially as their
prerequisites become available. If the task genuinely has only one substantive
implementation workstream, one implementation delegation is sufficient.

Delegation prompts may include the objective, relevant repository context and
scope, constraints, acceptance criteria, and repository findings needed to make
the delegation self-contained. They should leave solution design and
implementation choices to the subagent rather than prescribe a completed
solution. Review-only or test-only delegation does not satisfy the
implementation-workstream requirement.

After delegated work returns, the parent reviews and integrates the changes,
resolves conflicts, and performs final verification.

A MULTI run with zero completed delegations is an automatic protocol violation.
That check is only the minimum mechanical adherence check. Whether all
materially distinct workstreams were delegated and whether independent
workstreams were actually parallelized is assessed from the recorded trajectory
and is not inferred from subagent count alone.

## Resource policy

- one run per condition per instance
- wall-clock timeout: 45 minutes per inference
- no max-turn limit
- no experiment-imposed token limit
- token use, model messages, tool calls, subagent calls and wall time are outcomes
- timeout under otherwise functioning infrastructure is an experimental result

Tokens are deliberately not equalized: extra compute produced by MULTI is part
of the cost-performance effect of the treatment and is measured as an outcome.

## Isolation

- clean SWE-bench task image for every condition
- separate Claude profile
- `--safe-mode`
- WebFetch/WebSearch disabled in both conditions
- container egress restricted by the experiment proxy; repository/package hosts are blocked
- inference runs as nonroot
- patch collection occurs after inference as root
- official SWE-bench evaluator is used unchanged

## Ordering

The v4 task order and within-instance condition order are frozen in
`run-order-v4.tsv` before v4 main inference. The executable driver defaults to
this order and to `../preregistration/v4/tasks-main-v4.txt`.

Exactly 6 instances are SINGLE-first and 6 are MULTI-first. The v4 order was
generated once with Python `random.Random(20260911)`: the task list was shuffled,
then a list containing six `multi-first` and six `single-first` labels was
shuffled and assigned in the resulting task order. No main-series outcomes were
used to choose the order.

Runs execute strictly sequentially.

## Retries

No automatic retry.

Infrastructure failures are logged and handled according to the preregistered
paired-replacement protocol.

Agent timeout, exhausted reasoning, bad solution, empty patch, failing tests or
MULTI protocol violation are experimental outcomes and are not retried.
