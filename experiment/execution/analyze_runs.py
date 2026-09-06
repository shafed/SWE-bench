#!/usr/bin/env python3
"""
analyze_runs.py -- build predictions, join evaluations, compare the conditions.

Written and committed before the main series exists, so that the quantitative
analysis is fixed in the same way the sampling and the failure taxonomy are.
Nothing here reads an outcome that could then change the choice of test.

Preregistered quantitative analysis
-----------------------------------
Unit: the instance. Every instance contributes one SINGLE and one MULTI run, so
every comparison is paired and instance difficulty cancels out.

  * Primary quality outcome: `resolved` from the official SWE-bench report.
    Compared with an exact McNemar test on the discordant pairs (two-sided,
    binomial with p=0.5). With 12 pairs this is a small-sample test and will
    only detect a large effect; that is a property of the design, stated in
    advance rather than discovered afterwards.
  * Secondary quality outcome: fraction of FAIL_TO_PASS and PASS_TO_PASS tests
    passing, from the same report.
  * Cost outcomes: total tokens, output tokens, wall-clock seconds, model
    messages, tool calls. Each is compared as a paired difference MULTI - SINGLE, summarised by
    the median difference, and tested with an exact paired randomisation test
    (all 2^n sign flips of the observed differences, two-sided on the mean).
    Exact enumeration avoids assuming normality on 12 pairs.
  * A pair enters a cost comparison only if both runs report complete token
    accounting; pairs excluded for that reason are counted and reported. A
    pair is never dropped from the quality comparison for a resource reason.
  * The process measure is `unique_assistant_messages` from the trace, not
    `result.num_turns`. The CLI's own turn count does not describe a MULTI
    session: in the dev runs `runner-freeze-validation/multi` reports
    num_turns 1 with 36 tool calls and 71 assistant events, and
    `runner-final-sequential-20260906/multi` reports 2 with 21 tool calls,
    while the SINGLE runs of the same instance report 10-11 turns for 9-10 tool
    calls. Taken at face value it would make delegation look cheaper in turns
    purely as an artefact. `num_turns` stays in the per-run table as reported
    data; it is not compared.
  * MULTI runs whose delegation was not confirmed (`subagent_stats.completed`
    below 1) are reported separately as treatment non-compliance. They are not
    silently dropped and not retried.

Subcommands
  predictions  write predictions.jsonl for one condition from collected patches
  table        one row per run, joining metrics.json with the evaluation report
  summary      the paired comparison above, as text and JSON
"""

from __future__ import annotations

import argparse
import csv
import itertools
import json
import math
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNS_DIR = ROOT / "experiment" / "runs"
EVAL_ROOT = ROOT / "logs" / "evaluation"
MODEL = "claude-sonnet-5"
CONDITIONS = ("single", "multi")

COST_FIELDS = (
    ("total_tokens", "total tokens"),
    ("output_tokens", "output tokens"),
    ("wall_seconds", "wall-clock seconds"),
    ("unique_assistant_messages", "model messages"),
    ("tool_calls_total", "tool calls"),
)


def model_name(condition: str, label: str) -> str:
    """Prediction identity; also how an evaluation directory is found again."""
    return f"{MODEL}-{condition}-{label}"


def run_dirs(label: str) -> list[Path]:
    base = RUNS_DIR / label
    if not base.is_dir():
        raise SystemExit(f"no such run label: {base}")
    return sorted(d for d in base.glob("*/*") if (d / "metrics.json").exists())


def load_json(path: Path):
    return json.loads(path.read_text()) if path.exists() else None


def find_report(condition: str, label: str, instance: str, eval_root: Path) -> dict | None:
    """
    Locate the official evaluator's report for one run.

    The same predictions can be evaluated more than once (a rerun after an
    infrastructure failure). The most recently written report wins, and the
    table records which evaluation directory it came from, so the join is never
    a guess.
    """
    name = model_name(condition, label)
    candidates = sorted(
        eval_root.glob(f"*/{name}/{instance}/report.json"),
        key=lambda p: p.stat().st_mtime,
    )
    if not candidates:
        return None
    path = candidates[-1]
    data = load_json(path) or {}
    report = data.get(instance)
    if report is None:
        return None
    return {"report": report, "eval_run_id": path.parents[2].name, "path": path}


def test_fraction(report: dict) -> float | None:
    """Share of the evaluator's own required tests that passed."""
    status = report.get("tests_status") or {}
    passed = total = 0
    for key in ("FAIL_TO_PASS", "PASS_TO_PASS"):
        group = status.get(key) or {}
        good = len(group.get("success") or [])
        bad = len(group.get("failure") or [])
        passed += good
        total += good + bad
    return passed / total if total else None


