#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shamash doctor: one pasteable plain-text report of everything checkable
without touching WhatsApp itself.

Run it whenever something feels wrong, and always run it before asking for
help — the output is designed to be pasted whole into a GitHub issue. It
prints no secrets: bridge tokens are read to make the health calls but never
shown, phone numbers and chat ids are redacted, and no message content is
ever read (only the newest timestamp per database).

Usage:
    scripts\\doctor.cmd          (or: py -3 scripts\\doctor.py)
"""

import csv
import datetime
import io
import json
import platform
import shutil
import sqlite3
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config

# The four task names are a contract shared with the runbook (stage 8),
# update.py and uninstall.cmd. Change them in all four places or not at all.
TASKS = [
    "ShamashBridge",
    "ShamashContactBridge",
    "ShamashWatcher",
    "ShamashScheduler",
]

# whisper-daemon.py binds 127.0.0.1:8090 (see its module docstring).
WHISPER_HEALTH_URL = "http://127.0.0.1:8090/health"

# schtasks verbose-CSV column headers we care about. On a non-English Windows
# these are localized; when we can't find them we print the raw row instead of
# guessing — a pasteable raw row still helps whoever reads the issue.
CSV_FIELDS = ["Status", "Last Run Time", "Last Result", "Next Run Time"]


def line(label, value):
    print(f"  {label:<26} {value}")


def section(title):
    print()
    print(f"[{title}]")


# --------------------------------------------------------------------- config
def check_config():
    section("config")
    try:
        cfg = config.load()
    except config.ConfigError as exc:
        print("  CONFIG ERROR — this message is the thing to fix:")
        for l in str(exc).splitlines():
            print(f"    {l}")
        return None
    line("config.json", "resolves ok")
    line("agent_name", cfg["agent_name"])
    line("owner.name", "set" if cfg["owner"]["name"] else "MISSING")
    line("owner.phone", "set (redacted)" if cfg["owner"]["phone"] else "MISSING")
    line("timezone", cfg["owner"]["timezone"])
    line("permission_mode", cfg["permission_mode"])
    line("features", json.dumps(cfg["features"]))
    line("scan_times", ", ".join(cfg["schedule"]["scan_times"]))
    active = sorted(cfg["active_channels"])
    line("channels enabled", ", ".join(active) if active else "NONE — nothing can talk")
    for name in active:
        line(f"{name} bridge api", cfg["active_channels"][name]["api"])
    return cfg


# --------------------------------------------------------------------- claude
def check_claude(cfg):
    section("claude")
    exe = (cfg or {}).get("claude_exe") or shutil.which("claude") or ""
    if not exe:
        line("claude_exe", "NOT FOUND — set claude_exe in config.json")
        return
    line("claude_exe", exe)
    try:
        proc = subprocess.run(
            [exe, "--version"],
            capture_output=True, text=True, errors="replace", timeout=60,
        )
        out = (proc.stdout or proc.stderr).strip().splitlines()
        line("--version", out[0] if out else f"(no output, exit {proc.returncode})")
    except subprocess.TimeoutExpired:
        line("--version", "TIMED OUT after 60s")
    except OSError as exc:
        line("--version", f"FAILED to run: {exc}")


# -------------------------------------------------------------------- bridges
def check_bridges(cfg):
    section("bridges")
    if not cfg:
        print("  skipped — config did not resolve")
        return
    if not cfg["active_channels"]:
        print("  no channels enabled")
        return
    for name in sorted(cfg["active_channels"]):
        ch = cfg["active_channels"][name]
        token_path = Path(ch["token"])
        if not token_path.exists():
            line(name, "no .bridge-token yet — this bridge has never started/paired")
            continue
        token = token_path.read_text(encoding="utf-8").strip()
        req = urllib.request.Request(
            ch["api"] + "/health",
            headers={"Authorization": "Bearer " + token},
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                body = json.loads(resp.read().decode("utf-8", "replace"))
            connected = body.get("connected")
            line(name, "running, connected to WhatsApp" if connected
                 else f"running, connected={connected!r}")
        except urllib.error.HTTPError as exc:
            if exc.code == 503:
                line(name, "running but DISCONNECTED from WhatsApp — "
                           "the pairing may have expired (re-scan the QR)")
            elif exc.code == 401:
                line(name, "running but REJECTED our token (401) — "
                           "store and token are out of sync")
            else:
                line(name, f"unexpected HTTP {exc.code} from health check")
        except (urllib.error.URLError, OSError, ValueError) as exc:
            reason = getattr(exc, "reason", exc)
            # An unpaired bridge RUNS without listening: the upstream starts
            # its REST server only after WhatsApp pairing completes (verified
            # against the pinned commit). Distinguish that from a dead task.
            probe = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq whatsapp-bridge.exe",
                 "/FO", "CSV", "/NH"],
                capture_output=True, text=True,
            )
            if "whatsapp-bridge" in (probe.stdout or ""):
                line(name, f"NOT REACHABLE ({reason}) but a bridge PROCESS is "
                           "running — most likely it is waiting for a QR scan "
                           "(never paired, or the pairing was reset). See "
                           "docs/RE-PAIRING.md")
            else:
                line(name, f"NOT REACHABLE ({reason}) — bridge not running? "
                           "Check the ShamashBridge task below")


# ------------------------------------------------------------------ databases
def _age(ts_text):
    """Human age of an ISO-ish timestamp, or None if unparseable."""
    try:
        ts = datetime.datetime.fromisoformat(ts_text)
    except (ValueError, TypeError):
        return None
    if ts.tzinfo is None:
        ts = ts.astimezone()
    delta = datetime.datetime.now().astimezone() - ts
    minutes = int(delta.total_seconds() // 60)
    if minutes < 120:
        return f"{minutes} min ago"
    if minutes < 60 * 48:
        return f"{minutes // 60} h ago"
    return f"{minutes // (60 * 24)} days ago"


def check_databases(cfg):
    section("message databases")
    if not cfg:
        print("  skipped — config did not resolve")
        return
    if not cfg["active_channels"]:
        print("  no channels enabled")
        return
    for name in sorted(cfg["active_channels"]):
        db = Path(cfg["active_channels"][name]["db"])
        if not db.exists():
            line(name, f"missing: {db}")
            continue
        size_mb = db.stat().st_size / 2**20
        try:
            con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
            try:
                newest = con.execute(
                    "select max(timestamp) from messages"
                ).fetchone()[0]
            finally:
                con.close()
        except sqlite3.Error as exc:
            line(name, f"exists ({size_mb:.1f} MB) but UNREADABLE: {exc}")
            continue
        if newest is None:
            line(name, f"exists ({size_mb:.1f} MB) but has NO messages — never synced?")
        else:
            age = _age(newest)
            line(name, f"{size_mb:.1f} MB, newest message {age or newest}")


# ------------------------------------------------------------ scheduled tasks
def check_tasks(cfg):
    section("scheduled tasks")
    contact_enabled = bool(cfg and cfg["active_channels"].get("contact"))
    for task in TASKS:
        try:
            proc = subprocess.run(
                ["schtasks", "/Query", "/TN", task, "/FO", "CSV", "/V"],
                capture_output=True, text=True, errors="replace", timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            line(task, f"schtasks failed: {exc}")
            continue
        if proc.returncode != 0:
            if task == "ShamashContactBridge" and not contact_enabled:
                line(task, "not registered (expected — contact channel disabled)")
            else:
                line(task, "NOT REGISTERED — stage 8 of the runbook creates it")
            continue
        rows = list(csv.DictReader(io.StringIO(proc.stdout)))
        if not rows:
            line(task, "registered (schtasks returned no detail rows)")
            continue
        row = rows[0]
        if all(field in row for field in CSV_FIELDS):
            last_result = row["Last Result"].strip()
            verdict = "ok" if last_result == "0" else (
                "never run" if last_result == "267011" else f"code {last_result}")
            line(task, f"{row['Status'].strip() or '?'} | last result {verdict} | "
                       f"last run {row['Last Run Time'].strip()} | "
                       f"next run {row['Next Run Time'].strip()}")
        else:
            # Localized Windows: headers don't match. Print the raw row —
            # still pasteable, still useful.
            line(task, "registered (localized schtasks output, raw row follows)")
            print("    " + " | ".join(v.strip() for v in row.values() if v))


# ------------------------------------------------------------------- schedule
def check_schedule():
    """state/schedule.json drives ALL recurring work (scans, job shifts — see
    scheduler.py). A broken file doesn't crash anything; it silently stops
    every scheduled run, which is why this check is loud."""
    section("schedule")
    path = config.ROOT / "state" / "schedule.json"
    if not path.exists():
        print(f"  SCHEDULE BROKEN: {path} does not exist — no scheduled work will run")
        return
    try:
        jobs = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"  SCHEDULE BROKEN: schedule.json is unreadable/invalid JSON — {exc}")
        return
    if not isinstance(jobs, list):
        print("  SCHEDULE BROKEN: top level must be a LIST of job objects")
        return
    problems = []
    for i, job in enumerate(jobs):
        label = f"entry #{i + 1}"
        if not isinstance(job, dict):
            problems.append(f"{label} is not an object")
            continue
        if job.get("name"):
            label = f"job {job['name']!r}"
        else:
            problems.append(f"{label} has no name")
        if not job.get("command"):
            problems.append(f"{label} has no command")
        cadence = [k for k in ("at", "every_minutes", "at_datetime") if k in job]
        if len(cadence) != 1:
            problems.append(
                f"{label} needs exactly one of at/every_minutes/at_datetime "
                f"(has: {', '.join(cadence) or 'none'})"
            )
    if problems:
        for p in problems:
            print(f"  SCHEDULE BROKEN: {p}")
    else:
        line("schedule.json", f"{len(jobs)} job(s), all well-formed")


# -------------------------------------------------------------------- whisper
def check_whisper(cfg):
    if not (cfg and cfg["features"].get("voice_notes")):
        return
    section("whisper daemon")
    try:
        with urllib.request.urlopen(WHISPER_HEALTH_URL, timeout=5) as resp:
            body = json.loads(resp.read().decode("utf-8", "replace"))
        line("health", f"ok={body.get('ok')} loaded={body.get('loaded')} "
                       f"model={body.get('model')}")
    except (urllib.error.URLError, OSError, ValueError) as exc:
        reason = getattr(exc, "reason", exc)
        line("health", f"NOT REACHABLE ({reason}) — voice notes will fail. "
                       "Is the daemon running?")


# --------------------------------------------------------------------- system
def check_system():
    section("system")
    line("time", datetime.datetime.now().astimezone().isoformat(timespec="seconds"))
    line("windows", platform.platform())
    line("python", f"{sys.version.split()[0]} ({sys.executable})")
    usage = shutil.disk_usage(config.ROOT)
    free_gb = usage.free / 2**30
    warn = "  <-- LOW, things will start failing" if free_gb < 2 else ""
    line("disk free", f"{free_gb:.1f} GB of {usage.total / 2**30:.1f} GB{warn}")
    line("repo", str(config.ROOT))
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, errors="replace",
            timeout=10, cwd=str(config.ROOT),
        )
        commit = (proc.stdout or "").strip() if proc.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        commit = ""
    line("kit commit", commit or "unknown")


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass
    print("=== Shamash doctor ===")
    check_system()
    cfg = check_config()
    check_claude(cfg)
    check_bridges(cfg)
    check_databases(cfg)
    check_tasks(cfg)
    check_schedule()
    check_whisper(cfg)
    print()
    print("=== end of report — if you're asking for help, "
          "paste this whole block into a GitHub issue")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
