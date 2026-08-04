# Shamash — build status

Honest state of the kit, updated whenever work lands. If this file and the
runbook disagree, this file is right: the runbook describes the finished
product, this one describes what actually exists on disk.

Last updated: 2026-08-05 00:10 · 6 commits, `5e5ad74`, no git remote yet.

## Done

- `install/RUNBOOK.md` — all 13 stages written (0–10, incl. 6b/9b/9c), 294 lines.
- `README.md`, `docs/ARCHITECTURE.md`, `docs/JOBS.md`, `RISKS.md`, `LICENSE`.
- `config.example.json` + `scripts/config.py` — the config contract and loader.
- `brief/AGENT_BRIEF.template.md`, `brief/PEOPLE.template.md`.
- Brand: `scripts/build_brand.py` and three PNGs; `shamash-candle-warm.png` is
  **the** avatar (`docs/brand/README.md` records that so it can't drift).
- Welcome document: `scripts/build_welcome.py`, `welcome.html`, the 7-page
  `Welcome-to-Shamash.pdf`. Runbook stage 9b sends it, 9c sends the avatar.

## Not built yet — this is the remaining work

The kit today is documentation, contracts and branding. **None of the runtime
is in it.** A user who cloned this repo right now could read it but could not
install anything.

1. **`patches/` is empty.** Stage 4 says "apply the patches in `patches/`" —
   there are none. The whatsapp-mcp fork changes live only in
   `whatsapp-agent/bridge/` on this machine and have never been extracted.
2. **`prompts/` is empty.** No generic `scan.md` / `command.md`. These exist in
   `whatsapp-agent/prompts/` but are written around Yarden — they need the
   personal parts pulled out into config/brief lookups.
3. **`scripts/` has no runtime.** Missing: `notify.py` (contact-first delivery
   + messages.db verification), `command-watcher.py`, `scheduler.py`, the
   `run-*.cmd` launchers and `run-hidden.vbs`.
4. **`scripts/doctor.cmd` and `scripts/update.cmd` don't exist** — stage 10
   tells the user to run both.
5. **`install/stages/` is an empty directory** — decide whether stages get
   their own files or the single runbook stays the only source, then delete it
   or fill it.
6. **No git remote.** The repo has never been pushed anywhere, so "make Shamash
   an open repo" has not started. Public repo, license headers and a scrub for
   personal data (numbers, JIDs, paths) all still to do.
7. **Never installed end to end.** Nothing here has been tested by running it
   against a clean machine.

## The gate before it ships

Two Fable reviewers go over the finished kit — Yarden's instruction on
2026-08-04, a one-off for this project, not a standing rule. It has **not**
been done on the kit as a whole; they were run once, early, on the avatar
commit only (8 findings fixed in `5e5ad74`).

## Why it stalled

The kit is built inside live sessions with Yarden. When a session ends, work
stops — there is no background job that continues it and nothing that reports
it as open. Between 20:50 and 00:00 on 2026-08-04 it looked to him like an
agent was working on it; nothing was. The cross-project ledger in
`whatsapp-agent/OPEN-WORK.md` now carries these items so they surface in
every scan digest instead of living only in a session that ended.
