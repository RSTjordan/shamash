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
| Claude Code present + signed in | `claude --version` (needs ≥ 2.1), then a real headless probe: `claude -p "reply with exactly: ok"` — version alone passes on a signed-OUT machine | NO-GO — they must install and sign in first |
| Plan | Ask: Max, Pro, or unsure | Pro → warn clearly it will hit limits; let them decide |
| Disk | ≥ 5 GB free (≥ 10 GB if they want voice notes) | Warn |
| Ports 8080, 8081, 8090 free | `Get-NetTCPConnection -LocalPort` | Note which are taken; write different `bridge_port` values into `config.json` at stage 6 — the launchers read ports from config |
| `git` | `git --version` | Fixable in stage 3 |
| Machine stays on | Ask | Warn: on a laptop that sleeps, it only runs when awake |

## Stage 1 — The risk gate

Show them `RISKS.md` — or `RISKS.he.md` if their language is Hebrew. Not a
summary — the file.

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

**If they have no spare number, do not just move on — give them the two real
options and let them choose.** This is the single decision that most changes
how the finished thing feels, so it deserves thirty seconds:

> *"No problem — there are two ways to go, and you can switch later.*
>
> *(a) **Use the chat-with-yourself channel.** Free, works today, nothing else
> to buy. The catch: your assistant's messages arrive in a group as though
> **you** sent them, so your phone never notifies you. You have to remember to
> go and look. Fine if you mostly want the twice-daily digest.*
>
> *(b) **Get a second number just for it** — a second-line app like Onoff (or
> any "second phone number" app in your app store) sells one for roughly $5–7
> a month, no physical SIM. Then your assistant becomes a real
> contact: its messages arrive as messages, and something urgent actually rings
> your phone.*
>
> *Honestly: the person who built this started on (a) and disliked it enough to
> go and buy a number. If you think you'll want it to reach you rather than
> wait for you, (b) is the one. Recommended: start on (a), and move to (b) the
> first time you miss something that mattered. [a/b]"*

If they choose (b) but haven't bought the number yet, don't stall the install.
Finish everything on (a), and tell them that adding the number later is a
single re-run of stage 6b — nothing gets rebuilt.

If they stay on (a), set `channels.contact.enabled: false` and continue.
Nothing later in the install may assume the contact channel exists.

## Stage 3 — Dependencies

Install only what's missing, and only what stage 2 asked for. Use `winget`.

- `git`, `go`, `python` (3.11+), `uv`, `ffmpeg` (voice notes only)
  - Python must come with the Windows launcher: every launcher in `scripts\`
    invokes it as `py -3`, so `py -3 --version` is the check that matters,
    not `python --version`. The winget install includes it.
- **gcc** — the classic failure. The bridge needs CGO. Install MSYS2, then
  `pacman -S mingw-w64-ucrt-x86_64-gcc`, add `ucrt64\bin` to PATH for this
  session, and set `CGO_ENABLED=1`.
- Verify each with its `--version` before moving on. A tool that installed but
  isn't on PATH is the same as a tool that isn't installed.

## Stage 4 — Build the bridge

1. Clone `https://github.com/verygoodplugins/whatsapp-mcp` into `bridge/`,
   then **pin it to the proven commit**:
   `git -C bridge checkout 7830b860be3306e4e9158d014f9862c78e0cc5fb`
   — the entire REST contract the kit depends on (`/api/health`'s `connected`,
   `/api/send`'s `quoted_*`, `.bridge-token` auth, `WHATSAPP_BRIDGE_PORT`,
   `allowedMediaRoots`) was verified against exactly this commit. Only move
   the pin deliberately, with a full re-test.
2. Apply **only `patches/bridge-log-level.md`** now. The frame patch needs
   values from `config.json`, which doesn't exist until stage 6 — it is
   applied in stage 6c, and applying it now with guessed values causes the
   worst failure this kit has (see stage 6c).
3. Build. If the build fails on CGO, go back to gcc in stage 3 — that is nearly
   always the cause.
4. Start it once and confirm it reaches **"Waiting for QR code scan"** — that
   IS the success state here. Do not probe `/api/health` yet: on a first-ever
   run the REST server starts only AFTER pairing (verified against the pinned
   commit), so the health check belongs at the end of stage 5, not here.

## Stage 4b — Wire the MCP server into Claude Code

The agent's WhatsApp *tools* (list_messages, send_message, download_media)
come from the Python MCP server in `bridge/whatsapp-mcp-server` — without this
stage the agent can read nothing and reply to nothing, and the failure is
silent. Three steps, all mandatory:

