#!/usr/bin/env python3
"""
scheduled_series.py -- unattended one-condition series with session-limit waits.

Runs one condition of a frozen order through the frozen runner.py, in position
order, with the same freeze-manifest and runner-digest checks and the same
series-log.tsv as run_series.py. run_series.py and analyze_runs.py are frozen
inputs, so this driver imports them instead of changing them.

Rules (SCHEDULED_SERIES.md, fixed before the series starts):
  * Only --condition runs are executed; an existing run directory is skipped.
  * A run cut off by the subscription session limit -- a `rate_limit_event`
    with status "rejected", or a result with api_error_status 429 -- is
    infrastructure, whatever the runner exit code. Its directory moves to
    experiment/runs/discarded-<label>-session-limit/, the driver sleeps until
    the reported reset plus --reset-grace seconds and reruns the same instance.
  * Runner exit 50 raised by its pre-inference reachability probe ("allow-listed
    host unreachable") means no inference happened; per its preregistered
    meaning the run is discarded (moved to discarded-<label>-network/) and the
    same instance rerun once the network answers, at most 5 times.
  * Any other non-zero runner exit stops the series (run_series.py semantics).
  * While another experiment uses the host (OpenCode pilot), the driver waits.
  * After the last run: predictions, official evaluator, commit and push of
    the run artefacts.

Exit codes: 0 series and evaluation done; 10 precondition failed; 11 host
stayed busy; 12 too many session-limit waits; 13 network did not come up;
n runner exit that stopped the series; 60 evaluation failed.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

EXEC_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(EXEC_DIR))
import run_series as rs  # noqa: E402

ROOT = rs.ROOT
RUNS_DIR = rs.RUNS_DIR
ANALYZE = EXEC_DIR / "analyze_runs.py"
SWEBENCH = ROOT / ".venv" / "bin" / "swebench"
V1_ORDER = EXEC_DIR / "run-order.tsv"
V1_SAMPLE = rs.PREREG_DIR / "tasks-main.txt"
HOST_POLL_SECONDS = 300
MAX_PROBE_RETRIES = 5

LOG_FILE: Path | None = None


def log(msg: str) -> None:
    line = f"[{datetime.now(timezone.utc).isoformat(timespec='seconds')}] {msg}"
    print(line, flush=True)
    if LOG_FILE is not None:
        with LOG_FILE.open("a") as fh:
            fh.write(line + "\n")


def session_limit(trace: Path) -> dict | None:
    """Session-limit evidence in a trace, with the reset time when reported."""
    if not trace.exists():
        return None
    resets_at, rejected, status_429, text = None, False, False, ""
    with trace.open() as fh:
        for line in fh:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") == "rate_limit_event":
                info = event.get("rate_limit_info") or {}
                if info.get("status") == "rejected":
                    rejected = True
                    resets_at = info.get("resetsAt") or resets_at
            elif event.get("type") == "result" and event.get("api_error_status") == 429:
                status_429 = True
                text = str(event.get("result") or "")[:200]
    if not (rejected or status_429):
        return None
    return {"resets_at": resets_at, "rejected_event": rejected, "result_429": status_429, "text": text}


def host_busy() -> str | None:
    """Another experiment on this host would distort wall-clock measurements."""
    names = subprocess.run(["docker", "ps", "--format", "{{.Names}}"],
                           capture_output=True, text=True).stdout.split()
    busy = [n for n in names if n.startswith("ocpilot-")]
    # Anchored on the interpreter, so a shell whose command text merely mentions
    # the driver does not count.
    procs = subprocess.run(["pgrep", "-f", r"^\S*python\S* \S*run_v1_newprompt_series\.py"],
                           capture_output=True, text=True).stdout.split()
    if busy or procs:
        return f"containers={busy} driver_pids={procs}"
    return None


def wait_for_host(max_hours: float) -> bool:
    deadline = time.time() + max_hours * 3600
    while (why := host_busy()) is not None:
        if time.time() > deadline:
            log(f"host still busy after {max_hours} h: {why}")
            return False
        log(f"host busy, waiting {HOST_POLL_SECONDS}s: {why}")
        time.sleep(HOST_POLL_SECONDS)
    return True


def wait_for_network(max_minutes: float = 15) -> bool:
    """After resume from suspend the link comes up late, and the runner's
    reachability probe would turn that into a configuration failure."""
    deadline = time.time() + max_minutes * 60
    while True:
        started = time.time()
        probe = subprocess.run(["curl", "-sS", "-o", "/dev/null", "-w", "%{http_code}", "--max-time", "20",
                                "https://api.anthropic.com"], capture_output=True, text=True)
        if probe.returncode == 0:
            return True
        detail = (f"curl exit {probe.returncode} after {time.time() - started:.1f}s "
                  f"http={probe.stdout.strip()} {probe.stderr.strip()[-120:]}")
        if time.time() > deadline:
            log(f"api.anthropic.com unreachable after {max_minutes} min: {detail}")
            return False
        log(f"network not ready ({detail}), retrying in 20s")
        time.sleep(20)


def probe_failure(out_dir: Path) -> bool:
    """Runner exit 50 raised by its pre-inference reachability probe."""
    try:
        meta = json.loads((out_dir / "metadata.json").read_text())
    except (OSError, json.JSONDecodeError):
        return False
    return "allow-listed host unreachable" in str(meta.get("controller_exception", ""))


def sleep_until(epoch: float) -> None:
    while (left := epoch - time.time()) > 0:
        time.sleep(min(left, 600))


def discard(out_dir: Path, bucket: str, label: str, iid: str, condition: str) -> Path:
    """Move a run directory aside unchanged; never nest into an earlier attempt."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    parent = RUNS_DIR / f"discarded-{label}-{bucket}" / iid
    parent.mkdir(parents=True, exist_ok=True)
    dest, n = parent / f"{condition}-{stamp}", 1
    while dest.exists():
        n += 1
        dest = parent / f"{condition}-{stamp}-{n}"
    shutil.move(str(out_dir), dest)
    return dest


