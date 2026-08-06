"""Single source of truth for everything that differs between installations.

Nothing else in this codebase is allowed to hardcode a path, a phone number, a
chat id or a person's name. If you find yourself typing one into another file,
it belongs here instead.

Two rules that keep updates safe:

1. `config.json` is the USER's file. It is gitignored, created by the
   installer, and never overwritten by an update.
2. Everything under `prompts/` is the KIT's file. Those carry {{PLACEHOLDER}}
   tokens and are rendered at runtime by `render()` below — the user never
   edits them, so `git pull` can never conflict with their work.

The user's own words live in exactly one place: `brief/`. Generated once at
install time from the templates, then owned by them forever.
"""

import json
import os
import shutil
import sys
from pathlib import Path

# The repo root is derived, never configured: this file is <root>/scripts/config.py.
ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILE = ROOT / "config.json"

_cache = None


class ConfigError(RuntimeError):
    """Raised with a message meant to be read by a human, not a stack trace."""


DEFAULTS = {
    "agent_name": "Claude",
    "owner": {
        "name": "",
        "phone": "",
        "language": "English",
        "reply_language": "English",
        "timezone": "UTC",
    },
    "claude_exe": "",
    # The cost knob: the model (and effort) every agent run — watcher turns,
    # job shifts, scheduled scans — is started with.
    "model": "claude-opus-5",
    "effort": "high",
    "channels": {
        "main": {"enabled": True, "group_jid": "", "bridge_port": 8080},
        "contact": {"enabled": False, "bridge_port": 8081},
    },
    "features": {
        "voice_notes": False,
        "voice_model": "",  # empty = the voice scripts' built-in default
        "approvals": True,
        "teleport": False,
    },
    # Public default is "manual": every tool call outside the allowlist comes
    # back to the user as an approval card in WhatsApp. "auto" hands the
    # decision to the built-in safety classifier — faster, and a genuinely
    # different trade. See RISKS.md before changing it.
    "permission_mode": "manual",
    # Teleport (features.teleport): continuing a desk Claude Code session
    # from WhatsApp. Default off — it widens what the phone can reach to
    # any repo on this machine. See RISKS.md before enabling.
    "teleport": {"release_word": "release", "idle_minutes": 240,
                 "open_at_desk": True},
    # Read-only by default — RISKS.md promises that shell commands and file
    # writes come back as approval cards, and this list is what makes that
    # promise true. Every tool added here runs with NO card. The author runs
    # "Bash,PowerShell,Read,Write,Edit,Glob,Grep" on his own machine; widen
    # only knowing exactly which brake you removed.
    "allowed_tools": "Read,Glob,Grep",
    "schedule": {"scan_times": ["08:00", "20:00"]},
}


