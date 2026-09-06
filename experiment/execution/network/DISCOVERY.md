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
| `api.anthropic.com` | inference, OAuth token refresh | yes |
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
