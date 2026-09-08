# Harness Card — SINGLE vs MULTI subagent study

Disclosure of the harness under which every measured run was produced, in the
seven dimensions of Zhang et al. (2026) — Execution, Tools, Context,
Scheduling, Observability, Verification, Governance. Their argument is that a
benchmark number is a property of the pair `{model, harness}`, so a result
reported without the harness cannot be compared with anything; this card exists
so that ours can be.

The experimental factor is **Scheduling** (whether subagents are available at all).
Every other dimension is held identical between conditions and is listed here
so that the claim "only one thing differs" can be checked rather than trusted.

Authoritative sources: `experiment/execution/runner.py` (digest in
`runner.sha256`), `PROTOCOL.md`, `RUNNER_AMENDMENT.md`,
`../preregistration/PROTOCOL.md`. Where this card and the runner disagree, the
runner is what ran.

State: Claude Code `2.1.261`, model `claude-sonnet-5`, frozen 2026-09-06 at tag
`nir-runner-frozen-3`.

## E — Execution

| Item | Value |
| --- | --- |
| Agent | Claude Code CLI `2.1.261`, headless (`-p`), installed inside the task container |
| Model | `claude-sonnet-5`, both conditions; MULTI subagents pinned with `CLAUDE_CODE_SUBAGENT_MODEL` |
| Effort | `--effort high` plus `CLAUDE_CODE_EFFORT_LEVEL=high` (inherited by subagents) |
| Environment | one clean SWE-bench task image per condition, from `swe-bench-tasks/tasks/<instance>/task.yaml` |
| Working copy | repository at the instance's base commit; gold patch never present |
| Inference user | `nonroot`, `HOME=/home/nonroot` |
| Autoupdate | `DISABLE_AUTOUPDATER=1` |
| Ambient config | `--setting-sources ''`, `--strict-mcp-config`, `--mcp-config '{"mcpServers":{}}'` — no filesystem settings, no CLAUDE.md, no plugins, no MCP servers |
| Repetition | one run per (instance, condition); no automatic retry |

## T — Tools

| Item | Value |
| --- | --- |
| Tool surface | the CLI's default toolset (file read/edit, shell, search), identical in both conditions |
| Permission mode | `--permission-mode bypassPermissions` with `--safe-mode` |
| Disallowed, SINGLE | `Task`, `WebFetch`, `WebSearch` |
| Disallowed, MULTI | `WebFetch`, `WebSearch` |
| Delegation tool | `Task`; emitted calls may be named `Agent`, both counted |
| Network | task container on `--internal` network `nir-internal` (no gateway); sole route out is the squid allow-list proxy `nir-proxy` |
| Allow-list | `.anthropic.com`, `.claude.ai` only; GitHub, PyPI and CLI telemetry are refused |
| Egress evidence | per run: `github.com`, `raw.githubusercontent.com`, `pypi.org` probed unreachable and `api.anthropic.com` reachable, recorded in `network-probe.txt` and `metadata.json.network_isolation` |

## C — Context

| Item | Value |
| --- | --- |
| Task prompt | `prompt-template.txt` + the instance problem statement, identical in both conditions; digests recorded per run |
| Treatment | MULTI only: `multi-treatment.txt` via `--append-system-prompt`, requiring early delegation before implementation details are derived, independent solution-finding by subagents, parallel fan-out of independent workstreams, and orchestrator-owned integration and final verification |
| Placebo | none; SINGLE receives no compensating appended prompt |
| Context management | the CLI's own; not configured, not overridden, and not directly observable |
| Subagent context | native Claude Code semantics: separate context window, but free to explore the repository with its own tools. No artificially fixed context budget is imposed |
| Delegated context | captured per delegation as `prompt_chars` and `description_chars` in `metrics.json` |

## S — Scheduling  (the experimental factor)

| Item | SINGLE | MULTI |
| --- | --- | --- |
| Delegation | technically disabled (`Task` disallowed) | at least one implementation subtask required |
| Orchestration | none | independent workstreams assigned before the orchestrator derives their solutions; subagents derive implementations independently; orchestrator integrates and verifies |
| Compliance | any `Task`/`Agent` call is a violation | requires `subagent_stats.completed >= 1` |
| Turn budget | none | none |
| Token budget | none | none |
| Background-agent wait | not applicable | no CLI-specific ceiling (`CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS=0`); bounded by the runner wall-clock limit |
| Wall-clock | 2700 s | 2700 s |

