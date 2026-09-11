# Harness Card — SINGLE vs MULTI subagent study

Disclosure of the harness under which every measured run is produced, in the
seven dimensions of Zhang et al. (2026) — Execution, Tools, Context,
Scheduling, Observability, Verification, Governance. Their argument is that a
benchmark number is a property of the pair `{model, harness}`, so a result
reported without the harness cannot be compared with anything; this card exists
so that ours can be.

The experimental factor is **Scheduling/orchestration**: SINGLE has delegation
disabled, whereas MULTI must use a workstream-oriented subagent orchestration
policy. The treatment requires implementation delegation, parallel fan-out when
independent workstreams exist, sequential delegation for distinct dependent
workstreams, and parent-owned integration and verification. Every other harness
dimension is held as constant as the Claude Code interface permits.

Authoritative sources for the v4 main series:
`experiment/execution/runner.py`, `PROTOCOL.md`, `multi-treatment.txt`,
`FREEZE_V4.json`, `../preregistration/v4/selection_v4.json`,
`../preregistration/v4/ADHERENCE_PROTOCOL.md`, and
`../preregistration/v4/AMENDMENT.md`. Earlier v1/v3 preregistration and amendment
files are historical records. Where descriptive documentation and the runner
disagree about what actually executed, the run artifacts and runner are the
execution evidence.

State: Claude Code `2.1.261`, model `claude-sonnet-5`.

## E — Execution

| Item           | Value                                                                                                                                                |
| -------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| Agent          | Claude Code CLI `2.1.261`, headless (`-p`), installed inside the task container                                                                      |
| Model          | `claude-sonnet-5`, both conditions; MULTI subagents pinned with `CLAUDE_CODE_SUBAGENT_MODEL`                                                         |
| Effort         | `--effort high` plus `CLAUDE_CODE_EFFORT_LEVEL=high` (inherited by subagents)                                                                        |
| Environment    | one clean SWE-bench task image per condition, from `swe-bench-tasks/tasks/<instance>/task.yaml`                                                      |
| Working copy   | repository at the instance's base commit; gold patch never present in the task environment                                                           |
| Inference user | `nonroot`, `HOME=/home/nonroot`                                                                                                                      |
| Autoupdate     | `DISABLE_AUTOUPDATER=1`                                                                                                                              |
| Ambient config | `--setting-sources ''`, `--strict-mcp-config`, `--mcp-config '{"mcpServers":{}}'` — no filesystem settings, no CLAUDE.md, no plugins, no MCP servers |
| Repetition     | one run per (instance, condition); no automatic retry                                                                                                |

## T — Tools

| Item               | Value                                                                                                                                                                     |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Tool surface       | the CLI's default file/shell/search tool surface, except for explicitly disallowed tools below                                                                            |
| Permission mode    | `--permission-mode bypassPermissions` with `--safe-mode`                                                                                                                  |
| Disallowed, SINGLE | `Task`, `WebFetch`, `WebSearch`                                                                                                                                           |
| Disallowed, MULTI  | `WebFetch`, `WebSearch`                                                                                                                                                   |
| Delegation tool    | `Task`; emitted calls may be named `Agent`, both counted                                                                                                                  |
| Network            | task container on `--internal` network `nir-internal` (no gateway); sole route out is the squid allow-list proxy `nir-proxy`                                              |
| Allow-list         | Anthropic/Claude provider and authentication hosts required by the pinned CLI; GitHub, raw GitHub, PyPI and CLI telemetry are refused                                     |
| Egress evidence    | per run: blocked repository/package hosts are probed unreachable and `api.anthropic.com` reachable, recorded in `network-probe.txt` and `metadata.json.network_isolation` |

## C — Context

| Item        | Value                                                                                                          |
| ----------- | -------------------------------------------------------------------------------------------------------------- |
| Task prompt | `prompt-template.txt` + the instance problem statement, identical in both conditions; digests recorded per run |

| Treatment | MULTI only: `multi-treatment.txt` via `--append-system-prompt`, requiring at least one substantive delegated contribution before the solution is complete while leaving decomposition, subagent count and roles, scheduling, and integration to the lead agent |
=======

