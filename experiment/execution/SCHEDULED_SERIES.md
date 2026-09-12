# Scheduled MULTI series on the v1 sample

Label `main-v4prompt-v1`. Fixed before the series starts.

## Design

- Condition: MULTI only, with the current `multi-treatment.txt` and the
  orchestration gate, through the frozen `runner.py` (digest and
  `FREEZE_V4.json` checked before the first run).
- Sample and order: `preregistration/tasks-main.txt`, positions from
  `execution/run-order.tsv` (the `main-20260906` v1 sample).
- Comparison arms already on disk for the same 12 instances:
  SINGLE and MULTI-light from `main-20260906`; SINGLE and MULTI-model-directed
  from `main-model-directed-v1` (reconstructed patches).
- Limitation: SINGLE is not rerun. Same Claude Code version, model, effort and
  timeout, but run on another day, and the runner gained the gate and delegation
  checks in between.

## Session limit (amendment to "no automatic retry")

A run whose trace contains a `rate_limit_event` with status `rejected`, or a
result with `api_error_status` 429, was cut off by the subscription limit and is
infrastructure regardless of runner exit code:

1. its directory is moved unchanged to
   `runs/discarded-main-v4prompt-v1-session-limit/<instance>/multi-<UTC stamp>`;
2. the event is appended to `runs/main-v4prompt-v1/session-limit-events.tsv`;
3. the driver sleeps until the reported reset + 10 minutes and reruns the same
   instance; more than 8 such waits stop the series.

## Transient network at the reachability probe

Runner exit 50 whose `metadata.json` exception is "allow-listed host
unreachable" happened before inference (the preregistered meaning of 50 is
"discard this run … rerun the same instance"). The directory moves to
`runs/discarded-main-v4prompt-v1-network/`, the driver waits until
`api.anthropic.com` answers from the host (up to 15 minutes) and reruns; more
than 5 such retries stop the series. Host-side checks failing for minutes were
observed on 2026-09-11 around 18:30 UTC.

Every other non-zero runner exit stops the series as in `run_series.py`.
Discarded attempts are never analysed.

## Host sharing

Before the first run and after every limit wait, the driver waits while an
OpenCode pilot (`ocpilot-*` container or `run_v1_newprompt_series` process) is
active, polling every 5 minutes, up to 12 hours.

## After the series

`analyze_runs.py predictions --condition multi`, then
`swebench eval verified -r main-v4prompt-v1-multi -j 4`, then
`analyze_runs.py table`; the run directories are committed and pushed.

## Unattended start

`systemd/nir-multi-series.timer` fires at 2026-09-12 00:10 MSK (five-hour
window reset at 00:00 + 10 min), waking the machine if it is suspended, and starts `systemd/nir-multi-series.service`, which holds a
sleep inhibitor while the driver runs and schedules `shutdown -h +5` when it
ends, successfully or not.

Install (root):

```
sudo cp experiment/execution/systemd/nir-multi-series.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl start nir-multi-series.timer   # not enable: one-shot date
systemctl list-timers nir-multi-series.timer
```

Then suspend with `systemctl suspend`. Cancel: `sudo systemctl stop
nir-multi-series.timer`; abort a pending power-off: `sudo shutdown -c`.
Logs: `journalctl -u nir-multi-series` and
`runs/main-v4prompt-v1/scheduled-series.log`.
