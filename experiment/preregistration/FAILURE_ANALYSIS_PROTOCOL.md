# Failure-analysis preregistration

Qualitative coding scheme for the SINGLE vs MULTI runs. Frozen before any
main-series outcome is inspected. Categories, decision rules and the control
sample are fixed here so that the coding cannot be shaped by the results it is
applied to.

## Unit of analysis

One coded unit is one run: an (instance, condition) pair. SINGLE and MULTI runs
of the same instance are coded independently, never as a comparison.

## Which runs are coded

Primary: every failed run in both conditions.

A run is failed when the official SWE-bench evaluation does not resolve the
instance. This includes runs that timed out, produced an empty or invalid
patch, or exited non-zero. Exit code 20/40 runs replaced under the
preregistered infrastructure rule are not coded; their replacements are.

Control: 4 resolved runs, so that trajectory patterns found in failures can be
checked against runs that worked. Selected before coding begins by a fixed
rule: sort resolved runs by instance id, then take every k-th run
(k = floor(n_resolved / 4)) starting from the first. No discretionary choice.

## Evidence

Coding uses only preserved run artefacts: `trace.jsonl`, `patch.diff`,
`metadata.json`, `git-status.txt`, `untracked-files.txt`, the evaluation
report, and for MULTI the delegation tool calls and subagent activity. Every
assignment records at least one concrete citation (trace event index, tool call,
or patch hunk). An assignment with no citable evidence is `ambiguous`.

The coder cannot be blinded to condition: delegation calls are visible in the
trace. This is stated rather than claimed away. Blinding to the eventual
resolved/unresolved status is also infeasible, since the status determines
which runs are coded at all.

## Categories

Exactly one primary category per run. Contributing secondary categories may be
recorded, but every reported count uses primary categories only.

1. **context / delegation error** — the orchestrator omits information it had,
   states the delegated task incorrectly, or otherwise gives the subagent
   insufficient relevant context.
2. **subagent solution error** — sufficient relevant context was available, but
   the subagent chose or implemented an incorrect local solution.
3. **integration / verification error** — the subagent result is locally
   correct, but the orchestrator applies or integrates it incorrectly, or fails
   to detect a regression.
4. **technical / infrastructure failure** — tool, runtime, provider or
   environment failure unrelated to the substantive solution.
5. **ambiguous / unclassifiable** — evidence is insufficient to assign one
   category confidently.

### SINGLE runs

Categories 1–3 are written in terms of an orchestrator and a subagent, which
exist only in MULTI. SINGLE failures are coded with the same numbering against
the single agent's own trajectory, so that counts remain comparable:

1. the agent proceeds from an incorrect or incomplete reading of the problem or
   the code it had available (the analogue of misstated context);
2. the agent's context was adequate, but the implemented solution is incorrect;
3. the implementation was locally correct, but the agent integrated it
   incorrectly or failed to detect a regression it could have observed;
4. and 5. as above.

A count in category 1 or 3 therefore means something structurally different in
each condition. Report per-condition counts; do not present the difference as
a single effect on "delegation errors".

## Decision rules

Applied in order. The first rule that fires assigns the category.

1. If `metadata.json` records a controller, provider or runtime failure, or the
   trace ends in a tool/environment error unrelated to the solution, assign
   **4**. A timeout is not by itself category 4: it is an experimental outcome,
   coded by what the trajectory was doing when it ran out.
2. If the run produced no patch and the trace shows no substantive attempt at
   the task, assign **4** if an error explains it, otherwise **5**.
3. MULTI only: if a delegation occurred and the delegated instruction omits or
   misstates information present in the orchestrator's own context, assign
   **1**. The omission must be citable in the delegation call.
4. MULTI only: if the delegated instruction was adequate and the returned
   result is itself incorrect, assign **2**.
5. If the returned or produced solution was locally correct and the failure
   arises in how it was applied, combined with other edits, or verified,
   assign **3**.
6. Otherwise, if the substantive solution is incorrect, assign **2**.
7. If none of the above can be established from the evidence, assign **5**.

Runs where two categories are equally supported are assigned **5**, not the
more interesting one.

## Freeze rule

These categories, decision rules, the control-sample rule and the citation
requirement must not be changed after any main-series outcome has been
inspected. If coding reveals a genuinely unanticipated failure mode, it is
reported as such in the narrative and coded **5**; a new category is not added
to the frozen scheme after the fact.
