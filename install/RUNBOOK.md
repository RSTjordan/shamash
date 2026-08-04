# Shamash — install runbook

**You are Claude Code, installing Shamash on this person's Windows machine.
This document is addressed to you, not to them.**

Read the whole thing before you start. Then work the stages in order.

## How to run this

- **Talk to them like a person.** They are not a developer, and they should
  never see a stack trace. If something fails, read the error, say what it
  means in a sentence, and try the repair listed for that stage.
- **One question at a time**, and every question explains itself before it
  asks: what it is, what it means for them, what happens either way, and a
  recommended default they can accept by pressing enter.
- **Never invent an answer on their behalf.** Where this runbook says stop, stop.
- **Every stage is idempotent.** If you are unsure whether a stage completed,
  run it again — that is always safe and is the correct move.
- **Log everything** to `install/install.log` as you go: stage, result, any
  error verbatim. If they need help later, that file is what they send.
- If a stage fails twice, don't force it. Write down exactly where you are,
  tell them the install is paused and repairable, and stop.

---

## Stage 0 — Preflight

Check and print a go/no-go table. Do not continue past a NO-GO.

| Check | How | If it fails |
|---|---|---|
| Windows 10/11 | `[System.Environment]::OSVersion` | NO-GO — Windows only for now |
| Claude Code present + signed in | `claude --version` | NO-GO — they must install and sign in first |
| Plan | Ask: Max, Pro, or unsure | Pro → warn clearly it will hit limits; let them decide |
| Disk | ≥ 5 GB free (≥ 10 GB if they want voice notes) | Warn |
| Ports 8080, 8081, 8090 free | `Get-NetTCPConnection -LocalPort` | Note which are taken; stage 3 will reassign |
| `git` | `git --version` | Fixable in stage 3 |
| Machine stays on | Ask | Warn: on a laptop that sleeps, it only runs when awake |

## Stage 1 — The risk gate

Show them `RISKS.md`. Not a summary — the file.

Then ask them to type `yes`. Anything else, stop and delete nothing; they can
come back. **Do not soften this stage and do not accept a 👍.** They are about
to give WhatsApp messages a route to a shell on their computer.

## Stage 2 — Scope: what do they actually want?

This is before dependencies, because the answers decide what gets installed.
Both default to **no**.

**Voice notes.** *"I can transcribe voice messages you send me, so you can talk
to me instead of typing. It costs a 3.3 GB download now and a few minutes of
setup. If you say no, a voice note gets 'I couldn't hear that, send it as text'
— and you can add this later without reinstalling. Recommended: no to start.
[y/N]"*

If they say yes, ask which languages. English-only gets a much smaller model —
say so, because it saves them a few GB.

**A number of its own.** *"Do you have a spare phone number — an old SIM, a
second line? With one, your assistant becomes a real contact in your phone: its
messages arrive as messages, and urgent things actually ring. Without one, it
talks to you in a WhatsApp group with yourself, which works fine, but it arrives
as your own message and won't notify you. Recommended: no unless you already
have a spare number. [y/N]"*

If yes, ask the two disqualifying questions **now**, not at minute 20:

1. *Can that number receive an SMS or a call right now?* A dormant or
   disconnected SIM cannot be verified and there is no workaround. If it
   can't, their option is a paid virtual number (~$6.50/month) — that's a
   decision for right now, not after the build.
2. *Is that number still registered to a WhatsApp account somewhere?*
   Re-registering it will move that account and sign the other device out.
   They need to know this before, not discover it.

If either answer is bad, set `channels.contact.enabled: false` and continue.
Nothing later in the install may assume the contact channel exists.

## Stage 3 — Dependencies

Install only what's missing, and only what stage 2 asked for. Use `winget`.

- `git`, `go`, `python` (3.11+), `uv`, `ffmpeg` (voice notes only)
- **gcc** — the classic failure. The bridge needs CGO. Install MSYS2, then
  `pacman -S mingw-w64-ucrt-x86_64-gcc`, add `ucrt64\bin` to PATH for this
  session, and set `CGO_ENABLED=1`.
- Verify each with its `--version` before moving on. A tool that installed but
  isn't on PATH is the same as a tool that isn't installed.

## Stage 4 — Build the bridge

