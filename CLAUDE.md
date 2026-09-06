# Verification

Run `.venv/bin/pytest --exitfirst --cov` from the repository root (the pytest
arguments used by `.github/workflows/pytest.yaml`). The inference tests also
need the optional `anthropic` dependency when `tiktoken` is installed.

Runner regressions: `.venv/bin/pytest tests/test_experiment_runner.py -q`.
These tests exercise the controller with simulated Docker/inference and real
temporary Git repositories. They do not replace validation on a dev task image.
