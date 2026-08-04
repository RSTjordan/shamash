#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""One work-shift on one job per invocation — the execution layer for work
that outlives a chat turn.

Why this exists: "an agent is working on it" is fiction unless something makes
it true — chat-turn work dies with the turn and nothing anywhere says so. A
job makes the sentence true by construction: it is a folder under jobs/<slug>/
with a spec (JOB.md), a handoff document (STATUS.md), and this runner
advancing it in bounded shifts on a schedule. A stalled job is visible (stale
STATUS.md); a failing job gets LOUD (a message per failure, auto-blocked after
two in a row).

Contract with the shift (prompts/job-shift.md): the shift rewrites STATUS.md
before it ends — "## Shift summary" is what the owner receives, verbatim. The
runner, never the shift, sends the message: one voice, no doubles, and a
shift that dies mid-work still produces a report (a failure one).

Invocation: the generic scheduler (state/schedule.json) runs this
periodically. Each tick runs at most ONE shift. No runnable job = heartbeat
line only, no model run, no cost.

    python scripts/job-runner.py            # normal tick
    python scripts/job-runner.py --dry-run  # show which job would run, do nothing
    python scripts/job-runner.py --job X    # force job X now (ignores gap/window)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config
import notify  # the single outbound path — never hand-roll a bridge POST

CFG = config.load()
ROOT = Path(CFG["root"])
JOBS_DIR = Path(CFG["paths"]["jobs"])
LOG_FILE = CFG["paths"]["logs"] / "jobs.log"
SHIFT_LOG_DIR = CFG["paths"]["logs"] / "jobs"
LOCK_FILE = CFG["paths"]["state"] / "job-runner.lock"
STATE_FILE = CFG["paths"]["state"] / "job-runner-state.json"
CLAUDE = CFG["claude_exe"]

DEFAULT_MAX_SHIFT_MINUTES = 45
DEFAULT_MIN_GAP_HOURS = 3.0
GRACE_MINUTES = 15  # past max_shift_minutes before the tree is killed
FAIL_STREAK_BLOCKS = 2  # consecutive failures before the job is auto-blocked
# Shifts run unattended, so they get the interactive allowlist plus the tools
# that only make sense for long autonomous work.
ALLOWED_TOOLS = CFG["allowed_tools"] + ",Agent,WebSearch,WebFetch,TodoWrite"
NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def log(line: str) -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().isoformat(timespec="seconds")
    with LOG_FILE.open("a", encoding="utf-8") as fh:
        fh.write(f"{stamp} {line}\n")


# ------------------------------------------------------------------ job files


