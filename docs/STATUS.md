# Shamash — build status

Honest state of the kit, updated whenever work lands. If this file and the
runbook disagree, this file is right: the runbook describes the finished
product, this one describes what actually exists on disk.

Last updated: 2026-08-06 (survived its first real installation).

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
- Brand: `scripts/build_brand.py`, `shamash-avatar.png` (the robot-candle mascot) as
  THE avatar; the 7-page `Welcome-to-Shamash.pdf` + `scripts/build_welcome.py`.

- `scripts/` runtime, fully config-driven: watcher.py (steering, typing-ack,
  history replay, session recycling, approvals integration), notify.py
  (verified delivery), scheduler.py, job-runner.py (the jobs layer),
  approvals.py, transcribe.py + whisper-daemon.py (opt-in voice), the
  launchers + run-hidden.vbs, doctor / update / uninstall.
- `prompts/`: generic scan.md, command.md, command-followup.md, job-shift.md —
  rendered from config at runtime, verified to leave no unfilled tokens.

## Reviewed

Two independent adversarial reviewers (correctness/security + new-user
experience) went over the assembled kit on 2026-08-05. They found 4 criticals
(missing MCP wiring stage, a default tool list that contradicted RISKS.md, a
stale JOBS.md whose format would kill the scheduler, frame-patch ordering
that could loop the agent on itself) and ~20 majors/minors. All criticals and
majors were fixed the same night; the honest leftovers are below.

## First real installation (2026-08-06)

The kit's author migrated their own live agent onto a real runbook install
of this kit (fresh clone, stages followed as written, existing WhatsApp
pairing and message DB transplanted instead of stage 5's QR flow). The
install survived its proving period: two consecutive unattended scheduled
scans fired from the kit's own scheduler with verified WhatsApp delivery,
plus command round-trips on both channels, an approval card released by
reaction, and mid-turn steering. The previous system is retired.

Defects found by the install, all fixed and pushed:

- `start-bridge.cmd` / `start-contact-bridge.cmd` launched a bare exe name
  after `cd` — fails on machines with `NoDefaultCurrentDirectoryInExePath=1`.
  Now an explicit `.\` path.
- Runbook stage 8: `New-ScheduledTaskTrigger -AtLogOn` needs `-User` for
  unelevated registration, and `[TimeSpan]::MaxValue` as a repetition
  duration is rejected by Task Scheduler XML (now 3650 days).
- Every `.cmd`/`.vbs` shipped LF-only; cmd.exe requires CRLF and misparsed
  doctor.cmd on checkouts where git didn't convert. `.gitattributes` now
  forces CRLF for both extensions, and their comments are ASCII-only.
- Scan scheduling: the runbook's schedule.json needs an `anchor` date for
  any `every_days > 1` entry (a missing anchor silently skips the entry).

## Not done — the honest list before anyone installs this

1. **Never installed end-to-end on a clean machine.** A cold-clone
   rehearsal (2026-08-05: fresh kit clone + virgin pinned upstream, non-live
   ports) DID prove: the pin fetches, the patch docs apply to unmodified
   upstream, the patched bridge builds, `uv sync` works, config drives
   ports/channels, prompts render, the stage-5 terminal-QR flow behaves as
   documented, and doctor reports every state correctly — including the
   rehearsal's own discovery that the REST server only starts after pairing.
   The author's real installation (above) has since proven task
   registration and the full paired loop on one machine. Still unproven:
   dependency installs from nothing on a stranger's fresh Windows (winget
   path included), and the stage-5 QR pairing flow in a real install (the
   author's migration transplanted an existing pairing past it).
2. The welcome PDF and approval-card *flow* exist in English only; RISKS and
   the README are bilingual.
3. Known small gaps, accepted for v0: the whisper daemon port (8090) is not
   configurable; `effort` applies to the resident agent only; notify's
   card-verification match is first-60-chars (a resent identical card can
   mis-verify); no automated re-apply of bridge patches after `update`.
4. PUBLIC since 2026-08-05: https://github.com/RSTjordan/shamash