1. Install its dependencies: `cd bridge\whatsapp-mcp-server` and `uv sync`.
2. Register it at USER scope, so headless runs get it without per-project
   approval prompts:

       claude mcp add whatsapp --scope user -- uv --directory <ABSOLUTE-REPO-PATH>\bridge\whatsapp-mcp-server run main.py

3. Trust + allow: the kit ships `.claude/settings.json` allowing the
   `mcp__whatsapp__*` tools in headless runs — but project settings only
   apply after the human accepts the trust dialog. Have them open `claude`
   interactively in the repo folder once and accept it.

**Verify headlessly before moving on** — this is the check that would have
caught the worst assembly bug this kit ever had:

    claude -p "Use the whatsapp list_chats tool and reply with only the number of chats it returned."

A number = wired. A "tool not found" = stop and fix; nothing downstream works.

## Stage 5 — Pair WhatsApp

**One of the three moments they have to physically act.**

Run the bridge in a VISIBLE console for this stage (not the hidden task), with
`set BRIDGE_VERBOSE=1` — the quiet log patch hides the QR event otherwise. The
bridge renders the QR right in the terminal. Tell them: *"Open WhatsApp on
your phone → Settings → Linked devices → Link a device, and scan this."*

Then **verify** — don't trust the log line. Poll `messages.db` until synced
messages appear. Zero messages after 60 seconds means it didn't pair; QR codes
expire — let it print a fresh one and have them try again. Once paired, the
REST server comes up too — NOW `/api/health` (with the Bearer token from
`store\.bridge-token`) must answer; that closes stage 4's deferred check.
Then close the console; from stage 8 the hidden task owns the bridge.

Tell them the pairing needs re-scanning about every 20 days, and that the
procedure for that day is written down in `docs/RE-PAIRING.md` — it's the one
piece of routine maintenance this product has.

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
6. **Digest times**, and which chat is the assistant's channel. On the
   chat-with-yourself route, don't just ask which chat — **create it with them**:
   a WhatsApp group containing only them, named after the assistant. It is not
   the same as WhatsApp's built-in *Message yourself* chat, which can't be named
   or given an icon. Record the resulting JID in the config; later stages send
   into it.
7. **What to call it.** Default "Claude". This is their agent's name, not the
   project's.

Then **play it all back** — what they chose and what it implies — and get a
confirmation before writing a single file.

Also seed the working files the prompts rely on: create `OPEN-WORK.md` at the
repo root (the cross-session work ledger — just its header and an empty
"Open" section) and an empty `brief/PEOPLE.md` if the interview didn't
already fill it. Both are listed in `.gitignore`; they hold the owner's data
and must never be committed.

## Stage 6b — The dedicated number

Only if stage 2 said yes. In order:

1. Install **WhatsApp Business** on their phone. It coexists with regular
   WhatsApp — different app, different number, both keep working.
2. Register it with the spare number; they receive the code.
3. **Set a two-step PIN.** Not optional. Without it, anyone who gets an SMS to
   that number can take the registration — and that account can message their
   contacts as their assistant.
