"""Regressions for the minimal MULTI finalization gate."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.fixture
def gate():
    path = (
        Path(__file__).resolve().parents[1]
        / "experiment/execution/orchestration_gate.py"
    )
    spec = importlib.util.spec_from_file_location("orchestration_gate", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def event(name, **fields):
    return {
        "hook_event_name": name,
        "session_id": "lead-session",
        "prompt_id": "prompt-1",
        **fields,
    }


def test_multi_finalization_rejected_without_delegation(gate, tmp_path):
    allowed = gate.record_event(tmp_path, event("Stop", stop_hook_active=False))

    assert allowed is False
    state = json.loads((tmp_path / "state.json").read_text())
    assert state["successful_subagent_invocations"] == 0
    assert state["finalization_attempts"] == 1
    assert state["rejected_finalizations"] == 1
    logged = json.loads((tmp_path / "events.jsonl").read_text())
    assert logged["event"] == "finalization_attempt"
    assert logged["decision"] == "reject"


def test_multi_finalization_accepted_after_first_real_start(gate, tmp_path):
    gate.record_event(
        tmp_path,
        event("SubagentStart", agent_id="child-1", agent_type="general-purpose"),
    )

    assert gate.record_event(tmp_path, event("Stop")) is True
    state = json.loads((tmp_path / "state.json").read_text())
    assert state["successful_subagent_invocations"] == 1
    assert state["distinct_subagent_ids"] == ["child-1"]
    assert state["first_subagent_invocation"]["event_order"] == 1
    assert state["successful_finalizations"] == 1


def test_invalid_subagent_start_does_not_satisfy_gate(gate, tmp_path):
    gate.record_event(tmp_path, event("SubagentStart", agent_type="general-purpose"))

    assert gate.record_event(tmp_path, event("Stop")) is False
    state = json.loads((tmp_path / "state.json").read_text())
    assert state["successful_subagent_invocations"] == 0
    events = [
        json.loads(line)
        for line in (tmp_path / "events.jsonl").read_text().splitlines()
    ]
    assert events[0]["event"] == "invalid_subagent_start"
    assert events[0]["counted"] is False


def test_single_command_has_no_gate_and_still_disables_subagents(gate):
    del gate  # The hook is deliberately not involved in SINGLE.
    runner_path = (
        Path(__file__).resolve().parents[1] / "experiment/execution/runner.py"
    )
    spec = importlib.util.spec_from_file_location("experiment_runner", runner_path)
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    command = runner.build_claude_command(
        "single", set(runner.REQUIRED_FLAGS + runner.OPTIONAL_FLAGS)
    )

    assert "--include-hook-events" not in command
    assert "--append-system-prompt" not in command
    assert "--disallowedTools Task WebFetch WebSearch" in command


def test_gate_state_is_isolated_between_runs(gate, tmp_path):
    first = tmp_path / "run-one"
    second = tmp_path / "run-two"
    gate.record_event(first, event("SubagentStart", agent_id="child-1"))

    assert gate.record_event(first, event("Stop")) is True
    assert gate.record_event(second, event("Stop")) is False
    first_state = json.loads((first / "state.json").read_text())
    second_state = json.loads((second / "state.json").read_text())
    assert first_state["successful_subagent_invocations"] == 1
    assert second_state["successful_subagent_invocations"] == 0


def test_multiple_starts_remain_model_directed_and_are_counted(gate, tmp_path):
    gate.record_event(tmp_path, event("SubagentStart", agent_id="child-1"))
    gate.record_event(tmp_path, event("SubagentStart", agent_id="child-2"))
    # A duplicate delivery is not a new execution.
    gate.record_event(tmp_path, event("SubagentStart", agent_id="child-2"))

    state = json.loads((tmp_path / "state.json").read_text())
    assert state["successful_subagent_invocations"] == 2
    assert state["distinct_subagent_ids"] == ["child-1", "child-2"]
    assert gate.record_event(tmp_path, event("Stop")) is True


def test_hook_cli_returns_required_feedback(gate, tmp_path):
    script = Path(gate.__file__)
    completed = subprocess.run(
        [sys.executable, str(script), "--state-dir", str(tmp_path)],
        input=json.dumps(event("Stop")),
        text=True,
        capture_output=True,
        check=True,
    )

    response = json.loads(completed.stdout)
    assert response == {"decision": "block", "reason": gate.REJECTION_MESSAGE}


def test_stop_fails_closed_when_state_is_corrupt(gate, tmp_path):
    (tmp_path / "state.json").write_text("not json")

    script = Path(gate.__file__)
    completed = subprocess.run(
        [sys.executable, str(script), "--state-dir", str(tmp_path)],
        input=json.dumps(event("Stop")),
        text=True,
        capture_output=True,
        check=True,
    )

    assert json.loads(completed.stdout)["decision"] == "block"
    assert "orchestration gate error" in completed.stderr
