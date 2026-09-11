# Harness Card — SINGLE vs MULTI subagent study

Disclosure of the harness under which every measured run is produced, in the
seven dimensions of Zhang et al. (2026) — Execution, Tools, Context,
Scheduling, Observability, Verification, Governance.

The experimental factor is **Scheduling/orchestration**: SINGLE has delegation
disabled, whereas MULTI must use a workstream-oriented subagent orchestration
policy. The treatment requires implementation delegation, parallel fan-out when
independent workstreams exist, sequential delegation for distinct dependent
workstreams, and parent-owned integration and verification. Every other harness
dimension is held as constant as the Claude Code interface permits.

Authoritative sources for the v4 main series are
`experiment/execution/runner.py`, `PROTOCOL.md`, `multi-treatment.txt`,
`FREEZE_V4.json`, `../preregistration/v4/selection_v4.json`,
`../preregistration/v4/ADHERENCE_PROTOCOL.md`, and
`../preregistration/v4/AMENDMENT.md`. Earlier v1/v3 files and older treatment
experiments are historical records. Where descriptive documentation and actual
run artifacts disagree about what executed, the runner and preserved artifacts
are the execution evidence.

State: Claude Code `2.1.261`, model `claude-sonnet-5`.

## E — Execution

| Item | Value |
| --- | --- |
| Agent | Claude Code CLI `2.1.261`, headless (`-p`), installed inside the task container |
| Model | `claude-sonnet-5`, both conditions; MULTI subagents pinned with `CLAUDE_CODE_SUBAGENT_MODEL` |
| Effort | `--effort high` plus `CLAUDE_CODE_EFFORT_LEVEL=high` |
| Environment | one clean SWE-bench task image per condition |
| Working copy | repository at the instance base commit; gold patch never present in the task environment |
| Inference user | `nonroot`, `HOME=/home/nonroot` |
| Autoupdate | `DISABLE_AUTOUPDATER=1` |
| Ambient config | `--setting-sources ''`, strict empty MCP config, no filesystem settings, CLAUDE.md, plugins, or MCP servers |
| Repetition | one run per (instance, condition); no automatic retry |

## T — Tools

| Item | Value |
| --- | --- |
| Tool surface | default Claude Code file/shell/search tool surface except explicitly disallowed tools |
| Permission mode | `--permission-mode bypassPermissions` with `--safe-mode` |
| Disallowed, SINGLE | `Task`, `WebFetch`, `WebSearch` |
| Disallowed, MULTI | `WebFetch`, `WebSearch` |
| Delegation tool | `Task`; emitted calls may be named `Agent`, both counted |
| MULTI orchestration gate | managed Claude Code hooks observe `SubagentStart` and `Stop`; finalization is blocked until at least one real subagent start has been observed |
| Gate scope | minimum enforcement only; it does not establish workstream coverage, useful delegation, pre-edit timing, or parallel fan-out |
| Network | task container on internal network `nir-internal`; sole route out is the squid allow-list proxy |
| Allow-list | Anthropic/Claude provider and authentication hosts needed by the pinned CLI; GitHub, raw GitHub, PyPI and CLI telemetry are refused |
| Egress evidence | blocked repository/package hosts probed unreachable and `api.anthropic.com` reachable per run |

The gate is active only in MULTI through admin-managed settings mounted at
`/etc/claude-code/managed-settings.json`. It records ordered hook events and
state under the run artifact directory. A `SubagentStart` is necessary to pass
the live Stop gate, but it is not sufficient for full treatment adherence.

## C — Context

| Item | Value |
| --- | --- |
| Task prompt | `prompt-template.txt` + instance problem statement, identical in both conditions |
| Treatment | MULTI only: `multi-treatment.txt` via `--append-system-prompt` |
| Placebo | none; SINGLE receives no compensating appended prompt |
| Context management | Claude Code's own; not overridden or directly observable |
| Subagent context | native Claude Code separate context, free to inspect the repository with its own tools |
| Delegated context policy | parent may include objective, relevant repository context/scope, constraints, acceptance criteria, and repository findings needed to make the delegation self-contained; solution design and implementation choices remain with the subagent |
| Delegated context measurement | prompt/description sizes preserved when exposed by the trace |

The v4 treatment does **not** restrict the parent to shallow repository
inspection before delegation. The parent may understand the task and
architecture sufficiently to decompose it. The treatment boundary is that
production-code changes wait until substantive workstreams have been identified
and that delegated implementation choices remain genuinely delegated.

## S — Scheduling / orchestration (the experimental factor)

| Item | SINGLE | MULTI |
| --- | --- | --- |
| Delegation | technically disabled (`Task` disallowed) | required for substantive implementation work |
| Workstream decomposition | none imposed | identify substantive implementation workstreams and dependencies before production-code changes |
| Independent workstreams | n/a | separate subagents in parallel |
| Distinct dependent workstreams | n/a | delegated sequentially as prerequisites become available; dependence alone is not a reason to collapse them |
| One-workstream task | n/a | one implementation delegation is sufficient |
| Review/test-only delegation | n/a | does not satisfy treatment |
| Parent responsibility | solves task directly | reviews returned work, integrates changes, resolves conflicts, performs final verification |
| Mechanical compliance | any `Task`/`Agent` call is a violation | runner requires completed delegation; live gate additionally requires an observed `SubagentStart` before finalization |
| Full adherence | n/a | frozen A0–A7 trajectory coding in `../preregistration/v4/ADHERENCE_PROTOCOL.md` |
| Turn budget | none | none |
| Token budget | none | none |
| Background-agent wait | not applicable | no CLI-specific ceiling; bounded by runner wall-clock |
| Wall-clock | 2700 s | 2700 s |

