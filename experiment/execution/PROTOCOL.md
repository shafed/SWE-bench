# Execution protocol

## Fixed sample

12 frozen SWE-bench Verified main instances from the v3 orchestration-suitability
selection: 5 `orchestration-friendly`, 5 matched `single-friendly`, and 2
`orchestration-risky` tasks. The frozen selection is recorded in
`../preregistration/v3/selection_v3.json` and `../preregistration/v3/tasks-main.txt`.

Each instance is evaluated under both conditions.

## Conditions

SINGLE:
- Claude Code 2.1.261
- model: claude-sonnet-5
- Task disallowed
- WebFetch and WebSearch disallowed

MULTI:
- Claude Code 2.1.261
- orchestrator model: claude-sonnet-5
- subagent model: claude-sonnet-5
- Task available
- at least one completed delegation required by treatment instruction
- WebFetch and WebSearch disallowed

A MULTI run with zero completed delegations is a protocol violation. The model
still decides what to delegate, how many delegations to make beyond that
minimum, and whether to use subagents sequentially or in parallel.

## Resource policy

- one run per condition per instance
- wall-clock timeout: 45 minutes per inference
- no max-turn limit
- no experiment-imposed token limit
- token use, turns, tool calls, subagent calls and wall time are outcomes
- timeout under otherwise functioning infrastructure is an experimental result

## Isolation

- clean SWE-bench task image for every condition
- separate Claude profile
- --safe-mode
- no external web access
- inference runs as nonroot
- patch collection occurs after inference as root
- official SWE-bench evaluator is used unchanged

## Ordering

Task order and within-pair condition order are randomized before any main
inference.

Exactly 6 instances are SINGLE-first and 6 are MULTI-first.

The generated order is frozen before inference.

## Retries

No automatic retry.

Infrastructure failures are logged and handled according to the preregistered
paired-replacement protocol.

Agent timeout, exhausted reasoning, bad solution, empty patch, failing tests or
MULTI protocol violation are experimental outcomes and are not retried.
