#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Update the kit in place, without ever touching the user's files.

What it does, in order:

1. Refuses politely if the tree has local edits to KIT files — an update must
   never silently discard someone's changes. The user's own files
   (config.json, brief/, state/, logs/, the bridge stores) are gitignored, so
   they can never block an update and can never be overwritten by one.
2. `git pull --ff-only`. Fast-forward only: if the local history has diverged
   from the published one, we stop and say so rather than auto-merge — a
   surprise merge in a kit nobody here maintains is worse than a clear stop.
3. If anything actually changed: prints the change list, then restarts
   ShamashWatcher and ShamashScheduler so the new code is what's running.
   The watcher also reloads itself when its source changes — the restart is
   belt and braces, because "the update worked but the old code kept running
   for a week" is the failure nobody reports.

The bridge tasks are NOT restarted: bridge/ is a separate local clone outside
this repo's history, so a pull here never changes the running bridge. When a
document in patches/ changes, it carries its own rebuild procedure — we print
a loud reminder instead of guessing.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Kept in sync with the runbook (stage 8), doctor.py and uninstall.cmd.
RESTART_TASKS = ["ShamashWatcher", "ShamashScheduler"]


def git(*args, show=False):
    """Run git against the repo root. show=True streams output to the console."""
    return subprocess.run(
        ["git", "-C", str(ROOT), *args],
        capture_output=not show, text=True, errors="replace",
    )


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

    if git("rev-parse", "--is-inside-work-tree").returncode != 0:
        print(f"{ROOT} is not a git repository, so there is nothing to pull.")
        print("(Installed from a zip? Re-clone the repo to make updates work.)")
        return 1

    status = git("status", "--porcelain")
    # Untracked files ("??") are fine — config.json, brief/ and friends are
    # gitignored anyway, and a stray new file can't be clobbered by a pull.
    dirty = [l for l in status.stdout.splitlines()
             if l.strip() and not l.startswith("??")]
    if dirty:
        print("Not updating: these kit files have local edits, and an update")
        print("would run over them:")
        for l in dirty:
            print(f"  {l}")
        print()
        print("Your config.json and brief/ never appear in this list — they are")
        print("ignored by git and no update touches them. If you made these")
        print("edits on purpose, commit or stash them first; if they're a")
        print("mystery, `git diff` shows what changed. Then run update again.")
        return 1

    old = git("rev-parse", "HEAD").stdout.strip()
    print("Pulling the latest version...")
    if git("pull", "--ff-only", show=True).returncode != 0:
        print()
        print("The pull did not complete — no internet, no remote configured,")
        print("or local history has diverged from the published one. Nothing")
        print("was changed; it is safe to just try again later.")
        return 1

    new = git("rev-parse", "HEAD").stdout.strip()
    if old == new:
        print("Already up to date — nothing changed, nothing to restart.")
        return 0

    print()
    print("What changed:")
    print(git("log", "--oneline", f"{old}..{new}").stdout.rstrip())

    changed_files = git("diff", "--name-only", f"{old}..{new}").stdout.splitlines()
    if any(f.startswith("patches/") for f in changed_files):
        print()
        print("NOTE: files under patches/ changed. Those describe changes inside")
        print("your local bridge/ clone, which this update cannot apply for you —")
        print("re-apply them per patches/README.md (a bridge rebuild).")

    print()
    print("Restarting the background tasks so the new code is running:")
    for task in RESTART_TASKS:
        subprocess.run(["schtasks", "/End", "/TN", task], capture_output=True)
        run = subprocess.run(["schtasks", "/Run", "/TN", task],
                             capture_output=True, text=True, errors="replace")
        if run.returncode == 0:
            print(f"  {task}: restarted")
        else:
            detail = (run.stderr or run.stdout).strip()
            print(f"  {task}: could not restart — {detail}")
            print("    (Is it registered? scripts\\doctor.cmd will say.)")

    print()
    print("Done. Your config.json and brief/ were not touched — they never are.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
