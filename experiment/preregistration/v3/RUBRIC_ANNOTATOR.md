# Task structure rubric

You are characterising the **structure of the work** in a software task: how
many genuinely different pieces of thinking it contains, how visible those
pieces are in advance, and how costly it would be to split the work between
two engineers.

Throughout, "a second engineer" means a competent colleague who cannot see
your screen, does not share your context, and has to be briefed in writing.
Judge by the shape of the work, not by any tool, product or workflow.

You are not solving the task. You are not proposing a fix.

## Two passes

Which pass you are in is stated in your instructions.

- **Pass 1** — you have the problem statement and the repository as it stands
  before the fix. You score `spec_clarity`, `discoverability`, `early_fanout`,
  `fanout_kind`, `env_risk`.
- **Pass 2** — you additionally have the accepted fix. You score `n_subtasks`,
  `independence`, `integration_cost`, `global_context`, `locality`,
  `difficulty_overall`, `investigation_volume`, `change_type`,
  `nonproduction_patch`, `unsolvable`.

## What does NOT count as splittable work

Read this before scoring anything. A task is **not** splittable merely because:

- the fix is large;
- many files change;
- one central root cause has to be propagated mechanically to several places;
- a simple final review could be handed to someone else.

Splittable work requires **at least two semantically different lines of
reasoning** — not the same reasoning applied twice, and not one line of
reasoning plus its own clerical consequences.

"There is nothing here to split" is a common, correct and expected answer.
Score each task on its own merits. There is no target distribution.

---

## Pass 1 features

### `spec_clarity` (0–2)
How well-defined is the required behaviour?

- **0** — ill-defined: the statement does not pin down what "fixed" means, or
  the expected behaviour is actively contested in the report.
- **1** — mostly clear; some intent has to be inferred from the code.
- **2** — clear and testable from the statement alone.

### `discoverability` (0–2)
Reading only the statement and the repository, how visible are two or more
distinct lines of work **before** any implementation starts?

- **0** — the statement points at a single thing; any "second line" would be an
  artificial split of one job.
- **1** — a second line exists but only becomes visible after substantial
  investigation, i.e. after the work is largely done.
- **2** — two or more distinct lines are apparent from the statement plus a
  shallow reading of the repository.

### `early_fanout` (0–2)
Could two or more of those lines be worked **concurrently**, without one's
result being needed to start the other?

- **0** — strictly sequential; line B is meaningless until line A lands.
- **1** — nominally parallel, but one line dominates, or the two would largely
  duplicate each other's reading.
- **2** — two or more lines are genuinely concurrent, and each produces
  something the other does not.

### `fanout_kind` (enum)
The dominant shape of those concurrent lines, if any:
`parallel-investigation` | `parallel-implementation` | `mixed` | `none`.

- `parallel-investigation` — two different questions must be answered (say,
  "where is the value lost" and "what does this public API promise"), and
  answering one does not answer the other.
- `parallel-implementation` — two separable pieces of code can be written at
  the same time against an interface that already exists.
- `mixed` — one investigation line and one implementation line.
- `none` — no genuinely concurrent lines.

### `env_risk` (true/false)
True when the main difficulty is environment or setup, an external service, a
dependency version, or repository-specific infrastructure — rather than the
code change itself.

### `p1_notes` (free text, at most 6 lines)
Name the concrete lines of work you scored. If you scored
`discoverability >= 1`, say what the second line actually is.

---

## Pass 2 features

### `n_subtasks` (0–2)
Semantically distinct intellectual subtasks in the accepted fix.

- **0** — one subtask, however many files it touches.
- **1** — two, but the second is mechanical or derivative of the first
  (propagating one decision, updating call sites, adding the obvious test).
- **2** — two or more that require genuinely different reasoning.

### `independence` (0–2)
Could two engineers work these subtasks without seeing each other's work?

- **0** — they must be co-designed; the interface between them is itself the
  problem.
- **1** — partially; a short written handoff would be enough.
- **2** — the interface between them already exists in the repository.

### `integration_cost` (0–2) — *higher is worse*
- **0** — the pieces merge trivially.
- **1** — the join needs care but is routine.
- **2** — the join is the hard part of the task.

### `global_context` (0–2) — *higher is worse*
How much whole-task context a second engineer must be handed to be useful.

- **0** — a short, local brief suffices.
- **1** — a substantial slice of the task has to be transferred.
- **2** — effectively the entire task has to be re-explained; splitting saves
  nothing.

### `locality` (0–2) — *higher means MORE local and linear*
- **0** — the solution spans distinct concerns in distinct places.
- **1** — mixed.
- **2** — one place, straight-line reasoning.

### `difficulty_overall` (0–4)
Total effort including investigation, as if solved from scratch by a competent
contributor who does not already know the answer. 0 = minutes, 4 = a long day.
Do **not** use the number of changed lines as the measure.

### `investigation_volume` (0–2)
How much of the work is *finding* rather than *writing*:
0 = the location is essentially given, 2 = locating the cause is most of the job.

### `change_type` (enum)
`bugfix` | `behavior-change` | `feature` | `refactor` |
`validation-error-message`

### `nonproduction_patch` (true/false)
True when the bulk of the accepted fix is documentation, generated files,
snapshots, formatting or a mass mechanical rewrite, and the real production
change is marginal.

### `unsolvable` (true/false)
True when the change depends on knowledge derivable from neither the
repository nor the statement — an undocumented external decision, an
unexplained magic constant.

### `p2_notes` (free text, at most 8 lines)
State the subtasks you counted and why the second one is, or is not, a
different kind of reasoning. Say explicitly whether your count survives the
"what does NOT count as splittable work" list above.