The A0–A7 manipulation check covers completed delegation; delegation before
production-code modification; substantive implementation ownership; workstream
coverage; parallel fan-out when independence exists; subagent solution
independence; parent review/integration; and parent final verification.
Adherence never changes inclusion in the primary intention-to-treat comparison.

Tokens are deliberately not equalized: extra compute in MULTI is part of the
treatment's resource-performance effect and is measured as an outcome.

## O — Observability

| Item | Value |
| --- | --- |
| Trace | full `stream-json` trace per run, including hook lifecycle events when available |
| Actor attribution | orchestrator and subagent activity attributed using trace relationships exposed by the CLI |
| Gate evidence | `orchestration-gate/state.json` and ordered `orchestration-gate/events.jsonl` in MULTI |
| Resource accounting | last cumulative `result.modelUsage`, summed over all reported models, with per-model breakdown retained |
| Completeness | partial on timeout, error result, parse errors, or usage-bearing activity after the final result; trailing non-usage system housekeeping does not invalidate a cumulative snapshot |
| Process measures | wall-clock, tool calls by name/actor, delegation count/prompt size, unique assistant messages, subagent start/completion counts |
| Known-unreliable | `result.num_turns` under MULTI; recorded but not used as comparative process measure |
| Not observable | internal context compaction, exact internal prompts, server-side effort application, and other undisclosed Claude Code internals |
| Preserved | task prompt, treatment, patch, git status, untracked files, setup log, stderr, network probe, metadata with digests, execution trace, and MULTI gate artifacts |

## V — Verification

| Item | Value |
| --- | --- |
| Outcome | official SWE-bench evaluator, unmodified |
| Patch collection | `git add -A` then `git diff --cached <base> --binary` after inference as root; includes new files and agent commits |
| Secondary outcome | share of FAIL_TO_PASS and PASS_TO_PASS tests passing |
| Statistics | exact McNemar on paired resolution; exact paired randomisation test on resource differences (`analyze_runs.py`, fixed before v4 main series) |
| Agent-side verification | final verification required of the MULTI parent by treatment; exact commands/tests chosen by the agent |
| Stop gate | MULTI finalization attempts are rejected until at least one `SubagentStart`; afterward stopping is normal |
| Stopping | agent stops itself after gate conditions are met, or the 2700 s wall-clock ends the run; timeout is an experimental outcome |

The Stop gate is deliberately interpreted only as a minimum manipulation aid.
If the model solves the task first and delegates only after a rejected Stop, the
run remains in the primary analysis but fails relevant adherence checks such as
A1/A2. The gate therefore cannot convert ceremonial late delegation into full
compliance.

## G — Governance

| Item | Value |
| --- | --- |
| Sample | 12 v4 SWE-bench instances: 5 orchestration-friendly, 5 single-friendly, 2 orchestration-risky |
| Benchmark status | 10 SWE-bench Verified + 2 manually audited original SWE-bench instances |
| Pairing | primary treatment comparison is within-instance SINGLE vs MULTI; friendly/control pairs are descriptive |
| Dev instance | `sympy__sympy-20590`, excluded from sample; development/validation only |
| Gold patch | may be inspected during pre-experiment task-selection/construct audit; never supplied to solving model |
| Order | v4 task and within-instance condition order frozen in `run-order-v4.tsv`; six SINGLE-first and six MULTI-first |
| Freeze manifest | `FREEZE_V4.json` pins execution, treatment, gate, sample/order, analysis, adherence, and network inputs; `run_series.py` verifies it before main inference |
| Freeze bypass | validation-only override; prohibited for reported main runs |
| Adherence | A0–A7 protocol frozen in `../preregistration/v4/ADHERENCE_PROTOCOL.md`; non-compliance retained and reported |
| Substitution | only documented infrastructure failure under preregistered paired-replacement rules |
| Not substituted | timeouts, empty/invalid patches, failing tests, poor delegation, or treatment non-compliance |
| Failure analysis | frozen qualitative coding scheme in `../preregistration/FAILURE_ANALYSIS_PROTOCOL.md` |
| Credentials | per-run copy of dedicated Claude profile; refreshed tokens returned to original; never committed |

## Declared limitations

1. Provider/authentication hosts remain reachable because the agent cannot run
   without them. Repository and package hosts are blocked; the claim is no
   runtime access to the upstream fix, not zero network access.
2. Internal Claude Code mechanisms cannot be directly disclosed or controlled;
   they are held constant only through the same pinned CLI/model configuration.
3. 12 instances × 1 run per condition does not estimate run-to-run stochastic
   variance. The design is a small paired case study, not a universal estimate
   of multi-agent effectiveness.
4. The treatment estimates the effect of a **specific mandatory
   workstream-oriented orchestration policy**, not subagent availability in
   isolation. The effect includes decomposition, delegation, context routing,
   parallel/sequential scheduling, integration and final verification.
5. The live Stop gate enforces only the existence of at least one real subagent
   start. It does not prove substantive or timely delegation; those properties
   are assessed separately by the frozen adherence protocol.
6. The two cleanest Tier-A orchestration-friendly instances are outside
   SWE-bench Verified, while the remaining friendly instances are more coupled.
   Friendly-vs-control comparisons are exploratory heterogeneity analysis.
7. Blocking runtime access to GitHub/PyPI does not rule out benchmark
   contamination already present in model weights. This is symmetric between
   SINGLE and MULTI but can reduce the need for repository exploration and
   orchestration on memorized tasks.
