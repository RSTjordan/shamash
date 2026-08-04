# Patch: frame agent messages (bridge/whatsapp-mcp-server/whatsapp.py)

On the main channel the agent sends messages from the owner's own account, so
without a visible marker the owner cannot tell the agent's messages from their
own. This patch enforces the frame in the send path — deterministic, unlike
asking the model to remember formatting.

Apply-time values `<from config>`: the agent's display name (`agent_name`),
the command group JID (`channels.main.group_jid`, if any), and the owner's
phone number. Write them as literals when applying — the MCP server cannot
import the kit's config module.

In `whatsapp-mcp-server/whatsapp.py`, directly above `def send_message(`, add:

    _AGENT_CHATS = ("<group_jid>", "<phone>@s.whatsapp.net", "<phone>")

    def _frame_agent_message(recipient, message):
        if recipient not in _AGENT_CHATS:
            return message
        lines = message.split("\n")
        while lines and lines[0].startswith("\U0001f916"):
            lines.pop(0)
            while lines and not lines[0].strip():
                lines.pop(0)
        return "\U0001f916 *<agent_name>*\n\n" + "\n".join(lines)

Then, as the first statement after the recipient validation inside
`send_message`, add:

    message = _frame_agent_message(recipient, message)

Two hard-won rules — keep them exactly:

- **Match the recipient by EXACT string, never by prefix.** A user-created
  group whose JID happens to start with the phone number must be untouched.
- **Strip a model-added header minimally**: only leading lines starting with
  the 🤖 marker plus the blank lines after them. Never strip trailing lines,
  `> ` quote prefixes, or `---`/`***` rules — those are message CONTENT, and
  removing them corrupts quoted emails, diffs and markdown.
