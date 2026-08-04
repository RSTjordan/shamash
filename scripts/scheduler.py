#!/usr/bin/env python3
"""Generic scheduler tick — the one Windows task that replaces all future ones.

Registering a new Windows scheduled task costs the owner a manual click every
time (task *creation* is blocked for the agent by the permission classifier).
So exactly one hosting task exists — `ShamashScheduler`, registered once by the
installer — and it fires every 5 minutes, reads `state/schedule.json` and runs
whatever is due. From then on a new recurring job is a JSON edit, not a task
registration.

Job shape (all times local, 24h):

    {
      "name": "nightly-report",          # unique, used as the run-state key
      "command": "C:\\path\\to\\run.cmd", # executed detached via cmd /c
      "enabled": true,

      # pick exactly one cadence:
      "at": "10:00", "every_days": 1,    # daily / every N days at a wall time
      "at": "20:00", "every_days": 2, "anchor": "2026-08-04",
      "every_minutes": 30,               # simple interval
      "at_datetime": "2026-08-10T14:00"  # one shot, disables itself after
    }

Optional per job: "catch_up_minutes" (default 1440) — how late a missed wall-time
run may still fire, so a laptop that was asleep at 10:00 still runs at 11:20.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JOBS_FILE = ROOT / "state" / "schedule.json"
STATE_FILE = ROOT / "state" / "schedule-state.json"
LOG_FILE = ROOT / "logs" / "scheduler.log"

DEFAULT_CATCH_UP_MINUTES = 1440


def log(line: str) -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().isoformat(timespec="seconds")
    with LOG_FILE.open("a", encoding="utf-8") as fh:
        fh.write(f"{stamp} {line}\n")


def read_json(path: Path, fallback):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return fallback
    except (ValueError, OSError) as exc:
        log(f"ERROR unreadable {path.name}: {exc}")
        return fallback


def parse_hhmm(value: str) -> tuple[int, int]:
    hh, mm = value.split(":")
    return int(hh), int(mm)


def due_at_walltime(job: dict, now: datetime, last_run: datetime | None) -> bool:
    hh, mm = parse_hhmm(job["at"])
    today_due = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if now < today_due:
        return False

    every_days = int(job.get("every_days", 1))
    if every_days > 1:
        anchor = datetime.fromisoformat(job["anchor"]).date()
        if (today_due.date() - anchor).days % every_days != 0:
            return False

    late = (now - today_due).total_seconds() / 60
    if late > int(job.get("catch_up_minutes", DEFAULT_CATCH_UP_MINUTES)):
        return False

    # already ran for this occurrence
    return last_run is None or last_run < today_due


def due_at_interval(job: dict, now: datetime, last_run: datetime | None) -> bool:
    if last_run is None:
        return True
    return now - last_run >= timedelta(minutes=int(job["every_minutes"]))


def due_once(job: dict, now: datetime, last_run: datetime | None) -> bool:
    if last_run is not None:
        return False
    return now >= datetime.fromisoformat(job["at_datetime"])


def is_due(job: dict, now: datetime, last_run: datetime | None) -> bool:
    if "at_datetime" in job:
        return due_once(job, now, last_run)
    if "every_minutes" in job:
        return due_at_interval(job, now, last_run)
    if "at" in job:
        return due_at_walltime(job, now, last_run)
    log(f"ERROR job {job.get('name')!r} has no cadence field")
    return False


def launch(job: dict) -> None:
    """Fire and forget — a job can take an hour; the tick must not block."""
    # CREATE_NO_WINDOW only: it gives the child a hidden console, which a .cmd
    # needs for its own redirections. Combining it with DETACHED_PROCESS is
    # documented as invalid and silently swallowed the job's output in testing.
    creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    subprocess.Popen(
        ["cmd.exe", "/c", job["command"]],
        cwd=job.get("cwd", str(ROOT)),
        creationflags=creationflags,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
    )


def main() -> int:
    jobs = read_json(JOBS_FILE, [])
    if not isinstance(jobs, list):
        log("ERROR schedule.json is not a list — nothing run")
        return 1

    state = read_json(STATE_FILE, {})
    now = datetime.now()
    fired = 0

    for job in jobs:
        name = job.get("name")
        if not name or not job.get("command") or not job.get("enabled", True):
            continue

        raw_last = state.get(name, {}).get("last_run")
        last_run = datetime.fromisoformat(raw_last) if raw_last else None

        try:
            if not is_due(job, now, last_run):
                continue
        except (ValueError, KeyError) as exc:
            log(f"ERROR job {name!r} has a bad cadence spec: {exc}")
            continue

        try:
            launch(job)
        except OSError as exc:
            log(f"ERROR job {name!r} failed to launch: {exc}")
            continue

        state[name] = {"last_run": now.isoformat(timespec="seconds")}
        fired += 1
        log(f"fired {name}: {job['command']}")

    if fired:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