| Treatment | MULTI only: `multi-treatment.txt` via `--append-system-prompt` |

> > > > > > > refs/remotes/origin/main
> > > > > > > | Placebo | none; SINGLE receives no compensating appended prompt |
> > > > > > > | Context management | the CLI's own; not configured, not overridden, and not directly observable |
> > > > > > > | Subagent context | native Claude Code semantics: separate context window, free to inspect the repository with its own tools |
> > > > > > > | Delegated context policy | parent may include objective, relevant repository context/scope, constraints, acceptance criteria, and repository findings needed to make the delegation self-contained; solution design and implementation choices are left to the subagent rather than prescribed as a completed solution |
> > > > > > > | Delegated context measurement | delegation `prompt_chars` / `description_chars` are preserved in `metrics.json` when exposed by the trace |

The v4 treatment intentionally does **not** restrict the parent to an artificially
shallow repository inspection before delegation. The parent may understand the
task and architecture sufficiently to decompose it; the treatment boundary is
that production-code changes wait until workstreams have been identified and
that delegated implementation choices remain genuinely delegated.

## S — Scheduling / orchestration (the experimental factor)

| Item                           | SINGLE                                   | MULTI                                                                                                                                                                           |
| ------------------------------ | ---------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| <<<<<<< HEAD                   |
| Delegation                     | technically disabled (`Task` disallowed) | at least one substantive problem-solving contribution required before the solution is complete                                                                                  |
| Orchestration                  | none                                     | the lead autonomously chooses what to delegate, subagent count and roles, parallel or sequential execution, and integration                                                     |
| Compliance                     | any `Task`/`Agent` call is a violation   | the live gate requires at least one actual `SubagentStart`; substantive, pre-completion contribution and exclusion of review-only formality are established from the trajectory |
| =======                        |
| Delegation                     | technically disabled (`Task` disallowed) | required for substantive implementation work                                                                                                                                    |
| Workstream decomposition       | none imposed                             | identify substantive implementation workstreams and dependencies before production-code changes                                                                                 |
| Independent workstreams        | n/a                                      | separate subagents in parallel                                                                                                                                                  |
| Distinct dependent workstreams | n/a                                      | delegated sequentially as prerequisites become available; dependence alone is not a reason to collapse them                                                                     |
| One-workstream task            | n/a                                      | one implementation delegation is sufficient                                                                                                                                     |
| Review/test-only delegation    | n/a                                      | does not satisfy treatment                                                                                                                                                      |
| Parent responsibility          | solves task directly                     | reviews returned work, integrates changes, resolves conflicts, performs final verification                                                                                      |
| Mechanical compliance          | any `Task`/`Agent` call is a violation   | `subagent_stats.completed >= 1` is the minimum automatic check                                                                                                                  |
| Full adherence                 | n/a                                      | frozen A0-A7 trajectory coding in `../preregistration/v4/ADHERENCE_PROTOCOL.md`                                                                                                 |

> > > > > > > refs/remotes/origin/main
> > > > > > > | Turn budget | none | none |
> > > > > > > | Token budget | none | none |
> > > > > > > | Background-agent wait | not applicable | no CLI-specific ceiling (`CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS=0`); bounded by runner wall-clock limit |
> > > > > > > | Wall-clock | 2700 s | 2700 s |

The A0-A7 manipulation check covers: completed delegation; delegation before
production-code modification; substantive implementation ownership; workstream
coverage; parallel fan-out when independence exists; subagent solution
independence; parent review/integration; and parent final verification.
`validate_adherence.py` enforces the frozen coding vocabulary, overall-label
rule, exact v4 instance set and A0 consistency with run metrics. Adherence never
changes inclusion in the primary intention-to-treat comparison.

Tokens are deliberately not equalised: extra compute in MULTI is part of the
treatment's cost-performance effect and is measured as an outcome.

## O — Observability