def record_limit(label_dir: Path, fields: dict) -> None:
    path = label_dir / "session-limit-events.tsv"
    new = not path.exists()
    with path.open("a", newline="") as fh:
        w = csv.DictWriter(fh, delimiter="\t", fieldnames=list(fields))
        if new:
            w.writeheader()
        w.writerow(fields)


def run_one(label: str, position: int, iid: str, condition: str, timeout: int | None) -> int:
    cmd = [sys.executable, str(rs.RUNNER), "--instance", iid, "--condition", condition,
           "--label", label, "--position", str(position)]
    if timeout is not None:
        cmd += ["--timeout-seconds", str(timeout)]
    return subprocess.run(cmd, cwd=ROOT).returncode


def evaluate(label: str, condition: str, workers: int) -> int:
    pred = subprocess.run([sys.executable, str(ANALYZE), "--label", label, "predictions",
                           "--condition", condition], cwd=ROOT)
    if pred.returncode:
        return pred.returncode
    predictions = RUNS_DIR / label / f"predictions-{condition}.jsonl"
    log(f"evaluator: {predictions}")
    ev = subprocess.run([str(SWEBENCH), "eval", "verified", "-p", str(predictions),
                         "-r", f"{label}-{condition}", "-j", str(workers)], cwd=ROOT)
    if ev.returncode:
        return ev.returncode
    return subprocess.run([sys.executable, str(ANALYZE), "--label", label, "table"], cwd=ROOT).returncode


def commit_and_push(label: str) -> None:
    paths = [p for p in (RUNS_DIR / label, RUNS_DIR / f"discarded-{label}-session-limit",
                         RUNS_DIR / f"discarded-{label}-network") if p.exists()]
    rel = [str(p.relative_to(ROOT)) for p in paths]
    subprocess.run(["git", "add", "--", *rel], cwd=ROOT)
    if subprocess.run(["git", "diff", "--cached", "--quiet", "--", *rel], cwd=ROOT).returncode == 0:
        log("nothing to commit")
        return
    msg = f"Record scheduled {label} series\n\nWritten by experiment/execution/scheduled_series.py."
    subprocess.run(["git", "commit", "-q", "-m", msg, "--", *rel], cwd=ROOT)
    env = dict(os.environ, GIT_SSH_COMMAND="ssh -o BatchMode=yes -o ConnectTimeout=20")
    push = subprocess.run(["git", "push", "origin", "HEAD"], cwd=ROOT, env=env,
                          capture_output=True, text=True, timeout=120)
    log(f"git push exit {push.returncode}: {(push.stdout + push.stderr).strip()[-200:]}")


