"""Paired analysis: exact tests, the join to the evaluator, and exclusions."""

import importlib.util
import json
from pathlib import Path

import pytest

ANALYZE = Path(__file__).resolve().parents[1] / "experiment/execution/analyze_runs.py"


@pytest.fixture
def analysis(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location("experiment_analysis", ANALYZE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(module, "EVAL_ROOT", tmp_path / "eval")
    module._tmp = tmp_path
    return module


def write_run(analysis, instance, condition, *, label="t", complete=True, **fields):
    directory = analysis.RUNS_DIR / label / instance / condition
    directory.mkdir(parents=True, exist_ok=True)
    metrics = {
        "instance_id": instance, "condition": condition,
        "wall_seconds": 100.0, "unique_assistant_messages": 10,
        "tool_calls_total": 5, "num_turns": 3,
        "token_accounting": {
            "status": "complete" if complete else "partial_snapshot",
            "complete": complete,
            "totals": {"total_tokens": 1000, "output_tokens": 100},
        },
        "subagent_stats": {"spawned": 1, "completed": 1} if condition == "multi" else {},
        "protocol_status": "pass",
    }
    metrics.update(fields)
    (directory / "metrics.json").write_text(json.dumps(metrics))
    (directory / "metadata.json").write_text(json.dumps(
        {"network_isolation": {"enforced": True}}))
    (directory / "patch.diff").write_text(f"diff --{instance}-{condition}\n")
    return directory


def write_report(analysis, instance, condition, resolved, *, label="t",
                 run_id="eval-1", f2p=(1, 0)):
    name = analysis.model_name(condition, label)
    directory = analysis.EVAL_ROOT / run_id / name / instance
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "report.json").write_text(json.dumps({instance: {
        "resolved": resolved, "patch_successfully_applied": True,
        "tests_status": {"FAIL_TO_PASS": {
            "success": [f"t{i}" for i in range(f2p[0])],
            "failure": [f"f{i}" for i in range(f2p[1])]}},
    }}))
    return directory


def test_exact_mcnemar_matches_hand_computed_binomial(analysis):
    for instance in "abcd":
        write_run(analysis, instance, "single")
        write_run(analysis, instance, "multi")
        write_report(analysis, instance, "single", False)
        write_report(analysis, instance, "multi", True)
    summary = analysis.summarise(analysis.collect("t", analysis.EVAL_ROOT))
    q = summary["quality"]
    assert (q["only_multi"], q["only_single"], q["discordant"]) == (4, 0, 4)
    # two-sided exact binomial on 4 discordant pairs: 2 * (1/2)^4
    assert q["p_value_exact_mcnemar"] == pytest.approx(0.125)
    assert (q["single_resolved"], q["multi_resolved"]) == (0, 4)


def test_randomization_test_enumerates_the_exact_distribution(analysis):
    # sums over the 8 sign assignments of (1,2,3): only +-6 reach |6|
    assert analysis.randomization_test([1, 2, 3]) == pytest.approx(0.25)
    assert analysis.randomization_test([]) is None
    # one pair: both sign assignments are as extreme, so nothing is detectable
    assert analysis.randomization_test([5.0]) == pytest.approx(1.0)


def test_partial_token_accounting_drops_the_pair_from_cost_not_quality(analysis):
    write_run(analysis, "a", "single")
    write_run(analysis, "a", "multi", complete=False)
    write_run(analysis, "b", "single")
    write_run(analysis, "b", "multi", token_accounting={
        "status": "complete", "complete": True,
        "totals": {"total_tokens": 3000, "output_tokens": 300}})
    for instance in ("a", "b"):
        write_report(analysis, instance, "single", True)
        write_report(analysis, instance, "multi", True)
    summary = analysis.summarise(analysis.collect("t", analysis.EVAL_ROOT))
    assert summary["quality"]["n_pairs_scored"] == 2
    assert summary["cost"]["total_tokens"]["n"] == 1
    assert summary["cost"]["total_tokens"]["excluded"] == ["a"]
    # wall time does not depend on token accounting, so both pairs stay
    assert summary["cost"]["wall_seconds"]["n"] == 2


def test_unpaired_instance_is_named_not_silently_dropped(analysis):
    write_run(analysis, "a", "single")
    write_run(analysis, "a", "multi")
    write_run(analysis, "lonely", "single")
    summary = analysis.summarise(analysis.collect("t", analysis.EVAL_ROOT))
    assert summary["n_pairs"] == 1
    assert summary["unpaired_instances"] == ["lonely"]


def test_multi_without_confirmed_delegation_is_reported(analysis):
    write_run(analysis, "a", "single")
    write_run(analysis, "a", "multi", subagent_stats={"spawned": 1, "completed": 0})
    summary = analysis.summarise(analysis.collect("t", analysis.EVAL_ROOT))
    assert summary["multi_without_confirmed_delegation"] == ["a"]


def test_latest_evaluation_wins_and_is_recorded(analysis):
    write_run(analysis, "a", "single")
    old = write_report(analysis, "a", "single", False, run_id="eval-old")
    new = write_report(analysis, "a", "single", True, run_id="eval-new")
    import os
    os.utime(old / "report.json", (1, 1))
    os.utime(new / "report.json", (2, 2))
    row = analysis.collect("t", analysis.EVAL_ROOT)[0]
    assert row["resolved"] is True
    assert row["eval_run_id"] == "eval-new"


def test_test_fraction_counts_successes_over_required_tests(analysis):
    write_run(analysis, "a", "single")
    write_report(analysis, "a", "single", False, f2p=(3, 1))
    assert analysis.collect("t", analysis.EVAL_ROOT)[0]["test_fraction"] == 0.75


def test_missing_patch_still_produces_a_prediction(analysis, capsys):
    directory = write_run(analysis, "a", "multi")
    (directory / "patch.diff").unlink()
    out = analysis._tmp / "p.jsonl"
    analysis.main(["--label", "t", "--out", str(out), "predictions",
                   "--condition", "multi"])
    record = json.loads(out.read_text().strip())
    assert record["model_patch"] == ""
    assert record["model_name_or_path"] == "claude-sonnet-5-multi-t"


def test_unscored_runs_do_not_become_failures(analysis):
    write_run(analysis, "a", "single")
    write_run(analysis, "a", "multi")
    summary = analysis.summarise(analysis.collect("t", analysis.EVAL_ROOT))
    assert summary["quality"]["unknown"] == 1
    assert summary["quality"]["n_pairs_scored"] == 0
