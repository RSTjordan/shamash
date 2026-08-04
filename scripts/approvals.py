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

Answering is one tap: a REACTION on the card (the bridge stores inbound
reactions as media_type="reaction" rows whose quoted_message_id points back at
it), so 👍 approves without opening a keyboard. Typing 1 / תמיד / 0 works too.

  👍 ✅ 👌 🆗 / "1" "כן" "אשר" "ok"      -> allow, this once
  ❤️ 💯 ♾️ / "2" "תמיד" "always"          -> allow + persist the suggested rule
  👎 ❌ 🚫 / "0" "לא" "דחה" "עצור"        -> deny, with a reason for the agent

No answer inside APPROVAL_TIMEOUT is a deny, never a hang: an unattended
scheduled run must degrade to "kept working without it and said so", not sit
on a blocked stdin until the turn ceiling kills it.
"""
from __future__ import annotations

import datetime
import json
import logging
import pathlib
import sqlite3
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import config
import notify

CFG = config.load()
ROOT = pathlib.Path(CFG["root"])
AUDIT = CFG["paths"]["state"] / "approvals.jsonl"
AGENT_PREFIX = f"\U0001f916 *{CFG['agent_name']}*"
OWNER = CFG["owner"].get("name") or "the owner"

APPROVAL_TIMEOUT = 900.0  # 15 min, then deny-and-continue
POLL = 2.0

ONCE = {"1", "כן", "אשר", "אשרתי", "אישור", "ok", "okay", "yes", "y", "go", "כן."}
ALWAYS = {"2", "תמיד", "אשר תמיד", "always", "always allow", "מעכשיו", "כן תמיד"}
DENY = {"0", "לא", "לא!", "דחה", "עצור", "no", "n", "stop", "nope", "אל"}

REACT_ONCE = {"👍", "✅", "👌", "🆗", "🙏", "💪"}
REACT_ALWAYS = {"❤️", "❤", "💯", "♾️", "🔁"}
REACT_DENY = {"👎", "❌", "🚫", "✋", "🛑"}

# Answers already given for the same (tool, input) — an "always" must not be
# asked again a second time in the same process just because the persisted
# rule only takes effect on the next tool call.
_MEMO: dict[str, dict] = {}


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
    reason = (request.get("decision_reason") or "דורש אישור").strip()
    rules = _rule_labels(request.get("permission_suggestions"))
    lines = [
        "🔒 *פעולה נחסמה — צריך אישור שלך*",
        "",
        f"*{tool}:* {what}",
        f"_{reason}_",
    ]
    if context:
        lines.append(f"בשביל: {context}")
    lines += [
        "",
        "👍 = אשר פעם אחת",
    ]
    if rules:
        lines.append(f"❤️ = אשר תמיד ({', '.join(rules[:2])})")
    lines += [
        "👎 = דחה",
        "",
        "_(אפשר גם להשיב 1 / תמיד / 0)_",
    ]
    return "\n".join(lines)


def _rows_after(channel: dict, since_epoch: float, card_id: str | None) -> list:
    """The owner's messages and reactions in that chat since the card went out.

    Which rows are the owner's differs per channel: the contact bridge is a
    separate identity, so the owner is is_from_me=0 there; the main channel
    lives on the owner's own account, where everything is is_from_me=1 and
    only the agent header separates the agent's sends. notify.CHANNELS carries
    the right value per channel.
    """
    db = pathlib.Path(channel["db"])
    inbound = channel.get("is_from_me", 0)
    try:
        con = sqlite3.connect("file:" + db.as_posix() + "?mode=ro", uri=True, timeout=5)
    except sqlite3.Error:
        return []
    try:
        rows = con.execute(
            "select id, content, media_type, quoted_message_id, timestamp "
            "from messages where chat_jid = ? and is_from_me = ? "
            "and cast(strftime('%s', timestamp) as integer) >= ? "
            "order by strftime('%s', timestamp)",
            (channel["jid"], inbound, int(since_epoch)),
        ).fetchall()
    except sqlite3.Error:
        logging.exception("approval poll failed")
        return []
    finally:
        con.close()
    out = []
    for mid, content, media, quoted, ts in rows:
        text = (content or "").strip()
        if media == "reaction":
            # A reaction only counts as an answer to THIS card.
            if card_id and quoted and quoted != card_id:
                continue
            out.append((mid, text, True))
        else:
            if text.startswith(AGENT_PREFIX):  # the agent's own send in the group
                continue
            if text:
                out.append((mid, text, False))
    return out


def _classify(text: str, is_reaction: bool) -> str | None:
    if is_reaction:
        emoji = text.replace("️", "")
        if emoji in {e.replace("️", "") for e in REACT_ALWAYS}:
            return "always"
        if emoji in {e.replace("️", "") for e in REACT_DENY}:
            return "deny"
        if emoji in {e.replace("️", "") for e in REACT_ONCE}:
            return "once"
        return None
    body = " ".join(text.split()).strip().lower().rstrip("!.")
    if body in ALWAYS:
        return "always"
    if body in ONCE:
        return "once"
    if body in DENY:
        return "deny"
    return None


def _memo_key(request: dict) -> str:
    return json.dumps(
        [request.get("tool_name"), request.get("input")],
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


def ask(request: dict, context: str = "", timeout: float = APPROVAL_TIMEOUT) -> dict:
    """Put a blocked action to the owner and wait for the answer.

    Returns {"response": <control_response payload>, "consumed": [row ids],
             "verdict": once|always|deny|timeout|undeliverable}. `consumed`
    must be marked processed by the caller, otherwise the owner's "1" is
    picked up a second time as a fresh command.
    """
    key = _memo_key(request)
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
    started = time.time()
    # A second of slack: the card's own row must not be re-read as an answer,
    # but the owner's reply can land in the same DB second.
    since = started - 1

    verdict = None
    consumed: list[str] = []
    while time.time() - started < timeout:
        time.sleep(POLL)
        for mid, body, is_reaction in _rows_after(channel, since, card_id):
            if mid == card_id or mid in consumed:
                continue
            call = _classify(body, is_reaction)
            if call is None:
                continue  # unrelated message — leave it to be a normal command
            consumed.append(mid)
            verdict = call
            break
        if verdict:
            break

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
    _log({"verdict": verdict, "tool": request.get("tool_name"),
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
# watcher spots the denial in the tool result, asks, and on approval writes
# the rule into .claude/settings.local.json itself (a plain file write from
# the watcher process — no classifier stands between python and a JSON file).
# ---------------------------------------------------------------------------
CLASSIFIER_MARKERS = (
    "denied by the Claude Code auto mode classifier",
    "Blocked by classifier",
)
LOCAL_SETTINGS = ROOT / ".claude" / "settings.local.json"


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


def add_local_rule(rule: dict) -> bool:
    """Persist one allow-rule to .claude/settings.local.json."""
    try:
        data = json.loads(LOCAL_SETTINGS.read_text(encoding="utf-8"))
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
        LOCAL_SETTINGS.parent.mkdir(parents=True, exist_ok=True)
        LOCAL_SETTINGS.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError:
        logging.exception("could not write %s", LOCAL_SETTINGS)
        return False
    _log({"verdict": "rule-added", "rule": entry})
    return True


def ask_after_denial(tool: str, tool_input: dict, context: str = "",
                     timeout: float = APPROVAL_TIMEOUT) -> dict:
    """Card for a classifier denial. Approval writes the rule and asks for a
    retry; the rule also survives into every future run."""
    rule = derive_rule(tool, tool_input)
    request = {
        "tool_name": tool,
        "input": tool_input,
        "decision_reason": "נחסם ע\"י מסווג ההרשאות האוטומטי",
        "permission_suggestions": (
            [{"type": "addRules", "rules": [rule], "behavior": "allow",
              "destination": "localSettings"}] if rule else []
        ),
    }
    outcome = ask(request, context=context, timeout=timeout)
    verdict = outcome["verdict"]
    if verdict in ("once", "always", "memo") and rule:
        add_local_rule(rule)
    outcome["retry"] = verdict in ("once", "always", "memo")
    return outcome


def control_response(request_id: str, inner: dict) -> str:
    """The exact line the CLI is waiting for on stdin."""
    return json.dumps({
        "type": "control_response",
        "response": {"subtype": "success", "request_id": request_id,
                     "response": inner},
    }, ensure_ascii=False) + "\n"
