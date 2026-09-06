# Runner amendment before the main series

Date: 2026-09-06. This supplements the frozen `PROTOCOL.md`; the sample,
within-pair order, problem prompt and MULTI treatment remain as registered.
Validation uses only the excluded dev instance `sympy__sympy-20590`.

## Conditions and effort

- Claude Code stays at `2.1.261`; the solving model is `claude-sonnet-5`.
- Both conditions explicitly request `--effort high` and set
  `CLAUDE_CODE_EFFORT_LEVEL=high` in the inference process environment. Child
  processes inherit this variable. MULTI also sets
  `CLAUDE_CODE_SUBAGENT_MODEL=claude-sonnet-5`.
- `high` is the documented Sonnet 5 default. Subagents inherit session effort;
  the environment variable takes precedence over subagent effort overrides.
  Sources checked on 2026-09-06:
  [model configuration](https://code.claude.com/docs/en/model-config) and
  [subagents](https://code.claude.com/docs/en/sub-agents).
- `effort_requested` records the requested setting. Stream-json in the pinned
  CLI does not report applied effort, so this is configuration evidence, not
  a per-request observation of the server setting. Organization limits, if
  introduced, would need separate verification.
- SINGLE has no appended placebo. Only MULTI receives `multi-treatment.txt`.
- Both conditions use `--safe-mode` and have no experiment-imposed turn or
  token limit. The inference wall-clock limit remains 2700 seconds.
- The CLI toolset calls the delegation tool `Task`; emitted calls can be named
  `Agent`. Both names count. A call alone does not prove completion: MULTI
  requires `subagent_stats.completed >= 1`. Missing completion evidence is
  marked unverified, not passed. No automatic retry follows a violation.

## Token accounting

Primary resource fields are `metrics.json.token_accounting.totals`:

- `input_tokens`: uncached input;
- `cache_read_input_tokens`: cached input read;
- `cache_creation_input_tokens`: input written to cache;
- `output_tokens`: output including thinking;
- `total_tokens`: the sum of those four disjoint categories.

The source is the **last cumulative `result.modelUsage` snapshot**, summed over
all reported model entries. Repeated result snapshots are not added together.
Thinking tokens are not added again. Per-model records are retained in
`token_accounting.by_model`, so the solving model and CLI auxiliary calls
(observed as Haiku in dev runs) remain distinguishable. Auxiliary model usage
does not by itself mean that a solving subagent changed model.

Evidence from the real MULTI dev trace `runner-fix-reauth-20260906`:

- 48 assistant events correspond to 26 distinct actor/message-id pairs;
- summing every assistant event duplicates usage;
- deduplicated input/cache counts across parent and child exactly match the
  Sonnet `modelUsage` entry: 52 uncached, 40083 cache-created, 588838 cache-read;
- deduplicated streaming output snapshots show only 115 tokens, while final
  Sonnet `modelUsage` reports 8041 output tokens;
- the two final result events carry identical cumulative `modelUsage`, while
  their `usage` values differ. The last `usage.output_tokens` is only 2127.

Consequently `usage_reported` is retained only as raw result-event data, and
`message_usage_observed_by_actor` is diagnostic, deduplicated by actor/message
id. Neither is a substitute for complete experiment-level totals. The old
`usage_summed` field has been removed.

Missing or invalid `modelUsage` produces null totals, not zero. Timeouts, error
results, parse errors or activity after the last result mark any available
snapshot partial. Report missing/partial resource measurements explicitly;
do not exclude the corresponding quality outcomes or replace tasks because
resource accounting is incomplete.

## Patch and authentication handling

The evaluator receives `git add -A` followed by `git diff --cached <base>
--binary`, including new files and any commits made by the agent. Untracked
paths are recorded before staging. At timeout the container is stopped and
restarted only to collect its filesystem state; the timeout is still an
experimental outcome.

Each run uses a separate copy of the Claude profile. Real refresh probing
confirmed that refreshed tokens remain in that copy while the original profile
stays unchanged. Therefore refreshed `.credentials.json` is now atomically
returned to the original profile with mode 0600 before the copy is removed.
Run history and settings are not copied back. A profile lock prevents two
runners from refreshing the same session concurrently; a changed source file
causes synchronization to stop instead of overwriting a new login.

On synchronization failure the controller returns 20 and preserves the
temporary profile outside the artifact tree for manual recovery. It does not
retry or select a reserve automatically. Credentials are never committed.
CLI error messages with model `<synthetic>` remain errors, not model drift.

## Network isolation

Added 2026-09-06, before main inference began.

The previous runner disallowed `WebFetch` and `WebSearch` but left `PROXY_ENV`
empty and `DOCKER_NETWORK` unset, so the container itself kept full egress.
Removing the CLI's web tools is not the same as blocking the container's
network: Bash could still reach GitHub and PyPI.

Task containers now run on `nir-internal`, created with `--internal` and
therefore without a gateway. The only route out is the squid container
`nir-proxy`, attached to both `nir-internal` and `nir-egress`, which refuses
every destination outside `network/allowlist.txt`. The allow-list is
`.anthropic.com` (inference, OAuth refresh) and `.claude.ai` (CLI install
script and binary). It was read off an observed run rather than assumed;
`network/DISCOVERY.md` records the method and the full contacted host set.
GitHub, PyPI and the CLI's Datadog telemetry endpoint are excluded.

Isolation is evidenced per run, not per configuration. Before inference the
controller probes github.com, raw.githubusercontent.com, pypi.org and
api.anthropic.com from inside the task container, and writes the outcome to
`network-probe.txt` and `metadata.json.network_isolation`. A reachable blocked
host ends the run as a configuration violation (exit 50); an unreachable
api.anthropic.com ends it too, rather than spending the wall-clock budget on an
unauthenticated CLI. The controller also refuses to run if `nir-internal` is
not actually internal, or if the live proxy serves a configuration other than
the one on disk.

Validation on the excluded dev instance `sympy__sympy-20590`:

- `network-discovery-20260906`, SINGLE, open logging proxy (`--network-discovery`,
  recorded as `enforced: false`, not a measured run). Contacted
  api.anthropic.com, claude.ai, downloads.claude.ai,
  http-intake.logs.us5.datadoghq.com and github.com. `protocol_status: pass`.
- `network-isolation-validation-20260906`, MULTI, strict allow-list. Probes
  recorded github.com, raw.githubusercontent.com and pypi.org as unreachable
  (curl exit 56 against squid's 403) and api.anthropic.com as reachable. The
  proxy log shows 18 tunnels to api.anthropic.com, and denials for GitHub, PyPI
  and telemetry. `protocol_status: pass`, `subagent_stats.completed: 1`,
  `models_seen: {claude-sonnet-5: 52}`, patch collected.

The MULTI run establishes that subagent inference also works through the proxy,
and that neither the blocked telemetry endpoint nor the blocked GitHub request
affects the run.

That GitHub request is worth naming, since it is the observation behind the
audit item. Under the open configuration the CLI fetched 3.3 MB from
github.com _after_ inference had started: the copied profile registers the
plugin marketplace `anthropics/claude-plugins-official`, which the CLI
refreshes at startup. No plugin is enabled in that profile and no agent Bash
call touched GitHub, so nothing in the measured behaviour changed — but the
container demonstrably had working GitHub egress, which is exactly what the
audit said could not be ruled out.

Residual limitation: `.anthropic.com` and `.claude.ai` remain reachable,
because the agent cannot run without its provider. Neither hosts the repository
under test or its upstream fix. The claim is "no access to the fix", not "no
network".

## Snapshot completeness and the series driver

Added 2026-09-06, before main inference began. Third freeze.

### `partial_snapshot` was firing on healthy runs

Completeness of the token snapshot was defined as "no trace events after the
final `result` event". That is too strong for the observed CLI. In the real
MULTI validation trace
`runs/network-isolation-validation-20260906/sympy__sympy-20590/multi`, `result`
is event 140 of 143 and is followed by three `system` events —
`background_tasks_changed`, then `task_updated` and `task_notification` for the
backgrounded delegation task being torn down. The run was successful,
`parse_errors: 0`, `is_error: false`, and the totals were the final cumulative
ones, yet it was recorded `partial_snapshot`.

Token usage is reported only on `assistant` and `result` events; a `system`
event carries none and therefore cannot invalidate a cumulative snapshot. Since
MULTI ends with that teardown almost every time, the old rule would have marked
most MULTI runs partial and destroyed the distinction from a genuinely truncated
measurement — exactly the runs where resource outcomes matter most.

`read_trace` now counts both: `events_after_result` (all, unchanged meaning) and
`usage_events_after_result` (excluding `type: system`). Completeness uses the
latter; both are written to `metrics.json` so the judgement stays auditable.
Nothing about the totals themselves changed: recomputing the validation trace
gives the same
`{input 1201, output 8994, cache_read 519830, cache_creation 43604}` and now
reports `complete`.

This makes the flag less likely to fire, so it is stated plainly: a run whose
CLI emits assistant activity after the final result, times out, errors, or has
parse errors is still partial. The change was made before any main-series
outcome existed.

### `run_series.py`

`runner.py` executes one (instance, condition) pair and has no opinion about
what runs next; until now `run-order.tsv` was read by nothing at all, so the
frozen order depended entirely on typing 24 commands correctly. The driver
`experiment/execution/run_series.py` executes the series and refuses to start
unless the order file describes exactly the instances in `tasks-main.txt` and
`sha256sum -c runner.sha256` passes, so a series cannot be produced by an
unfrozen runner. It follows the recorded within-pair order, runs strictly
sequentially (the profile lock and the shared proxy make concurrency unsafe, and
interleaved runs would not have comparable wall-clock), skips run directories
that already exist rather than re-running them, and stops the whole series on
any nonzero runner exit, naming the preregistered decision that exit requires.
It writes `series-log.tsv` next to the runs. It adds no retry and no
substitution logic: both remain human decisions under the preregistered rules.

### `analyze_runs.py` and the harness card

`experiment/execution/analyze_runs.py` builds the prediction files, joins each
run to the official evaluation report, and produces the paired comparison. It
is committed now, before any main outcome exists, so the choice of statistical
test cannot be made after seeing the data: exact McNemar on paired resolution,
and an exact paired randomisation test (full enumeration of the 2^n sign flips)
on cost differences. Its docstring is the analysis specification.

One measurement decision is recorded there and repeated here, because it
changes a preregistered process metric. `result.num_turns` does not describe a
MULTI session: `runner-freeze-validation/multi` reports 1 turn against 36 tool
calls and 71 assistant events, and `runner-final-sequential-20260906/multi`
reports 2 against 21 tool calls, while SINGLE runs of the same instance report
10-11 turns for 9-10 tool calls. Reported as-is it would make delegation look
cheaper in turns as a pure artefact. The compared process measure is therefore
`unique_assistant_messages` from the trace; `num_turns` is kept in the per-run
table as reported data and is not compared.

`experiment/execution/HARNESS_CARD.md` is the ETCSOVG disclosure of the frozen
configuration, closing the third finding of the Zhang audit. It is a
description of the runner, not a second source of truth: where the two
disagree, the runner is what ran.

## Authentication reachability and failed inference

Added 2026-09-06, before main inference began. Fourth freeze. Both items were
found by the first validation run of the third freeze and are recorded here
with the observation that produced them.

### The allow-list was missing the OAuth refresh host

The discovery run that produced the allow-list carried a fresh access token, so
the CLI never refreshed it, `platform.claude.com` never appeared in the log, and
`api.anthropic.com` was credited with the refresh role on assumption. The first
validation run started two hours after the token expired. The proxy refused
`platform.claude.com` six times between 14:55:21 and 14:55:26, interleaved with
two 401 `authentication_failed` retries, and the run ended in 5 seconds with
"OAuth access token has expired". `platform.claude.com` is now allow-listed;
`network/DISCOVERY.md` carries the evidence. It is Anthropic's own auth host and
serves no repository or package index, so the contamination claim is unchanged.
An access token lives roughly six hours, so over a 24-run series a refresh is a
certainty, not a contingency.

### An unauthenticated run must not look like a defeated agent

That same run exited 0 with `protocol_status: pass`, a 0-byte patch, no tool
calls and no model usage — indistinguishable, downstream, from an agent that
tried and failed. In a main series one expired token would have turned every
subsequent instance into a silent unresolved outcome.

`inference_failure()` now identifies runs that never reached the model:
`models_seen` empty (the CLI's `<synthetic>` error messages are not counted as
an LLM answer) together with `terminal_reason: api_error`, or with retried
provider errors on an error result. Such a run exits 20, which the
preregistration already classifies as infrastructure eligible for paired
substitution ("provider/network outage prevents inference from taking place"),
and `run_series.py` stops the series on it. `metrics.json` gains
`result_terminal_reason`, `result_text`, `api_retry_statuses` and
`inference_failure`.

An agent that answers and solves nothing is untouched by this: it produced
model messages, so it stays an experimental outcome.

### The proxy freshness check could not fail

Adding the host to `allowlist.txt` was not enough: the next run was refused
again, by a proxy container started at 11:00 UTC with the older file. The
staleness check read `/etc/squid/squid.conf` and `/etc/squid/allowlist.txt` back
out of the container and compared them to the files on disk — but both are
bind-mounted read-only from exactly those paths, so the comparison was between a
file and itself and could never report a difference. squid parses its ACLs once,
at startup, so what matters is which files existed when the process started.

The proxy is now stamped at creation with a label carrying the sha256 of both
config files, and freshness compares that label to the current digest. A changed
allow-list therefore forces the container to be recreated. `metadata.json`
records the digest under `network_isolation.proxy_config_digest`.

### Validation of the fourth freeze

`runs/runner-frozen4-validation-b`, dev instance `sympy__sympy-20590`, both
conditions, enforced isolation, with the expired token that produced the
failure being refreshed live through the proxy.

| | SINGLE | MULTI |
| --- | --- | --- |
| protocol_status | pass | pass |
| patch bytes | 647 | 647 |
| wall seconds | 73.5 | 77.9 |
| token accounting | complete | complete |
| total tokens | 210 699 | 470 868 |
| model messages | 10 | 22 |
| tool calls | 9 | 20 |
| subagents spawned/completed | — | 1 / 1 |
| official evaluator | resolved | resolved |

`credential_refresh_status: updated` — the refreshed token was written back to
the source profile, so the container did reach `platform.claude.com`. Probes
recorded GitHub, raw.githubusercontent and PyPI unreachable and
`api.anthropic.com` reachable in both runs. Both snapshots came out `complete`,
which is what the third freeze was for. The full chain patch -> predictions ->
official evaluator -> report -> paired summary was exercised end to end
(`frozen4-val-single`, `frozen4-val-multi`), so the analysis path is validated,
not just the runner.

## Verification and freeze

Repository gate: `.venv/bin/pytest --exitfirst --cov`.

The runner digest is stored in `runner.sha256`; verify from the repository root
with `sha256sum -c experiment/execution/runner.sha256`. The immutable-intent
local tag `nir-runner-frozen` identifies the commit containing this runner and
amendment. Do not move that tag after main inference begins.

The network-isolation amendment is a second freeze, made before main inference
began. `nir-runner-frozen` was left where it is, so that the state the audit
examined stays identifiable; that runner and amendment are tagged
`nir-runner-frozen-2`. The snapshot-completeness fix and the series driver are
a third freeze, `nir-runner-frozen-3`, and the authentication-reachability fix
is a fourth, `nir-runner-frozen-4`; both were also made before main inference. The
frozen failure-analysis protocol is tagged `nir-failure-analysis-frozen`. From
here the same rule applies to all of them: do not move them once main inference
begins. The main series must be produced by the runner whose digest matches
`runner.sha256` at `nir-runner-frozen-4`; the driver checks this itself.

Runs made before the isolation amendment are not part of the main series and
must not be merged into it. Any main-series run must carry
`metadata.json.network_isolation.enforced: true` and probe results showing the
blocked hosts unreachable; a run without that evidence is not a measured run.
