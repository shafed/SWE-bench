"""Controller regressions: observed CLI trace schema and real Git patches."""

import importlib.util
import json
import shlex
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def runner():
    path = Path(__file__).resolve().parents[1] / "experiment/execution/runner.py"
    spec = importlib.util.spec_from_file_location("experiment_runner", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def trace_events(condition, *, name="Agent", completed=1):
    # Field layout observed in Claude Code 2.1.261 runner-dev stream-json.
    count = int(condition == "multi")
    content = ([{"type": "tool_use", "id": "delegation-1", "name": name,
                 "input": {"description": "Check fix", "prompt": "Run tests"}}]
               if count else [])
    return [
        {"type": "assistant", "message": {
            "model": "claude-sonnet-5", "content": content}},
        {"type": "result", "is_error": False, "subtype": "success",
         "subagent_stats": {"spawned": count, "completed": count * completed}},
    ]


@pytest.mark.parametrize("name", ["Task", "Agent"])
def test_delegation_aliases_and_completion(runner, tmp_path, name):
    path = tmp_path / "trace.jsonl"
    for completed in (0, 1):
        path.write_text("\n".join(map(json.dumps, trace_events(
            "multi", name=name, completed=completed))))
        trace = runner.read_trace(path)
        assert len(trace["delegations"]) == 1
        assert trace["delegations"][0]["prompt_chars"] == len("Run tests")
        assert runner.delegation_status("multi", trace) == (
            "pass" if completed else "violation_no_completed_subagent")
        assert runner.delegation_status("single", trace) == "violation_subagent_spawned"


def test_incomplete_trace_does_not_claim_completed_delegation(runner, tmp_path):
    path = tmp_path / "trace.jsonl"
    path.write_text(json.dumps(trace_events("multi")[0]))
    assert runner.delegation_status("multi", runner.read_trace(path)) == (
        "unverified_subagent_completion|no_final_result")


@pytest.fixture
def usage_trace(tmp_path):
    # Redacted excerpt from runner-fix-reauth-20260906 MULTI: repeated
    # content-block usage and two identical cumulative modelUsage snapshots.
    events = json.loads((Path(__file__).parent / "fixtures/runner_multi_usage.json").read_text())
    path = tmp_path / "trace.jsonl"
    path.write_text("\n".join(map(json.dumps, events)))
    return path


def test_final_accounting_includes_subagents_and_auxiliary_model(runner, usage_trace):
    trace = runner.read_trace(usage_trace)
    accounting = runner.token_accounting(trace)
    assert trace["result_events"] == 2
    assert accounting["status"] == "complete"
    assert accounting["complete"] is True
    assert accounting["totals"] == {
        "input_tokens": 1207, "output_tokens": 8055,
        "cache_read_input_tokens": 588838,
        "cache_creation_input_tokens": 40083, "total_tokens": 638183,
    }
    assert accounting["by_model"]["claude-sonnet-5"]["outputTokens"] == 8041
    # Thinking is already included in output; result.usage is only one turn
    # sequence and therefore not the total for this resumed/background run.
    assert trace["result"]["usage"]["output_tokens"] == 2127
    assert trace["unique_assistant_messages"] == 2
    assert trace["message_usage_by_actor"]["orchestrator"]["input_tokens"] == 2
    child = next(k for k in trace["message_usage_by_actor"] if k != "orchestrator")
    assert trace["message_usage_by_actor"][child]["input_tokens"] == 2


def test_timeout_keeps_partial_snapshot_without_claiming_full_cost(runner, usage_trace):
    accounting = runner.token_accounting(runner.read_trace(usage_trace), timed_out=True)
    assert accounting["status"] == "partial_snapshot"
    assert accounting["complete"] is False
    assert accounting["totals"]["output_tokens"] == 8055


def test_activity_after_result_marks_snapshot_partial(runner, usage_trace):
    with usage_trace.open("a") as f:
        f.write('\n{"type":"system","subtype":"init"}\n')
    assert runner.token_accounting(runner.read_trace(usage_trace))["status"] == "partial_snapshot"


@pytest.mark.parametrize("with_result", [False, True])
def test_missing_model_usage_is_unavailable_not_zero(runner, tmp_path, with_result):
    events = trace_events("single")
    path = tmp_path / "trace.jsonl"
    path.write_text("\n".join(map(json.dumps, events if with_result else events[:1])))
    accounting = runner.token_accounting(runner.read_trace(path))
    assert accounting["status"] == "unavailable"
    assert accounting["totals"] is None
    assert accounting["complete"] is False


def test_incomplete_model_fields_are_not_silently_zeroed(runner, usage_trace):
    trace = runner.read_trace(usage_trace)
    del trace["result"]["modelUsage"]["claude-sonnet-5"]["outputTokens"]
    assert runner.token_accounting(trace)["status"] == "invalid_model_usage"


def credentials(access, refresh):
    return json.dumps({"claudeAiOauth": {"accessToken": access, "refreshToken": refresh}}).encode()


def test_profile_lock_rejects_concurrent_runner(runner, tmp_path):
    lock = runner.lock_profile(tmp_path)
    try:
        with pytest.raises(RuntimeError, match="already in use"):
            runner.lock_profile(tmp_path)
    finally:
        lock.close()
    runner.lock_profile(tmp_path).close()


def test_refresh_does_not_overwrite_new_login(runner, tmp_path):
    source, copied = tmp_path / "source", tmp_path / "copied"
    before = credentials("old", "old-refresh")
    source.write_bytes(credentials("external-login", "external-refresh"))
    copied.write_bytes(credentials("refreshed", "new-refresh"))
    with pytest.raises(RuntimeError, match="changed during run"):
        runner.preserve_credentials(source, copied, before)
    assert source.read_bytes() == credentials("external-login", "external-refresh")


def test_invalid_refresh_is_not_saved(runner, tmp_path):
    source, copied = tmp_path / "source", tmp_path / "copied"
    before = credentials("old", "old-refresh")
    source.write_bytes(before)
    copied.write_text('{}')
    with pytest.raises(RuntimeError, match="invalid"):
        runner.preserve_credentials(source, copied, before)
    assert source.read_bytes() == before


@pytest.mark.parametrize("condition", ["single", "multi"])
@pytest.mark.parametrize("outcome", ["success", "timeout", "auth_error"])
def test_controller_preserves_new_files_and_commits(
    runner, tmp_path, monkeypatch, condition, outcome
):
    timed_out = outcome == "timeout"
    auth_error = outcome == "auth_error"
    repo = tmp_path / "testbed"
    repo.mkdir()
    real_run = subprocess.run

    def git(*args):
        return real_run(["git", *args], cwd=repo, check=True,
                        text=True, capture_output=True).stdout

    git("init", "-q")
    git("config", "user.name", "Runner test")
    git("config", "user.email", "test@example.invalid")
    (repo / "old.py").write_text("original\n")
    git("add", "-A")
    git("commit", "-qm", "base")
    base = git("rev-parse", "HEAD").strip()
    profile = tmp_path / "profile"
    profile.mkdir()
    (profile / ".credentials.json").write_bytes(credentials("old", "old-refresh"))
    problem = tmp_path / "problem.md"
    problem.write_text("Fix the issue.\n")
    monkeypatch.setattr(runner, "CLAUDE_PROFILE", profile)
    monkeypatch.setattr(runner, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(runner, "task_image", lambda _: "dev-image")
    monkeypatch.setattr(runner, "task_problem", lambda _: problem)
    monkeypatch.setattr(sys, "argv", ["runner", "--instance", "dev-instance",
                                    "--condition", condition])
    commands = []
    copied_profile = []

    def fake_run(cmd, **kwargs):
        commands.append(cmd)
        if cmd[:2] == ["git", "rev-parse"]:
            return SimpleNamespace(returncode=0, stdout="controller-head\n")
        if cmd[:3] == ["docker", "image", "inspect"]:
            return SimpleNamespace(returncode=0, stdout="sha256:dev|[]\n")
        if cmd[:2] == ["docker", "run"]:
            mount = next(x for x in cmd if x.endswith(":/home/nonroot/.claude-swebench"))
            copied_profile.append(Path(mount.split(":", 1)[0]))
        assert cmd[0] == "docker"
        return SimpleNamespace(returncode=0, stdout="")

    def fake_dexec(container, script, *, user=None, env=None, **kwargs):
        if "claude --version" in script:
            return SimpleNamespace(returncode=0, stdout="2.1.261 (Claude Code)\n")
        if "claude --help" in script:
            return SimpleNamespace(returncode=0, stdout=(
                "--model --effort --output-format --verbose --permission-mode "
                "--append-system-prompt --disallowedTools --safe-mode "
                "--forward-subagent-text"))
        if "safe.directory" in script:
            return SimpleNamespace(returncode=0, stdout="")
        assert script.startswith("cd /testbed && ")
        return real_run(["bash", "-c", script.removeprefix("cd /testbed && ")],
                        cwd=repo, text=True, **kwargs)

    class Inference:
        def __init__(self, cmd, *, stdout, **kwargs):
            (copied_profile[0] / ".credentials.json").write_bytes(
                credentials("refreshed", "new-refresh"))
            shell = cmd[-1]
            args = shlex.split(shell[shell.index("claude -p"):])
            assert "--safe-mode" in args
            assert args[args.index("--effort") + 1] == "high"
            assert "CLAUDE_CODE_EFFORT_LEVEL=high" in cmd
            assert "--max-turns" not in args
            assert "--max-budget-usd" not in args
            assert ("--append-system-prompt" in args) == (condition == "multi")
            denied = args[args.index("--disallowedTools") + 1:]
            assert ("Task" in denied) == (condition == "single")
            assert "WebFetch" in denied and "WebSearch" in denied
            (repo / "old.py").write_text("fixed\n")
            git("add", "-A")
            git("commit", "-qm", "agent fix")
            (repo / "new.py").write_text("needed new module\n")
            events = trace_events(condition)
            if auth_error:
                events = trace_events("single")
                events[0]["message"]["model"] = "<synthetic>"
                events[0]["message"]["content"] = [{"type": "text", "text":
                    "Failed to authenticate: OAuth session expired and could not be refreshed"}]
                events[1]["is_error"] = True
            if timed_out:
                events = events[:1]
            stdout.write("\n".join(map(json.dumps, events)) + "\n")
            stdout.flush()
            self.waits = 0

        def wait(self, timeout=None):
            self.waits += 1
            if timed_out and self.waits == 1:
                raise subprocess.TimeoutExpired("inference", timeout)
            return 1 if auth_error else 0

    monkeypatch.setattr(runner, "run", fake_run)
    monkeypatch.setattr(runner, "dexec", fake_dexec)
    process_api = SimpleNamespace(**vars(subprocess))
    process_api.Popen = Inference
    process_api.run = fake_run
    monkeypatch.setattr(runner, "subprocess", process_api)

    assert runner.main() == (30 if auth_error else 0)
    out = tmp_path / "runs/dev/dev-instance" / condition
    metadata = json.loads((out / "metadata.json").read_text())
    metrics = json.loads((out / "metrics.json").read_text())
    assert metadata["max_turns"] is None
    assert metadata["effort_requested"] == "high"
    assert metadata["credential_refresh_status"] == "updated"
    assert (profile / ".credentials.json").read_bytes() == credentials("refreshed", "new-refresh")
    assert (profile / ".credentials.json").stat().st_mode & 0o777 == 0o600
    assert not copied_profile[0].exists()
    assert "new-refresh" not in (out / "metadata.json").read_text()
    assert metadata["agent_committed"] is True
    assert (out / "input/treatment.txt").exists() == (condition == "multi")
    assert metrics["patch_collection_ok"] is True
    assert metrics["timed_out"] is timed_out
    assert metrics["inference_exit_code"] == (124 if timed_out else 1 if auth_error else 0)
    assert metrics["task_calls"] == int(condition == "multi" and not auth_error)
    if auth_error:
        assert metrics["models_seen"] == {}
        assert "violation_model_mismatch" not in metrics["protocol_status"]
        assert metrics["result_is_error"] is True
    else:
        assert metrics["protocol_status"] == (
            ("unverified_subagent_completion" if condition == "multi" else "pass")
            + "|no_final_result" if timed_out else "pass")
    assert "new.py" in (out / "untracked-files.txt").read_text()
    patch = out / "patch.diff"
    assert "old.py" in patch.read_text() and "new.py" in patch.read_text()
    git("reset", "--hard", base)
    git("clean", "-fd")
    git("apply", str(patch))
    assert (repo / "old.py").read_text() == "fixed\n"
    assert (repo / "new.py").read_text() == "needed new module\n"
    if timed_out:
        assert any(cmd[:2] == ["docker", "kill"] for cmd in commands)
        assert any(cmd[:2] == ["docker", "start"] for cmd in commands)