Tokens are deliberately not equalised: extra compute in MULTI is part of the
treatment and is measured as an outcome, not controlled away.

## O — Observability

| Item | Value |
| --- | --- |
| Trace | full `stream-json` trace per run (`trace.jsonl`), orchestrator and subagent events attributed by `parent_tool_use_id` |
| Resource accounting | last cumulative `result.modelUsage`, summed over all reported models, in `metrics.json.token_accounting`; per-model breakdown retained |
| Completeness | flagged `partial_snapshot` on timeout, error result, parse errors, or usage-bearing events after the final result; trailing CLI `system` housekeeping does not flag it |
| Process measures | wall-clock, tool calls by name and by actor, delegation count and prompt size, unique assistant messages |
| Known-unreliable | `result.num_turns` under MULTI (reports 1–2 turns for runs with 20–36 tool calls); recorded but never compared |
| Not observable | the CLI's internal context compaction, its applied effort setting, its internal prompts. Stated as a limit, not claimed as controlled |
| Preserved | prompt, treatment, patch, `git-status.txt`, `untracked-files.txt`, setup log, stderr, network probe, metadata with digests |

## V — Verification

| Item | Value |
| --- | --- |
| Outcome | official SWE-bench evaluator, unmodified |
| Patch collection | `git add -A` then `git diff --cached <base> --binary`, after inference, as root; includes new files and agent commits |
| Secondary outcome | share of FAIL_TO_PASS and PASS_TO_PASS tests passing |
| Statistics | exact McNemar on paired resolution; exact paired randomisation test on cost differences (`analyze_runs.py`, committed before the series) |
| Agent-side verification | whatever the agent chooses to run; not prescribed, not part of the outcome |
| Stopping | agent stops itself, or the 2700 s wall-clock ends the run; a timeout is an experimental outcome |

## G — Governance

| Item | Value |
| --- | --- |
| Sample | 12 SWE-bench Verified instances, seed 118, stratified L/M/D × difficulty, frozen before inference (`tasks-main.txt`) |
| Dev instance | `sympy__sympy-20590`, excluded from the sample; all debugging happens there |
| Order | task order and within-pair condition order randomised and frozen (`run-order.tsv`), enforced by `run_series.py` |
| Substitution | only for documented infrastructure failure (runner exit 20/40), always paired, from preregistered reserves |
| Not substituted | timeouts, empty or invalid patches, failing tests, poor delegation — all experimental outcomes |
| Freezes | `nir-preregistration`, `nir-sample-frozen`, `nir-execution-frozen`, `nir-runner-frozen`, `nir-runner-frozen-2`, `nir-runner-frozen-3`, `nir-failure-analysis-frozen` |
| Amendments | recorded in `RUNNER_AMENDMENT.md` with date and reason, all before main inference |
| Failure analysis | preregistered coding scheme in `../preregistration/FAILURE_ANALYSIS_PROTOCOL.md`, frozen before outcomes were seen |
| Credentials | a per-run copy of a dedicated Claude profile; refreshed tokens returned to the original; never committed |

## Declared limitations

1. `.anthropic.com` and `.claude.ai` stay reachable — the agent cannot run
   without its provider. Neither hosts the repository under test or its
   upstream fix. The claim is "no access to the fix", not "no network".
2. Internal Claude Code mechanisms (context compaction, retry behaviour, the
   effort setting actually applied server-side) cannot be disclosed or
   controlled from outside the CLI. They are held constant only in the sense
   that both conditions run the same pinned version.
3. 12 instances × 1 run per condition does not estimate run-to-run stochastic
   variance. The design is a small paired experiment on one model, not an
   estimate of general harness variance.
4. The treatment assigns MULTI an orchestrator role and requires at least one
   implementation delegation. It directs early parallel fan-out when
   independent workstreams are available and prohibits supplying a solved
   implementation in delegation prompts. The measured effect therefore
   includes this explicit scheduling policy rather than subagent availability
   alone. A MULTI run without a completed delegation is a protocol violation.