| Item                         | Value                                                                                                                                                                                                        |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| <<<<<<< HEAD                 |
| Trace                        | full `stream-json` trace per run (`trace.jsonl`), including hook lifecycle events; orchestrator and subagent events attributed by `parent_tool_use_id`                                                       |
| Resource accounting          | last cumulative `result.modelUsage`, summed over all reported models, in `metrics.json.token_accounting`; per-model breakdown retained                                                                       |
| Completeness                 | flagged `partial_snapshot` on timeout, error result, parse errors, or usage-bearing events after the final result; trailing CLI `system` housekeeping does not flag it                                       |
| Process measures             | wall-clock, tool calls by name and by actor, delegation count and prompt size, subagent start/completion/result summaries, unique assistant messages                                                         |
| Known-unreliable             | `result.num_turns` under MULTI (reports 1–2 turns for runs with 20–36 tool calls); recorded but never compared                                                                                               |
| Not observable               | the CLI's internal context compaction, its applied effort setting, its internal prompts. Stated as a limit, not claimed as controlled                                                                        |
| Preserved                    | prompt, treatment, patch, `git-status.txt`, `untracked-files.txt`, setup log, stderr, network probe, metadata with digests, and per-run `orchestration-gate/state.json` plus ordered `events.jsonl` in MULTI |
| =======                      |
| Trace                        | full `stream-json` trace per run (`trace.jsonl`), orchestrator and subagent events attributed when the CLI exposes actor relationships                                                                       |
| Resource accounting          | last cumulative `result.modelUsage`, summed over all reported models, in `metrics.json.token_accounting`; per-model breakdown retained                                                                       |
| Completeness                 | flagged partial on timeout, error result, parse errors, or usage-bearing activity after the final result; trailing non-usage CLI housekeeping does not invalidate a cumulative snapshot                      |
| Process measures             | wall-clock, tool calls by name and actor, delegation count/prompt size, unique assistant messages, subagent spawned/completed counts                                                                         |
| Treatment-adherence evidence | task/repository plus trace, metrics, metadata, patch and git-status artifacts; gold patch/evaluator outcome excluded during adherence coding                                                                 |
| Known-unreliable             | `result.num_turns` under MULTI; recorded but not used as the comparative process measure                                                                                                                     |
| Not observable               | internal context compaction, exact internal prompts, server-side applied effort, and other undisclosed Claude Code internals                                                                                 |
| Preserved                    | task prompt, treatment, patch, git status, untracked files, setup log, stderr, network probe, metadata with digests, full execution trace                                                                    |

> > > > > > > refs/remotes/origin/main

## V — Verification

| Item                    | Value                                                                                                                                                                                              |
| ----------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Outcome                 | official SWE-bench evaluator, unmodified                                                                                                                                                           |
| Patch collection        | `git add -A` then `git diff --cached <base> --binary`, after inference, as root; includes new files and agent commits                                                                              |
| Secondary outcome       | share of FAIL_TO_PASS and PASS_TO_PASS tests passing                                                                                                                                               |
| <<<<<<< HEAD            |
| Statistics              | exact McNemar on paired resolution; exact paired randomisation test on cost differences (`analyze_runs.py`, committed before the series)                                                           |
| Agent-side verification | whatever the agent chooses to run; not prescribed, not part of the outcome                                                                                                                         |
| Stopping                | SINGLE stops normally. In MULTI, a managed `Stop` hook rejects finalization until one `SubagentStart`; afterward stopping is normal. The 2700 s wall-clock remains an experimental timeout outcome |
| =======                 |
| Statistics              | exact McNemar on paired resolution; exact paired randomisation test on cost differences (`analyze_runs.py`, fixed before the v4 main series)                                                       |
| Agent-side verification | final verification is required of the MULTI parent by treatment; exact commands/tests remain chosen by the agent                                                                                   |
| Stopping                | agent stops itself, or the 2700 s wall-clock ends the run; a timeout is an experimental outcome                                                                                                    |

> > > > > > > refs/remotes/origin/main

## G — Governance

