"""The kit's own voice, in the owner's language.

Everything the KIT itself says into the owner's WhatsApp — acks, notices,
approval cards — comes from this table. The agent's replies are already in
the owner's language because the prompts demand it; this file closes the gap
for the fixed strings around them.

Scope rule: only strings the OWNER reads belong here. Deny/timeout messages
returned to the agent's CLI stay English in their callers — they are
instructions to the model, not chat.

Adding a language is one dict. An unknown `owner.reply_language` (or a
missing key in a translation) falls back to English, so a config typo
degrades politely instead of breaking a send.
"""

import config

_ENGLISH = {
    "on_it": "On it…",
    "steer_ack": "Folding that into the current task…",
    "voice_message": "voice message",
    "failure_notice": "I couldn't complete this command. Try again or rephrase.",
    "skip_notice": (
        "Found {count} old message(s) from system downtime — skipped them. "
        "Resend whatever is still relevant."
    ),
    "card_title": "🔒 *Action blocked — needs your approval*",
    "card_for": "For: {context}",
    "card_once": "👍 = allow this once",
    "card_always": "❤️ = always — saves a permanent rule ({rules})",
    "card_deny": "👎 = deny",
    "card_hint": "_(replying 1 / always / 0 works too)_",
    "poll_expired": "⏱ This expired — ask me again if still needed.",
}

_HEBREW = {
    "on_it": "על זה…",
    "steer_ack": "משלב את זה במשימה הנוכחית…",
    "voice_message": "הודעה קולית",
    "failure_notice": "לא הצלחתי להשלים את הפקודה. נסו שוב או נסחו אחרת.",
    "skip_notice": (
        "מצאתי {count} הודעות ישנות מזמן שהמערכת הייתה כבויה — דילגתי עליהן. "
        "שלחו שוב את מה שעדיין רלוונטי."
    ),
    "card_title": "🔒 *פעולה נחסמה — צריך את האישור שלך*",
    "card_for": "עבור: {context}",
    "card_once": "👍 = לאשר פעם אחת",
    "card_always": "❤️ = תמיד — נשמר ככלל קבוע ({rules})",
    "card_deny": "👎 = לדחות",
    "card_hint": "_(אפשר גם לענות 1 / תמיד / 0)_",
    "poll_expired": "⏱ פג תוקף — שלחו שוב אם עדיין רלוונטי.",
}

_TABLES = {"english": _ENGLISH, "hebrew": _HEBREW}


def t(key: str, **fmt) -> str:
    """The string for `key` in the owner's reply language, formatted."""
    try:
        lang = str(config.load()["owner"].get("reply_language", "")).strip().lower()
    except Exception:  # no/broken config — never let a send die over a string
        lang = ""
    table = _TABLES.get(lang, _ENGLISH)
    text = table.get(key) or _ENGLISH[key]
    return text.format(**fmt) if fmt else text
