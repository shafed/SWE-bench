#!/usr/bin/env python3
"""
runner.py -- one (instance, condition) run of the SINGLE vs MULTI subagent study.

Frozen design invariants (must not change after the `preregistration` tag):

  * Only MULTI receives multi-treatment.txt as an appended system prompt.
    SINGLE has no additional treatment, as in the validated dev protocol.
    The intended difference is availability and mandated use of `Task`.

  * Both conditions run with identical isolation flags, identical wall-clock
    timeout, with no experiment-imposed turn or token budget.

  * A timeout is an EXPERIMENTAL OUTCOME. It is never a reason to substitute a
    reserve instance. Only exit code 20/40 (infrastructure) may trigger
    substitution, and only for the instance in BOTH conditions.

Exit codes
  0   run completed; outcome recorded (includes timeouts and protocol violations)
  20  controller / infrastructure failure  -> eligible for reserve substitution
  30  claude exited non-zero               -> pre-registered manual classification
  40  patch collection failed              -> infrastructure
  50  configuration violation              -> discard, fix config, rerun same instance
"""

from __future__ import annotations

import argparse
import collections
import fcntl
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


# ----------------------------------------------------------------------------
# Frozen configuration
# ----------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[2]
EXEC_DIR = ROOT / "experiment" / "execution"
TASK_REPO = ROOT / "swe-bench-tasks"
RUNS_DIR = ROOT / "experiment" / "runs"

CLAUDE_PROFILE = Path.home() / ".claude-swebench"
CLAUDE_VERSION = "2.1.261"
MODEL = "claude-sonnet-5"
EFFORT = "high"

DEFAULT_TIMEOUT = 45 * 60  # wall-clock budget, identical in both conditions
MAX_TURNS = None  # frozen protocol: no experiment-imposed turn limit
MAX_BUDGET_USD = None  # set a float to add --max-budget-usd, or leave None

DOCKER_SETUP_TIMEOUT = 600  # per setup docker exec
DOCKER_COLLECT_TIMEOUT = 300  # per collection docker exec
KILL_GRACE = 30

# Allow the runtime `curl | bash` install. Prefer False plus a preflight-built
# image that already ships the pinned CLI: it removes both the network
# dependency and the version-drift surface from the measured run.
ALLOW_RUNTIME_INSTALL = True

# Egress control. The task container sits on an --internal Docker network and
# therefore has no route off the host at all; the only way out is the squid
# allow-list proxy, which refuses every destination outside allowlist.txt. This
# is what stops Bash from reaching GitHub/PyPI and retrieving the upstream fix.
# Disabling the Claude Code web tools alone does not achieve that.
NETWORK_DIR = Path(__file__).resolve().parent / "network"
PROXY_IMAGE = "ubuntu/squid:latest"
PROXY_CONTAINER = "nir-proxy"
INTERNAL_NETWORK = "nir-internal"  # no gateway: task containers live here
EGRESS_NETWORK = "nir-egress"  # proxy's second interface, has a route out

PROXY_ENV: dict[str, str] = {
    "HTTPS_PROXY": f"http://{PROXY_CONTAINER}:3128",
    "HTTP_PROXY": f"http://{PROXY_CONTAINER}:3128",
    "NO_PROXY": "localhost,127.0.0.1",
}
DOCKER_NETWORK: str | None = INTERNAL_NETWORK

# Probed inside the task container before inference. A reachable blocked host
# is a configuration violation, not a warning: it means the run could have seen
# the upstream fix. An unreachable allowed host fails the run early instead of
# letting it burn the wall-clock budget on an unauthenticated CLI.
BLOCKED_PROBE_URLS = (
    "https://github.com",
    "https://raw.githubusercontent.com",
    "https://pypi.org",
)
ALLOWED_PROBE_URL = "https://api.anthropic.com"

# Flags the command is built from. Verified against `claude --help` at runtime so
# that a renamed or removed flag fails loudly instead of silently no-op'ing.
REQUIRED_FLAGS = [
    "--model",
    "--effort",
    "--output-format",
    "--verbose",
    "--permission-mode",
    "--append-system-prompt",
    "--disallowedTools",
    "--safe-mode",
]
OPTIONAL_FLAGS = [
    "--setting-sources",
    "--strict-mcp-config",
    "--mcp-config",
    "--forward-subagent-text",
    "--max-budget-usd",
]

