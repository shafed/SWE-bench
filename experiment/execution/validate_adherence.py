#!/usr/bin/env python3
"""Validate filled v4 MULTI adherence coding against the preregistered rules."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TASKS = ROOT / "experiment" / "preregistration" / "v4" / "tasks-main-v4.txt"
RUNS = ROOT / "experiment" / "runs"

CHECKS = [
    "A0_completed",
    "A1_before_prod_edit",
    "A2_impl_delegation",
    "A3_workstream_coverage",
    "A4_parallel_if_independent",
    "A5_solution_independence",
    "A6_parent_integration",
    "A7_final_verification",
]
BASIC = {"pass", "fail", "unclear"}
WITH_NA = BASIC | {"na"}


def derive_overall(row: dict[str, str]) -> str:
    values = [row[name] for name in CHECKS]
    if "fail" in values:
        return "clear_violation"
    if "unclear" in values:
        return "unclear"
    if row["A3_workstream_coverage"] not in {"pass", "na"}:
        return "unclear"
    if row["A4_parallel_if_independent"] not in {"pass", "na"}:
        return "unclear"
    return "full"


def expected_a0(label: str, instance: str) -> str:
    path = RUNS / label / instance / "multi" / "metrics.json"
    if not path.exists():
        raise ValueError(f"missing metrics for {instance}: {path}")
    metrics = json.loads(path.read_text())
    completed = ((metrics.get("subagent_stats") or {}).get("completed") or 0)
    return "pass" if completed >= 1 else "fail"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--label", required=True, help="main run label under experiment/runs")
    p.add_argument("--coding", type=Path, required=True, help="filled adherence TSV")
    args = p.parse_args()

    expected = [line.strip() for line in TASKS.read_text().splitlines() if line.strip()]
    with args.coding.open(newline="") as fh:
        rows = list(csv.DictReader(fh, delimiter="\t"))

    required_columns = {"instance_id", "condition", *CHECKS, "overall_adherence", "evidence"}
    missing_columns = required_columns - set(rows[0] if rows else {})
    errors: list[str] = []
    if missing_columns:
        errors.append(f"missing columns: {sorted(missing_columns)}")

    instances = [row.get("instance_id", "") for row in rows]
    if len(rows) != len(expected) or set(instances) != set(expected):
        errors.append("coding rows must contain exactly the 12 frozen v4 instances once each")
    if len(set(instances)) != len(instances):
        errors.append("duplicate instance in coding file")

    for row in rows:
        iid = row.get("instance_id", "<missing>")
        if row.get("condition") != "multi":
            errors.append(f"{iid}: condition must be multi")
            continue
        for name in CHECKS:
            allowed = WITH_NA if name in {"A3_workstream_coverage", "A4_parallel_if_independent"} else BASIC
            value = row.get(name, "")
            if value not in allowed:
                errors.append(f"{iid}: {name}={value!r}, allowed={sorted(allowed)}")
        if not row.get("evidence", "").strip():
            errors.append(f"{iid}: evidence is empty")
        if all(row.get(name, "") in (WITH_NA if name in {"A3_workstream_coverage", "A4_parallel_if_independent"} else BASIC) for name in CHECKS):
            derived = derive_overall(row)
            if row.get("overall_adherence") != derived:
                errors.append(
                    f"{iid}: overall_adherence={row.get('overall_adherence')!r}, expected {derived!r}"
                )
        try:
            a0 = expected_a0(args.label, iid)
        except Exception as exc:
            errors.append(f"{iid}: cannot verify A0: {exc}")
        else:
            if row.get("A0_completed") != a0:
                errors.append(f"{iid}: A0_completed={row.get('A0_completed')!r}, metrics require {a0!r}")

    if errors:
        print("adherence validation FAILED")
        for error in errors:
            print(f"  - {error}")
        return 1

    counts = {key: 0 for key in ("full", "clear_violation", "unclear")}
    for row in rows:
        counts[row["overall_adherence"]] += 1
    print(
        "adherence validation OK: "
        f"full={counts['full']} clear_violation={counts['clear_violation']} unclear={counts['unclear']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
