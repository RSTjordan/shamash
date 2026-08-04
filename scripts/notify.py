#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The single outbound path for PROACTIVE notifications to the owner.

Why this file exists: a background script that hand-rolls its own bridge POST
will keep pointing at whatever chat existed when it was written, long after
the owner has moved to a better one. So: background scripts must NEVER build
their own send. Call notify() and it goes where the owner actually reads.

Order: the contact channel first when enabled (a separate WhatsApp identity —
its message is a real incoming bubble with a real push notification), the main
channel as the fallback if the contact bridge is down or the send cannot be
verified. "Sent" means the bridge accepted it AND the message row shows up in
that bridge's messages.db — an HTTP 200 alone is not delivery; the bridge can
accept a payload and still fail to hand it to WhatsApp, and the only witness
is the database.

CLI (for testing the path end to end):
    python scripts/notify.py "text"            # normal: contact, main only on failure
    python scripts/notify.py --both "text"     # deliberately every channel
    python scripts/notify.py --file d.txt      # body from a UTF-8 file — use this
                                               # for anything long or multi-line
                                               # (a digest through a shell argument
                                               # is one stray quote from mangled)
"""
import argparse
import datetime
import json
import pathlib
import shutil
import sqlite3
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import config

CFG = config.load()
LOG_FILE = CFG["paths"]["logs"] / "notify.log"
OUTBOX = pathlib.Path(CFG["outbox"])


def _build_channels(cfg):
    """Ordered send list from the active channels: contact first, main after.

    Recipient per channel: on the contact channel the agent IS the other party,
    so it messages the owner's own JID. On the main channel (the owner's own
    account) the message goes to the shared group when one is configured, and
    to the self-chat otherwise.
    """
    group_jid = cfg["channels"]["main"].get("group_jid") or ""
    channels = []
    for name in ("contact", "main"):
        ch = cfg["active_channels"].get(name)
        if not ch:
            continue
        if name == "contact":
            jid = cfg["self_jid"]
        else:
            jid = group_jid or cfg["self_jid"]
        channels.append({
            "name": name,
            "api": ch["api"] + "/send",
            "token": ch["token"],
            "db": ch["db"],
            "jid": jid,
            "header": ch["header"],  # empty on contact (the sender IS the agent)
            "is_from_me": ch["is_from_me"],
        })
    return channels


# Ordered: primary first. approvals.py reads this list to find the channel a
# card was delivered on.
CHANNELS = _build_channels(CFG)

VERIFY_TIMEOUT = 12.0  # seconds to wait for the row to appear in messages.db
VERIFY_POLL = 1.0


def log(msg):
    """Append to the notify log. Never let logging break a notification."""
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().isoformat(timespec="seconds")
    line = "[{}] {}\n".format(stamp, msg)
    for _ in range(5):  # concurrent runs share the file; Windows locks it
        try:
            with LOG_FILE.open("a", encoding="utf-8") as fh:
                fh.write(line)
            return
        except OSError:
            time.sleep(0.2)


def _post(channel, text, quote=None):
    token = pathlib.Path(channel["token"]).read_text(encoding="utf-8").strip()
    payload = {"recipient": channel["jid"], "message": channel["header"] + text}
    if quote:
        payload["quoted_message_id"], payload["quoted_sender_jid"], payload["quoted_content"] = quote
    req = urllib.request.Request(
        channel["api"], data=json.dumps(payload).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + token},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _verify(channel, text):
    """True once the outgoing row is actually in that bridge's messages.db."""
    needle = (channel["header"] + text)[:60]
    db = pathlib.Path(channel["db"])
    deadline = time.time() + VERIFY_TIMEOUT
    while time.time() < deadline:
        try:
            con = sqlite3.connect("file:" + db.as_posix() + "?mode=ro", uri=True, timeout=5)
            try:
                row = con.execute(
                    "SELECT id FROM messages WHERE chat_jid=? AND is_from_me=1 "
                    "AND substr(content,1,60)=? ORDER BY timestamp DESC LIMIT 1",
                    (channel["jid"], needle),
                ).fetchone()
            finally:
                con.close()
            if row:
                return row[0]
        except sqlite3.Error:
            pass
        time.sleep(VERIFY_POLL)
    return None


def _post_file(channel, path, caption=None):
    token = pathlib.Path(channel["token"]).read_text(encoding="utf-8").strip()
    payload = {"recipient": channel["jid"], "media_path": str(path)}
    # The header would become the caption; on the contact channel it is empty,
    # and on the main channel it is the loop-breaker the framing patch expects.
    if caption or channel["header"]:
        payload["message"] = (channel["header"] + (caption or "")).strip()
    req = urllib.request.Request(
        channel["api"], data=json.dumps(payload).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + token},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:  # uploads are slower
        return json.loads(resp.read().decode("utf-8"))