1. Clone `https://github.com/verygoodplugins/whatsapp-mcp` into `bridge/`.
2. Apply the patches in `patches/` (each is a `.patch` with a `.md` explaining
   what it does and why).
3. Build. If the build fails on CGO, go back to gcc in stage 3 — that is nearly
   always the cause.
4. Start it and confirm it responds before continuing.

## Stage 5 — Pair WhatsApp

**One of the three moments they have to physically act.**

Start the bridge, render the QR to a local page, open their browser, and tell
them: *"Open WhatsApp on your phone → Settings → Linked devices → Link a
device, and scan this."*

Then **verify** — don't trust the log line. Poll `messages.db` until synced
messages appear. Zero messages after 60 seconds means it didn't pair; re-render
the QR (they expire) and have them try again.

Tell them the pairing needs re-scanning about every 20 days.

## Stage 6 — The interview

**This is the product. Take your time here.**

Write `config.json` and `brief/AGENT_BRIEF.md` from
`brief/AGENT_BRIEF.template.md`. Ask in this order:

1. **Their name**, the number they just paired, their timezone.
2. **Languages** — what they speak, and what language the assistant should use
   *back to them*. These are often different: mirroring the sender is right for
   other people's chats, but a long reply full of file paths and code is far
   easier to read in English.
3. **Who matters.** Do not hand them a blank file. Read the 20 busiest chats
   from `messages.db`, propose a table — *saved name → who they think this is →
   relationship* — and have them correct it. Nicknames in a phone are not real
   names; that gap is exactly what `brief/PEOPLE.md` exists to close.
4. **Signal vs noise** — which groups it should act on, which to ignore.
5. **What it may do on its own.** The template's "Never do" list is already
   populated with strong defaults (never message someone new, never discuss
   money, never accept anything contractual). They can add; walk them through
   removing anything only if they ask.
6. **Digest times**, and which chat is the assistant's channel.
7. **What to call it.** Default "Claude". This is their agent's name, not the
   project's.

Then **play it all back** — what they chose and what it implies — and get a
confirmation before writing a single file.

## Stage 6b — The dedicated number

Only if stage 2 said yes. In order:

1. Install **WhatsApp Business** on their phone. It coexists with regular
   WhatsApp — different app, different number, both keep working.
2. Register it with the spare number; they receive the code.
3. **Set a two-step PIN.** Not optional. Without it, anyone who gets an SMS to
   that number can take the registration — and that account can message their
   contacts as their assistant.
4. Pair the second bridge instance (its own port, own store, own token) as a
   linked device, same QR flow as stage 5.

## Stage 7 — Connectors

Walk them through enabling the Google Calendar and Gmail connectors in their
claude.ai settings.

Then **verify from a headless run** — `claude -p` with a trivial calendar
query — because this is the step most likely to look fine and be silently
broken. Interactive auth does not always carry over to background runs. If the
tools aren't reachable, say so plainly rather than letting them find out in a
week when nothing gets booked.

## Stage 8 — Autostart

Register the scheduled tasks: watcher, bridge, scans. Then the generic
scheduler, so they never have to register a Windows task again.

- Remove the battery conditions — the default stops tasks on battery, which on
  a laptop means it silently doesn't run.
- Use `run-hidden.vbs` so nothing flashes a console window at them.
- Warn them: these are logon-triggered. A reboot that stops at the login screen
  leaves everything dead.

## Stage 9 — Smoke test, and it ends in WhatsApp

**An exe that started is not a working system.**

Have their newly installed agent send them a real WhatsApp message: *"I'm
alive. Reply 'test' and I'll know the whole loop works."*

Then wait for their reply to come back through the watcher. Only a completed
round trip counts as installed. If it doesn't arrive, run `doctor` and work
the layer it points at.

## Stage 10 — Hand over

Run `scripts/doctor.cmd` and show the result. Then tell them, in plain words:

- Where their brief lives, and that editing it is how they change its behaviour.
- That `scripts/update.cmd` updates it, and never touches their brief.
- That the WhatsApp pairing needs re-scanning about every 20 days.
- That `install/install.log` is what to send if they need help.
- Which optional features they said no to, and that adding one later is a
  single re-run of that stage.