DELEGATION_TOOLS = {"Task", "Agent"}
TOKEN_FIELDS = {
    "input_tokens": "inputTokens",
    "output_tokens": "outputTokens",
    "cache_read_input_tokens": "cacheReadInputTokens",
    "cache_creation_input_tokens": "cacheCreationInputTokens",
}

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]")
PROFILE_IGNORE = shutil.ignore_patterns(
    "projects", "todos", "shell-snapshots", "statsig", "*.log", ".nir-runner.lock"
)


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path: Path, data: dict) -> None:
    """Atomic: a crash mid-write must not truncate the provenance file."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


def lock_profile(profile: Path):
    """Only one runner may refresh a given OAuth session at a time."""
    fd = os.open(profile / ".nir-runner.lock", os.O_CREAT | os.O_RDWR, 0o600)
    lock = os.fdopen(fd, "r+")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        lock.close()
        raise RuntimeError("Claude profile is already in use by another runner") from None
    return lock


def preserve_credentials(source: Path, copied: Path, before: bytes | None) -> str:
    """Return refreshed auth only; never copy run history/settings back.

    The runner lock serializes our own runs. The byte comparison also refuses
    to overwrite a login performed externally while inference was running.
    """
    if before is None or not copied.exists():
        return "not_present"
    refreshed = copied.read_bytes()
    if refreshed == before:
        return "unchanged"
    data = json.loads(refreshed)
    oauth = data.get("claudeAiOauth") or {}
    if not all(isinstance(oauth.get(k), str) and oauth[k]
               for k in ("accessToken", "refreshToken")):
        raise RuntimeError("Refreshed OAuth credentials are invalid")
    if not source.exists() or source.read_bytes() != before:
        raise RuntimeError("Source credentials changed during run; refusing to overwrite")
    fd, temp = tempfile.mkstemp(prefix=".nir-auth-", dir=source.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(refreshed)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temp, 0o600)
        os.replace(temp, source)
    finally:
        Path(temp).unlink(missing_ok=True)
    return "updated"


def run(cmd, *, check=True, stdout=None, stderr=None, timeout=None):
    return subprocess.run(
        cmd,
        cwd=ROOT,
        check=check,
        stdout=stdout,
        stderr=stderr,
        text=True,
        timeout=timeout,
    )


def docker_exec(container: str, *, user=None, env=None) -> list[str]:
    cmd = ["docker", "exec"]
    if user:
        cmd += ["-u", user]
    for key, value in (env or {}).items():
        cmd += ["-e", f"{key}={value}"]
    cmd.append(container)
    return cmd


def dexec(container, script, *, user=None, env=None, **kw):
    """Run a bash -lc script inside the container."""
    return run(
        docker_exec(container, user=user, env=env) + ["bash", "-lc", script], **kw
    )


def docker_out(args, *, check=False) -> str:
    return run(
        ["docker", *args],
        check=check,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    ).stdout.strip()


def ensure_network(name: str, internal: bool) -> None:
    existing = docker_out(["network", "inspect", "-f", "{{.Internal}}", name])
    if not existing:
        run(
            ["docker", "network", "create"] + (["--internal"] if internal else []) + [name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
        )
        existing = docker_out(["network", "inspect", "-f", "{{.Internal}}", name])
    if (existing == "true") != internal:
        raise RuntimeError(
            f"docker network {name} has Internal={existing}, expected {internal}"
        )


def ensure_egress_proxy(config_name: str) -> dict:
    """Start, or verify, the allow-list proxy and the isolated network.

    Idempotent, and deliberately unforgiving: a network that is not actually
    internal, or a proxy still serving a superseded allow-list, raises rather
    than degrades. The failure being prevented is a run that silently had full
    egress and could have read the upstream fix.
    """
    squid_conf = NETWORK_DIR / config_name
    allowlist = NETWORK_DIR / "allowlist.txt"
    wanted = {
        "/etc/squid/squid.conf": squid_conf.read_text().strip(),
        "/etc/squid/allowlist.txt": allowlist.read_text().strip(),
    }

    ensure_network(INTERNAL_NETWORK, internal=True)
    ensure_network(EGRESS_NETWORK, internal=False)

    running = docker_out(["inspect", "-f", "{{.State.Running}}", PROXY_CONTAINER])
    if running == "true":
        stale = any(
            docker_out(["exec", PROXY_CONTAINER, "cat", path]) != body
            for path, body in wanted.items()
        )
    else:
        stale = True

    if stale:
        run(
            ["docker", "rm", "-f", PROXY_CONTAINER],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        run(
            [
                "docker", "run", "-d",
                "--name", PROXY_CONTAINER,
                "--network", INTERNAL_NETWORK,
                "-v", f"{squid_conf}:/etc/squid/squid.conf:ro",
                "-v", f"{allowlist}:/etc/squid/allowlist.txt:ro",
                PROXY_IMAGE,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
            timeout=DOCKER_SETUP_TIMEOUT,
        )
        run(
            ["docker", "network", "connect", EGRESS_NETWORK, PROXY_CONTAINER],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
        )
        deadline = time.monotonic() + 60
        while "listening port: 3128" not in docker_out(["logs", PROXY_CONTAINER]):
            if time.monotonic() > deadline:
                raise RuntimeError("egress proxy did not start listening on 3128")
            time.sleep(2)

    return {
        "proxy_container": PROXY_CONTAINER,
        "proxy_image_id": docker_out(["inspect", "-f", "{{.Image}}", PROXY_CONTAINER]),
        "internal_network": INTERNAL_NETWORK,
        "squid_config": config_name,
        "squid_config_sha256": sha256_file(squid_conf),
        "allowlist_sha256": sha256_file(allowlist),
        "allowlist": [
            line.strip()
            for line in allowlist.read_text().splitlines()
            if line.strip() and not line.startswith("#")
        ],
    }


def probe_egress(container: str, log) -> dict:
    """Evidence, per run, that the container could not reach the fix.

    curl exits non-zero when squid refuses the CONNECT tunnel, so the exit code
    is the observation; the allowed URL confirms the proxy path itself works.
    """
    results = {}
    for url in (*BLOCKED_PROBE_URLS, ALLOWED_PROBE_URL):
        probe = dexec(
            container,
            f"curl -sS -o /dev/null -w '%{{http_code}}' --max-time 25 {shlex.quote(url)}",
            user="nonroot",
            env={"HOME": "/home/nonroot", **PROXY_ENV},
            check=False,
            stdout=subprocess.PIPE,
            stderr=log,
            timeout=DOCKER_SETUP_TIMEOUT,
        )
        results[url] = {
            "exit_code": probe.returncode,
            "http_code": probe.stdout.strip(),
            "reachable": probe.returncode == 0,
        }
    return results


def task_image(instance_id: str) -> str:
    path = TASK_REPO / "tasks" / instance_id / "task.yaml"
    text = path.read_text()
    if yaml is not None:
        data = yaml.safe_load(text) or {}
        image = data.get("image")
        if not image:
            raise RuntimeError(f"No top-level `image` field in {path}")
        return str(image).strip()
    # Fallback: top-level key only (no leading whitespace), quotes stripped.
    for line in text.splitlines():
        if line.startswith("image:"):
            return line.split(":", 1)[1].strip().strip("\"'")
    raise RuntimeError(f"No image field in {path}")


def task_problem(instance_id: str) -> Path:
    path = TASK_REPO / "tasks" / instance_id / "problem_statement.md"
    if not path.exists():
        raise FileNotFoundError(path)
    return path


# ----------------------------------------------------------------------------
# Trace parsing
# ----------------------------------------------------------------------------
def read_trace(path: Path) -> dict:
    """
    Extract everything the analysis needs from the stream-json trace.

    Actor attribution matters: in MULTI the stream carries both orchestrator and
    subagent events, so an undifferentiated tool count cannot separate the cost
    of delegation from the cost of the work itself.
    """
    out = {
        "result": None,
        "parse_errors": 0,
        "tools": collections.Counter(),
        "tools_by_actor": collections.defaultdict(collections.Counter),
        "models": collections.Counter(),
        "delegations": [],
        "message_usage_by_actor": collections.defaultdict(collections.Counter),
        "messages_without_id": 0,
        "assistant_events": 0,
        "result_events": 0,
        "events_after_result": 0,
    }
    if not path.exists():
        return out

    message_usage = {}
    for raw in path.read_text(errors="replace").splitlines():
        line = ANSI_RE.sub("", raw).strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            out["parse_errors"] += 1
            continue
        if not isinstance(obj, dict):
            out["parse_errors"] += 1
            continue

        if obj.get("type") == "result":
            out["result"] = obj
            out["result_events"] += 1
            out["events_after_result"] = 0
        elif out["result"] is not None:
            out["events_after_result"] += 1

        if obj.get("type") != "assistant":
            continue

        out["assistant_events"] += 1
        msg = obj.get("message") or {}
        actor = obj.get("parent_tool_use_id") or "orchestrator"

        # CLI errors (for example expired OAuth) use <synthetic>, not an LLM.
        # Keep their result/error event, but do not report model drift.
        if msg.get("model") and msg["model"] != "<synthetic>":
            out["models"][msg["model"]] += 1

        # One API message can produce several content-block events sharing an
        # id and usage snapshot. These snapshots are diagnostic, not final
        # billed usage: in particular output_tokens can still be incomplete.
        if msg.get("id"):
            message_usage[(actor, msg["id"])] = msg.get("usage") or {}
        else:
            out["messages_without_id"] += 1

        for item in msg.get("content") or []:
            if not isinstance(item, dict) or item.get("type") != "tool_use":
                continue
            name = item.get("name", "<unknown>")
            out["tools"][name] += 1
            out["tools_by_actor"][actor][name] += 1
            if name in DELEGATION_TOOLS:
                inp = item.get("input") or {}
                # prompt_chars operationalises "how much context crossed the
                # context boundary" -- the core quantity of the hypothesis.
                out["delegations"].append(
                    {
                        "tool_use_id": item.get("id"),
                        "parent": actor,
                        "subagent_type": inp.get("subagent_type"),
                        "description_chars": len(inp.get("description") or ""),
                        "prompt_chars": len(inp.get("prompt") or ""),
                    }
                )
    for (actor, _), usage in message_usage.items():
        for key in TOKEN_FIELDS:
            value = usage.get(key)
            if type(value) is int and value >= 0:
                out["message_usage_by_actor"][actor][key] += value
    out["unique_assistant_messages"] = len(message_usage)
    return out


def token_accounting(trace: dict, *, timed_out: bool = False) -> dict:
    """Use the last cumulative modelUsage snapshot, never sum result events.

    All reported models are included, including CLI auxiliary calls. Per-model
    values allow the fixed research model to be analyzed separately. Thinking
    tokens are part of output tokens and must not be added a second time.
    """
    result = trace["result"] or {}
    reported = result.get("modelUsage")
    accounting = {
        "source": "result.modelUsage",
        "scope": "all_reported_models_including_subagents_and_cli_auxiliary_calls",
        "status": "unavailable",
        "complete": False,
        "totals": None,
        "by_model": reported if isinstance(reported, dict) else None,
    }
    if not reported or not isinstance(reported, dict):
        return accounting
    totals = {key: 0 for key in TOKEN_FIELDS}
    for usage in reported.values():
        if not isinstance(usage, dict):
            accounting["status"] = "invalid_model_usage"
            return accounting
        for key, field in TOKEN_FIELDS.items():
            value = usage.get(field)
            if type(value) is not int or value < 0:
                accounting["status"] = "invalid_model_usage"
                return accounting
            totals[key] += value
    totals["total_tokens"] = sum(totals.values())
    complete = (
        not timed_out
        and result.get("is_error") is False
        and trace["parse_errors"] == 0
        and trace["events_after_result"] == 0
    )
    accounting.update(
        totals=totals,
        complete=complete,
        status="complete" if complete else "partial_snapshot",
    )
    return accounting


def delegation_status(condition: str, trace: dict) -> str:
    """A tool request alone does not establish a completed delegation."""
    calls = sum(trace["tools"].get(name, 0) for name in DELEGATION_TOOLS)
    result = trace["result"]
    stats = (result or {}).get("subagent_stats") or {}
    spawned = stats.get("spawned")
    completed = stats.get("completed")
    if condition == "single":
        status = "violation_subagent_spawned" if calls or spawned or completed else "pass"
    elif completed is not None:
        status = "pass" if completed >= 1 else "violation_no_completed_subagent"
    elif spawned == 0 and calls == 0:
        status = "violation_no_subagent"
    else:
        status = "unverified_subagent_completion"
    if spawned is not None and spawned != calls:
        status += "|stats_mismatch"
    if result is None:
        status += "|no_final_result"
    return status


# ----------------------------------------------------------------------------
# Command construction
# ----------------------------------------------------------------------------
def available_flags(help_text: str, flags: list[str]) -> set[str]:
    return {f for f in flags if f in help_text}


def build_claude_command(condition: str, present: set[str]) -> str:
    parts = [
        "claude",
        "-p",
        '"$(cat /task/prompt.txt)"',
        "--model",
        shlex.quote(MODEL),
        "--effort",
        EFFORT,
        "--output-format",
        "stream-json",
        "--verbose",
        "--permission-mode",
        "bypassPermissions",
        "--safe-mode",
    ]

    # Isolation: do not let ambient settings, CLAUDE.md, plugins or MCP servers
    # leak into the measured run.
    if "--setting-sources" in present:
        parts += ["--setting-sources", "''"]
    if "--strict-mcp-config" in present:
        parts += ["--strict-mcp-config"]
    if "--mcp-config" in present:
        parts += ["--mcp-config", shlex.quote('{"mcpServers":{}}')]

    if MAX_BUDGET_USD is not None and "--max-budget-usd" in present:
        parts += ["--max-budget-usd", str(MAX_BUDGET_USD)]

    if condition == "single":
        parts += ["--disallowedTools", "Task", "WebFetch", "WebSearch"]
    else:
        parts += ["--append-system-prompt", '"$(cat /task/treatment.txt)"']
        parts += ["--disallowedTools", "WebFetch", "WebSearch"]
        if "--forward-subagent-text" in present:
            parts += ["--forward-subagent-text"]

    return " ".join(parts)


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------
def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--instance", required=True)
    p.add_argument("--condition", required=True, choices=("single", "multi"))
    p.add_argument("--label", default="dev")
    p.add_argument("--position", type=int)
    p.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT)
    p.add_argument(
        "--network-discovery",
        action="store_true",
        help="VALIDATION ONLY: run behind the open, logging proxy configuration "
        "to observe which hosts the CLI contacts. Reachable blocked hosts are "
        "then recorded instead of failing the run, so such a run is not a "
        "measured run and is marked as unenforced in metadata.json.",
    )
    args = p.parse_args()

    iid = args.instance
    condition = args.condition

    out = RUNS_DIR / args.label / iid / condition
    if out.exists():
        raise SystemExit(f"Refusing to overwrite existing run: {out}")
    out.mkdir(parents=True)

    # --- inputs: read-only mount, nothing the controller writes goes in here ---
    task_in = out / "input"
    task_in.mkdir()

    prompt_template = EXEC_DIR / "prompt-template.txt"
    treatment_source = EXEC_DIR / "multi-treatment.txt" if condition == "multi" else None
    problem_source = task_problem(iid)

    prompt = prompt_template.read_text()
    if not prompt.endswith("\n"):
        prompt += "\n"
    prompt += problem_source.read_text()

    (task_in / "prompt.txt").write_text(prompt)
    if treatment_source is not None:
        shutil.copyfile(treatment_source, task_in / "treatment.txt")
    os.chmod(task_in, 0o755)
    for child in task_in.iterdir():
        os.chmod(child, 0o644)

    image = task_image(iid)
    git_head = run(["git", "rev-parse", "HEAD"], stdout=subprocess.PIPE).stdout.strip()

    metadata = {
        "instance_id": iid,
        "condition": condition,
        "position": args.position,
        "image": image,
        "model": MODEL,
        "effort_requested": EFFORT,
        "subagent_effort_policy": "CLAUDE_CODE_EFFORT_LEVEL inherited from parent process",
        "claude_code_requested_version": CLAUDE_VERSION,
        "timeout_seconds": args.timeout_seconds,
        "max_turns": MAX_TURNS,
        "max_budget_usd": MAX_BUDGET_USD,
        "runner_sha256": sha256_file(Path(__file__)),
        "controller_git_head": git_head,
        "prompt_template_sha256": sha256_file(prompt_template),
        "problem_statement_sha256": sha256_file(problem_source),
        "treatment_file": treatment_source.name if treatment_source else None,
        "treatment_sha256": sha256_file(treatment_source) if treatment_source else None,
        "setup_started_at": utc_now(),
    }
    write_json(out / "metadata.json", metadata)

    trace_path = out / "trace.jsonl"
    stderr_path = out / "stderr.log"

    safe_iid = "".join(c if c.isalnum() else "-" for c in iid)
    container = f"nir-{safe_iid}-{condition}-{os.getpid()}"

    # Per-run copy of the CLI profile: no cross-run mutation, no race when runs
    # are parallel, and credentials stay out of the artefact tree.
    run_profile = Path(tempfile.mkdtemp(prefix="nir-profile-"))
    profile_dst = run_profile / "profile"
    profile_lock = None
    credentials_before = None
    credential_sync_failed = False

    container_created = False
    inference_exit = None
    timed_out = False
    wall_seconds = None
    patch_ok = False
    base_commit = None
    config_violation = None

    with open(out / "setup.log", "w") as setup_log:
        try:
            egress_config = (
                "squid-discovery.conf" if args.network_discovery else "squid.conf"
            )
            metadata["network_isolation"] = ensure_egress_proxy(egress_config)
            metadata["network_isolation"]["enforced"] = not args.network_discovery
            write_json(out / "metadata.json", metadata)

            profile_lock = lock_profile(CLAUDE_PROFILE)
            credential_source = CLAUDE_PROFILE / ".credentials.json"
            if credential_source.exists():
                credentials_before = credential_source.read_bytes()
            shutil.copytree(CLAUDE_PROFILE, profile_dst, ignore=PROFILE_IGNORE)
            inspect = run(
                [
                    "docker",
                    "image",
                    "inspect",
                    "-f",
                    "{{.Id}}|{{json .RepoDigests}}",
                    image,
                ],
                stdout=subprocess.PIPE,
                stderr=setup_log,
            ).stdout.strip()
            image_id, _, repo_digests = inspect.partition("|")
            metadata["image_id"] = image_id
            metadata["image_repo_digests"] = json.loads(repo_digests or "[]")

            docker_run = [
                "docker",
                "run",
                "-d",
                "--name",
                container,
                "-v",
                f"{task_in.resolve()}:/task:ro",
                "-v",
                f"{profile_dst.resolve()}:/home/nonroot/.claude-swebench",
                "-e",
                "CLAUDE_CONFIG_DIR=/home/nonroot/.claude-swebench",
            ]
            if DOCKER_NETWORK:
                docker_run += ["--network", DOCKER_NETWORK]
            docker_run += [image, "sleep", "infinity"]
            run(
                docker_run,
                stdout=setup_log,
                stderr=subprocess.STDOUT,
                timeout=DOCKER_SETUP_TIMEOUT,
            )
            container_created = True

            basic_env = {"HOME": "/home/nonroot", **PROXY_ENV}

            probes = probe_egress(container, setup_log)
            metadata["network_isolation"]["probes"] = probes
            (out / "network-probe.txt").write_text(
                "\n".join(
                    f"{url}\texit={r['exit_code']}\thttp={r['http_code'] or '-'}\t"
                    f"reachable={r['reachable']}"
                    for url, r in probes.items()
                )
                + "\n"
            )
            leaked = [u for u in BLOCKED_PROBE_URLS if probes[u]["reachable"]]
            if leaked and not args.network_discovery:
                config_violation = f"egress not isolated; reachable: {leaked}"
                raise RuntimeError(config_violation)
            if not probes[ALLOWED_PROBE_URL]["reachable"]:
                config_violation = (
                    f"allow-listed host unreachable: {ALLOWED_PROBE_URL}; "
                    "inference would run unauthenticated"
                )
                raise RuntimeError(config_violation)

            # Git considers /testbed owned by a different uid.
            dexec(
                container,
                "git config --global --add safe.directory /testbed",
                user="nonroot",
                env=basic_env,
                stdout=setup_log,
                stderr=subprocess.STDOUT,
                timeout=DOCKER_SETUP_TIMEOUT,
            )

            # Provenance of the repository the agent will see. If future refs are
            # reachable here, the gold fix is two commands away from the agent.
            with open(out / "repo-provenance.txt", "w") as prov:
                dexec(
                    container,
                    "cd /testbed && git rev-parse HEAD && git status -sb && "
                    "git remote -v && git log --all --oneline | head -30",
                    check=False,
                    stdout=prov,
                    stderr=setup_log,
                    timeout=DOCKER_COLLECT_TIMEOUT,
                )

            base_commit = dexec(
                container,
                "cd /testbed && git rev-parse HEAD",
                stdout=subprocess.PIPE,
                stderr=setup_log,
                timeout=DOCKER_COLLECT_TIMEOUT,
            ).stdout.strip()
            metadata["base_commit"] = base_commit

            # --- CLI: install only if the image does not already ship it ------
            probe = dexec(
                container,
                'export PATH="$HOME/.local/bin:$PATH"; claude --version',
                user="nonroot",
                env=basic_env,
                check=False,
                stdout=subprocess.PIPE,
                stderr=setup_log,
                timeout=DOCKER_SETUP_TIMEOUT,
            )
            if probe.returncode != 0:
                if not ALLOW_RUNTIME_INSTALL:
                    raise RuntimeError(
                        "claude not present and runtime install disabled"
                    )
                dexec(
                    container,
                    "curl -fsSL https://claude.ai/install.sh "
                    f"| bash -s {CLAUDE_VERSION}",
                    user="nonroot",
                    env=basic_env,
                    stdout=setup_log,
                    stderr=subprocess.STDOUT,
                    timeout=DOCKER_SETUP_TIMEOUT,
                )
                probe = dexec(
                    container,
                    'export PATH="$HOME/.local/bin:$PATH"; claude --version',
                    user="nonroot",
                    env=basic_env,
                    stdout=subprocess.PIPE,
                    stderr=setup_log,
                    timeout=DOCKER_SETUP_TIMEOUT,
                )

            version = probe.stdout.strip()
            metadata["claude_code_actual_version"] = version
            if CLAUDE_VERSION not in version:
                config_violation = (
                    f"version drift: requested {CLAUDE_VERSION}, got {version!r}"
                )
                raise RuntimeError(config_violation)

            # --- flag verification: a renamed flag must fail, not no-op -------
            help_text = dexec(
                container,
                'export PATH="$HOME/.local/bin:$PATH"; claude --help 2>&1',
                user="nonroot",
                env=basic_env,
                check=False,
                stdout=subprocess.PIPE,
                stderr=setup_log,
                timeout=DOCKER_SETUP_TIMEOUT,
            ).stdout
            (out / "claude-help.txt").write_text(help_text)

            missing = sorted(
                set(REQUIRED_FLAGS) - available_flags(help_text, REQUIRED_FLAGS)
            )
            if missing:
                config_violation = f"required flags absent from --help: {missing}"
                raise RuntimeError(config_violation)

            present = available_flags(help_text, REQUIRED_FLAGS + OPTIONAL_FLAGS)
            metadata["flags_present"] = sorted(present)
            metadata["flags_absent_optional"] = sorted(set(OPTIONAL_FLAGS) - present)

            claude_env = {
                "HOME": "/home/nonroot",
                "CLAUDE_CONFIG_DIR": "/home/nonroot/.claude-swebench",
                "DISABLE_AUTOUPDATER": "1",
                # Environment priority also overrides subagent frontmatter.
                "CLAUDE_CODE_EFFORT_LEVEL": EFFORT,
                **PROXY_ENV,
            }
            if condition == "multi":
                # Best-effort only. The authoritative check is models_seen below.
                claude_env["CLAUDE_CODE_SUBAGENT_MODEL"] = MODEL

            claude_command = build_claude_command(condition, present)
            metadata["claude_command"] = claude_command
            metadata["inference_started_at"] = utc_now()
            write_json(out / "metadata.json", metadata)

            shell_command = (
                "set -o pipefail; "
                "cd /testbed; "
                "source /opt/miniconda3/etc/profile.d/conda.sh; "
                "conda activate testbed; "
                'export PATH="$HOME/.local/bin:$PATH"; ' + claude_command
            )
            command = docker_exec(container, user="nonroot", env=claude_env) + [
                "bash",
                "-lc",
                shell_command,
            ]

            start = time.monotonic()
            with open(trace_path, "w") as trace, open(stderr_path, "w") as stderr:
                proc = subprocess.Popen(
                    command, cwd=ROOT, stdout=trace, stderr=stderr, text=True
                )
                try:
                    inference_exit = proc.wait(timeout=args.timeout_seconds)
                    wall_seconds = time.monotonic() - start
                except subprocess.TimeoutExpired:
                    timed_out = True
                    # Measured before the teardown, so the number is the budget,
                    # not the budget plus the kill.
                    wall_seconds = time.monotonic() - start

                    run(
                        ["docker", "kill", container],
                        check=False,
                        stdout=setup_log,
                        stderr=subprocess.STDOUT,
                    )
                    try:
                        proc.wait(timeout=KILL_GRACE)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait()

                    # Restart only to read the filesystem back. A failure here
                    # must NOT reclassify the timeout as an infrastructure fault.
                    restarted = run(
                        ["docker", "start", container],
                        check=False,
                        stdout=setup_log,
                        stderr=subprocess.STDOUT,
                    )
                    metadata["container_restart_ok"] = restarted.returncode == 0
                    inference_exit = 124

            # --- collection (controller work, therefore root) -----------------
            with open(out / "git-status.txt", "w") as status:
                dexec(
                    container,
                    "cd /testbed && git status --short",
                    check=False,
                    stdout=status,
                    stderr=setup_log,
                    timeout=DOCKER_COLLECT_TIMEOUT,
                )

            head_after = dexec(
                container,
                "cd /testbed && git rev-parse HEAD",
                check=False,
                stdout=subprocess.PIPE,
                stderr=setup_log,
                timeout=DOCKER_COLLECT_TIMEOUT,
            ).stdout.strip()
            metadata["head_after_run"] = head_after
            metadata["agent_committed"] = bool(head_after and head_after != base_commit)

            # Record untracked paths before staging. New source files are part
            # of the submitted solution, just like edits to existing files.
            with open(out / "untracked-files.txt", "w") as untracked:
                dexec(
                    container,
                    "cd /testbed && git ls-files --others --exclude-standard",
                    check=False,
                    stdout=untracked,
                    stderr=setup_log,
                    timeout=DOCKER_COLLECT_TIMEOUT,
                )

            # Include new files and commits made by the agent. Always compare
            # against the pre-inference commit, never the agent's final HEAD.
            with open(out / "patch.diff", "w") as patch:
                patch_proc = dexec(
                    container,
                    f"cd /testbed && git add -A && "
                    f"git diff --cached {base_commit} --binary",
                    check=False,
                    stdout=patch,
                    stderr=setup_log,
                    timeout=DOCKER_COLLECT_TIMEOUT,
                )
            patch_ok = patch_proc.returncode == 0
            shutil.copyfile(out / "patch.diff", out / "patch-full-snapshot.diff")

        except Exception as exc:
            metadata["controller_exception"] = repr(exc)
            metadata["failed_at"] = utc_now()
            write_json(out / "metadata.json", metadata)
            print(f"RUNNER ERROR: {exc}", file=sys.stderr)
            return 50 if config_violation else 20

        finally:
            if container_created:
                subprocess.run(
                    ["docker", "rm", "-f", container],
                    cwd=ROOT,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    text=True,
                )
            try:
                metadata["credential_refresh_status"] = preserve_credentials(
                    CLAUDE_PROFILE / ".credentials.json",
                    profile_dst / ".credentials.json",
                    credentials_before,
                )
            except Exception as exc:
                credential_sync_failed = True
                metadata["credential_refresh_error"] = str(exc)
                # Keep refreshed auth outside the artifact tree for recovery.
                metadata["credential_recovery_profile"] = str(profile_dst)
                print(f"CREDENTIAL SYNC ERROR: {exc}", file=sys.stderr)
            finally:
                if profile_lock is not None:
                    profile_lock.close()
                if not credential_sync_failed:
                    shutil.rmtree(run_profile, ignore_errors=True)
                write_json(out / "metadata.json", metadata)

    # ------------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------------
    tr = read_trace(trace_path)
    result = tr["result"]

    patch_path = out / "patch.diff"
    patch_bytes = patch_path.stat().st_size if patch_path.exists() else None

    subagent_stats = result.get("subagent_stats") if result else None
    task_calls = sum(tr["tools"].get(name, 0) for name in DELEGATION_TOOLS)
    protocol_status = delegation_status(condition, tr)

    # A model mismatch means MULTI differs from SINGLE by architecture AND model.
    models_seen = dict(tr["models"])
    model_ok = bool(models_seen) and all(m.startswith(MODEL) for m in models_seen)
    if models_seen and not model_ok:
        protocol_status += "|violation_model_mismatch"

    metrics = {
        "instance_id": iid,
        "condition": condition,
        "position": args.position,
        "inference_exit_code": inference_exit,
        "timed_out": timed_out,
        "wall_seconds": wall_seconds,
        "patch_collection_ok": patch_ok,
        "patch_bytes": patch_bytes,
        "agent_committed": metadata.get("agent_committed"),
        "trace_parse_errors": tr["parse_errors"],
        "result_event_present": result is not None,
        "result_is_error": result.get("is_error") if result else None,
        "result_subtype": result.get("subtype") if result else None,
        "num_turns": result.get("num_turns") if result else None,
        "total_cost_usd_reported": result.get("total_cost_usd") if result else None,
        "usage_reported": result.get("usage") if result else None,
        "token_accounting": token_accounting(tr, timed_out=timed_out),
        # Diagnostic snapshots only; not a fallback for complete token totals.
        "message_usage_observed_by_actor": {
            actor: dict(usage)
            for actor, usage in tr["message_usage_by_actor"].items()
        },
        "unique_assistant_messages": tr.get("unique_assistant_messages", 0),
        "messages_without_id": tr["messages_without_id"],
        "result_events": tr["result_events"],
        "assistant_events": tr["assistant_events"],
        "models_seen": models_seen,
        "subagent_stats": subagent_stats,
        "task_calls": task_calls,
        "delegations": tr["delegations"],
        "delegation_prompt_chars_total": sum(
            d["prompt_chars"] for d in tr["delegations"]
        ),
        "tool_calls_by_name": dict(sorted(tr["tools"].items())),
        "tool_calls_by_actor": {
            actor: dict(sorted(counter.items()))
            for actor, counter in sorted(tr["tools_by_actor"].items())
        },
        "tool_calls_total": sum(tr["tools"].values()),
        "protocol_status": protocol_status,
        "finished_at": utc_now(),
    }
    write_json(out / "metrics.json", metrics)

    metadata["finished_at"] = utc_now()
    metadata["inference_exit_code"] = inference_exit
    metadata["timed_out"] = timed_out
    write_json(out / "metadata.json", metadata)

    print(json.dumps(metrics, indent=2, ensure_ascii=False))

    if credential_sync_failed:
        return 20
    if models_seen and not model_ok:
        print(f"CONFIG VIOLATION: unexpected models {models_seen}", file=sys.stderr)
        return 50
    if not patch_ok:
        return 40
    if timed_out:  # timeout is an experimental outcome
        return 0
    if inference_exit != 0:  # pre-registered manual classification
        return 30
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
