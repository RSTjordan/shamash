# Jobs — recurring work beyond the digest

A **job** is anything you want to happen on a schedule that isn't the twice-daily
scan: a report on a business, a watcher for a price, a Friday summary of a group.

The rule: **jobs are opt-in, and they never enter the kit.** The kit ships the
machinery and one example. What you actually run is yours, lives in the
gitignored `jobs/` directory, and is nobody else's business — literally.

## Why not Windows scheduled tasks per job

Because then every new job means registering a task, which means an admin
prompt, a `.cmd` wrapper and a `.vbs` to hide the console window — three files
and a UAC dialog to answer a question like "remind me about X on Fridays".

So there is **one** scheduled task, a small always-on scheduler, and jobs are
rows in a JSON file. Adding a job becomes editing a file — or just asking your
assistant to add it, which is the point.

## Anatomy of a job

```
jobs/
  weekly-report.md          ← the prompt: what to do, in plain language
state/schedule.json         ← when to run it
```

```json
{
  "jobs": [
    {
      "name": "weekly-report",
      "prompt": "jobs/weekly-report.md",
      "cron": "0 17 * * 5",
      "enabled": true
    }
  ]
}
```

The prompt is an ordinary instruction file — the same kind of thing you'd type
into the chat, written down once. It has the same tools and the same brief as
any other run.

## Rules a job must follow

1. **Reach the user through `scripts/notify.py`.** Never hand-roll a bridge
   POST, and never treat HTTP 200 as delivered — a send counts only once the
   message shows up in that bridge's database. This is not pedantry: a watcher
   that ignored it once announced something at 00:35 into a channel nobody was
   reading, and it went unseen for seven hours.
2. **Be idempotent.** A job may run twice — after a reboot, after a catch-up.
   Log what you did to `state/actions.jsonl` with a stable key and check it
   before acting.
3. **Say nothing when there is nothing to say.** A job that reports "no change"
   every hour trains its reader to ignore it, and then it fails to be read on
   the day it matters.
4. **Never assume the contact channel exists.** Many installations run without
   a second number.

## Adding one

Ask your assistant: *"every Friday at 5, summarise what happened in the work
group this week and send it to me."* It writes the prompt file, adds the
schedule row, and tells you what it created. No task registration, no restart.

Or write the two files yourself. The scheduler picks up changes on its own.
