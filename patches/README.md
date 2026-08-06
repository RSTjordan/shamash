# Bridge patches

`bridge/` is a git-ignored clone of
[verygoodplugins/whatsapp-mcp](https://github.com/verygoodplugins/whatsapp-mcp)
(MIT), created by the installer. These patches are changes Shamash needs inside
that clone — they live here as documents rather than diffs because the
upstream file layout drifts, and an agent applying a described change survives
drift better than a line-number patch.

**Re-apply after every update of the clone.** Applying is agent-driven and
manual: the installer walks this directory at its stages (log-level at stage
4, the frame patch at stage 6c — it needs config values that exist only
then), and `scripts/update.cmd` *reminds* you when `patches/` changed but
does not re-apply anything itself.

| Patch | What it does | Required? |
|---|---|---|
| `bridge-log-level.md` | Stops the bridge logging message bodies and DEBUG floods to disk | Yes |
| `frame-agent-messages.md` | Frames every agent-sent message with the agent's header, deterministically | Yes (main channel) — apply only at stage 6c |
| `bridge-group-photo.md` | Adds an API endpoint to set a group's photo | Optional — currently unused (stage 9c has the owner set the photo by hand); kept for automated group installs |
| `bridge-polls.md` | Adds `POST /api/poll`, decrypts incoming poll votes into `messages.db`, and a loopback `/api/vote` test endpoint | Yes — polls; without it `ask.py` runs permanently in text-fallback mode |

Go patches require a rebuild: build to a temp name, stop the bridge task, swap
the exe, restart the task (`bridge-log-level.md` has the exact procedure).

Values written as `<from config>` are filled in from the user's `config.json`
at apply time — patches never contain a real number or chat id.
