#!/usr/bin/env python3
"""Claude Code hooks enforcing one real subagent start before MULTI stops."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


REJECTION_MESSAGE = (
    "The orchestration requirement has not yet been satisfied. "
    "Delegate substantive problem-solving work to a subagent before "
    "completing the task."
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def initial_state() -> dict:
    return {
        "version": 1,
        "condition": "multi",
        "event_sequence": 0,
        "successful_subagent_invocations": 0,
        "distinct_subagent_ids": [],
        "first_subagent_invocation": None,
        "finalization_attempts": 0,
        "rejected_finalizations": 0,
        "successful_finalizations": 0,
    }


def load_state(path: Path) -> dict:
    if not path.exists():
        return initial_state()
    state = json.loads(path.read_text())
    if not isinstance(state, dict) or state.get("version") != 1:
        raise ValueError("unsupported orchestration gate state")
    return state


def write_state(path: Path, state: dict) -> None:
    fd, temporary = tempfile.mkstemp(prefix="state.", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(state, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def append_event(path: Path, event: dict) -> None:
    with path.open("a") as stream:
        stream.write(json.dumps(event, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def record_event(state_dir: Path, hook_input: dict) -> bool | None:
    """Record one hook event and return whether a Stop attempt may proceed."""
    state_dir.mkdir(parents=True, exist_ok=True)
    state_path = state_dir / "state.json"
    events_path = state_dir / "events.jsonl"
    event_name = hook_input.get("hook_event_name")

    with (state_dir / "state.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = load_state(state_path)
        state["event_sequence"] += 1
        order = state["event_sequence"]
        timestamp = utc_now()

        common = {
            "condition": "multi",
            "event_order": order,
            "timestamp": timestamp,
            "hook_event_name": event_name,
            "session_id": hook_input.get("session_id"),
            "prompt_id": hook_input.get("prompt_id"),
        }

        if event_name == "SubagentStart":
            agent_id = hook_input.get("agent_id")
            if not isinstance(agent_id, str) or not agent_id:
                event = {**common, "event": "invalid_subagent_start", "counted": False}
                append_event(events_path, event)
                write_state(state_path, state)
                return None

            ids = state["distinct_subagent_ids"]
            counted = agent_id not in ids
            if counted:
                ids.append(agent_id)
                state["successful_subagent_invocations"] += 1
            invocation = {
                **common,
                "event": "subagent_started",
                "counted": counted,
                "subagent_id": agent_id,
                "subagent_type": hook_input.get("agent_type"),
            }
            if counted and state["first_subagent_invocation"] is None:
                state["first_subagent_invocation"] = invocation.copy()
            append_event(events_path, invocation)
            write_state(state_path, state)
            return None

        if event_name == "Stop":
            allowed = state["successful_subagent_invocations"] >= 1
            state["finalization_attempts"] += 1
            if allowed:
                state["successful_finalizations"] += 1
            else:
                state["rejected_finalizations"] += 1
            event = {
                **common,
                "event": "finalization_attempt",
                "decision": "allow" if allowed else "reject",
                "stop_hook_active": bool(hook_input.get("stop_hook_active")),
                "successful_subagent_invocations": state[
                    "successful_subagent_invocations"
                ],
            }
            append_event(events_path, event)
            write_state(state_path, state)
            return allowed

        event = {**common, "event": "ignored_hook_event"}
        append_event(events_path, event)
        write_state(state_path, state)
        return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-dir", type=Path, required=True)
    args = parser.parse_args()
    hook_input = None
    try:
        hook_input = json.load(sys.stdin)
        if not isinstance(hook_input, dict):
            raise ValueError("hook input must be a JSON object")
        allowed = record_event(args.state_dir, hook_input)
    except Exception as exc:
        print(f"orchestration gate error: {exc}", file=sys.stderr)
        # Stop must fail closed: an unreadable/corrupt state must never turn
        # into a successful finalization without an observed subagent start.
        if hook_input is None or hook_input.get("hook_event_name") == "Stop":
            print(json.dumps({"decision": "block", "reason": REJECTION_MESSAGE}))
            return 0
        return 1

    if allowed is False:
        print(json.dumps({"decision": "block", "reason": REJECTION_MESSAGE}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