def collect(label: str, eval_root: Path) -> list[dict]:
    rows = []
    for directory in run_dirs(label):
        metrics = load_json(directory / "metrics.json") or {}
        metadata = load_json(directory / "metadata.json") or {}
        instance = metrics.get("instance_id") or directory.parent.name
        condition = metrics.get("condition") or directory.name
        accounting = metrics.get("token_accounting") or {}
        totals = accounting.get("totals") or {}
        stats = metrics.get("subagent_stats") or {}
        found = find_report(condition, label, instance, eval_root)
        report = found["report"] if found else None
        rows.append({
            "instance_id": instance,
            "condition": condition,
            "position": metrics.get("position"),
            "resolved": report.get("resolved") if report else None,
            "test_fraction": test_fraction(report) if report else None,
            "patch_applied": report.get("patch_successfully_applied") if report else None,
            "eval_run_id": found["eval_run_id"] if found else None,
            "timed_out": metrics.get("timed_out"),
            "protocol_status": metrics.get("protocol_status"),
            "delegation_completed": stats.get("completed"),
            "delegation_spawned": stats.get("spawned"),
            "delegations": len(metrics.get("delegations") or []),
            "delegation_prompt_chars_total": metrics.get("delegation_prompt_chars_total"),
            "wall_seconds": metrics.get("wall_seconds"),
            "unique_assistant_messages": metrics.get("unique_assistant_messages"),
            "num_turns_reported": metrics.get("num_turns"),
            "assistant_events": metrics.get("assistant_events"),
            "tool_calls_total": metrics.get("tool_calls_total"),
            "token_status": accounting.get("status"),
            "token_complete": accounting.get("complete"),
            "total_tokens": totals.get("total_tokens"),
            "output_tokens": totals.get("output_tokens"),
            "input_tokens": totals.get("input_tokens"),
            "cache_read_input_tokens": totals.get("cache_read_input_tokens"),
            "cache_creation_input_tokens": totals.get("cache_creation_input_tokens"),
            "cost_usd_reported": metrics.get("total_cost_usd_reported"),
            "patch_bytes": metrics.get("patch_bytes"),
            "network_enforced": (metadata.get("network_isolation") or {}).get("enforced"),
        })
    return rows


def pairs(rows: list[dict]) -> dict[str, dict[str, dict]]:
    out: dict[str, dict[str, dict]] = {}
    for row in rows:
        out.setdefault(row["instance_id"], {})[row["condition"]] = row
    return {k: v for k, v in sorted(out.items()) if set(v) == set(CONDITIONS)}


def mcnemar_exact(pairs_: dict) -> dict:
    """Two-sided exact McNemar: the discordant pairs under p = 0.5."""
    both = only_single = only_multi = neither = unknown = 0
    for pair in pairs_.values():
        s, m = pair["single"]["resolved"], pair["multi"]["resolved"]
        if s is None or m is None:
            unknown += 1
        elif s and m:
            both += 1
        elif s and not m:
            only_single += 1
        elif m and not s:
            only_multi += 1
        else:
            neither += 1
    discordant = only_single + only_multi
    if discordant:
        tail = sum(math.comb(discordant, k) for k in range(min(only_single, only_multi) + 1))
        p = min(1.0, 2 * tail / 2 ** discordant)
    else:
        p = 1.0
    return {
        "both_resolved": both, "only_single": only_single, "only_multi": only_multi,
        "neither_resolved": neither, "unknown": unknown,
        "discordant": discordant, "p_value_exact_mcnemar": p,
        "single_resolved": both + only_single, "multi_resolved": both + only_multi,
        "n_pairs_scored": both + only_single + only_multi + neither,
    }


def randomization_test(diffs: list[float]) -> float | None:
    """
    Exact two-sided paired randomisation test on the mean difference.

    Under the null the sign of each paired difference is exchangeable, so every
    one of the 2^n sign assignments is equally likely. With n <= 12 the whole
    reference distribution is enumerated; no normality assumption is needed.
    """
    values = [d for d in diffs if d is not None]
    if not values:
        return None
    observed = abs(sum(values))
    if len(values) > 20:  # enumeration would stop being cheap
        return None
    extreme = sum(
        abs(sum(v * s for v, s in zip(values, signs))) >= observed - 1e-12
        for signs in itertools.product((1, -1), repeat=len(values))
    )
    return extreme / 2 ** len(values)


def cost_comparison(pairs_: dict, field: str) -> dict:
    """MULTI - SINGLE differences, using only pairs with complete accounting."""
    diffs, excluded = [], []
    token_field = field.endswith("tokens")
    for instance, pair in pairs_.items():
        s, m = pair["single"], pair["multi"]
        if token_field and not (s.get("token_complete") and m.get("token_complete")):
            excluded.append(instance)
            continue
        if s.get(field) is None or m.get(field) is None:
            excluded.append(instance)
            continue
        diffs.append(m[field] - s[field])
    if not diffs:
        return {"n": 0, "excluded": excluded, "median_difference": None,
                "mean_difference": None, "p_value_exact_randomization": None,
                "single_median": None, "multi_median": None, "ratio_of_medians": None}
    singles = [pair["single"][field] for i, pair in pairs_.items() if i not in excluded]
    multis = [pair["multi"][field] for i, pair in pairs_.items() if i not in excluded]
    single_median = statistics.median(singles)
    multi_median = statistics.median(multis)
    return {
        "n": len(diffs), "excluded": excluded,
        "median_difference": statistics.median(diffs),
        "mean_difference": statistics.fmean(diffs),
        "p_value_exact_randomization": randomization_test(diffs),
        "single_median": single_median, "multi_median": multi_median,
        "ratio_of_medians": (multi_median / single_median) if single_median else None,
    }


