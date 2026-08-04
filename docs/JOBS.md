# Jobs and schedules — how work happens when you're not talking to it

Two different machines, often confused. Get the distinction and everything
else follows:

- **The schedule** (`state/schedule.json`) fires *commands* at times — the
  scans, the job-runner tick, anything else. It knows nothing about content.
- **A job** (`jobs/<slug>/`) is a *long-running project* with its own state,
  advanced in bounded work-shifts by the job-runner. It knows nothing about
  time — the schedule fires the runner, the runner picks the job.

Both live in gitignored directories: what you run is yours and never enters
the kit.

## The schedule — `state/schedule.json`

A top-level **JSON list** (not an object — the scheduler refuses anything
else, loudly in `logs/scheduler.log`, and then runs NOTHING, so treat this
file with respect). Each entry:

```json
[
  {"name": "morning-scan", "command": "C:\\path\\to\\scripts\\run-scan.cmd",
   "at": "08:00", "every_days": 1, "enabled": true},
  {"name": "job-runner", "command": "C:\\path\\to\\scripts\\run-job-runner.cmd",
   "every_minutes": 30, "enabled": true}
]
```

Exactly one cadence per entry: `at` (+ optional `every_days` and `anchor`
date for every-N-days runs) · `every_minutes` · `at_datetime` (one shot,
then it disables itself). Optional `catch_up_minutes` (default 1440) lets a
run missed while the machine slept still fire late. There is **no cron
syntax**. The `command` runs via `cmd /c` from the repo root. Run state
lives in `state/schedule-state.json`; the tick itself is the
`ShamashScheduler` Windows task, every 5 minutes.

Rules for anything you schedule: be idempotent (a run may fire twice after a
catch-up — key your actions in `state/actions.jsonl` and check before
acting); say nothing when there is nothing to say; reach the owner only
through `scripts/notify.py`; never assume the contact channel exists.

## A job — `jobs/<slug>/`

Created by asking your assistant to take on something multi-day ("take the
ball on X"). It writes two files:

- **`JOB.md`** — frontmatter (`status: active|paused|blocked|done`,
  `priority` (1 = first), `target` (the repo/folder the work happens in),
  `max_shift_minutes`, `min_gap_hours`, optional `window` like
  `08:00-23:00`) and then the goal, definition of done, and constraints.
- **`STATUS.md`** — the handoff document. Every shift reads it first and
  rewrites it last: Shift summary (what you get sent), Done so far, Next
  steps, Blockers.

Every 30 minutes the runner picks the single highest-priority runnable job
and runs ONE bounded work-shift on it. The runner — never the shift itself —
sends you a WhatsApp message with each shift's summary. A shift that fails
tells you; two failures in a row and the job sets itself to `blocked` and
tells you that too. `shifts.log` in the job folder is the history.

Steering costs one sentence in the chat: "pause the X job", "make Y the
priority", "what's happening with Z" — the agent edits the job files or
reads STATUS.md and answers. To force a shift right now:
`py -3 scripts\job-runner.py --job <slug>`.

## What this costs

A shift is a full Claude session (the model set by `"model"` in
`config.json`) for up to `max_shift_minutes`. An always-active job at the
default 45-minute shifts and 3-hour gaps can spend several model-hours a
day. The digest reports every job's state — nothing burns silently — but
set `min_gap_hours` with your plan in mind, and `paused` is always free.
