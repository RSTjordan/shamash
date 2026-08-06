#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Teleport: discovery and selection of desk Claude Code sessions.

This module holds everything about FINDING and CHOOSING a session —
scanning ~/.claude/projects transcripts, matching the owner's hint,
running the confirmation polls — and the request handoff file. It holds
NO runner code: the watcher owns the TeleportSession and the routing,
and imports this module (never the reverse; watcher.py raises at import
time without a config, which would make a circular import a startup
trap).

The handoff: the resident agent runs `--request "<hint>" --channel X`;
this module confirms a choice with the owner via polls and writes
state/teleport.json with phase="requested". The watcher's main loop
notices it between turns, spawns the runner, and flips routing. A
request older than REQUEST_TTL is discarded — a watcher that was down
must not fire a teleport the owner confirmed an hour ago.
"""
import argparse
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import config
import strings

CFG = config.load()
KIT_ROOT = pathlib.Path(CFG["root"]).resolve()
STATE_FILE = CFG["paths"]["state"] / "teleport.json"
PROJECTS_DIR = pathlib.Path.home() / ".claude" / "projects"
REQUEST_TTL = 120.0
TAIL_BYTES = 64 * 1024
OPEN_AT_DESK_S = 600  # transcript touched this recently = "looks open"
DESC_MAX = 60


def _tail_lines(path):
    """Last TAIL_BYTES of a transcript, split into parseable JSON lines.
    The first line is dropped ONLY when a seek happened (it may be cut
    mid-JSON); a short transcript keeps every line — its first entry is
    often the only one carrying cwd."""
    try:
        size = path.stat().st_size
        seeked = size > TAIL_BYTES
        with path.open("rb") as fh:
            if seeked:
                fh.seek(size - TAIL_BYTES)
            raw = fh.read().decode("utf-8", errors="replace")
    except OSError:
        return []
    lines = raw.splitlines()
    if seeked and len(lines) > 1:
        lines = lines[1:]
    out = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def _describe(entries):
    """The LAST summary entry if any; else the LAST user message text."""
    summaries = [e["summary"] for e in entries
                 if e.get("type") == "summary" and e.get("summary")]
    if summaries:
        desc = summaries[-1]
    else:
        users = []
        for e in entries:
            if e.get("type") == "user":
                content = (e.get("message") or {}).get("content")
                if isinstance(content, str) and content.strip():
                    users.append(content)
                elif isinstance(content, list):
                    for b in content:
                        if isinstance(b, dict) and b.get("type") == "text":
                            users.append(b.get("text", ""))
        desc = users[-1] if users else ""
    desc = " ".join(str(desc).split())
    return desc[:DESC_MAX] + ("…" if len(desc) > DESC_MAX else "")


def _cwd_of(entries):
    for e in entries:
        if e.get("cwd"):
            return str(e["cwd"])
    return ""


def _discover_in(projects_dir, limit=40):
    """Candidates newest-first. Excluded: sessions whose cwd is the kit
    root (the resident/scans/jobs — teleporting the agent into itself is
    a hall of mirrors). An exclusion, not a whitelist: nothing else is
    filtered."""
    files = []
    try:
        for d in projects_dir.iterdir():
            if not d.is_dir():
                continue
            for f in d.glob("*.jsonl"):
                try:
                    files.append((f.stat().st_mtime, f))
                except OSError:
                    continue
    except OSError:
        return []
    files.sort(key=lambda t: t[0], reverse=True)
    out = []
    for mtime, f in files[:limit]:
        entries = _tail_lines(f)
        if not entries:
            continue
        cwd = _cwd_of(entries)
        if not cwd:
            continue
        try:
            if pathlib.Path(cwd).resolve() == KIT_ROOT:
                continue
        except OSError:
            pass
        out.append({
            "session_id": f.stem,
            "cwd": cwd,
            "repo": pathlib.Path(cwd).name,
            "mtime": mtime,
            "description": _describe(entries),
            "transcript": str(f),
        })
    return out


def discover(limit=40):
    return _discover_in(PROJECTS_DIR, limit=limit)


def _match(hint, candidates):
    """Hint-filtered candidates, newest first; empty hint = all."""
    hint_words = [w for w in (hint or "").lower().split() if len(w) > 2]
    if not hint_words:
        return sorted(candidates, key=lambda c: c["mtime"], reverse=True)
    hits = []
    for c in candidates:
        hay = f"{c['repo']} {c['description']} {c['cwd']}".lower()
        if any(w in hay for w in hint_words):
            hits.append(c)
    return sorted(hits, key=lambda c: c["mtime"], reverse=True)


def _age_str(mtime):
    mins = max(0, int((time.time() - mtime) / 60))
    if mins < 60:
        return f"{mins}m"
    if mins < 60 * 24:
        return f"{mins // 60}h"
    return f"{mins // (60 * 24)}d"


def looks_open(candidate):
    return time.time() - candidate["mtime"] < OPEN_AT_DESK_S


def write_request(candidate, channel):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({
        "phase": "requested", "channel": channel,
        "source_session_id": candidate["session_id"],
        "forked_session_id": "",
        "cwd": candidate["cwd"], "repo": candidate["repo"],
        "requested_at": time.time(), "started": 0.0, "last_activity": 0.0,
    }, ensure_ascii=False), encoding="utf-8")
    tmp.replace(STATE_FILE)


def read_state():
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def clear_state():
    try:
        STATE_FILE.unlink()
    except OSError:
        pass


def request_fresh(state):
    return (time.time() - float(state.get("requested_at", 0))) < REQUEST_TTL


POLL_TIMEOUT = 120.0  # two selection polls back-to-back must fit the
# agent's documented 300s tool timeout with margin


def _confirm(candidate, channel):
    import ask as ask_mod
    warn = strings.t("tp_open_warn") if looks_open(candidate) else ""
    q = strings.t("tp_confirm_q", repo=candidate["repo"],
                  desc=candidate["description"],
                  age=_age_str(candidate["mtime"])) + warn
    opts = [strings.t("tp_continue"), strings.t("tp_pick_other"),
            strings.t("tp_cancel")]
    res = ask_mod.ask(q, opts, timeout=POLL_TIMEOUT, channel=channel)
    return res["chosen"]


def _pick(candidates, channel):
    """Top-5 picker. Option labels are capped HERE (ask.py would truncate
    and possibly renumber, making equality against our originals lossy) —
    and the chosen label is matched by its `N) ` prefix, never by string
    equality, so truncation and vote-content mangling can't turn a valid
    pick into a phantom cancel."""
    import ask as ask_mod
    top = candidates[:5]
    opts = [f"{i + 1}) {c['repo']} · {_age_str(c['mtime'])} · {c['description']}"[:100]
            for i, c in enumerate(top)]
    opts.append(strings.t("tp_cancel"))
    res = ask_mod.ask(strings.t("tp_pick_q"), opts, timeout=POLL_TIMEOUT,
                      channel=channel)
    chosen = res["chosen"] or ""
    if not chosen or chosen == strings.t("tp_cancel"):
        return None
    for i in range(len(top)):
        if chosen.startswith(f"{i + 1}) "):
            return top[i]
    return None


def request(hint, channel):
    """The full selection flow. Returns a dict for the caller's reply."""
    candidates = discover()
    if not candidates:
        return {"requested": False, "reason": "no sessions found"}
    hits = _match(hint, candidates)
    chosen = None
    if len(hits) == 1:
        verdict = _confirm(hits[0], channel)
        if verdict == strings.t("tp_continue"):
            chosen = hits[0]
        elif verdict == strings.t("tp_pick_other"):
            chosen = _pick(candidates, channel)
    else:
        chosen = _pick(hits or candidates, channel)
    if chosen is None:
        return {"requested": False, "reason": "cancelled or no answer"}
    write_request(chosen, channel)
    return {"requested": True, "repo": chosen["repo"],
            "session_id": chosen["session_id"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--request", metavar="HINT")
    ap.add_argument("--channel", choices=["contact", "main"])
    args = ap.parse_args()
    if args.list:
        print(json.dumps(discover(), ensure_ascii=False, indent=2))
        return 0
    if args.request is not None:
        if not args.channel:
            ap.error("--request needs --channel")
        print(json.dumps(request(args.request, args.channel),
                         ensure_ascii=False))
        return 0
    ap.error("give --list or --request")


if __name__ == "__main__":
    sys.exit(main())