4. Build the second bridge's directory — this layout is a contract, not a
   suggestion (`start-contact-bridge.cmd` and `config.py` both assume it):

       mkdir bridge\contact-bridge
       copy bridge\whatsapp-bridge\whatsapp-bridge.exe bridge\contact-bridge\

   The store directory (`bridge\contact-bridge\store\`, with its own
   `messages.db` and `.bridge-token`) is created by the exe on first run;
   the launcher gives it its own port via `WHATSAPP_BRIDGE_PORT`.
5. Pair it as a linked device of the NEW WhatsApp Business account — same
   visible-console QR flow as stage 5, run through
   `scripts\start-contact-bridge.cmd` with `BRIDGE_VERBOSE=1`.
6. Set `channels.contact.enabled` to `true` in `config.json`.

## Stage 6c — The frame patch (main channel; needs config.json)

Now — and only now — apply `patches/frame-agent-messages.md`, writing the
agent's name, the group JID from stage 6, and the owner's phone as literals
into `bridge/whatsapp-mcp-server/whatsapp.py`.

Why the ordering is sacred: on the main channel the agent's replies come FROM
the owner's own account. The header this patch adds is the only thing telling
the watcher "this row is mine, not a command". Applied wrong — or not at all —
the agent reads its own replies as fresh commands and answers itself in a
loop, at the owner's expense, until someone kills the task. After applying,
verify: send a message through the MCP `send_message` tool and confirm the row
in `messages.db` starts with the 🤖 header.

## Stage 7 — Connectors

Walk them through enabling the Google Calendar and Gmail connectors in their
claude.ai settings.

Then **verify from a headless run** — `claude -p` with a trivial calendar
query — because this is the step most likely to look fine and be silently
broken. Interactive auth does not always carry over to background runs. If the
tools aren't reachable, say so plainly rather than letting them find out in a
week when nothing gets booked.

## Stage 7b — Voice (only if they said yes in stage 2)

The watcher expects a dedicated venv at `whisper-env\` in the repo root — it
runs the transcription daemon with `whisper-env\Scripts\python.exe` and never
touches the system Python:

    py -3 -m venv whisper-env
    whisper-env\Scripts\pip install faster-whisper

Then pre-download the model so the first voice note isn't a 3.3 GB surprise:
start the daemon once in the foreground —
`whisper-env\Scripts\python.exe scripts\whisper-daemon.py` — and poll
`http://127.0.0.1:8090/health` until it reports `loaded: true`, then stop it
(the watcher will supervise it from now on). English-only installs should set
`features.voice_model` to `large-v3-turbo` first — much smaller than the
default Hebrew-tuned model. Tell them what is downloading and how big it is. Set
`features.voice_notes` to `true` in `config.json` only AFTER the model loads
once successfully — the setting is the last step, not the first. The watcher
starts and supervises the daemon by itself; there is no separate task to
register.

## Stage 8 — Autostart

Register the Windows scheduled tasks. There are exactly four, and the names
are a contract — `doctor`, `update` and `uninstall` all look tasks up by
these names:

| Task | Trigger | Action | Settings |
|---|---|---|---|
| `ShamashBridge` | At logon | `run-hidden.vbs` → `scripts\start-bridge.cmd` | restart on failure 10× / 2 min, no time limit |
| `ShamashContactBridge` | At logon | `run-hidden.vbs` → `scripts\start-contact-bridge.cmd` | same — **register only if `channels.contact.enabled` is true** |
| `ShamashWatcher` | At logon | `pyw.exe -3 scripts\watcher.py` (windowless python, no VBS needed) | restart on failure 10× / 2 min, no time limit |
| `ShamashScheduler` | Every 5 minutes, indefinitely | `run-hidden.vbs` → `scripts\run-scheduler.cmd` | 10 min time limit |

All four: battery conditions REMOVED (the default silently stops tasks on
battery, which on a laptop means it silently doesn't run), multiple instances
**IgnoreNew**, StartWhenAvailable, working directory = the repo root.
`scripts\run-hidden.vbs` waits for its child and propagates the exit code —
that is what makes restart-on-failure and the time limit act on the real
process — and nothing ever flashes a console window at them.

`schtasks /Create` cannot express the battery settings, so use PowerShell.
The pattern, with `$root` set to the absolute repo path (fill the other three
rows in from the table):

```powershell
$root = "C:\path\to\shamash"   # substitute the real path
$action = New-ScheduledTaskAction -Execute "wscript.exe" `
  -Argument "`"$root\scripts\run-hidden.vbs`" `"$root\scripts\start-bridge.cmd`"" `
  -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
  -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew `
  -StartWhenAvailable -RestartCount 10 `
  -RestartInterval (New-TimeSpan -Minutes 2) `
  -ExecutionTimeLimit ([TimeSpan]::Zero)
Register-ScheduledTask -TaskName "ShamashBridge" -Action $action `
  -Trigger $trigger -Settings $settings -Force
```

Differences for the other rows:

```powershell
# ShamashWatcher — windowless python directly, no VBS. Resolve the full path:
# a scheduled task can't be trusted to share your PATH.
$action = New-ScheduledTaskAction -Execute (Get-Command pyw.exe).Source `
  -Argument "-3 `"$root\scripts\watcher.py`"" -WorkingDirectory $root

# ShamashScheduler — repeating trigger and a real time limit:
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) `
  -RepetitionInterval (New-TimeSpan -Minutes 5) `
  -RepetitionDuration ([TimeSpan]::MaxValue)
# ...and in its settings set: -ExecutionTimeLimit (New-TimeSpan -Minutes 10)
```

**There is no scan task.** Scans ride the generic scheduler: seed
`state\schedule.json` with one entry per time in `schedule.scan_times` from
their `config.json`, plus the job-runner tick — after this, a new recurring
job is an edit to that file, never another Windows task:

```json
[
  {"name": "scan-morning", "command": "scripts\\run-scan.cmd", "at": "08:00", "every_days": 1, "enabled": true},
  {"name": "scan-evening", "command": "scripts\\run-scan.cmd", "at": "20:00", "every_days": 1, "enabled": true},
  {"name": "job-runner", "command": "scripts\\run-job-runner.cmd", "every_minutes": 30, "enabled": true}
]
```

(The scan times above are the defaults — write the ones they chose in
stage 6.)

Then start each task once with `schtasks /Run /TN <name>` and confirm with
`scripts\doctor.cmd` that every task is registered and both bridges answer
their health checks.

Warn them: these are logon-triggered. A reboot that stops at the login screen
leaves everything dead until they log in.

## Stage 9 — Smoke test, and it ends in WhatsApp

**An exe that started is not a working system.** Three tests, in this order —
each proves a loop the previous one doesn't:

1. **The notify round trip.** Have their newly installed agent send them a
   real WhatsApp message: *"I'm alive. Reply 'test' and I'll know the whole
   loop works."* Wait for the reply to come back through the watcher.
2. **The MCP reply path** — the loop the daily product actually uses. Have
   them send a small real command ("what's the newest message in this chat?")
   and confirm the agent's answer arrives *as a message in the chat* (on the
   main channel that reply travels through the MCP `send_message` tool — the
   piece stage 4b wired; this is its live test).
3. **One forced scan.** Run `scripts\run-scan.cmd` once by hand and confirm a
   digest lands in the agent chat. This is tomorrow morning's product; "the
   watcher works" does not prove it.

Only all three counts as installed. If any fails, run `scripts\doctor.cmd`
and work the layer it points at.

### Stage 9b — The welcome document

Once the round trip works, the agent's **second** message is the welcome PDF:

```
py -3 scripts\build_welcome.py          # regenerates docs\welcome\Welcome-to-Shamash.pdf
```

Send `docs/welcome/Welcome-to-Shamash.pdf` into the same chat, captioned:
*"Everything you need to know about me, in five minutes. The last page has five
things to try — start there."*

This is deliberate: the first thing a new user gets is not a wall of terminal
output, it is a document that tells them what they now have, what it will never
do, and what to send it first. Do not skip it and do not paraphrase it into the
chat instead — the PDF is the onboarding.

If the build fails (it needs headless Edge or Chrome), send
`docs/welcome/welcome.html` instead and say it opens in a browser.

### Stage 9c — Give it a face

Immediately after the welcome PDF, send them the avatar —
`docs/brand/shamash-candle-warm.png` — as an **image** in the same chat. It is
already square, 1024px, and drawn so a circular crop never clips it, so they can
set it straight from the chat on their phone. Do not skip this and do not offer
them a choice of marks; this is the one.

If the file is missing (a partial clone), regenerate it:

```
py -3 scripts\build_brand.py
```

That needs headless Edge or Chrome, same as stage 9b. If it isn't there, skip
the image entirely and move on — a missing profile picture is not worth
stalling an install over.

**Branch on what actually got built, not on what they said in stage 2.** Read
`channels.contact.enabled` from their config: someone who chose (b) but hasn't
bought the number yet was finished on (a), and stage 6b never ran, so telling
them to open WhatsApp Business would send them into an app they don't have.

- **`contact.enabled: true` — it has its own number.** *"And this is my face, if
  you want me to have one. Save the image to your gallery, then in WhatsApp
  Business: Settings → your profile at the top → the camera icon → choose it.
  Then I show up in your chat list looking like something, instead of a grey
  circle."*
- **`contact.enabled: false` — the chat-with-yourself channel.** There is no
  separate account to give a picture to. If their channel is a **group** they
  created, the picture goes on the group icon: *"And this is my face. Save it,
  then open this chat → tap its name at the top → the camera icon → choose it.
  It won't change what I do — it just means you can find me in the chat list at
  a glance."* If they are on WhatsApp's built-in *Message yourself* chat
  instead, it takes no icon: send the image anyway, and say it's theirs for
  whenever they give the assistant a number of its own. **Check which one they
  have before writing the caption** — do not send taps that don't exist.

Say "save the image", not "long-press to save": on most Android setups it is
already in their gallery, and the long-press menu they'd be hunting for is an
iPhone thing.

Either way it is one message, optional for them, and it does not block stage 10.
If they ignore it, move on — do not ask again.

## Stage 10 — Hand over

Run `scripts/doctor.cmd` and show the result. Then tell them, in plain words:

- Where their brief lives, and that editing it is how they change its behaviour.
- That `scripts/update.cmd` updates it, and never touches their brief.
- That the WhatsApp pairing needs re-scanning about every 20 days, and
  `docs/RE-PAIRING.md` is the recipe for that day.
- That `scripts\doctor.cmd` prints the report to paste into a GitHub issue if
  they need help (attach `install/install.log` too for install problems).
- Which optional features they said no to, and that adding one later is a
  single re-run of that stage.