def summarise(rows: list[dict]) -> dict:
    paired = pairs(rows)
    unpaired = sorted({r["instance_id"] for r in rows} - set(paired))
    noncompliant = sorted(
        r["instance_id"] for r in rows
        if r["condition"] == "multi" and (r["delegation_completed"] or 0) < 1
    )
    single_violation = sorted(
        r["instance_id"] for r in rows
        if r["condition"] == "single" and "violation" in (r["protocol_status"] or "")
    )
    unenforced = sorted(
        f"{r['instance_id']}/{r['condition']}" for r in rows
        if r["network_enforced"] is not True
    )
    return {
        "n_runs": len(rows),
        "n_pairs": len(paired),
        "unpaired_instances": unpaired,
        "multi_without_confirmed_delegation": noncompliant,
        "single_with_delegation_violation": single_violation,
        "runs_without_enforced_isolation": unenforced,
        "quality": mcnemar_exact(paired),
        "test_fraction": cost_comparison(paired, "test_fraction"),
        "cost": {field: cost_comparison(paired, field) for field, _ in COST_FIELDS},
    }


def render(summary: dict) -> str:
    q = summary["quality"]
    lines = [
        f"runs {summary['n_runs']}   complete pairs {summary['n_pairs']}",
        "",
        "Quality (official SWE-bench evaluator)",
        f"  SINGLE resolved : {q['single_resolved']}/{q['n_pairs_scored']}",
        f"  MULTI  resolved : {q['multi_resolved']}/{q['n_pairs_scored']}",
        f"  discordant pairs: {q['discordant']} "
        f"(only SINGLE {q['only_single']}, only MULTI {q['only_multi']})",
        f"  exact McNemar p : {q['p_value_exact_mcnemar']:.4f}",
        "",
        "Cost (MULTI - SINGLE, paired)",
    ]
    for field, title in COST_FIELDS:
        c = summary["cost"][field]
        if not c["n"]:
            lines.append(f"  {title:<20} no comparable pairs")
            continue
        p = c["p_value_exact_randomization"]
        ratio = c["ratio_of_medians"]
        lines.append(
            f"  {title:<20} n={c['n']:<3} median {c['single_median']:>12,.1f} -> "
            f"{c['multi_median']:>12,.1f}  diff {c['median_difference']:>+12,.1f}"
            + (f"  x{ratio:.2f}" if ratio else "")
            + (f"  p={p:.4f}" if p is not None else "")
        )
        if c["excluded"]:
            lines.append(f"  {'':<20} excluded: {', '.join(c['excluded'])}")
    for key, title in (
        ("unpaired_instances", "instances without both conditions"),
        ("multi_without_confirmed_delegation", "MULTI without confirmed delegation"),
        ("single_with_delegation_violation", "SINGLE with delegation violation"),
        ("runs_without_enforced_isolation", "runs without enforced isolation"),
    ):
        if summary[key]:
            lines += ["", f"{title}: {', '.join(summary[key])}"]
    return "\n".join(lines)


def cmd_predictions(args) -> int:
    written = 0
    out_path = args.out or RUNS_DIR / args.label / f"predictions-{args.condition}.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as fh:
        for directory in run_dirs(args.label):
            if directory.name != args.condition:
                continue
            patch = directory / "patch.diff"
            fh.write(json.dumps({
                "instance_id": directory.parent.name,
                "model_name_or_path": model_name(args.condition, args.label),
                # An empty patch is an experimental outcome and must reach the
                # evaluator as an unresolved instance, not vanish from the file.
                "model_patch": patch.read_text() if patch.exists() else "",
            }) + "\n")
            written += 1
    print(f"{written} predictions -> {out_path}")
    return 0


def cmd_table(args) -> int:
    rows = collect(args.label, args.eval_root)
    if not rows:
        raise SystemExit(f"no runs under label {args.label}")
    out_path = args.out or RUNS_DIR / args.label / "runs-table.tsv"
    with out_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, delimiter="\t", fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"{len(rows)} rows -> {out_path}")
    return 0


def cmd_summary(args) -> int:
    rows = collect(args.label, args.eval_root)
    summary = summarise(rows)
    text = render(summary)
    print(text)
    out_path = args.out or RUNS_DIR / args.label / "summary.json"
    out_path.write_text(json.dumps(summary, indent=2) + "\n")
    (out_path.parent / "summary.txt").write_text(text + "\n")
    print(f"\n-> {out_path}")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--label", required=True)
    p.add_argument("--eval-root", type=Path, default=EVAL_ROOT)
    p.add_argument("--out", type=Path)
    sub = p.add_subparsers(dest="command", required=True)
    pred = sub.add_parser("predictions")
    pred.add_argument("--condition", required=True, choices=CONDITIONS)
    pred.set_defaults(func=cmd_predictions)
    sub.add_parser("table").set_defaults(func=cmd_table)
    sub.add_parser("summary").set_defaults(func=cmd_summary)
    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