def main(argv=None) -> int:
    global LOG_FILE
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--label", required=True)
    p.add_argument("--condition", choices=("single", "multi"), default="multi")
    p.add_argument("--order-file", type=Path, default=V1_ORDER)
    p.add_argument("--sample-file", type=Path, default=V1_SAMPLE)
    p.add_argument("--timeout-seconds", type=int)
    p.add_argument("--reset-grace", type=int, default=600)
    p.add_argument("--max-limit-waits", type=int, default=8)
    p.add_argument("--host-wait-hours", type=float, default=12)
    p.add_argument("--eval-workers", type=int, default=4)
    p.add_argument("--skip-eval", action="store_true")
    p.add_argument("--no-commit", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)

    try:
        rows = rs.read_order(args.order_file)
        rs.check_sample(rows, args.sample_file)
        freeze = rs.check_freeze_manifest()
        digest = rs.check_runner_digest()
    except SystemExit as exc:
        print(exc, file=sys.stderr)
        return 10

    plan = [t for t in rs.planned_runs(rows) if t[2] == args.condition]
    label_dir = RUNS_DIR / args.label
    print(f"label {args.label} | condition {args.condition} | {freeze} | runner {digest[:12]}")
    for position, iid, condition in plan:
        state = "skip" if (label_dir / iid / condition).exists() else "run "
        print(f"  {state} {position:>2}  {iid:<34} {condition}")
    if args.dry_run:
        return 0

    label_dir.mkdir(parents=True, exist_ok=True)
    LOG_FILE = label_dir / "scheduled-series.log"
    log(f"start: {len(plan)} planned {args.condition} runs")
    if not wait_for_host(args.host_wait_hours):
        return 11
    if not wait_for_network():
        return 13

    limit_waits = 0
    probe_retries = 0
    for position, iid, condition in plan:
        out_dir = label_dir / iid / condition
        while not out_dir.exists():
            started = rs.utc_now()
            log(f"run  {position} {iid} {condition}")
            code = run_one(args.label, position, iid, condition, args.timeout_seconds)
            fields = {"started_at": started, "finished_at": rs.utc_now(), "position": position,
                      "instance_id": iid, "condition": condition, "runner_exit_code": code}
            fields.update(rs.run_summary(out_dir))
            rs.log_row(label_dir / "series-log.tsv", fields)
            limit = session_limit(out_dir / "trace.jsonl")
            log(f"     exit {code} {fields['protocol_status']} session_limit={bool(limit)}")
            if limit:
                dest = discard(out_dir, "session-limit", args.label, iid, condition)
                limit_waits += 1
                resets = limit["resets_at"] or time.time() + 1800
                record_limit(label_dir, {"moved_at": rs.utc_now(), "position": position, "instance_id": iid,
                                         "condition": condition, "runner_exit_code": code,
                                         "resets_at": datetime.fromtimestamp(resets, timezone.utc).isoformat(),
                                         "discarded_to": str(dest.relative_to(ROOT)), "text": limit["text"]})
                if limit_waits > args.max_limit_waits:
                    log(f"stop: more than {args.max_limit_waits} session-limit waits")
                    return 12
                wake = max(resets + args.reset_grace, time.time() + 60)
                log(f"session limit: moved to {dest}; sleeping until "
                    f"{datetime.fromtimestamp(wake, timezone.utc).isoformat(timespec='seconds')}")
                sleep_until(wake)
                if not wait_for_host(args.host_wait_hours):
                    return 11
                if not wait_for_network():
                    return 13
                continue
            if code == 50 and probe_failure(out_dir):
                dest = discard(out_dir, "network", args.label, iid, condition)
                probe_retries += 1
                log(f"reachability probe failed before inference: moved to {dest} "
                    f"(retry {probe_retries}/{MAX_PROBE_RETRIES})")
                if probe_retries > MAX_PROBE_RETRIES or not wait_for_network():
                    return code
                continue
            if code != 0:
                log(f"stop at {position} {iid} {condition}: runner exit {code}: "
                    f"{rs.EXIT_MEANING.get(code, 'unexpected runner exit code')}")
                if not args.no_commit:
                    commit_and_push(args.label)
                return code

    status = 0
    if not args.skip_eval:
        rc = evaluate(args.label, args.condition, args.eval_workers)
        log(f"evaluation exit {rc}")
        status = 0 if rc == 0 else 60
    if not args.no_commit:
        commit_and_push(args.label)
    log(f"done, exit {status}")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
