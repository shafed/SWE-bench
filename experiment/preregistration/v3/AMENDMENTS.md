# v3 amendments and known limitations

Numbered deviations from the selection plan, and the properties of the final
sample that a reader has to know to interpret the result. All of this was
fixed before any SINGLE/MULTI run of the v3 sample.

## Amendment 1 — the extension draw exhausts the `hard` stratum

Plan section 8 says an under-filled category is topped up "in blocks of 10 by
the same method". After block 1 (40 candidates, annotated blind) the counts
were:

| category | block 1 |
| --- | --- |
| orchestration-friendly | 3 (fan-out 1, sequential 2) |
| orchestration-risky | 0 |
| single-friendly | 23 |
| borderline | 12 |
| excluded | 2 |

All 3 friendly candidates came from the `hard` difficulty bucket — 3 of 15
(20%) — and none from the 25 `easy` and `medium` candidates. Drawing further
blocks on the plan's 2:3:3 bucket cycle would have spent roughly 60% of each
block on strata with an observed friendly rate of zero.

The extension therefore appended **every remaining eligible `hard` instance**
(24 of them), in the same seeded order the base draw already used, via
`candidate_pool.py --extend-bucket hard`. The base 40 are unchanged and were
not redrawn.

This changes *which instances are annotated*. It does not touch the rubric, the
feature definitions, or the classification rules. The `hard` stratum of
SWE-bench Verified is now exhausted: 39 of 39 eligible hard instances are
annotated, so this question cannot recur within this population.

Result after the extension (64 candidates):

| category | total |
| --- | --- |
| orchestration-friendly | 5 (fan-out 2, sequential 3) |
| orchestration-risky | 2 |
| single-friendly | 30 |
| borderline | 25 |
| excluded | 2 |

## Amendment 2 — `MIN_FANOUT` relaxed from 3 to 2

Plan section 2 asks for "desirably 3" fan-out tasks out of the 5 friendly.
`match.py` originally hard-coded that as a requirement. The exhausted pool
contains exactly 2 fan-out tasks, so the requirement was relaxed to 2.

This is a relaxation of a *design target*, not of the rubric: no candidate's
scores changed, and no candidate was reclassified. The stratum that produces
fan-out tasks is exhausted, so the shortfall cannot be closed within
SWE-bench Verified.

The two fan-out tasks do represent different situations, as plan section 12
asks: `sympy__sympy-13852` is `mixed` (one investigation line + one
implementation line) and `sympy__sympy-13878` is `parallel-implementation`.
The third situation, `parallel-investigation`, is not represented.

## Terminology — `pipeline` renamed to `sequential`

The classifier's rule for a non-fan-out friendly task is simply "friendly and
not fan-out". Plan section 12 caps at 2 the friendly tasks whose main pattern
is `implementation ↔ testing/debug/review`, because the experiment must not
degenerate into a test of `single + reviewer`.

Calling the classifier's bucket `pipeline` would have made the sample look
like it violates that cap with 3. It does not: **none** of the three is the
reviewer pattern. Each is two dependent implementation lines —

- `astropy__astropy-13398` — attribute plumbing on `ITRS`, then a new
  topocentric transform module with refraction physics;
- `sphinx-doc__sphinx-7590` — literal-suffix regex correctness, then the
  representation of user-defined literals in the C++ domain;
- `sympy__sympy-18199` — the reported boundary case in `nthroot_mod`, then an
  unrequested composite-modulus algorithm (factorint + CRT + Hensel lifting).

So the cap is satisfied at 0, and the bucket is named `sequential`.

## Limitation 1 — friendly tasks are features, single-friendly tasks are bugfixes

All 5 orchestration-friendly tasks have `change_type == feature`. Of the 30
single-friendly tasks, 23 are `bugfix`, 5 are `feature`, 2 are
`behavior-change` — and the 5 features top out at `difficulty_overall == 3`.

This is a property of the population, not of the matcher: in SWE-bench
Verified, a task with two genuinely independent lines of reasoning is nearly
always the addition of two capabilities, while a task that is local and linear
is nearly always a single bug. Matching cannot remove it, because the pool
does not contain enough hard single-friendly *features* to pair against.

Consequence for interpretation: a MULTI advantage on the friendly arm is
confounded with a feature-vs-bugfix difference. The confound must be stated
whenever the paired comparison is reported. `change_type` is recorded per task
in `selection_v3.json` so the confound can at least be shown rather than
hidden.

## Limitation 2 — the single-friendly pool has a difficulty ceiling

`difficulty_overall` reaches 4 for two friendly tasks (`sympy__sympy-13878`,
`sympy__sympy-18199`) but only 3 among single-friendly tasks. Those two pairs
carry a forced difficulty gap of 1, which dominates their mismatch scores
(7.6 and 7.8 against 2.1–2.9 for the other three).

## Limitation 3 — repository concentration

The 12 selected tasks are sympy 5, django 4, sphinx 2, astropy 1. The plan's
soft ceiling of 3 per repository is exceeded for sympy and django. It is soft,
and `match.py` charges a penalty for it, but the exhausted hard stratum is
itself 21/39 django and 7/39 sympy, so a flatter mix was not available.

## Limitation 4 — annotator agreement was not measured

Every candidate was scored once per pass. There is no second independent
annotator and therefore no inter-annotator agreement figure.

The two-pass split demonstrably did work. Six of the 64 candidates looked
cleanly decomposable before the fix was visible — `discoverability == 2` and
`early_fanout == 2` in pass 1 — and only **two** of those six survived pass 2
with `n_subtasks == 2`:

| candidate | pass-1 read | pass-2 `n_subtasks` |
| --- | --- | --- |
| `sympy__sympy-13852` | two unrelated polylog issues | 2 — held |
| `sympy__sympy-13878` | 11 independent distribution CDFs | 2 — held |
| `django__django-11400` | two filter classes, two line numbers | 1 |
| `django__django-12708` | schema fix + autodetector optimisation | 0 |
| `django__django-14631` | two `BoundField` refactors | 0 |
| `mwaskom__seaborn-3069` | three independent Nominal-scale behaviours | 1 |

A one-pass procedure, or any procedure keyed on the gold patch's file spread,
would have taken all six. Four of them are the v1 failure mode exactly: the
issue text names several things, and the accepted fix turns out to be one line
of reasoning. That is the strongest single piece of evidence that the v1 sample
was mis-selected, and it is the reason pass-1 scores are frozen before the
patch is seen.

What remains unmeasured is "how often would a second annotator agree with
these scores".
