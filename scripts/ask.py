#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The single egress for ASKING the owner a multi-choice question.

notify.py's rule, extended: background code must never hand-roll a poll
POST, for the same reason it must never hand-roll a send — it would keep
pointing at whatever chat existed when it was written. Call ask() and the
question goes where the owner actually reads, as a native WhatsApp poll
(one tap, no keyboard), and the answer comes back as data.

Three answer forms are accepted, checked every poll cycle:
  - a poll VOTE (media_type="poll_vote" row quoting the poll),
  - a REACTION on the poll message or any id in also_watch_ids
    (classified only through reaction_aliases — a bare 👍 on a generic
    picker means nothing; approvals passes its emoji sets),
  - TEXT: a bare option number, the exact option text, or an alias.

Timeout is an answer too: chosen=None, plus a quoted "expired" notice on
the poll so a late tap is never a silent black hole. If the poll cannot
be POSTed at all (bridge without the patch, dead bridge, a surface the
install marked poll-incapable in state/poll-surfaces.json), the fallback
is a numbered text message — unless text_fallback=False, for callers
whose accompanying message already IS the numbered legend (approvals).

While waiting, state/ask-open.json is touched every cycle; the watcher
holds its turn clocks while that marker is fresh — an open question to a
human is never a wedge. Marker writes are best-effort: concurrent askers
share the path on Windows, and a missed touch costs one clock cycle.
"""
import argparse
import json
import pathlib
import sqlite3
import sys
import time
import urllib.request

# The answer comes back in whatever language the poll was written in. On a
# Windows console that is cp1252, so printing a Hebrew option crashed the
# script AFTER the tap had already been consumed — the vote survived only in
# notify.log. The caller must never lose an answer to the console codepage.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import config
import notify
import strings

CFG = config.load()
MARKER = CFG["paths"]["state"] / "ask-open.json"
SURFACES_FILE = CFG["paths"]["state"] / "poll-surfaces.json"

POLL = 2.0
MAX_OPTIONS = 12
OPTION_MAX = 100
QUESTION_MAX = 255


def _prepare_options(options):
    """Truncate BEFORE the bridge hashes, and make labels unique — votes
    come back as hashes of the label bytes, so duplicates are
    indistinguishable."""
    options = [str(o).strip() for o in options if str(o).strip()]
    if not 1 <= len(options) <= MAX_OPTIONS:
        raise ValueError(f"1..{MAX_OPTIONS} options required, got {len(options)}")
    out = [o[:OPTION_MAX] for o in options]
    if len(set(out)) != len(out):
        out = [f"{i + 1}) {o}"[:OPTION_MAX] for i, o in enumerate(out)]
    return out


def _clamp_selectable(n, option_count):
    try:
        n = int(n)
    except (TypeError, ValueError):
        return 1
    if not 1 <= n <= option_count:
        return 1
    return n


def _classify_vote(body, options):
    """A vote's content is the chosen labels joined with ", " — but a label
    may itself contain ", ", so an exact match against the options the poll
    was actually sent with (the PREPARED list: what the bridge hashed, and
    so what comes back) wins before any splitting. Empty content is a
    CLEARED vote, not an answer: None."""
    body = (body or "").strip()
    if not body:
        return None
    return body if body in options else body.split(", ")[0]


def _strip_vs(emoji):
    return (emoji or "").replace("\ufe0f", "")


def _classify_reaction(emoji, reaction_aliases):
    if not reaction_aliases:
        return None
    bare = _strip_vs(emoji)
    for label, emojis in reaction_aliases.items():
        if bare in {_strip_vs(e) for e in emojis}:
            return label
    return None


def _classify_text(text, options, text_aliases):
    """Aliases FIRST: approvals' legacy keyword sets contain "1"/"2"/"0",
    and positional digits would map "2" to the wrong option on a
    two-option card. Then bare positional digits, then exact option
    text."""
    body = " ".join((text or "").split()).strip().lower().rstrip("!.")
    if not body:
        return None
    for label, aliases in (text_aliases or {}).items():
        if body in {a.strip().lower() for a in aliases}:
            return label
    if body.isdigit():
        i = int(body)
        if 1 <= i <= len(options):
            return options[i - 1]
        return None
    for opt in options:
        if body == opt.strip().lower():
            return opt
    return None


def _send_text(channel, text, quote=None):
    """One channel, notify's own post+verify primitives — NEVER
    notify.notify()'s ordered fallback: a named-channel caller bound the
    conversation to that chat, and a picker legend falling through to a
    shared group is a privacy leak. Returns the message id or None."""
    try:
        resp = notify._post(channel, text, quote=quote)
        ok = bool(resp.get("success", True))
    except Exception as exc:
        notify.log(f"ask: text send failed on {channel['name']}: {exc}")
        return None
    if not ok:
        return None
    return notify._verify(channel, text)


def _poll_sender_jid(channel, poll_id):
    """The poll row's sender, as a full JID — the right quoted_sender for
    notices about the poll (on the contact channel the sender is the
    agent's own account, not the owner)."""
    try:
        con = sqlite3.connect(
            f"file:{pathlib.Path(channel['db']).as_posix()}?mode=ro",
            uri=True, timeout=5)
        try:
            row = con.execute("SELECT sender FROM messages WHERE id=?",
                              (poll_id,)).fetchone()
        finally:
            con.close()
        if row and row[0]:
            return f"{row[0]}@s.whatsapp.net"
    except sqlite3.Error:
        pass
    return CFG["self_jid"]


def _poll_capable(channel_name, surfaces=None):
    """Missing file or key = optimistic true; the POST failure path still
    catches a wrong guess (it just costs one failed request)."""
    if surfaces is None:
        try:
            surfaces = json.loads(SURFACES_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            surfaces = {}
    return bool(surfaces.get(channel_name, True))


def _touch_marker(channel_name, poll_id):
    try:
        MARKER.write_text(json.dumps(
            {"channel": channel_name, "poll_id": poll_id, "ts": time.time()}
        ), encoding="utf-8")
    except OSError:
        pass  # best-effort by design


def _clear_marker():
    try:
        MARKER.unlink()
    except OSError:
        pass


def _post_poll(channel, question, options, selectable_count):
    """POST /api/poll on this channel's bridge. Returns message_id or None."""
    base = channel["api"].rsplit("/", 1)[0]  # ".../api/send" -> ".../api"
    try:
        token = pathlib.Path(channel["token"]).read_text(encoding="utf-8").strip()
        req = urllib.request.Request(
            base + "/poll",
            data=json.dumps({
                "recipient": channel["jid"], "question": question,
                "options": options, "selectable_count": selectable_count,
            }).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json",
                     "Authorization": "Bearer " + token},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # any failure = this surface can't poll now
        notify.log(f"ask: poll POST failed on {channel['name']}: {exc}")
        return None
    if not body.get("success") or not body.get("message_id"):
        notify.log(f"ask: poll rejected on {channel['name']}: {body}")
        return None
    return body["message_id"]


def _verify_poll_row(channel, poll_id):
    """The bridge's 200 is not delivery; the row in messages.db is."""
    db = pathlib.Path(channel["db"])
    deadline = time.time() + 12.0
    while time.time() < deadline:
        try:
            con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True, timeout=5)
            try:
                row = con.execute(
                    "SELECT id FROM messages WHERE id=? AND media_type='poll'",
                    (poll_id,)).fetchone()
            finally:
                con.close()
            if row:
                return True
        except sqlite3.Error:
            pass
        time.sleep(1.0)
    return False


def _answer_rows(channel, since_epoch, watch_ids):
    """Owner-side rows since the poll went out: votes on watch_ids,
    reactions on watch_ids, and plain text. Skips the watched rows
    themselves by id — on the main channel the poll row is is_from_me
    with NO header, so only the id check keeps the question from
    answering itself."""
    db = pathlib.Path(channel["db"])
    try:
        con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True, timeout=5)
    except sqlite3.Error:
        return []
    try:
        rows = con.execute(
            "SELECT id, content, media_type, quoted_message_id, filename "
            "FROM messages WHERE chat_jid = ? AND is_from_me = ? "
            "AND CAST(strftime('%s', timestamp) AS INTEGER) >= ? "
            "ORDER BY strftime('%s', timestamp)",
            (channel["jid"], channel["is_from_me"], int(since_epoch)),
        ).fetchall()
    except sqlite3.Error:
        notify.log("ask: answer poll query failed")
        return []
    finally:
        con.close()
    out = []
    header = channel.get("header") or ""
    for mid, content, media, quoted, fname in rows:
        if mid in watch_ids:
            continue
        text = (content or "").strip()
        if media == "poll_vote":
            if quoted in watch_ids or fname in watch_ids:
                out.append((mid, text, "vote"))
        elif media == "reaction":
            if fname in watch_ids:
                out.append((mid, text, "reaction"))
        elif not media:
            if header and text.startswith(header.strip().split("\n")[0]):
                continue  # the agent's own framed send on this channel
            if text:
                out.append((mid, text, "text"))
    return out


