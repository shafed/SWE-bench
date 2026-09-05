# SWE-bench sample preregistration

## Population

Dataset: SWE-bench Verified.

Development instance `sympy__sympy-20590` is excluded because it was used to
debug the experimental pipeline.

No repository is excluded as a whole.

## Structural strata

Tasks are classified using the gold patch only as a pre-experiment structural
proxy.

Dispersion:

- L: exactly 1 production Python file;
- M: at least 2 production Python files, all in one directory;
- D: production Python files span at least 2 directories.

Test files are excluded when calculating these features.

## Difficulty split

Primary split:

- short: `<15 min fix` or `15 min - 1 hour`;
- long: `1-4 hours` or `>4 hours`.

Pre-registered fallback:

1. If every primary cell has at least 4 candidates:
   use 2 main + 2 reserve tasks per cell.
2. If every primary cell has at least 2 candidates but some have only 2–3:
   retain the primary split; select 2 main tasks and as many reserves as exist.
3. If any primary cell has fewer than 2 candidates:
   switch the whole design to:
   - easy: `<15 min fix`;
   - nontrivial: all other difficulty categories.
4. If the fallback still has a cell with fewer than 2 candidates:
   stop; do not modify the design after inspecting task identities.

The audit and split selection are executed by code, not manually.

## Sampling

There are 6 cells: L/M/D × low/high difficulty.

Select 2 main tasks from each cell = 12 tasks total.

Sampling is pseudorandom from sorted candidate lists. Seeds are tested starting
from 0. The first seed whose MAIN sample contains no more than 2 tasks from the
same repository is accepted.

Task identities and problem statements must not be inspected before the draw is
fixed.

## Reserves

Up to 2 reserve tasks are sampled per cell in the same draw.

A reserve can replace a main task only after a documented infrastructure
failure.

Replacement is always paired:

- if an instance is removed, both SINGLE and MULTI data for that instance are
  removed;
- the reserve instance is then run under both conditions.

Never retain SINGLE for one instance while replacing only MULTI, or vice versa.

## Infrastructure failure

Eligible for replacement:

- Docker/task image cannot be built or started;
- evaluator infrastructure fails;
- filesystem/container/runtime infrastructure fails;
- provider/network outage prevents inference from taking place.

Not eligible for replacement:

- Claude reaches the experimental task timeout;
- Claude exhausts its turn/token budget;
- Claude produces an empty or invalid patch;
- tests fail;
- SINGLE or MULTI fails to solve the task;
- MULTI makes a poor delegation decision.

Those are experimental outcomes.

Every infrastructure replacement must preserve the corresponding logs,
exit codes, or stderr as evidence.

## Freeze rule

After this preregistration is committed, sampling criteria, prompts, model,
Claude Code version, treatment and replacement rules must not be changed based
on observed experimental outcomes.
