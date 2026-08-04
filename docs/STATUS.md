# Shamash — build status

Honest state of the kit, updated whenever work lands. If this file and the
runbook disagree, this file is right: the runbook describes the finished
product, this one describes what actually exists on disk.

Last updated: 2026-08-05 (assembly night — being refreshed as the runtime
lands; see the bottom section).

## Done

- `install/RUNBOOK.md` — the staged install contract.
- `README.md` + `README.he.md`, `docs/ARCHITECTURE.md`, `docs/JOBS.md`,
  `RISKS.md`, `LICENSE`.
- `config.example.json` + `scripts/config.py` — the config contract and
  loader: one file holds everything personal; prompts are rendered from
  `{{TOKENS}}` at runtime, so updates can never collide with the owner's
  files.
- `brief/AGENT_BRIEF.template.md`, `brief/PEOPLE.template.md`.
- `patches/` — the bridge modifications, as apply-time documents (log
  redaction, message framing, optional group photo).
- Brand: `scripts/build_brand.py`, three PNGs, `shamash-candle-warm.png` as
  THE avatar; the 7-page `Welcome-to-Shamash.pdf` + `scripts/build_welcome.py`.

## In assembly (this file is refreshed as each lands)

- `scripts/` runtime: watcher.py, notify.py, scheduler.py, job-runner.py,
  approvals.py, transcribe.py, whisper-daemon.py, the launchers,
  doctor / update / uninstall.
- `prompts/`: generic scan.md, command.md, command-followup.md, job-shift.md.

## Not done — the honest list before anyone installs this

1. **Never installed end-to-end on a clean machine.** Everything was proven
   on ONE machine (the author's), inside the personal installation the kit
   was extracted from. The first stranger's install will find things.
2. The review gate: two independent reviewer agents over the finished kit.
3. No git remote yet — the repo goes public only after 1–2 and a final
   personal-data scrub.
