# Orchestrator arm — probe findings and design decisions

Probes were run on the host CLI (2.1.263); the pinned runner version is 2.1.261.
Anything load-bearing must be re-confirmed in the container before a freeze.

## What was established

1. `--disallowedTools` is session-wide and reaches subagents.
   Probe A: the subagent reported "the Write tool is disabled at the session
   level (for subagents too)". Denying a tool to the orchestrator denies it to
   the team, so a plain denial cannot separate the two roles.

2. `--safe-mode` disables custom agents and workflows.
   `claude --help`: "Start with all customizations (CLAUDE.md, skills, plugins,
   hooks, MCP servers, custom commands and agents, output styles, workflows,
   custom themes, keybindings, and more) disabled". Probes E1-E3 and F1-F3 all
   carried `--safe-mode`, copied from the runner, so none of them could ever
   register a custom agent. Those six results say nothing about `--agents`.

3. With `--safe-mode` dropped, per-role tool sets do work.
   Probe H1: `orchestrator` and `worker` both register. H2: `--agent
   orchestrator` restricts the session's own tool set. H3: the orchestrator
   reported "I don't have file-write access", delegated, and the worker wrote
   the file. The mechanism is real and available if it is ever wanted.

## Decision: not used

Tools are NOT removed from the orchestrator. The constraint is carried by the
treatment text alone, and `--safe-mode` stays.

Consequences of keeping `--safe-mode`, which are the reason it stays:

  * the tested repository's own CLAUDE.md cannot enter the prompt;
  * user skills, plugins, hooks and custom commands cannot load;
  * workflows are unavailable, so deterministic orchestration is off the table.

Isolation already in place, verified 2026-09-07: `CLAUDE_CONFIG_DIR` points at a
per-run copy of `~/.claude-swebench`, which contains no CLAUDE.md, no skills, no
agents and no commands; `settings.json` there holds only theme and notification
preferences. The operator's personal `~/.claude` is a different directory and is
never mounted.

## Treatment as frozen for this arm

MULTI:  "You are the orchestrator of a team of subagents."
SINGLE: "You are working alone on this task."

One line each, delivered the same way (--append-system-prompt). The role framing
is the whole manipulation: no quota, no prohibition, no strategy advice and no
verification instructions, so nothing rides along with it that could explain a
difference on its own. SINGLE now gets a matched placebo, which the frozen arm
did not have.

The word "team" carries plurality implicitly rather than as a number. Since the
text no longer explains how to run subagents concurrently (several Task calls in
one message), an absence of parallelism cannot be read as a choice: the model may
simply not reach for it. Number of subagents and concurrency are outcomes here,
and that ambiguity is a property of the measurement, to be stated rather than
resolved after the fact.
