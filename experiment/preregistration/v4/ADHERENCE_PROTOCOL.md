# v4 MULTI treatment-adherence protocol

Status: frozen before the v4 main series.

This protocol is a manipulation check for the MULTI condition. It is not an
outcome filter: a run is never retried, removed, or replaced merely because it
violates the treatment. Adherence is reported alongside quality and resource
outcomes.

## Unit and evidence

The unit is one MULTI run. Coding uses the task statement, repository state,
`trace.jsonl`, `metrics.json`, `metadata.json`, `patch.diff`, and preserved git
status artefacts. Gold patches and official evaluator outcomes must not be used
while coding adherence.

The coder may know the instance and that the run is MULTI; that cannot be
blinded because delegation is visible. To reduce outcome bias, adherence should
be coded before consulting resolved/unresolved status whenever operationally
possible.

Every non-automatic judgement must cite concrete evidence: trace event/tool-call
indices and, when relevant, file paths or patch hunks. If the evidence cannot
support a judgement, record `unclear` rather than inferring compliance.

## Frozen checks

### A0 — completed delegation (automatic)

`pass` when `subagent_stats.completed >= 1`; otherwise `fail`.

This is the runner's minimum mechanical check only. A0 alone does not establish
that the workstream-oriented treatment was followed.

### A1 — delegation before production-code change

`pass` when the parent issues the first substantive implementation delegation
before its first production-code modification.

Repository inspection, read-only commands, reasoning, and test execution before
delegation are allowed. A production-code modification means a write/edit to a
tracked non-test implementation file, or a shell command whose observable effect
modifies such a file. If the trace does not make the ordering defensible, record
`unclear`.

### A2 — implementation delegation, not ceremonial delegation

`pass` when at least one delegation owns substantive implementation work.
Delegations whose sole purpose is review, testing, summarisation, or validation
do not satisfy A2.

### A3 — workstream coverage

First identify the materially distinct implementation workstreams that are
visible from the task and repository without using the gold patch. A workstream
is materially distinct when it requires a separable implementation decision or
change, not merely mechanical propagation of the same edit.

Code:
- `pass`: every materially distinct workstream that can be meaningfully
  separated is delegated;
- `fail`: at least one clearly separable substantive workstream is retained by
  the parent without delegation;
- `na`: the task genuinely has one substantive implementation workstream and
  that workstream is delegated;
- `unclear`: the workstream boundary cannot be defended from the available
  evidence.

Dependency does not by itself justify collapsing two substantive workstreams;
dependent workstreams may be delegated sequentially.

### A4 — parallel fan-out when independence exists

First decide whether two or more delegated substantive workstreams can proceed
independently at the point of delegation.

Code:
- `pass`: independent workstreams are launched so that their execution overlaps
  rather than waiting for one to finish before starting the other;
- `fail`: clearly independent workstreams are unnecessarily serialized;
- `na`: no pair of substantive workstreams can proceed independently;
- `unclear`: concurrency/independence cannot be established from the trace.

Do not infer parallelism from subagent count alone.

### A5 — delegation preserves subagent solution independence

`pass` when delegation prompts provide objective, relevant repository context
and scope, constraints, acceptance criteria, and any repository findings needed
for a self-contained task, while leaving solution design and implementation
choices to the subagent.

`fail` when the parent effectively supplies a completed implementation plan or
step-by-step solution such that the subagent is reduced to transcription.
Ordinary architectural context, discovered constraints, file locations, and
observed repository facts are allowed.

### A6 — parent review/integration after delegated work

`pass` when, after delegated work returns, the parent substantively inspects the
returned findings and/or changes and takes responsibility for integrating or
accepting them. A bare acknowledgement with no inspection when changes require
integration is `fail`. If the delegated work is already directly present in the
shared working tree, inspection of the resulting diff/files counts as review.

### A7 — parent final verification

`pass` when the parent performs a final verification step after integration,
such as relevant tests, targeted reproduction, or direct inspection adequate to
check the integrated solution. Verification performed only by a subagent does
not satisfy A7. If infrastructure makes verification impossible, record
`unclear` and cite the reason rather than treating it as adherence failure.

## Overall adherence label

The frozen overall label is derived as follows:

- `full`: A0, A1, A2, A5, A6 and A7 are `pass`, and A3/A4 are `pass` or `na`;
- `clear_violation`: any of A0, A1, A2, A3, A4, A5 or A6 is `fail`;
- `unclear`: no required check is `fail`, but at least one required check is
  `unclear`;
- A7 alone being `unclear` because verification was technically impossible does
  not convert an otherwise full run to `clear_violation`; it yields `unclear`.

No adherence label changes the primary intention-to-treat comparison. The
primary comparison includes every measured run. Adherence may be described as a
process result and used in qualitative interpretation, but not as a post-hoc
basis for excluding inconvenient outcomes.

## Coding record

Use `adherence-template.tsv`. One row is completed for every MULTI main run.
Free-text `evidence` must identify the trace/tool-call evidence supporting the
judgements. The coding vocabulary and overall-label rule above are frozen and
must not be changed after main outcomes are inspected.