def _merge(base, override):
    """Deep-merge, so a config missing a new key still starts after an update."""
    out = dict(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def _find_claude_exe():
    """Locate claude.exe. Its location varies per install method, so we look
    rather than assume, and only fail once every candidate has missed."""
    found = shutil.which("claude") or shutil.which("claude.exe")
    if found:
        return found
    candidates = [
        Path.home() / ".local" / "bin" / "claude.exe",
        Path.home() / "AppData" / "Local" / "Programs" / "claude" / "claude.exe",
        Path(os.environ.get("PROGRAMFILES", "C:/Program Files")) / "claude" / "claude.exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return ""


def load(required=True):
    """Return the merged config. Cached: config is read once per process."""
    global _cache
    if _cache is not None:
        return _cache

    if not CONFIG_FILE.exists():
        if required:
            raise ConfigError(
                f"No config.json at {CONFIG_FILE}.\n"
                "This installation was never completed. Run the installer, or copy "
                "config.example.json to config.json and fill it in."
            )
        raw = {}
    else:
        try:
            raw = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ConfigError(f"config.json is not valid JSON — {exc}") from exc

    cfg = _merge(DEFAULTS, raw)

    if required:
        phone = str(cfg["owner"].get("phone") or "").strip()
        if not phone.isdigit():
            raise ConfigError(
                "owner.phone must be your number in international digits, no '+' "
                f"and no spaces (e.g. 447700900123). Got: {phone!r}"
            )
        if not cfg["owner"].get("name"):
            raise ConfigError("owner.name is empty — the agent needs to know who it works for.")

    if not cfg.get("claude_exe"):
        cfg["claude_exe"] = _find_claude_exe()

    # ---- derived values. Never stored, always computed, so they cannot drift.
    phone = str(cfg["owner"].get("phone") or "").strip()
    cfg["root"] = ROOT
    cfg["self_jid"] = f"{phone}@s.whatsapp.net" if phone else ""
    cfg["outbox"] = Path.home() / ".local" / "share" / "whatsapp-mcp" / "outbox"
    cfg["paths"] = {
        "state": ROOT / "state",
        "logs": ROOT / "logs",
        "tmp": ROOT / "state" / "tmp",
        "prompts": ROOT / "prompts",
        "brief": ROOT / "brief",
        "bridge": ROOT / "bridge",
        "jobs": ROOT / "jobs",
    }

    group_jid = cfg["channels"]["main"].get("group_jid") or ""
    main_port = cfg["channels"]["main"].get("bridge_port", 8080)
    contact_port = cfg["channels"]["contact"].get("bridge_port", 8081)

    # A chat list with no group is still valid — the self-chat alone works.
    main_chats = [jid for jid in (group_jid, cfg["self_jid"]) if jid]

    channels = {}
    if cfg["channels"]["contact"].get("enabled"):
        channels["contact"] = {
            "api": f"http://127.0.0.1:{contact_port}/api",
            "store": ROOT / "bridge" / "contact-bridge" / "store",
            "marker": ROOT / "state" / "last_contact.json",
            "chat_jids": [cfg["self_jid"]],
            # On the contact's own account, the owner's messages arrive as
            # somebody else's — the mirror image of the main channel.
            "is_from_me": 0,
            "header": "",
            "system_delivers_reply": True,
            "typing_ack": True,
        }
    if cfg["channels"]["main"].get("enabled", True):
        channels["main"] = {
            "api": f"http://127.0.0.1:{main_port}/api",
            "store": ROOT / "bridge" / "whatsapp-bridge" / "store",
            "marker": ROOT / "state" / "last_command.json",
            "chat_jids": main_chats,
            # The owner's own account: commands are his own outgoing messages.
            "is_from_me": 1,
            "header": f"\U0001f916 *{cfg['agent_name']}*\n\n",
            "system_delivers_reply": False,
            "typing_ack": False,
        }
    for channel in channels.values():
        channel["token"] = channel["store"] / ".bridge-token"
        channel["db"] = channel["store"] / "messages.db"
    cfg["active_channels"] = channels

    _cache = cfg
    return cfg


# Fixed digest section labels per reply language. Fixed on purpose: letting the
# model re-translate the labels each scan makes every digest look different.
# Languages without a table fall back to a translate-consistently instruction.
_DIGEST_LABELS = {
    "he": (
        "✅ מה נסגר · 📅 נקבע ביומן · ⚠️ צריך אותך · 📧 מיילים · "
        "ℹ️ מה סונן · 🧰 עבודות רקע · ובבוקר: 📅 היום ביומן · "
        "⏳ מחכים לך · 🔄 נשאר מאתמול"
    ),
    "en": (
        "✅ Done · 📅 Booked · ⚠️ Needs you · 📧 Mail · "
        "ℹ️ Noise skipped · 🧰 Jobs · and mornings: 📅 Today's calendar · "
        "⏳ Waiting on you · 🔄 Carried over"
    ),
}


def _digest_labels(reply_language):
    lang = str(reply_language).strip().lower()
    if lang in ("he", "hebrew", "עברית") or "hebrew" in lang or "עברית" in lang:
        return _DIGEST_LABELS["he"]
    if lang in ("en", "english") or "english" in lang:
        return _DIGEST_LABELS["en"]
    return (
        f"translate the English section names into {reply_language} yourself, "
        "and use the SAME translation every scan"
    )


_TELEPORT_RULE = """4e. TELEPORT: when {OWNER} asks to continue a desk
   Claude Code session from here ("teleport into <repo>", "continue the
   session where we were building X", or any clear continue-that-session
   intent), your FIRST action — before any text, any other tool, any
   question — is running:
     py -3 scripts/teleport.py --request "<their hint, in your words>" --channel {CHANNEL} --jid <the chat jid noted next to the command>
   with a shell tool timeout of at least 300000 ms. The script itself
   shows {OWNER} the matching desk sessions as a poll and waits for the
   tap — that poll IS the whole interface; anything you send around it
   is noise. The --jid is the chat THIS command arrived in (each command
   line above names it, "in chat ...") — every announcement about the
   teleport is sent there, so it must not be guessed. The script prints
   JSON when done. If "requested" is true, reply with one short line
   that it is starting — the system announces the rest. If false, relay
   the "reason" in one line and stop: do not investigate config, feature
   flags, or logs on your own."""


def _teleport_rule(cfg):
    """The teleport prompt rule exists only on installs that enabled the
    feature — on the rest the agent must not know to offer it. The owner
    name is substituted HERE, not via a {{TOKEN}}: render() does one
    .replace per placeholder over the same string, so a {{TOKEN}} injected
    by an earlier substitution is never itself rendered."""
    if not cfg.get("features", {}).get("teleport"):
        return ""
    return _TELEPORT_RULE.replace("{OWNER}", cfg["owner"]["name"])


def placeholders(cfg=None):
    """The token table shared by prompt rendering and the install templates."""
    cfg = cfg or load()
    main = cfg["channels"]["main"]
    return {
        "AGENT_NAME": cfg["agent_name"],
        "OWNER_NAME": cfg["owner"]["name"],
        "OWNER_PHONE": str(cfg["owner"]["phone"]),
        "OWNER_LANGUAGE": cfg["owner"]["language"],
        "REPLY_LANGUAGE": cfg["owner"]["reply_language"],
        "DIGEST_LABELS": _digest_labels(cfg["owner"]["reply_language"]),
        "TELEPORT_RULE": _teleport_rule(cfg),
        "TIMEZONE": cfg["owner"]["timezone"],
        "SELF_JID": cfg["self_jid"],
        "GROUP_JID": main.get("group_jid", ""),
        "PROJECT_ROOT": str(cfg["root"]),
        "OUTBOX": str(cfg["outbox"]),
    }


def render(text, cfg=None):
    """Substitute {{TOKENS}} in a kit-owned template.

    An unknown token is left untouched on purpose: a typo should show up in the
    output as `{{WHOOPS}}` rather than silently becoming an empty string and
    quietly changing what the agent was told to do.
    """
    cfg = cfg or load()
    for key, value in placeholders(cfg).items():
        text = text.replace("{{" + key + "}}", str(value))
    return text


def read_prompt(name, cfg=None):
    """Load a kit prompt and render it. `name` is a filename under prompts/."""
    cfg = cfg or load()
    path = cfg["paths"]["prompts"] / name
    if not path.exists():
        raise ConfigError(f"Missing prompt file: {path}")
    return render(path.read_text(encoding="utf-8"), cfg)


def main():
    """`python scripts/config.py` prints the resolved config — the first thing
    to run when something behaves as though it were installed for somebody else."""
    try:
        cfg = load()
    except ConfigError as exc:
        print(f"CONFIG ERROR\n{exc}", file=sys.stderr)
        return 1
    printable = {
        "agent_name": cfg["agent_name"],
        "owner": cfg["owner"],
        "root": str(cfg["root"]),
        "self_jid": cfg["self_jid"],
        "claude_exe": cfg["claude_exe"] or "NOT FOUND",
        "permission_mode": cfg["permission_mode"],
        "features": cfg["features"],
        "channels": sorted(cfg["active_channels"]),
    }
    print(json.dumps(printable, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
