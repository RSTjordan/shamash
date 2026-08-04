# Patch (optional): /api/group-photo endpoint (bridge/whatsapp-bridge/main.go)

Lets the install set the command group's photo to the Shamash avatar, so the
group has a face instead of a grey circle. Skip it if the owner sets the photo
by hand, or if the install is self-chat-only (no group).

Re-apply after any update of the clone, then rebuild (build/swap procedure in
`bridge-log-level.md`).

Adds `POST /api/group-photo` (auth'd, JSON `{"chat_jid","image_path"}`),
registered right before the `/api/react` handler. It parses the JID, validates
`image_path` against `allowedMediaRoots` (the outbox), reads the file and
calls `client.SetGroupPhoto(r.Context(), jid, data)`. JPEG only — the bytes go
straight to WhatsApp.

Note: WhatsApp requires group-admin rights. The owner created the group, so
their linked device qualifies.