def parse_job(job_dir: Path) -> dict | None:
    """JOB.md frontmatter + body. None if the file is missing or malformed."""
    path = job_dir / "JOB.md"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    m = re.match(r"\A---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not m:
        log(f"ERROR {path} has no frontmatter — skipped")
        return None
    meta: dict = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.lstrip().startswith("#"):
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    return {
        "slug": job_dir.name,
        "dir": job_dir,
        "status": meta.get("status", "active").lower(),
        "priority": int(meta.get("priority", 5) or 5),
        "target": meta.get("target", str(ROOT)),
        "max_minutes": int(meta.get("max_shift_minutes", DEFAULT_MAX_SHIFT_MINUTES)),
        "min_gap_hours": float(meta.get("min_gap_hours", DEFAULT_MIN_GAP_HOURS)),
        "window": meta.get("window", ""),
        "body": text[m.end():],
        "raw": text,
        "path": path,
    }


def set_job_status(job: dict, new_status: str) -> None:
    """Rewrite the status: line inside the frontmatter block only."""
    text = job["raw"]
    m = re.match(r"\A(---\s*\n)(.*?)(\n---\s*\n)", text, re.DOTALL)
    if not m:
        return
    front = re.sub(
        r"^status:.*$", f"status: {new_status}", m.group(2), count=1, flags=re.MULTILINE
    )
    job["path"].write_text(
        m.group(1) + front + m.group(3) + text[m.end():], encoding="utf-8"
    )


def in_window(window: str, now: datetime) -> bool:
    if not window:
        return True
    try:
        lo, hi = window.split("-")
        lo_h, lo_m = (int(x) for x in lo.strip().split(":"))
        hi_h, hi_m = (int(x) for x in hi.strip().split(":"))
    except ValueError:
        log(f"ERROR bad window {window!r} — treating as always-open")
        return True
    minutes = now.hour * 60 + now.minute
    return lo_h * 60 + lo_m <= minutes <= hi_h * 60 + hi_m


def read_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def write_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    os.replace(tmp, STATE_FILE)


def pick_job(now: datetime, state: dict, force: str | None = None) -> dict | None:
    if not JOBS_DIR.is_dir():
        return None
    candidates = []
    for d in sorted(JOBS_DIR.iterdir()):
        if not d.is_dir():
            continue
        job = parse_job(d)
        if job is None:
            continue
        if force:
            if job["slug"] == force:
                return job
            continue
        if job["status"] != "active":
            continue
        if not in_window(job["window"], now):
            continue
        last_end = state.get(job["slug"], {}).get("last_end")
        if last_end:
            gap_h = (now - datetime.fromisoformat(last_end)).total_seconds() / 3600
            if gap_h < job["min_gap_hours"]:
                continue
        candidates.append((job["priority"], last_end or "", job))
    if force:
        log(f"ERROR forced job {force!r} not found")
        return None
    if not candidates:
        return None
    # Lowest priority number first; among equals, the one idle longest.
    candidates.sort(key=lambda t: (t[0], t[1]))
    return candidates[0][2]


# --------------------------------------------------------------------- shift


def build_prompt(job: dict, now: datetime) -> str:
    # read_prompt renders the kit's {{TOKENS}}; the single-brace {PLACEHOLDERS}
    # below are per-shift runtime values and are substituted here.
    template = config.read_prompt("job-shift.md", CFG)
    status_path = job["dir"] / "STATUS.md"
    try:
        status = status_path.read_text(encoding="utf-8")
    except OSError:
        status = "(no STATUS.md yet — this is the first shift; create it)"
    return (
        template
        .replace("{NOW}", now.isoformat(timespec="seconds"))
        .replace("{SLUG}", job["slug"])
        .replace("{TARGET}", job["target"])
        .replace("{MAX_MINUTES}", str(job["max_minutes"]))
        .replace("{JOB_DIR}", str(job["dir"]))
        .replace("{JOB_SPEC}", job["body"].strip())
        .replace("{STATUS}", status.strip())
    )


def run_shift(job: dict, now: datetime) -> tuple[str, str]:
    """Run one bounded claude shift. Returns (outcome, detail) where outcome
    is 'ok' | 'failed' | 'timeout'."""
    if not CLAUDE:
        return "failed", "claude executable not found (set claude_exe in config.json)"
    SHIFT_LOG_DIR.mkdir(parents=True, exist_ok=True)
    shift_log = SHIFT_LOG_DIR / f"{job['slug']}-{now.strftime('%Y%m%d-%H%M')}.log"
    prompt = build_prompt(job, now)
    deadline = time.time() + (job["max_minutes"] + GRACE_MINUTES) * 60
    with shift_log.open("w", encoding="utf-8", errors="replace") as out:
        proc = subprocess.Popen(
            [
                CLAUDE, "-p",
                "--model", "claude-opus-5",
                "--allowedTools", ALLOWED_TOOLS,
            ],
            cwd=job["target"] if Path(job["target"]).is_dir() else str(ROOT),
            stdin=subprocess.PIPE,
            stdout=out,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=NO_WINDOW,
        )
        try:
            # The prompt goes through stdin: immune to the variadic
            # --allowedTools flag eating a trailing positional argument, which
            # silently discards the prompt and runs an empty session.
            proc.stdin.write(prompt)
            proc.stdin.close()
        except OSError as e:
            proc.kill()
            return "failed", f"stdin write failed: {e}"
        while proc.poll() is None:
            if time.time() > deadline:
                subprocess.run(
                    ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                    capture_output=True, creationflags=NO_WINDOW,
                )
                return "timeout", f"killed after {job['max_minutes']}m+{GRACE_MINUTES}m grace"
            time.sleep(20)
    if proc.returncode != 0:
        return "failed", f"exit {proc.returncode} — see {shift_log.name}"
    return "ok", shift_log.name


def shift_summary(job: dict, started: datetime) -> str | None:
    """The '## Shift summary' section of a STATUS.md rewritten this shift.
    None = the shift broke its contract (stale or missing status)."""
    status_path = job["dir"] / "STATUS.md"
    try:
        if status_path.stat().st_mtime < started.timestamp() - 5:
            return None
        text = status_path.read_text(encoding="utf-8")
    except OSError:
        return None
    m = re.search(r"^## Shift summary\s*\n(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL)
    if not m or not m.group(1).strip():
        return None
    return m.group(1).strip()


# ---------------------------------------------------------------------- lock


def take_lock() -> bool:
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(str(LOCK_FILE), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        return True
    except FileExistsError:
        try:
            pid = int(LOCK_FILE.read_text().strip())
        except (OSError, ValueError):
            pid = None
        if pid:
            probe = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                capture_output=True, text=True, creationflags=NO_WINDOW,
            )
            if "python" in (probe.stdout or "").lower():
                return False  # a real shift is in progress — normal, not an error
        # stale lock (crashed run): take over
        try:
            LOCK_FILE.unlink()
        except OSError:
            return False
        return take_lock()


def release_lock() -> None:
    try:
        LOCK_FILE.unlink()
    except OSError:
        pass


# ---------------------------------------------------------------------- main


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--job", help="force this job slug now (ignores gap/window)")
    args = ap.parse_args()

    now = datetime.now()
    state = read_state()
    job = pick_job(now, state, force=args.job)
    if job is None:
        log("tick: no runnable job")
        return 0
    if args.dry_run:
        print(f"would run: {job['slug']} (priority {job['priority']}, "
              f"max {job['max_minutes']}m)")
        return 0
    if not take_lock():
        log(f"tick: lock held — a shift is already running, skipping {job['slug']}")
        return 0
    try:
        log(f"shift start: {job['slug']}")
        started = now
        outcome, detail = run_shift(job, now)
        summary = shift_summary(job, started) if outcome == "ok" else None
        finished = datetime.now()
        minutes = (finished - started).total_seconds() / 60

        entry = state.get(job["slug"], {})
        entry["last_end"] = finished.isoformat(timespec="seconds")

        # Re-read the frontmatter — the shift may have set done/blocked itself.
        current = parse_job(job["dir"])
        new_status = current["status"] if current else job["status"]

        if outcome == "ok" and summary:
            entry["fail_streak"] = 0
            log(f"shift ok: {job['slug']} in {minutes:.0f}m ({detail})")
            icon = {"done": "✅", "blocked": "⛔"}.get(new_status, "🧰")
            head = {
                "done": f"{icon} *{job['slug']}* — job COMPLETE",
                "blocked": f"{icon} *{job['slug']}* — blocked, needs you",
            }.get(new_status, f"{icon} *{job['slug']}* — shift done ({minutes:.0f}m)")
            notify.notify(f"{head}\n\n{summary}")
        else:
            reason = detail if outcome != "ok" else "shift ended without updating STATUS.md"
            entry["fail_streak"] = entry.get("fail_streak", 0) + 1
            log(f"shift FAILED: {job['slug']} — {reason} (streak {entry['fail_streak']})")
            if entry["fail_streak"] >= FAIL_STREAK_BLOCKS and new_status == "active":
                set_job_status(job, "blocked")
                notify.notify(
                    f"⛔ *{job['slug']}* — {entry['fail_streak']} shifts failed in a row "
                    f"({reason}). I've paused the job (status: blocked) so it doesn't "
                    f"spin; say the word to resume once we've looked at logs/jobs/."
                )
            else:
                notify.notify(
                    f"⚠️ *{job['slug']}* — work shift failed ({reason}). "
                    f"Will retry next slot."
                )

        with (job["dir"] / "shifts.log").open("a", encoding="utf-8") as fh:
            fh.write(
                f"{started.isoformat(timespec='seconds')} → "
                f"{finished.isoformat(timespec='seconds')} {outcome} "
                f"status={new_status} {detail}\n"
            )
        state[job["slug"]] = entry
        write_state(state)
        return 0
    finally:
        release_lock()


if __name__ == "__main__":
    raise SystemExit(main())
