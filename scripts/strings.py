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
    "card_once": "👍 = allow this once (react here)",
    "card_always": "❤️ = always — saves a permanent rule ({rules})",
    "card_deny": "👎 = deny",
    "card_hint": "_(replying 1 / always / 0 works too)_",
    "card_rules": "_\"always\" saves a permanent rule: {rules}_",
    "poll_expired": "⏱ This expired — ask me again if still needed.",
    "poll_approve_q": "Approve? — {tool}",
    "opt_allow_once": "Allow once",
    "opt_always": "Always",
    "opt_deny": "Deny",
    "tp_confirm_q": "🖥️ Continue *{repo}* — {desc} (last active {age} ago)?",
    "tp_open_warn": " ⚠️ This session looks open at the desk — teleporting forks it; typing at the desk afterwards won't reach this copy.",
    "tp_continue": "Continue",
    "tp_pick_other": "Pick another",
    "tp_cancel": "Cancel",
    "tp_pick_q": "🖥️ Which session? (⚠️ = looks open at the desk — teleporting forks it; typing there afterwards won't reach this copy)",
    "tp_busy": "🖥️ A teleport into *{repo}* is already running — say *{release}* first, then ask again.",
    "tp_spawn_failed": "🖥️ Couldn't start the teleport into *{repo}* — its folder is missing, or the session wouldn't start. Nothing changed here; ask again to retry.",
    "tp_enter": "🖥️ Teleported into *{repo}*. Everything you send here goes to that session now. Say *{release}* to come back.",
    "tp_exit": "🖥️ Released *{repo}*. Resume at the desk with:\n`claude --resume {sid}`",
    "tp_exit_idle": "🖥️ Released *{repo}* after {mins} minutes of quiet. Resume at the desk with:\n`claude --resume {sid}`",
    "tp_exit_crash": "🖥️ The *{repo}* session crashed and was released. The transcript survived — resume at the desk with:\n`claude --resume {sid}`",
    "tp_dropped": "🖥️ A teleport into *{repo}* was pending/active when I restarted — dropped it. Resume at the desk with:\n`claude --resume {sid}`, or teleport again.",
    "tp_stale_request": "🖥️ Found a teleport request older than {mins} minutes — discarded it. Ask again if you still want it.",
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
    "card_once": "👍 = לאשר פעם אחת (ריאקציה כאן)",
    "card_always": "❤️ = תמיד — נשמר ככלל קבוע ({rules})",
    "card_deny": "👎 = לדחות",
    "card_hint": "_(אפשר גם לענות 1 / תמיד / 0)_",
    "card_rules": "_תמיד = נשמר ככלל קבוע: {rules}_",
    "poll_expired": "⏱ פג תוקף — שלחו שוב אם עדיין רלוונטי.",
    "poll_approve_q": "לאשר? — {tool}",
    "opt_allow_once": "אישור",
    "opt_always": "תמיד",
    "opt_deny": "דחייה",
    "tp_confirm_q": "🖥️ להמשיך את *{repo}* — {desc} (פעיל לפני {age})?",
    "tp_open_warn": " ⚠️ נראה שהסשן פתוח במחשב — טלפורט מפצל אותו; מה שיוקלד שם אחר כך לא יגיע לעותק הזה.",
    "tp_continue": "המשך",
    "tp_pick_other": "בחר אחר",
    "tp_cancel": "ביטול",
    "tp_pick_q": "🖥️ איזה סשן? (⚠️ = נראה פתוח במחשב — טלפורט מפצל אותו, ומה שיוקלד שם אחר כך לא יגיע לעותק הזה)",
    "tp_busy": "🖥️ כבר רץ טלפורט ל-*{repo}*. כדי לעבור לסשן אחר צריך קודם לכתוב *{release}*.",
    "tp_spawn_failed": "🖥️ לא הצלחתי להתחיל טלפורט ל-*{repo}* — התיקייה חסרה או שהסשן לא עלה. שום דבר לא השתנה כאן, אפשר לבקש שוב.",
    "tp_enter": "🖥️ טלפורט ל-*{repo}*. כל מה שתשלחו כאן עובר עכשיו לסשן הזה. כתבו *{release}* כדי לחזור.",
    "tp_exit": "🖥️ שוחרר *{repo}*. להמשיך במחשב:\n`claude --resume {sid}`",
    "tp_exit_idle": "🖥️ שוחרר *{repo}* אחרי {mins} דקות של שקט. להמשיך במחשב:\n`claude --resume {sid}`",
    "tp_exit_crash": "🖥️ הסשן של *{repo}* קרס ושוחרר. התמליל נשמר — להמשיך במחשב:\n`claude --resume {sid}`",
    "tp_dropped": "🖥️ טלפורט ל-*{repo}* היה פעיל/ממתין כשעליתי מחדש — בוטל. להמשיך במחשב:\n`claude --resume {sid}`, או לבקש טלפורט שוב.",
    "tp_stale_request": "🖥️ נמצאה בקשת טלפורט ישנה מ-{mins} דקות — בוטלה. בקשו שוב אם עדיין רלוונטי.",
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
