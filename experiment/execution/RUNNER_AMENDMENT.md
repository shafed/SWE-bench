# Runner amendments before the v4 main series

This file is a historical record of runner-level changes discovered during
development and validation. It is **not** the source of truth for the current
v4 treatment. Current execution semantics are defined by `PROTOCOL.md`,
`HARNESS_CARD.md`, `multi-treatment.txt`, the runner, and the frozen v4
preregistration files.

All validation mentioned here used excluded development instances or historical
pre-v4 runs. Historical v1/v3 run artifacts are not part of the v4 main series.

## Conditions and effort

- Claude Code is pinned to `2.1.261` and the solving model to
  `claude-sonnet-5`.
- Both conditions request `--effort high` and set
  `CLAUDE_CODE_EFFORT_LEVEL=high`.
- MULTI pins subagents to `claude-sonnet-5` with
  `CLAUDE_CODE_SUBAGENT_MODEL`.
- SINGLE receives no appended placebo; only MULTI receives
  `multi-treatment.txt`.
- Both conditions use `--safe-mode`, the same wall-clock limit, and no
  experiment-imposed turn or token budget.

## Token accounting amendment

Primary resource fields are `metrics.json.token_accounting.totals`:

- `input_tokens`;
- `cache_read_input_tokens`;
- `cache_creation_input_tokens`;
- `output_tokens`;
- `total_tokens`, the sum of those four disjoint categories.

The source is the last cumulative `result.modelUsage` snapshot, summed across
reported models. Repeated result snapshots are not added together. Per-model
records are retained. Missing or invalid usage produces null totals rather than
zero. Timeouts, error results, parse errors, or usage-bearing activity after the
last result make the available accounting partial; such runs remain in the
quality analysis.

`result.num_turns` is recorded but not used as the comparative process measure
because dev traces showed it does not represent MULTI sessions consistently.
The process measure used for comparison is `unique_assistant_messages`.

## Patch and authentication handling

The evaluator receives `git add -A` followed by
`git diff --cached <base> --binary`, so new files and agent commits are included.
At timeout the filesystem is preserved for collection; timeout remains an
experimental outcome.

Each run uses a separate copy of the Claude profile. Refreshed credentials are
returned atomically to the original dedicated profile; run history/settings are
not copied back. A profile lock prevents concurrent refresh races. Credential
synchronization failure is infrastructure, not an experimental failure.

## Network-isolation amendment

Early validation showed that disabling `WebFetch` and `WebSearch` did not block
Bash/network access. The task container therefore runs on an internal Docker
network whose only external route is the experiment squid allow-list proxy.
Repository/package hosts such as GitHub, raw GitHub and PyPI are blocked while
provider/authentication hosts required by Claude Code remain reachable.

Per-run probes record the blocked hosts as unreachable and
`api.anthropic.com` as reachable. A reachable blocked host is a configuration
violation rather than a measured result. The live proxy is stamped with a digest
of its config/allowlist so a stale parsed configuration cannot silently survive
a file change.

The claim is no runtime retrieval of the upstream repository/fix, not zero
network access. This does not remove benchmark memorization risk in model
weights.

## Snapshot completeness amendment

Observed MULTI traces can contain non-usage system housekeeping events after the
final cumulative result. Those events do not invalidate token accounting.
Completeness therefore distinguishes all trailing events from trailing
usage-bearing events; timeout/error/parse failures or usage-bearing activity
after the final result still make the snapshot partial.

## Series-driver and analysis amendment

`run_series.py` executes the frozen order sequentially, refuses sample/order
mismatch, skips existing run directories rather than overwriting them, and
stops the series on non-zero runner exits that require a preregistered human
decision.

`analyze_runs.py` was fixed before v4 main outcomes: exact McNemar is used for
paired resolution and exact paired sign-randomization for resource differences.

## Authentication reachability amendment

Validation found that an expired OAuth token requires `platform.claude.com`.
That Anthropic authentication host was added to the allow-list. The runner also
distinguishes a provider/authentication failure that prevents inference from an
agent that actually ran and produced a bad solution; only the former is treated
as infrastructure.

## v4 orchestration treatment — authoritative current state

A local experimental branch briefly used a **minimal** mandatory-delegation
prompt that left decomposition, subagent count, scheduling and integration
entirely to the lead agent. That prompt is historical and **superseded**. It must
not be used for the v4 main series.

The frozen v4 construct is **mandatory workstream-oriented orchestration**:

- before production-code changes, the parent may inspect the task/repository as
  deeply as needed to identify substantive implementation workstreams and their
  dependencies;
- every substantive implementation workstream that can be meaningfully
  separated is delegated;
- independent workstreams are delegated to separate subagents in parallel;
- distinct dependent workstreams are delegated sequentially as prerequisites
  become available;
- if the task genuinely contains one substantive implementation workstream,
  one implementation delegation is sufficient;
- review-only, test-only, confirmation-only, or post-hoc ceremonial delegation
  does not satisfy the treatment;
- delegation may include relevant repository context/findings, while solution
  design and implementation choices remain with the subagent;
- the parent owns review, integration, conflict resolution, and final
  verification.

The authoritative wording is `multi-treatment.txt`. The v4 adherence protocol
(A0–A7) in `../preregistration/v4/ADHERENCE_PROTOCOL.md` was written for this
workstream-oriented treatment.

## Live orchestration gate

The merged runner contains a MULTI-only admin-managed hook gate:
`orchestration_gate.py` plus `orchestration-gate-settings.json`.

The gate records `SubagentStart` and `Stop` events. A Stop attempt is blocked
until at least one real subagent start has been observed. This is a **minimum
mechanical aid**, not proof of full compliance. It does not enforce A1–A7 and it
cannot make late ceremonial delegation compliant. If a model solves first and
delegates only after a rejected Stop, the run remains in the primary
intention-to-treat analysis but is coded non-compliant from the trajectory.

## Final v4 freeze

The machine-checkable source is `FREEZE_V4.json`. It pins the current runner,
runner digest file, series driver, freeze verifier, MULTI treatment, live gate
code/settings, common prompt, v4 sample/order, analyzer, network configuration,
and preregistered adherence/failure-analysis files.

`run_series.py` invokes `verify_freeze.py` before reported v4 main inference and
also checks `runner.sha256`. The validation-only bypass must never be used for a
reported main run.