| Item             | Value                                                                                                                                                                                                  |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Sample           | 12 v4 SWE-bench instances: 5 `orchestration-friendly`, 5 `single-friendly`, 2 `orchestration-risky`; frozen in `../preregistration/v4/selection_v4.json` and `../preregistration/v4/tasks-main-v4.txt` |
| Benchmark status | 10 SWE-bench Verified + 2 manually audited original SWE-bench instances (`sympy__sympy-19201`, `django__django-12508`)                                                                                 |
| Pairing          | primary treatment comparison is within-instance SINGLE vs MULTI; friendly/control pairs are descriptive, not newly optimized exact matches                                                             |
| Dev instance     | `sympy__sympy-20590`, excluded from the sample; development/validation only                                                                                                                            |
| Gold patch       | may be inspected only during pre-experiment task-selection/construct audit; never supplied to the solving model                                                                                        |
| Order            | v4 task and within-instance condition order frozen in `run-order-v4.tsv`; six SINGLE-first and six MULTI-first; `run_series.py` defaults to the v4 files                                               |
| Order generation | Python `random.Random(20260911)`: shuffle the 12-task list, then shuffle six `multi-first` plus six `single-first` labels and assign them in order                                                     |
| Freeze manifest  | `FREEZE_V4.json` pins Git blob hashes for execution, treatment, sample/order, analysis, adherence and main network inputs; `run_series.py` verifies it before main inference                           |
| Freeze bypass    | only `--allow-unfrozen-runner`, reserved for validation and prohibited for reported main runs                                                                                                          |
| Adherence        | A0-A7 protocol frozen in `../preregistration/v4/ADHERENCE_PROTOCOL.md`; non-compliance is retained and reported, never retried/excluded                                                                |
| Substitution     | only for documented infrastructure failure under the preregistered paired-replacement rules                                                                                                            |
| Not substituted  | timeouts, empty/invalid patches, failing tests, poor delegation, treatment non-compliance — experimental outcomes                                                                                      |
| Amendments       | v4 task-selection/treatment amendment recorded in `../preregistration/v4/AMENDMENT.md` before v4 main outcomes                                                                                         |
| Failure analysis | preregistered coding scheme in `../preregistration/FAILURE_ANALYSIS_PROTOCOL.md`; no outcome-driven recoding                                                                                           |
| Credentials      | a per-run copy of a dedicated Claude profile; refreshed tokens returned to the original; never committed                                                                                               |

## Declared limitations

1. Provider/authentication hosts remain reachable because the agent cannot run
   without them. Repository and package hosts are blocked; the claim is no
   runtime access to the upstream fix, not zero network access.
2. Internal Claude Code mechanisms (including context compaction, retry
   behaviour and server-side effort application) cannot be directly disclosed
   or controlled. They are held constant only through the same pinned CLI/model
   configuration across conditions.
3. 12 instances × 1 run per condition does not estimate run-to-run stochastic
   <<<<<<< HEAD
   variance. The design is a small paired experiment on one model, not an
   estimate of general harness variance.
4. The treatment assigns MULTI a lead-agent role and requires at least one
   substantive delegated contribution before the solution is complete. It
   leaves the decomposition, number and roles of subagents, scheduling, and
   integration to the model, but excludes a post-hoc review or other formality
   as the only delegated contribution. An actual subagent start is necessary
   but not sufficient for compliance; substantive contribution requires
   trajectory annotation.
   \=======
   variance. The design is a small paired case study, not a universal estimate
   of multi-agent effectiveness.
5. The treatment estimates the effect of a **specific mandatory workstream-oriented
   orchestration policy**, not subagent availability in isolation. The effect
   includes decomposition, delegation, context routing, parallel/sequential
   scheduling, integration and final verification requirements.
6. The two cleanest Tier-A orchestration-friendly instances are outside
   SWE-bench Verified, while the remaining friendly instances are more coupled.
   Friendly-vs-control stratum comparisons are therefore exploratory
   heterogeneity analysis and should not be interpreted as an exact matched
   causal contrast.
7. Blocking runtime access to GitHub/PyPI does not rule out benchmark
   contamination already present in model weights. This is symmetric between
   SINGLE and MULTI but can reduce the need for repository exploration and
   orchestration on memorized tasks.

> > > > > > > refs/remotes/origin/main
