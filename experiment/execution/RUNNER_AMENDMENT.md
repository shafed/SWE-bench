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

Added 2026-09-06 in response to item 1 of `experiment/METHODOLOGY_AUDIT_2026-09-06.md`.

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

## Verification and freeze

Repository gate: `.venv/bin/pytest --exitfirst --cov`.

The runner digest is stored in `runner.sha256`; verify from the repository root
with `sha256sum -c experiment/execution/runner.sha256`. The immutable-intent
local tag `nir-runner-frozen` identifies the commit containing this runner and
amendment. Do not move that tag after main inference begins.