def _verify_file(channel, path):
    """Media rows carry a filename rather than the text, so verify on that."""
    name = pathlib.Path(path).name
    db = pathlib.Path(channel["db"])
    deadline = time.time() + VERIFY_TIMEOUT
    while time.time() < deadline:
        try:
            con = sqlite3.connect("file:{}?mode=ro".format(db), uri=True, timeout=5)
            try:
                row = con.execute(
                    "SELECT id FROM messages WHERE chat_jid=? AND is_from_me=1 "
                    "AND filename LIKE ? ORDER BY timestamp DESC LIMIT 1",
                    (channel["jid"], "%" + name),
                ).fetchone()
            finally:
                con.close()
            if row:
                return row[0]
        except sqlite3.Error:
            pass
        time.sleep(VERIFY_POLL)
    return None


def send_file(path, caption=None, both=False):
    """Send a FILE to the owner through the same ordered channels as notify().

    Exists because the agent's MCP send_file only sees one account, so without
    this every screenshot and document lands wherever that account happens to
    point. Same rule as text: it is sent only once the row appears in that
    bridge's messages.db.
    """
    path = pathlib.Path(path).resolve()
    if not path.exists():
        log("send_file: no such file {}".format(path))
        return [{"channel": None, "sent": False, "verified": False,
                 "detail": "file not found: {}".format(path)}]
    # The bridge only reads media from its allowed roots — a deliberate control
    # so it can't be turned into a general file-read primitive. So stage the
    # file into the outbox rather than asking the bridge to relax, and keep the
    # original filename because that is what the recipient sees.
    if OUTBOX not in path.parents:
        OUTBOX.mkdir(parents=True, exist_ok=True)
        staged = OUTBOX / path.name
        if staged.resolve() != path:
            shutil.copy2(path, staged)
        path = staged
    results = []
    for channel in CHANNELS:
        try:
            resp = _post_file(channel, path, caption=caption)
            ok = bool(resp.get("success", True))
            detail = resp.get("message", "")
        except (urllib.error.URLError, OSError, ValueError, TimeoutError) as exc:
            ok, detail = False, str(exc)
        msg_id = _verify_file(channel, path) if ok else None
        results.append({"channel": channel["name"], "sent": ok,
                        "verified": bool(msg_id), "id": msg_id, "detail": detail})
        log("{}: file={} sent={} verified={} {}".format(
            channel["name"], path.name, ok, bool(msg_id), detail))
        if ok and msg_id and not both:
            break
    if not any(r["verified"] for r in results):
        log("ALL CHANNELS FAILED for file " + str(path))
    return results


def notify(text, quote=None, both=False):
    """Send `text` to the owner. Returns a list of per-channel result dicts.

    Falls through to the next channel whenever a send fails OR cannot be
    verified, so a dead bridge degrades to the backup door instead of to
    silence. With both=True every channel gets it (for anything critical).
    """
    results = []
    for channel in CHANNELS:
        try:
            resp = _post(channel, text, quote=quote)
            ok = bool(resp.get("success", True))
            detail = resp.get("message", "")
        except (urllib.error.URLError, OSError, ValueError, TimeoutError) as exc:
            ok, detail = False, str(exc)
        msg_id = _verify(channel, text) if ok else None
        results.append({"channel": channel["name"], "sent": ok,
                        "verified": bool(msg_id), "id": msg_id, "detail": detail})
        log("{}: sent={} verified={} {}".format(channel["name"], ok, bool(msg_id), detail))
        if ok and msg_id and not both:
            break
    if not any(r["verified"] for r in results):
        log("ALL CHANNELS FAILED: " + text[:120].replace("\n", " "))
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("text", nargs="?")
    ap.add_argument("--file", help="read the body from this UTF-8 file (for long/multi-line text)")
    ap.add_argument("--send-file", help="send this FILE (image/pdf/doc) instead of text")
    ap.add_argument("--both", action="store_true")
    args = ap.parse_args()
    if args.send_file:
        results = send_file(args.send_file, caption=args.text, both=args.both)
        print(json.dumps(results, ensure_ascii=False))
        return 0 if any(r["verified"] for r in results) else 1
    if args.file:
        text = pathlib.Path(args.file).read_text(encoding="utf-8").strip()
    elif args.text:
        text = args.text
    else:
        ap.error("give TEXT or --file")
    if not text:
        ap.error("refusing to send an empty message")
    results = notify(text, both=args.both)
    print(json.dumps(results, ensure_ascii=False))
    return 0 if any(r["verified"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
