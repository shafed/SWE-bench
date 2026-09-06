"""Series driver: the frozen run order must survive resume and failure."""

import csv
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
DRIVER = REPO / "experiment/execution/run_series.py"


@pytest.fixture
def series(monkeypatch, tmp_path):
    """Load the driver with every path redirected into a temporary tree."""
    spec = importlib.util.spec_from_file_location("experiment_series", DRIVER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    order = tmp_path / "run-order.tsv"
    order.write_text(
        "position\tinstance_id\torder\n"
        "1\talpha__alpha-1\tmulti-first\n"
        "2\tbeta__beta-2\tsingle-first\n"
    )
    tasks = tmp_path / "tasks-main.txt"
    tasks.write_text("alpha__alpha-1\nbeta__beta-2\n")

    monkeypatch.setattr(module, "ORDER_FILE", order)
    monkeypatch.setattr(module, "TASKS_MAIN", tasks)
    monkeypatch.setattr(module, "RUNS_DIR", tmp_path / "runs")
    module._order = order
    module._tasks = tasks
    module._runs = tmp_path / "runs"
    return module


def invoke(series, monkeypatch, *args, exits=(), skip_digest=True):
    """Run main() with a fake runner that reports the given exit codes."""
    calls = []
    codes = list(exits)

    real_run = subprocess.run

    def fake_run(cmd, cwd=None, **kwargs):
        if "--instance" not in cmd:  # precondition checks, e.g. sha256sum
            return real_run(cmd, cwd=cwd, **kwargs)
        calls.append(cmd)
        iid = cmd[cmd.index("--instance") + 1]
        condition = cmd[cmd.index("--condition") + 1]
        label = cmd[cmd.index("--label") + 1]
        out = series._runs / label / iid / condition
        out.mkdir(parents=True)
        code = codes.pop(0) if codes else 0
        (out / "metrics.json").write_text(json.dumps(
            {"protocol_status": "pass", "patch_bytes": 10, "timed_out": False}))
        return subprocess.CompletedProcess(cmd, code)

    monkeypatch.setattr(series.subprocess, "run", fake_run)
    argv = ["run_series.py", "--label", "t", "--order-file", str(series._order)]
    if skip_digest:
        argv.append("--allow-unfrozen-runner")
    monkeypatch.setattr(sys, "argv", argv + list(args))
    return series.main(), calls


def executed(calls):
    return [(c[c.index("--instance") + 1], c[c.index("--condition") + 1])
            for c in calls]


def test_within_pair_order_follows_the_frozen_file(series, monkeypatch):
    code, calls = invoke(series, monkeypatch)
    assert code == 0
    assert executed(calls) == [
        ("alpha__alpha-1", "multi"), ("alpha__alpha-1", "single"),
        ("beta__beta-2", "single"), ("beta__beta-2", "multi"),
    ]
    log = list(csv.DictReader(
        (series._runs / "t" / "series-log.tsv").open(), delimiter="\t"))
    assert [r["condition"] for r in log] == ["multi", "single", "single", "multi"]
    assert {r["runner_exit_code"] for r in log} == {"0"}


def test_nonzero_exit_stops_the_series_immediately(series, monkeypatch):
    code, calls = invoke(series, monkeypatch, exits=[0, 50])
    assert code == 50
    # The pair that failed is not completed and position 2 never starts.
    assert executed(calls) == [
        ("alpha__alpha-1", "multi"), ("alpha__alpha-1", "single"),
    ]


def test_existing_runs_are_skipped_not_rerun(series, monkeypatch):
    (series._runs / "t" / "alpha__alpha-1" / "multi").mkdir(parents=True)
    code, calls = invoke(series, monkeypatch)
    assert code == 0
    assert ("alpha__alpha-1", "multi") not in executed(calls)
    assert len(calls) == 3


def test_from_position_leaves_earlier_positions_alone(series, monkeypatch):
    code, calls = invoke(series, monkeypatch, "--from-position", "2")
    assert code == 0
    assert executed(calls) == [("beta__beta-2", "single"), ("beta__beta-2", "multi")]


def test_dry_run_starts_no_inference(series, monkeypatch):
    code, calls = invoke(series, monkeypatch, "--dry-run")
    assert code == 0
    assert calls == []


def test_order_file_must_match_the_frozen_sample(series, monkeypatch):
    series._tasks.write_text("alpha__alpha-1\ngamma__gamma-3\n")
    with pytest.raises(SystemExit) as exc:
        invoke(series, monkeypatch)
    assert "frozen sample" in str(exc.value)


def test_positions_must_be_contiguous(series, monkeypatch):
    series._order.write_text(
        "position\tinstance_id\torder\n"
        "1\talpha__alpha-1\tmulti-first\n"
        "3\tbeta__beta-2\tsingle-first\n"
    )
    with pytest.raises(SystemExit) as exc:
        invoke(series, monkeypatch)
    assert "positions" in str(exc.value)


def test_unknown_condition_order_is_rejected(series, monkeypatch):
    series._order.write_text(
        "position\tinstance_id\torder\n1\talpha__alpha-1\teither\n")
    with pytest.raises(SystemExit) as exc:
        invoke(series, monkeypatch)
    assert "unknown order" in str(exc.value)


def test_unfrozen_runner_stops_the_series_before_inference(series, monkeypatch, tmp_path):
    digest = tmp_path / "runner.sha256"
    digest.write_text("0" * 64 + "  experiment/execution/runner.py\n")
    monkeypatch.setattr(series, "DIGEST_FILE", digest)
    with pytest.raises(SystemExit) as exc:
        invoke(series, monkeypatch, skip_digest=False)
    assert "frozen runner" in str(exc.value)


def test_real_order_file_matches_the_real_frozen_sample():
    spec = importlib.util.spec_from_file_location("experiment_series_real", DRIVER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rows = module.read_order(module.ORDER_FILE)
    module.check_sample(rows)
    plan = module.planned_runs(rows)
    assert len(rows) == 12 and len(plan) == 24
    first = [c for _, _, c in plan[::2]]
    assert first.count("single") == 6 and first.count("multi") == 6
