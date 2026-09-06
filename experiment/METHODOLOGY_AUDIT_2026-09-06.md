# Methodology audit — 2026-09-06

This note records issues found during a methodological audit of the frozen SINGLE vs MULTI experiment before the main series.

## 1. Critical: external network access is not actually isolated

The execution protocol says that external web access is disabled, and Claude Code is started with `WebFetch` and `WebSearch` disallowed. However, `runner.py` currently has:

```python
PROXY_ENV = {}
DOCKER_NETWORK = None
```

The runner itself also warns that with this configuration the agent can still use Bash to access GitHub/PyPI and could potentially retrieve the upstream fix.

### Why this matters

Disabling Claude Code web tools is not equivalent to blocking network egress from the task container. If Bash can access arbitrary external hosts, a run may obtain information that is unavailable in the intended benchmark environment. For SWE-bench this creates a contamination/leakage risk and means the implemented environment does not match the declared protocol.

### Required fix before main inference

Enforce network egress at the container/network layer. The agent must retain only the connectivity required for Claude inference/authentication, while arbitrary access to GitHub, package indexes, search engines and other external sites is blocked.

After changing this, validate the runner only on the excluded development instance and freeze a new runner digest/amendment before main inference.

## 2. Methodological gap: failure-analysis categories are not preregistered in the experiment repository

The experiment already preserves trajectories, patches, tool calls and subagent activity, but the manual qualitative analysis scheme for failed runs is not yet frozen in this repository.

The planned categories are:

- **context / delegation error** — the orchestrator omits important information, formulates the delegated task incorrectly, or otherwise gives the subagent insufficient relevant context;
- **subagent solution error** — sufficient relevant context was available, but the subagent chose or implemented an incorrect local solution;
- **integration / verification error** — the subagent result is locally correct, but the orchestrator applies or integrates it incorrectly, or fails to detect a regression;
- **technical / infrastructure failure** — tool, runtime, provider or environment failure unrelated to the substantive solution;
- **ambiguous / unclassifiable** — evidence is insufficient to assign one category confidently.

Primary manual analysis should cover all failed runs. A small sample of successful runs may be inspected as a comparison/control for trajectory patterns.

### Why this matters

If the categories are defined only after observing main results, the qualitative failure analysis becomes vulnerable to post-hoc interpretation. The taxonomy and decision rules should therefore be frozen before inspecting main-series outcomes.

### Required fix before main inference

Add and freeze a separate failure-analysis protocol with explicit decision rules and an `ambiguous` category. Do not alter those rules in response to observed main results.

## 3. Interpretation issue: MULTI measures mandatory use, not mere availability of subagents

`multi-treatment.txt` requires at least one completed delegation and instructs the orchestrator to use the returned information. Therefore the experiment does **not** estimate the effect of merely making subagents available. It estimates the effect of a harness condition in which at least one subagent delegation is mandatory.

This is not a runner bug, but the research question, hypothesis and final report must use wording consistent with the implemented treatment.

## 4. Reproducibility gap: harness disclosure is distributed across several files

The relevant harness configuration is currently split across `experiment/preregistration/PROTOCOL.md`, `experiment/execution/PROTOCOL.md`, `RUNNER_AMENDMENT.md`, `runner.py`, the prompt template and treatment file.

This is not a validity failure, but a compact Harness Card would make the experiment easier to audit and reproduce. It should summarize at least:

- Execution: Docker/runtime, timeouts, task image, filesystem/network policy;
- Tool: available/disallowed tools and error behavior;
- Context: prompt construction, profile isolation, subagent context/delegation contract;
- Scheduling: agent loop constraints, retries, stopping, mandatory delegation in MULTI;
- Observability: traces, metrics, patches, tool/subagent logs;
- Verification: official SWE-bench evaluation and patch collection;
- Governance: permissions, safe mode, network and side-effect boundaries.

This item is recommended rather than blocking by itself.

## Status

Do not start the main series until items 1 and 2 are resolved and frozen. Item 3 must be reflected consistently in the written methodology. Item 4 is recommended for reproducibility and reporting quality.