def _scan_since(explicit, started):
    """The epoch answers are scanned from, with 1s of DB-resolution slack.

    Default is ask()'s own send time. A caller whose accompanying message
    went out BEFORE the poll passes its send time instead — see ask()."""
    return (explicit if explicit is not None else started) - 1


def ask(question, options, timeout=900.0, selectable_count=1, channel=None,
        also_watch_ids=(), text_fallback=True, text_aliases=None,
        reaction_aliases=None, since=None, jid: str | None = None):
    """Send a poll and wait for the answer. See module docstring.

    `since` is the epoch to scan answers from; by default that is the moment
    the poll went out. Callers whose accompanying message went out BEFORE the
    poll (approvals' card, which is watched through `also_watch_ids`) pass
    their own send time — posting and verifying the poll row costs up to ~12s,
    and an answer landing in that window would otherwise fall before the scan
    origin and be permanently invisible.

    `jid` pins the question to ONE chat. Naming the channel is not enough:
    the main channel's canonical jid is the GROUP when one is configured,
    so a picker that enumerates what is on this machine — the teleport
    session list — would be posted to a shared chat. Callers that know
    which conversation they belong to pass it, and the recipient, the
    fallback legend, the expiry notice and the chat the answer is watched
    in all follow (they read `ch["jid"]` from the same dict)."""
    question = str(question).strip()[:QUESTION_MAX]
    options = _prepare_options(options)
    selectable_count = _clamp_selectable(selectable_count, len(options))

    if channel is not None:
        channels = [c for c in notify.CHANNELS if c["name"] == channel]
    else:
        channels = list(notify.CHANNELS)
    if not channels:
        return {"chosen": None, "answered_by": None, "channel": None,
                "poll_id": None, "consumed_ids": [], "fallback_used": False}
    if jid:
        # Shallow copies: notify.CHANNELS is module state shared by every
        # caller in this process, and one pinned question must not
        # re-address anybody else's. Every later use — _post_poll,
        # _send_text, _answer_rows, _poll_sender_jid — reads ch["jid"]
        # from the dict it is handed, so overriding it here is enough.
        channels = [dict(c, jid=jid) for c in channels]

    poll_id = None
    used = None
    fallback_used = False
    for ch in channels:
        if not _poll_capable(ch["name"]):
            continue
        pid = _post_poll(ch, question, options, selectable_count)
        if pid and _verify_poll_row(ch, pid):
            poll_id, used = pid, ch
            break

    if used is None:
        # Poll path unavailable on every allowed channel. The wait still
        # happens on the first allowed channel; the numbered legend goes
        # out only when the caller wants it — and only through THAT
        # channel (see _send_text's docstring for why never notify()).
        used = channels[0]
        if text_fallback:
            fallback_used = True
            legend = question + "\n" + "\n".join(
                f"{i + 1}. {o}" for i, o in enumerate(options))
            if not _send_text(used, legend):
                return {"chosen": None, "answered_by": None, "channel": None,
                        "poll_id": None, "consumed_ids": [],
                        "fallback_used": True}

    watch_ids = set(also_watch_ids)
    if poll_id:
        watch_ids.add(poll_id)
    started = time.time()  # the timeout clock — always from here
    since = _scan_since(since, started)
    chosen = None
    answered_by = None
    consumed = []
    try:
        while time.time() - started < timeout:
            _touch_marker(used["name"], poll_id)
            time.sleep(POLL)
            for mid, body, kind in _answer_rows(used, since, watch_ids):
                if mid in consumed:
                    continue
                if kind == "vote":
                    label = _classify_vote(body, options)
                    if label is None:
                        continue  # cleared vote — ignored by design
                    chosen, answered_by = label, "poll"
                elif kind == "reaction":
                    label = _classify_reaction(body, reaction_aliases)
                    if label is None:
                        continue
                    chosen, answered_by = label, "reaction"
                else:
                    label = _classify_text(body, options, text_aliases)
                    if label is None:
                        continue
                    chosen, answered_by = label, "text"
                consumed.append(mid)
                break
            if chosen is not None:
                break
    finally:
        _clear_marker()

    if chosen is None and poll_id:
        # A late tap must never be a silent black hole. Same channel as the
        # poll, quoting the poll, with the poll's own sender as the quoted
        # sender (on the contact channel that is the agent's account).
        if not _send_text(used, strings.t("poll_expired"),
                          quote=(poll_id, _poll_sender_jid(used, poll_id),
                                 question[:80])):
            notify.log("ask: expired notice failed")
    notify.log(f"ask: {used['name']} chosen={chosen!r} by={answered_by} "
               f"fallback={fallback_used}")
    return {"chosen": chosen, "answered_by": answered_by,
            "channel": used["name"], "poll_id": poll_id,
            "consumed_ids": consumed, "fallback_used": fallback_used}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("question")
    ap.add_argument("--option", action="append", required=True)
    ap.add_argument("--timeout", type=float, default=240.0)
    ap.add_argument("--channel", choices=["contact", "main"])
    ap.add_argument("--selectable-count", type=int, default=1)
    args = ap.parse_args()
    result = ask(args.question, args.option, timeout=args.timeout,
                 channel=args.channel, selectable_count=args.selectable_count)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["chosen"] is not None else 1


if __name__ == "__main__":
    sys.exit(main())
