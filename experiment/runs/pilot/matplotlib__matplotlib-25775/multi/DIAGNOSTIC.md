# Pilot attempt diagnostic — 2026-09-10

Command run exactly as instructed:

```
uv run python experiment/execution/runner.py --instance matplotlib__matplotlib-25775 --condition multi --label pilot --position 0
```

Result: `runner_exit_code 50` (configuration violation — "discard, fix config,
rerun same instance", per `runner.py`'s own exit-code table). The run never
reached inference: no model was ever called, no gold patch was shown to the
agent (the prompt sent — `input/prompt.txt` — contains only the problem
statement, confirmed by inspection), and no MULTI treatment content was
exercised. This attempt therefore does **not** count as a test of the MULTI
treatment prompt; it is a pre-inference environment failure. No prompt edits
were made as a result.

## What was verified working in this session

- Docker daemon started successfully (`dockerd`, overlayfs storage driver) and
  `docker pull hello-world` succeeded — general container egress works.
- `swe-bench-tasks` cloned per `README.md` (`git clone --depth 1
  https://github.com/SWE-bench/swe-bench-tasks.git`).
- Task image `swebench/sweb.eval.x86_64.matplotlib_1776_matplotlib-25775:latest`
  pulled successfully from Docker Hub (10.8 GB).
- Python env installed via `uv sync` (+ `--group dev --extra datasets` for
  `anthropic`/`tiktoken`, avoiding the `inference` extra's `flash-attn`/`torch`
  build, which is irrelevant to running `runner.py`).
- `.venv/bin/pytest tests/test_experiment_runner.py -q` — 26/26 passed. (The
  full `pytest --exitfirst --cov` gate stalled for 20+ minutes on
  `tests/test_collect_cli.py::test_collect_one`, an unauthenticated live
  GitHub API pagination call unrelated to `runner.py`; it was killed as
  out-of-scope for this task rather than left blocking indefinitely.)
- `runner.sha256` matches the working tree, so `run_series.py` would not have
  refused a real series on tooling-integrity grounds.

## Why the run stopped (two independent, compounding blockers)

### 1. No portable Anthropic credential is available in this session

`runner.py` requires a pre-existing, already-authenticated Claude Code profile
at `~/.claude-swebench/.credentials.json` (an OAuth access/refresh token
pair), which it copies into each task container so the nested `claude` CLI can
authenticate directly against `api.anthropic.com`. That file does not exist in
this session:

- `claude auth status` reports `"loggedIn": true, "authMethod": "oauth_token"`,
  but this session's own authentication is host-managed
  (`CLAUDE_CODE_PROVIDER_MANAGED_BY_HOST=1`, session-ingress routed) and is not
  backed by a portable `.credentials.json` on disk anywhere in the container.
- `claude setup-token` (the documented non-interactive-looking path to a
  long-lived token) hangs indefinitely waiting on an interactive
  browser/device authorization flow; it produces no output and cannot
  complete without a human present to approve it. There is no human watching
  this scheduled run.
- No `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, or `CLAUDE_CODE_OAUTH_TOKEN`
  is set in the environment (all three are auth paths the installed CLI
  supports as an alternative to `.credentials.json`).

The prior successful pilot/main attempts recorded in this repo (for example
`runs/main-v3-single-subagent-treatment`, `runs/main-20260906`) show
`"credential_refresh_status": "unchanged"` or `"updated"`, meaning a working
profile already existed in whatever session produced them. Nothing in this
session provisioned one, and nothing in this session's own access lets it
complete the interactive OAuth flow needed to create one.

### 2. This sandbox's own egress path breaks the experiment's network-isolation probe

Independently of (1), the controller's own pre-inference safety check (`ensure
egress isolated, then confirm api.anthropic.com is actually reachable *before*
spending wall-clock on an unauthenticated CLI` — see `RUNNER_AMENDMENT.md`,
"Authentication reachability and failed inference") correctly refused to
proceed:

```
https://github.com                exit=56  http=000  reachable=False
https://raw.githubusercontent.com exit=56  http=000  reachable=False
https://pypi.org                  exit=56  http=000  reachable=False
https://api.anthropic.com         exit=60  http=000  reachable=False
```

`exit=60` is a TLS trust failure ("SSL certificate problem: self-signed
certificate in certificate chain"), not a routing failure. This remote
execution environment terminates **all** outbound HTTPS — including from
nested Docker containers — through its own intercepting proxy (documented
elsewhere in this session as an "agent proxy" with a custom CA bundle at
`/root/.ccr/ca-bundle.crt`). The experiment's isolated `nir-proxy` (squid)
container has no reason to trust that CA, so its probe of the one allow-listed
host it must reach cannot complete, and the controller correctly treats that
as "inference would run unauthenticated" and aborts (`exit 50`) rather than
silently letting it through or scoring it as a solved/unsolved task.

Making this probe pass would require either handing the nested proxy the
sandbox's own intercepting CA (which would mean every "isolated" run in this
environment is actually being read by a platform-level MITM proxy of unknown
scope — a materially different isolation guarantee than the frozen protocol
documents and not something to decide unilaterally) or running this experiment
from an environment with genuine direct egress to `api.anthropic.com`. Neither
is available in this session.

## Disposition

Per task instruction #8: this is treated as an unsolvable infrastructure
failure from within this session. Stopping here.

- 0 of the allowed 3 pilot attempts were spent revising
  `multi-treatment.txt` — the failure occurs before any model call, so the
  treatment prompt was never exercised and there is nothing about it to learn
  from this attempt.
- The main 12-task series (`run-order-v3.tsv`) was **not** started.
- No protocol, runner, or treatment file was modified as a workaround.
- Raw artifacts from the attempt (`metadata.json`, `network-probe.txt`,
  `setup.log`, `input/prompt.txt`, `input/treatment.txt`) are preserved
  alongside this note.

## What would unblock a retry

Either of:

1. A session/environment where `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, or
   `CLAUDE_CODE_OAUTH_TOKEN` is provisioned as a secret (so `runner.py` could
   be adapted to use it), or where `~/.claude-swebench` already carries a
   valid, previously-completed interactive login; **and**
2. Confirmation that the environment's task containers can reach
   `api.anthropic.com` directly (or through the experiment's own allow-listed
   squid proxy) without a platform-level TLS-intercepting layer in between.
