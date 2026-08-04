#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""One scheduled scan: render prompts/scan.md, stamp it with the local
date/time, and hand it to Claude Code headless.

Why the prompt goes in on stdin: `--allowedTools` is variadic, and a prompt
passed as a trailing positional argument after it gets swallowed as one more
tool name — a real bug we hit, and the scan silently did nothing. `-p` with
the prompt on stdin sidesteps the whole class.

Why the date/time is injected here: a headless model run has no reliable
sense of "now", and the scan prompt reasons about time ("this morning",
"since the last digest"). The launcher knows; the model shouldn't guess.

Exit code: 0 on success, non-zero otherwise. run-scan.cmd turns a non-zero
exit into a WhatsApp failure note via notify.py — a scan that dies silently
is a digest the owner never knows they missed.
"""

import datetime
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config

# A scan that runs longer than this is stuck, not thorough. The scheduled
# task's time limit is the outer fence; this inner one still produces a
# readable exit code and therefore a failure notification.
TIMEOUT_SECONDS = 3600


def main():
    try:
        cfg = config.load()
    except config.ConfigError as exc:
        print(f"CONFIG ERROR\n{exc}", file=sys.stderr)
        return 1

    claude = cfg.get("claude_exe")
    if not claude:
        print(
            "claude executable not found: not set in config.json and not in any "
            "of the usual places. Run scripts\\doctor.cmd.",
            file=sys.stderr,
        )
        return 1

    try:
        prompt = config.read_prompt("scan.md")
    except config.ConfigError as exc:
        print(f"CONFIG ERROR\n{exc}", file=sys.stderr)
        return 1

    now = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    prompt = f"Local date/time now: {now} (ISO, local timezone).\n\n{prompt}"

    cmd = [
        claude, "-p",
        "--model", cfg.get("model", "claude-opus-5"),  # same cost knob as the watcher
        "--allowedTools", cfg["allowed_tools"],
    ]
    print(f"[run_scan] {now} starting scan", flush=True)
    try:
        # stdout/stderr are inherited on purpose: run-scan.cmd appends them to
        # logs\scan.log, so the model's output lands next to these markers.
        proc = subprocess.run(
            cmd,
            input=prompt.encode("utf-8"),
            cwd=str(cfg["root"]),
            timeout=TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        print(
            f"[run_scan] scan exceeded {TIMEOUT_SECONDS}s and was killed",
            file=sys.stderr,
        )
        return 1
    except OSError as exc:
        print(f"[run_scan] could not start {claude}: {exc}", file=sys.stderr)
        return 1

    print(f"[run_scan] scan finished with exit code {proc.returncode}", flush=True)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
