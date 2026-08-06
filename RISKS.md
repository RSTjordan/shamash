# Read this before you install

This is not a disclaimer to scroll past. Installing Shamash has real
consequences and some of them are irreversible. The installer will show you
this file and ask you to type `yes`.

## 1. It runs code on your computer, triggered by messages

The watcher takes WhatsApp messages and feeds them to a Claude Code session
on your machine. That is the entire point of it — and it means **anyone who
can get a message into your agent chat can, in effect, ask your computer to
do something**.

The brakes, exactly as they are:

- Only messages from *your own account*, in the one or two chats you
  designate, are ever treated as commands.
- Content that was forwarded, pasted or quoted from someone else is treated
  as data to analyse, never as instructions. Understand what this is: an
  *instruction to the model*, which holds in testing but is not a mechanical
  guarantee. The mechanical guarantee is the next line.
- Out of the box, the pre-approved tool list is **read-only** (`Read`, `Glob`,
  `Grep`) plus the WhatsApp and calendar tools. Anything else — every shell
  command, every file write or edit — stops and comes back to you in WhatsApp
  as an approval card. 👍 approves that one action. ❤️ approves it **and
  saves a permanent rule** that auto-approves it from then on; every ❤️
  weakens the brake, deliberately and forever (rules live in
  `.claude/settings.local.json` — prune them there).
- If you widen `allowed_tools` in `config.json` (adding `Bash` or
  `PowerShell`, as the author does on his own machine) those tools run **with
  no card at all**. At that point one successful prompt injection — inside a
  forwarded message, an email the scan reads, a web page — is unattended code
  execution on your machine, and note that the agent can write
  `state/schedule.json`, which executes commands every 5 minutes: injected
  code has an easy persistence path. `permission_mode: "auto"` swaps the
  cards for Claude's built-in safety classifier — faster, and a genuinely
  different trade. Make either change knowing exactly what you removed.

## 1b. Teleport reaches every project on this machine (if you enable it)

Teleport (off by default) lets your WhatsApp continue any Claude Code
session on this computer — not just this kit's own world. Actions in the
teleported session are guarded by the same approval cards AND by whatever
permission rules that project already has: a broad rule you once approved
at the desk in some repo is phone-reachable with that rule intact, and
the `allowed_tools` baseline you chose applies in every teleported repo
too. Two scripts are pre-approved to run without cards — `scripts/ask.py`
and `scripts/teleport.py` — since they only message you and read local
state. That pre-approval lives in the kit's own `.claude/settings.json`,
so it does not ride along: in a teleported repo they stop for a card
like anything else, and an ❤️ there saves the rule into *that* repo's
`.claude/settings.local.json`, not the kit's.

## 2. Your WhatsApp history ends up in local files, unencrypted

The bridge syncs your messages into a SQLite database on your disk — anyone
with your laptop has your message archive, without your phone or your PIN.
The kit's own logs (`logs/commands.log`, `state/actions.jsonl`,
`state/approvals.jsonl`) also contain the text of your commands, the agent's
replies, and approved actions. Message content is likewise sent to Anthropic
as part of prompts, like anything else you put in Claude.

## 3. It sends messages as you, and there is no undo

The agent replies to people under your name. They cannot tell. A wrong
message is a real message to a real person — the digest is your audit trail,
but it arrives *after* the fact.

Start with autonomous replies off if that sentence made you uncomfortable.

## 4. Ban risk on your personal number

This uses an unofficial, reverse-engineered WhatsApp client
([verygoodplugins/whatsapp-mcp](https://github.com/verygoodplugins/whatsapp-mcp),
a maintained fork of lharries/whatsapp-mcp) paired as a linked device. That
is against WhatsApp's terms of service. The observed risk is low, but it is
not zero, and the account at stake is your personal one. Nobody can appeal a
ban on your behalf.

## 5. Cost

Every command, every scan, and every job work-shift runs a Claude Code
session — by default on **Opus** (`"model"` in `config.json` is the cost
knob). Two scans a day plus normal chatting fits a Max plan; a Pro plan will
hit its limits quickly. An *active background job* adds up to a 45-minute
Opus session as often as every 3 hours — several model-hours per day for as
long as the job runs. The digest always shows what's running; `paused` is
free.

## 6. It only works while the machine is on

- The computer must stay awake and logged in. A reboot that stops at the
  login screen leaves the scheduled tasks dead and the agent silently gone.
- The WhatsApp pairing expires roughly every 20 days and you have to re-scan
  the QR code (`docs/RE-PAIRING.md` — two minutes).
- If you use a dedicated second number and its SIM or subscription lapses,
  that channel dies quietly.

## 7. Uninstalling removes less than you think

`scripts\uninstall.cmd` removes the scheduled tasks and stops the processes.
It deliberately does NOT delete: the repo, your `config.json` and brief, the
bridge stores (your full message history, in the clear), or the outbox — it
prints where each lives. It also cannot unlink the device from your phone
(WhatsApp → Linked devices) or revoke the Google connectors you authorized
in claude.ai — do those by hand if you're done.

## 8. Support

This is a personal project, shared because it might be useful to somebody
else. It has **never been installed on a machine other than the author's** —
early installers are test pilots. No warranty, no promised response time —
but run `scripts\doctor.cmd`, open an issue with its output, and I'll do my
best to help. PRs welcome.
