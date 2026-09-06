# How the allow-list was derived

Date: 2026-09-06. Instance: `sympy__sympy-20590` (the excluded dev instance),
condition SINGLE, run label `network-discovery-20260906`.

The allow-list is not a guess about which hosts Claude Code needs. The task
container was put on the isolated network behind `squid-discovery.conf`, which
permits every destination and logs it, and one full run was executed. The
observed set is the allow-list's evidence base.

## Observed destinations

From the proxy access log for that run, excluding the runner's own probe
requests (the first four entries, at container setup):

| host | role | allow-listed |
| --- | --- | --- |
| `api.anthropic.com` | inference | yes |
| `downloads.claude.ai` | CLI binary download | yes |
| `claude.ai` | CLI install script | yes |
| `http-intake.logs.us5.datadoghq.com` | CLI telemetry | no |
| `github.com` | plugin marketplace refresh (see below) | no |

## The GitHub fetch

One `CONNECT github.com:443` of 3.3 MB occurred *after* inference had started.
It is not the agent solving the task: the trace contains no GitHub reference,
and no Bash tool call fetched anything. It is the CLI refreshing the plugin
marketplace `anthropics/claude-plugins-official`, which the copied profile
registers in `plugins/known_marketplaces.json`.

No plugin is enabled in that profile, so the refresh has no effect on the
agent's toolset. Under `squid.conf` the refresh is refused like any other
GitHub request, and the run proceeds.

This is worth recording for a different reason: it is a direct observation that
the task container had working GitHub egress under the pre-amendment
configuration. Whether or not any agent used it, the capability was there.

## Telemetry

`http-intake.logs.us5.datadoghq.com` is not required for inference and is not
allow-listed, so no run data leaves for a third party. The confirmation run
under the strict configuration verifies that its absence does not affect the
run.

## Amendment 2026-09-06: the OAuth refresh host

The table above is what one discovery run contacted. It is not the complete set
of hosts the CLI can need, and one absence was load-bearing: that run started
with a valid access token, so the CLI never refreshed it and never revealed
where refresh goes. `api.anthropic.com` was credited with the role on
assumption.

The gap surfaced on the first validation run started with an expired token
(`runs/runner-frozen3-validation-20260906/.../single`). The proxy refused
`platform.claude.com` six times between 14:55:21 and 14:55:26, interleaved with
two 401 `authentication_failed` retries against `api.anthropic.com`, and the
run ended after 5 seconds with

    Failed to authenticate. API Error: 401 OAuth access token has expired.
    Re-authenticate to continue.

`platform.claude.com` is therefore allow-listed. It is Anthropic's own auth
host; it serves neither the repository under test nor a package index, so the
"no access to the fix" claim is unchanged. Without it any run whose token
expires cannot authenticate, which over a 24-run series is a certainty rather
than a risk: the access token lives about six hours.

The same run showed a second defect, fixed in the runner rather than here: an
authentication failure produced no patch, no tool calls and exit 0, which would
have entered the analysis as a legitimate unresolved instance. Runs that never
reach the model now exit 20 as infrastructure.
