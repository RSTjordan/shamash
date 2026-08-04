# Shamash

*The shamash is the attendant candle — the one that lights the others and then
stands to the side.*

A chief of staff for your WhatsApp, running on your own machine.

It reads your chats twice a day and sends you one digest: what it handled, what
it booked in your calendar, and what it deliberately left for you and why. You
can also just message it — in your own WhatsApp — and ask it to do things:
check your calendar, summarise a group you've ignored for a week, find a file,
answer somebody.

It is not a cloud service. There is no server, no account, and nothing to sign
up for. It runs on your computer, on your WhatsApp, and stops when you close it.

---

## Read this first

This gives WhatsApp messages a route to a shell on your laptop, it can send
messages as you with no undo, and it pairs an unofficial client to your
personal WhatsApp account. **[RISKS.md](RISKS.md) — read it before you
install.** The installer will make you confirm it anyway.

## What you need

- **Windows** (10 or 11). Only Windows for now.
- **Claude Code**, signed in — realistically on a **Max** plan.
- A computer that stays on. This is not a phone app.
- ~25 minutes, of which about 2 are you doing something.

Optional, and the installer asks you about both:

- **Voice notes** — transcription of voice messages. A 3.3 GB download.
- **A spare phone number** — turns the agent into a real contact that *rings
  your phone*, instead of a group that quietly updates itself.

## Install

Open Claude Code in an empty folder and paste this:

```
Clone https://github.com/RSTjordan/shamash into this folder, then read
install/RUNBOOK.md and carry it out stage by stage. Stop and ask me wherever
the runbook says to stop. Don't skip the risk gate.
```

Then answer its questions. It builds the bridge, pairs your WhatsApp, asks you
who matters to you, sets up the scheduled jobs, and finishes by sending you a
real WhatsApp message and waiting for you to reply to it. Nothing counts as
installed until that round trip completes.

It is safe to re-run. Every stage is idempotent — a failure costs you one
stage, not the install.

## What it actually does

**Out of the box:**

- **Digest, twice a day** — what it did, what needs you, what's on your
  calendar, unread mail worth your attention.
- **On-demand commands** — message it in your own chat and it does the thing.
- **Calendar** — books meetings people ask you for, after checking you're
  actually free; turns "I'll send it tomorrow" into a reminder.
- **Approval cards** — anything risky stops and asks you in WhatsApp. React 👍
  and it proceeds.

**Opt-in, because they cost something:**

- **Voice notes** (3.3 GB model download)
- **The agent as a real contact** (needs a second number, so it can send you
  alerts that actually ring)
- **Your own scheduled jobs** — anything you can describe, on a cron.

## The part that makes it useful

The code is the cheap half. What makes this worth running is that it knows *who
your people are* — that the contact saved as "Big Man 😎" is your father, that
one group is noise and another is your job, that you never want it discussing
money on your behalf.

So the install interviews you, one question at a time, and every question
explains what it means before it asks. It will also read your busiest chats
after pairing and *propose* the who's-who list for you to correct, rather than
handing you a blank file.

The result is `brief/AGENT_BRIEF.md` — a plain-English document describing how
your assistant should behave. It's yours. Edit it whenever you like; the agent
reads it on every run, and updates never overwrite it.

## Updating

```
scripts\update.cmd
```

Pulls the latest, runs any migrations, re-registers changed jobs, then runs
`doctor`. Your config and your brief are never touched.

## Credits

The WhatsApp bridge is [whatsapp-mcp](https://github.com/lharries/whatsapp-mcp)
by Luke Harries, via [verygoodplugins'
fork](https://github.com/verygoodplugins/whatsapp-mcp). Both MIT. Shamash
clones it at install time rather than vendoring it.

## Support

This is a personal project I run on my own machine. No warranty, and I can't
promise a response time — but open an issue and I'll do my best to help. PRs
welcome.

MIT licensed.
