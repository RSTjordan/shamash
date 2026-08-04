# Re-pairing WhatsApp — the every-~20-days ritual

The bridge is a linked device, and WhatsApp quietly expires linked devices
roughly every 20 days. When that happens the agent goes silent: `doctor`
shows the bridge running but `connected: false`, and the digest stops
arriving. This is normal, takes two minutes, and loses nothing.

## The recipe

1. Stop the bridge task so it doesn't fight you for the exe:

       schtasks /End /TN ShamashBridge

2. Run the bridge in a VISIBLE console with the QR event un-hidden:

       cd /d <repo>\bridge\whatsapp-bridge
       set BRIDGE_VERBOSE=1
       whatsapp-bridge.exe

3. A QR code renders in the terminal. On your phone: **WhatsApp → Settings →
   Linked devices → Link a device**, scan it. QR codes expire after ~20
   seconds — the bridge prints a fresh one, just wait for it.

4. When the console shows it connected, press Ctrl-C, close the console, and
   hand the bridge back to the hidden task:

       schtasks /Run /TN ShamashBridge

5. Confirm: `scripts\doctor.cmd` should show `connected` for the channel.

Same procedure for the dedicated-number channel, with `ShamashContactBridge`,
`bridge\contact-bridge\`, and the **WhatsApp Business** app on the phone.

## If scanning fails repeatedly

Delete nothing yet. A store that refuses to re-pair usually just needs the
bridge restarted once more (QR generation stops after a few codes). If it
truly won't pair, ask your agent to walk you through it — and only as a last
resort remove `store\whatsmeow.db` (this forgets the pairing, then the next
run starts fresh; `messages.db` — your history — is untouched).
