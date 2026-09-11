#!/usr/bin/env python3
"""
run_series.py -- drive the frozen v4 run order for the SINGLE vs MULTI study.

`runner.py` executes exactly one (instance, condition) run. This driver is the
only thing that decides *which* run happens next, and it takes that decision
from `run-order-v4.tsv`, which was randomized and frozen before any v4 main
inference. Doing it by hand is how a series silently stops being the
preregistered one: a skipped pair, a reversed within-pair order or a resumed
series that re-runs an instance are all invisible afterwards.

Rules enforced here:

  * The order file must describe exactly the frozen v4 main sample; a mismatch
    with `preregistration/v4/tasks-main-v4.txt` stops the series before inference.
  * `FREEZE_V4.json` must match every frozen treatment/sample/analysis/network
    input listed in it; a changed file stops the series before inference.
  * The legacy runner digest must also match `runner.sha256`.
  * Within a pair the recorded condition order is followed exactly.
  * Runs happen strictly sequentially. The Claude profile lock and the shared
    egress proxy make concurrent runs unsafe, and interleaved wall-clock
    measurements would not be comparable.
  * Only exit code 0 continues the series. 20/30/40/50 all require a
    preregistered human decision (reserve substitution, manual classification
    or a configuration fix), so the driver stops and says which one applies.
  * An existing run directory is never overwritten or re-run; it is skipped,
    which is what makes an interrupted series resumable.

Exit codes
  0   every planned run completed with runner exit 0
  10  precondition failed; no inference was started
  n   the runner exit code that stopped the series
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXEC_DIR = ROOT / "experiment" / "execution"
PREREG_DIR = ROOT / "experiment" / "preregistration"
RUNS_DIR = ROOT / "experiment" / "runs"
RUNNER = EXEC_DIR / "runner.py"
ORDER_FILE = EXEC_DIR / "run-order-v4.tsv"
DIGEST_FILE = EXEC_DIR / "runner.sha256"
FREEZE_VERIFIER = EXEC_DIR / "verify_freeze.py"
TASKS_MAIN = PREREG_DIR / "v4" / "tasks-main-v4.txt"

ORDER_CONDITIONS = {
    "single-first": ("single", "multi"),
    "multi-first": ("multi", "single"),
}

EXIT_MEANING = {
    20: "controller/infrastructure failure -- eligible for PAIRED reserve "
        "substitution; remove both conditions of this instance before rerunning",
    30: "claude exited non-zero -- preregistered manual classification, no "
        "automatic retry",
    40: "patch collection failed -- infrastructure; same paired rule as 20",
    50: "configuration violation -- discard this run, fix the configuration, "
        "then rerun the same instance",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_order(path: Path) -> list[dict]:
    rows = []
    with path.open() as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            missing = {"position", "instance_id", "order"} - set(row)
            if missing:
                raise SystemExit(f"{path}: missing columns {sorted(missing)}")
            if row["order"] not in ORDER_CONDITIONS:
                raise SystemExit(f"{path}: unknown order {row['order']!r}")
            row["position"] = int(row["position"])
            rows.append(row)
    rows.sort(key=lambda r: r["position"])
    if [r["position"] for r in rows] != list(range(1, len(rows) + 1)):
        raise SystemExit(f"{path}: positions must be 1..n without gaps")
    return rows


def check_sample(rows: list[dict], sample_file: Path = TASKS_MAIN) -> None:
    """The order file and the frozen sample must describe the same 12 tasks."""
    ordered = [r["instance_id"] for r in rows]
    if len(set(ordered)) != len(ordered):
        raise SystemExit("run order contains a duplicate instance")
    frozen = [l.strip() for l in sample_file.read_text().splitlines() if l.strip()]
    if set(ordered) != set(frozen):
        only_order = sorted(set(ordered) - set(frozen))
        only_frozen = sorted(set(frozen) - set(ordered))
        raise SystemExit(
            f"run order does not match the frozen sample ({sample_file}) "
            f"(order only: {only_order}; sample only: {only_frozen})"
        )


def check_freeze_manifest() -> str:
    proc = subprocess.run(
        [sys.executable, str(FREEZE_VERIFIER)],
        cwd=ROOT, capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise SystemExit(
            "v4 freeze manifest verification failed; no main inference may start.\n"
            f"{proc.stdout}{proc.stderr}"
        )
    return proc.stdout.strip()


def check_runner_digest() -> str:
    proc = subprocess.run(
        ["sha256sum", "-c", str(DIGEST_FILE)],
        cwd=ROOT, capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise SystemExit(
            "runner digest does not match runner.sha256; a main series must be "
            f"produced by the frozen runner.\n{proc.stdout}{proc.stderr}"
        )
    return DIGEST_FILE.read_text().split()[0]


def planned_runs(rows: list[dict]) -> list[tuple[int, str, str]]:
    plan = []
    for row in rows:
        for condition in ORDER_CONDITIONS[row["order"]]:
            plan.append((row["position"], row["instance_id"], condition))
    return plan


def log_row(log_path: Path, fields: dict) -> None:
    header = not log_path.exists()
    with log_path.open("a", newline="") as fh:
        writer = csv.DictWriter(fh, delimiter="\t", fieldnames=list(fields))
        if header:
            writer.writeheader()
        writer.writerow(fields)


def run_summary(out_dir: Path) -> dict:
    """Read back what the runner recorded, so the series log is self-contained."""
    metrics = out_dir / "metrics.json"
    if not metrics.exists():
        return {"protocol_status": "", "patch_bytes": "", "timed_out": ""}
    data = json.loads(metrics.read_text())
    return {
        "protocol_status": data.get("protocol_status", ""),
        "patch_bytes": data.get("patch_bytes", ""),
        "timed_out": data.get("timed_out", ""),
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--label", required=True,
                   help="run label; also the directory under experiment/runs/")
    p.add_argument("--order-file", type=Path, default=ORDER_FILE)
    p.add_argument("--sample-file", type=Path, default=TASKS_MAIN,
                   help="frozen instance list the order file must match "
                        "(default: the v4 main sample)")
    p.add_argument("--timeout-seconds", type=int)
    p.add_argument("--from-position", type=int, default=1,
                   help="resume at this position (earlier positions are left alone)")
    p.add_argument("--dry-run", action="store_true",
                   help="check preconditions and print the plan; run nothing")
    p.add_argument("--allow-unfrozen-runner", action="store_true",
                   help="VALIDATION ONLY: skip the v4 freeze-manifest and runner "
                        "digest checks. Never use for a reported main series.")
    args = p.parse_args()

    rows = read_order(args.order_file)
    check_sample(rows, args.sample_file)
    if args.allow_unfrozen_runner:
        freeze_status = "unchecked (validation override)"
        digest = "unchecked"
    else:
        freeze_status = check_freeze_manifest()
        digest = check_runner_digest()

    plan = [t for t in planned_runs(rows) if t[0] >= args.from_position]
    label_dir = RUNS_DIR / args.label
    todo = [t for t in plan if not (label_dir / t[1] / t[2]).exists()]

    print(f"label            : {args.label}")
    print(f"freeze manifest  : {freeze_status}")
    print(f"runner sha256    : {digest}")
    print(f"order file       : {args.order_file}")
    print(f"sample file      : {args.sample_file}")
    print(f"planned runs     : {len(plan)}")
    print(f"already present  : {len(plan) - len(todo)}")
    for position, iid, condition in plan:
        state = "skip" if (label_dir / iid / condition).exists() else "run "
        print(f"  {state} {position:>2}  {iid:<34} {condition}")
    if args.dry_run:
        return 0
    if not todo:
        print("nothing to do")
        return 0

    label_dir.mkdir(parents=True, exist_ok=True)
    log_path = label_dir / "series-log.tsv"

    for position, iid, condition in plan:
        out_dir = label_dir / iid / condition
        if out_dir.exists():
            print(f"[{utc_now()}] skip {position} {iid} {condition} (present)")
            continue
        cmd = [sys.executable, str(RUNNER), "--instance", iid,
               "--condition", condition, "--label", args.label,
               "--position", str(position)]
        if args.timeout_seconds is not None:
            cmd += ["--timeout-seconds", str(args.timeout_seconds)]
        started = utc_now()
        print(f"[{started}] run  {position} {iid} {condition}", flush=True)
        exit_code = subprocess.run(cmd, cwd=ROOT).returncode
        fields = {
            "started_at": started, "finished_at": utc_now(),
            "position": position, "instance_id": iid, "condition": condition,
            "runner_exit_code": exit_code,
        }
        fields.update(run_summary(out_dir))
        log_row(log_path, fields)
        print(f"    exit {exit_code}  {fields['protocol_status']}")
        if exit_code != 0:
            meaning = EXIT_MEANING.get(exit_code, "unexpected runner exit code")
            print(f"\nSeries stopped at position {position} ({iid}, {condition}).")
            print(f"Runner exit {exit_code}: {meaning}")
            print(f"Log: {log_path}")
            return exit_code

    print(f"\nSeries complete: {len(todo)} runs executed. Log: {log_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
