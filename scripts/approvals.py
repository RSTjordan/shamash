#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Blocked-action approvals over WhatsApp.

Why this exists: in headless runs there is no terminal to approve anything in.
Without this, a blocked action (`git init`, `schtasks /Create`, a write
outside the project) just comes back as a denial the agent has to work around,
and the owner learns about it — if at all — from a sentence at the end of the
reply.

The CLI already knows how to ask. Run it with `--permission-prompt-tool stdio`
and every blocked call arrives on stdout as

    {"type":"control_request","request_id":...,
     "request":{"subtype":"can_use_tool","tool_name":"Bash",
                "input":{...},"decision_reason":"...",
                "permission_suggestions":[{"type":"addRules",...}]}}

and the process waits for a matching control_response. This module is what
fills that wait: it renders the request as one WhatsApp card, waits for the
owner to answer it, and turns the answer into a decision.

Answering is one tap. The card goes out first (it is the legend: what is
blocked, why, and what "always" would persist), then scripts/ask.py puts the
same question as a native WhatsApp poll — tapping an option is the fast path
and needs no keyboard. A REACTION on the card or on the poll counts too (the
bridge stores inbound reactions as media_type="reaction" rows whose `filename`
carries the id they target), and so does typing 1 / always / 0 (English and
Hebrew keywords are both accepted, and they are passed to ask() as aliases so
they keep their meaning regardless of the poll's option order).

  👍 ✅ 👌 🆗 / "1" "yes" "ok" "כן"       -> allow, this once (persists nothing)
  ❤️ 💯 ♾️ / "2" "always" "תמיד"          -> allow + persist the suggested rule
  👎 ❌ 🚫 / "0" "no" "deny" "לא"         -> deny, with a reason for the agent

No answer inside APPROVAL_TIMEOUT is a deny, never a hang: an unattended
scheduled run must degrade to "kept working without it and said so", not sit
on a blocked stdin until the turn ceiling kills it.
"""
from __future__ import annotations

import datetime
import json
import logging
import pathlib
import sys
import threading
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import config
import notify
import ask as ask_mod
import strings

CFG = config.load()
ROOT = pathlib.Path(CFG["root"])
AUDIT = CFG["paths"]["state"] / "approvals.jsonl"
OWNER = CFG["owner"].get("name") or "the owner"

APPROVAL_TIMEOUT = 900.0  # 15 min, then deny-and-continue

ONCE = {"1", "כן", "אשר", "אשרתי", "אישור", "ok", "okay", "yes", "y", "go", "כן."}
ALWAYS = {"2", "תמיד", "אשר תמיד", "always", "always allow", "מעכשיו", "כן תמיד"}
DENY = {"0", "לא", "לא!", "דחה", "עצור", "no", "n", "deny", "stop", "nope", "אל"}

REACT_ONCE = {"👍", "✅", "👌", "🆗", "🙏", "💪"}
REACT_ALWAYS = {"❤️", "❤", "💯", "♾️", "🔁"}
REACT_DENY = {"👎", "❌", "🚫", "✋", "🛑"}

# Answers already given for the same (tool, input) — an "always" must not be
# asked again a second time in the same process just because the persisted
# rule only takes effect on the next tool call.
_MEMO: dict[str, dict] = {}

# Shared state the watcher reads (this module runs in-process, imported by
# watcher.py). While a card is open on a channel, the owner's next message
# there is almost certainly its answer — the watcher's wait-tick must not
# steer or ack it out from under the poll loop below. And a row that WAS
# consumed as an answer must never surface again as a command afterwards.
# Cards are asked on side threads, hence the lock and the per-channel count.
CONSUMED_IDS: set[str] = set()
_OPEN_CARDS: dict[str, int] = {}
_OPEN_LOCK = threading.Lock()


def channel_has_open_card(name: str) -> bool:
    with _OPEN_LOCK:
        return _OPEN_CARDS.get(name, 0) > 0


def _card_opened(name: str) -> None:
    with _OPEN_LOCK:
        _OPEN_CARDS[name] = _OPEN_CARDS.get(name, 0) + 1


def _card_closed(name: str) -> None:
    with _OPEN_LOCK:
        left = _OPEN_CARDS.get(name, 0) - 1
        if left > 0:
            _OPEN_CARDS[name] = left
        else:
            _OPEN_CARDS.pop(name, None)


def _log(record: dict) -> None:
    record["ts"] = datetime.datetime.now().isoformat(timespec="seconds")
    try:
        AUDIT.parent.mkdir(parents=True, exist_ok=True)
        with AUDIT.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        logging.exception("approval audit write failed")


def _summarize(tool: str, tool_input: dict) -> str:
    """The one line that tells the owner what is actually about to happen."""
    if not isinstance(tool_input, dict):
        return str(tool_input)[:300]
    for key in ("command", "file_path", "path", "url", "pattern", "query"):
        val = tool_input.get(key)
        if isinstance(val, str) and val.strip():
            body = " ".join(val.split())
            return body[:300] + ("…" if len(body) > 300 else "")
    body = json.dumps(tool_input, ensure_ascii=False)
    return body[:300] + ("…" if len(body) > 300 else "")


def _rule_labels(suggestions: list) -> list[str]:
    out = []
    for s in suggestions or []:
        for rule in s.get("rules", []) or []:
            content = rule.get("ruleContent")
            label = rule.get("toolName", "")
            out.append(f"{label}({content})" if content else label)
    return out


def card(request: dict, context: str = "") -> str:
    tool = request.get("tool_name", "?")
    what = _summarize(tool, request.get("input") or {})
    reason = (request.get("decision_reason") or "approval required").strip()
    rules = _rule_labels(request.get("permission_suggestions"))
    lines = [
        strings.t("card_title"),
        "",
        f"*{tool}:* {what}",
        f"_{reason}_",
    ]
    if context:
        lines.append(strings.t("card_for", context=context))
    lines += [
        "",
        strings.t("card_once"),
    ]
    if rules:
        lines.append(strings.t("card_always", rules=", ".join(rules[:2])))
    lines += [
        strings.t("card_deny"),
        "",
        strings.t("card_hint"),
    ]
    return "\n".join(lines)


def _memo_key(request: dict, project_root=None) -> str:
    # The project the action would run in is part of the identity of the
    # answer: the same `git push` in another checkout is another question.
    return json.dumps(
        [str(project_root or ROOT), request.get("tool_name"), request.get("input")],
        ensure_ascii=False, sort_keys=True,
    )


# Not everything the CLI routes through the permission tool is worth waking
# the owner for. Reading a file inside the project is the agent's normal
# breathing; a card for it trains the owner to tap 👍 without reading, which
# is exactly how a real card gets approved by reflex.
READ_ONLY_TOOLS = {"Read", "Glob", "Grep", "NotebookRead"}


def _inside_project(value: str) -> bool:
    try:
        p = pathlib.Path(value).resolve()
    except (OSError, ValueError):
        return False
    return p == ROOT or ROOT in p.parents


def auto_ok(request: dict) -> bool:
    """True for reads that stay inside the project — allowed without a card."""
    if request.get("tool_name") not in READ_ONLY_TOOLS:
        return False
    tool_input = request.get("input") or {}
    if not isinstance(tool_input, dict):
        return False
    for key in ("file_path", "path"):
        val = tool_input.get(key)
        if isinstance(val, str) and val.strip():
            return _inside_project(val)
    return True  # Glob/Grep with no path search the project cwd


def ask(request: dict, context: str = "", timeout: float = APPROVAL_TIMEOUT,
        project_root=None) -> dict:
    """Put a blocked action to the owner and wait for the answer.

    Returns {"response": <control_response payload>, "consumed": [row ids],
             "verdict": once|always|deny|timeout|undeliverable}. `consumed`
    must be marked processed by the caller, otherwise the owner's "1" is
    picked up a second time as a fresh command.
    """
    key = _memo_key(request, project_root)
    memo = _MEMO.get(key)
    if memo is not None:
        return {"response": memo, "consumed": [], "verdict": "memo"}

    if auto_ok(request):
        logging.info("approval auto-allowed (read inside project): %s",
                     request.get("tool_name"))
        return {
            "response": {"behavior": "allow",
                         "updatedInput": request.get("input") or {}},
            "consumed": [], "verdict": "auto",
        }

    suggestions = request.get("permission_suggestions") or []
    text = card(request, context)
    sent = notify.notify(text)
    delivered = next((r for r in sent if r["verified"]), None)
    if delivered is None:
        _log({"verdict": "undeliverable", "tool": request.get("tool_name"),
              "input": request.get("input")})
        return {
            "response": {"behavior": "deny", "message":
                         f"Could not reach {OWNER} to ask for approval (all "
                         "messaging channels down). Continue without this "
                         "action and say at the end that it stayed blocked."},
            "consumed": [], "verdict": "undeliverable",
        }
    channel = next(c for c in notify.CHANNELS if c["name"] == delivered["channel"])
    card_id = delivered["id"]
    # The answer window opens with the CARD, not with the poll: posting and
    # verifying the poll row costs up to ~12s, and a 👍 tapped on the card in
    # that window must not fall before ask()'s scan origin — degraded-poll is
    # exactly when the card reaction is the only answer form left.
    card_sent = time.time()
    _card_opened(channel["name"])
    started = time.time()
    # The card above is the legend; the poll is the tap surface. The legacy
    # answer forms survive as ask()'s aliases: the emoji sets classify
    # reactions on either the card (also_watch_ids) or the poll, and the
    # keyword sets classify text — checked BEFORE positional digits, so "2"
    # still means "always" even on a two-option card.
    once_l, always_l, deny_l = (strings.t("opt_allow_once"),
                                strings.t("opt_always"), strings.t("opt_deny"))
    options = [once_l, always_l, deny_l] if suggestions else [once_l, deny_l]
    try:
        outcome = ask_mod.ask(
            strings.t("poll_approve_q", tool=request.get("tool_name", "?")),
            options,
            timeout=timeout,
            channel=channel["name"],
            also_watch_ids=(card_id,),
            text_fallback=False,  # the card IS the numbered legend already
            text_aliases={once_l: ONCE, always_l: ALWAYS, deny_l: DENY},
            reaction_aliases={once_l: REACT_ONCE, always_l: REACT_ALWAYS,
                              deny_l: REACT_DENY},
            since=card_sent,
        )
    finally:
        _card_closed(channel["name"])
    verdict = {once_l: "once", always_l: "always", deny_l: "deny"}.get(
        outcome["chosen"])
    consumed = outcome["consumed_ids"]
    for mid in consumed:
        if len(CONSUMED_IDS) > 500:
            CONSUMED_IDS.clear()
        CONSUMED_IDS.add(mid)

    if verdict == "always":
        inner = {"behavior": "allow", "updatedInput": request.get("input") or {}}
        if suggestions:
            inner["updatedPermissions"] = suggestions
    elif verdict == "once":
        inner = {"behavior": "allow", "updatedInput": request.get("input") or {}}
    elif verdict == "deny":
        inner = {"behavior": "deny", "message":
                 f"{OWNER} declined this action. Do not retry it and do not "
                 "look for a way around it — continue with the rest of the "
                 "task and say at the end what you skipped."}
    else:
        verdict = "timeout"
        inner = {"behavior": "deny", "message":
                 f"No answer from {OWNER} within {int(timeout)}s. Continue "
                 "without this action and say at the end that it is still "
                 "waiting for approval."}

    if verdict == "always":
        _MEMO[key] = inner
    _log({"verdict": verdict, "answered_by": outcome["answered_by"],
          "tool": request.get("tool_name"),
          "input": request.get("input"), "channel": channel["name"],
          "card_id": card_id, "consumed": consumed,
          "waited_s": round(time.time() - started, 1)})
    logging.info("approval %s for %s", verdict, request.get("tool_name"))
    return {"response": inner, "consumed": consumed, "verdict": verdict}


# ---------------------------------------------------------------------------
# Second class of block: the auto-mode classifier.
#
# Rule-based blocks arrive as can_use_tool and can simply be answered. The
# classifier is different — it denies inside the tool result, after the fact,
# and nothing is waiting for an answer. Those denials get the same card: the
# watcher spots the denial in the tool result, asks, and on an "always" answer
# writes the rule into .claude/settings.local.json itself (a plain file write
# from the watcher process — no classifier stands between python and a JSON
# file). A "once" approves the single retry and persists nothing.
# ---------------------------------------------------------------------------
CLASSIFIER_MARKERS = (
    "denied by the Claude Code auto mode classifier",
    "Blocked by classifier",
)


def _local_settings(project_root=None):
    """Where an "always" rule is persisted — the project the agent is actually
    running in, which is the teleport cwd when there is one, else the kit."""
    return pathlib.Path(project_root or ROOT) / ".claude" / "settings.local.json"


def is_classifier_denial(text: str) -> bool:
    return any(m in (text or "") for m in CLASSIFIER_MARKERS)


# Heads that must never become a standing allow-rule, however the owner
# answered the card in front of them: approving one deletion is not approving
# all of them.
DESTRUCTIVE_HEADS = {
    "rm", "del", "erase", "rmdir", "rd", "remove-item", "ri", "format",
    "mkfs", "dd", "shutdown", "restart-computer", "stop-computer", "taskkill",
    "stop-process", "kill", "reg", "diskpart", "cipher", "takeown", "icacls",
}
COMPOUND = (";", "&&", "||", "|", "\n", "`", "$(")


def derive_rule(tool: str, tool_input: dict) -> dict | None:
    """The narrowest allow-rule that would let this exact action through.

    None means "allow it this once, but persist nothing" — the honest answer
    whenever the first two words of the command do not describe the whole of
    what the owner approved. Deriving a rule from `rm -f <one file>; <the real
    action>` would turn a single 👍 about that action into a standing
    `Bash(rm -f:*)`, i.e. a blanket delete permission.
    """
    if not isinstance(tool_input, dict):
        return None
    if tool in ("Bash", "PowerShell"):
        cmd = (tool_input.get("command") or "").strip()
        if not cmd:
            return None
        if any(sep in cmd for sep in COMPOUND):
            return None  # a chain: its head speaks only for its first link
        words = cmd.split()
        if words[0].split("/")[-1].split("\\")[-1].lower() in DESTRUCTIVE_HEADS:
            return None
        return {"toolName": tool, "ruleContent": " ".join(words[:2]) + ":*"}
    path = tool_input.get("file_path") or tool_input.get("path")
    if path:
        return {"toolName": tool, "ruleContent": str(path)}
    return {"toolName": tool}


def add_local_rule(rule: dict, project_root=None) -> bool:
    """Persist one allow-rule to .claude/settings.local.json."""
    settings = _local_settings(project_root)
    try:
        data = json.loads(settings.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    perms = data.setdefault("permissions", {})
    allow = perms.setdefault("allow", [])
    content = rule.get("ruleContent")
    entry = f"{rule['toolName']}({content})" if content else rule["toolName"]
    if entry in allow:
        return True
    allow.append(entry)
    try:
        settings.parent.mkdir(parents=True, exist_ok=True)
        settings.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError:
        logging.exception("could not write %s", settings)
        return False
    _log({"verdict": "rule-added", "rule": entry})
    return True


def ask_after_denial(tool: str, tool_input: dict, context: str = "",
                     timeout: float = APPROVAL_TIMEOUT,
                     project_root=None) -> dict:
    """Card for a classifier denial. Any approval asks for a retry; only an
    "always" answer writes the rule, so it survives into future runs. A
    "once" (or a memo of an earlier answer) approves the retry and persists
    nothing — that is what the card's legend promises."""
    rule = derive_rule(tool, tool_input)
    request = {
        "tool_name": tool,
        "input": tool_input,
        "decision_reason": "Blocked by the automatic permission classifier",
        "permission_suggestions": (
            [{"type": "addRules", "rules": [rule], "behavior": "allow",
              "destination": "localSettings"}] if rule else []
        ),
    }
    outcome = ask(request, context=context, timeout=timeout,
                  project_root=project_root)
    verdict = outcome["verdict"]
    if verdict == "always" and rule:
        add_local_rule(rule, project_root)
    outcome["retry"] = verdict in ("once", "always", "memo")
    return outcome


def control_response(request_id: str, inner: dict) -> str:
    """The exact line the CLI is waiting for on stdin."""
    return json.dumps({
        "type": "control_response",
        "response": {"subtype": "success", "request_id": request_id,
                     "response": inner},
    }, ensure_ascii=False) + "\n"
