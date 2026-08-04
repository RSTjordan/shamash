# Architecture — the one rule

Every file in a Shamash installation belongs to exactly one of two owners, and
this is the rule the whole design hangs off:

| | **Kit** (this repo) | **Instance** (the user's machine) |
|---|---|---|
| Contains | code, prompts, templates, installer, docs | config, brief, state, logs, bridge |
| Updated by | `git pull` | never by an update |
| Contains a person's name? | **never** | always |

Nothing is both. When a file wants to be both, it splits into a template that
belongs to the kit and a generated file that belongs to the user.

Why it matters: it means `git pull` is always safe. An update cannot overwrite
the brief somebody spent an evening tuning, because that file does not exist in
this repo. And personal data cannot leak into a public repo through a careless
commit, because no file that could hold it is tracked.

## The three kinds of file

**1. Kit-owned, generic.** `scripts/*`, `install/*`, `docs/*`. No paths, no
phone numbers, no names. If you need one, read it from config:

```python
import config
cfg = config.load()
cfg["self_jid"]          # derived from owner.phone
cfg["paths"]["state"]    # derived from the repo location
cfg["agent_name"]        # what this user calls their assistant
```

`config.py` derives the repo root from its own location, so the code has no
opinion about where it was installed.

**2. Kit-owned, rendered at runtime.** `prompts/*.md`. These carry
`{{PLACEHOLDER}}` tokens and are substituted when read:

```python
prompt = config.read_prompt("command.md")   # {{OWNER_NAME}} → "Dana"
```

Rendering at *runtime* rather than at install time is deliberate. If the
installer filled these in and wrote them back, every update would either
clobber the result or need a three-way merge. Because they are rendered on
every read, the file on disk stays pristine and `git pull` just works.

The token list lives in `config.placeholders()`. An unknown token is left in
the output verbatim — a typo should be visible as `{{WHOPS}}` in the prompt, not
silently become an empty string that changes what the agent was told.

**3. User-owned.** `config.json`, `brief/*.md`, `state/`, `logs/`, `bridge/`,
`jobs/`. Generated once at install from `*.template.md`, then theirs. All
gitignored.

## Where does a new rule go?

The question that comes up constantly once this is running: you improve
something about how the agent behaves — does it go in the kit or the instance?

- *"Always answer me in English"* → **instance.** One person's preference.
- *"Never discuss money on someone's behalf"* → **kit template.** Everyone
  wants this and a new user should start with it.
- *"His dad is saved in the phone under a nickname"* → **instance.** Obviously.
- *"Read the who's-who file before acting on a chat"* → **kit template.** It's
  a mechanism, not a fact about a person.

The test: *would this sentence be true for a stranger?* If yes it's a kit
default and belongs in `brief/AGENT_BRIEF.template.md`. If it only makes sense
for one person, it stays on their machine.

## Custom jobs

Anything specific to one user's life or work — a business report, a
site watcher — is a **job**, living in the gitignored `jobs/` directory as a
prompt plus a schedule entry. Jobs never enter the kit. The kit ships the
scheduler and one worked example, not somebody's actual business.

## Adding a config key

1. Add it to `DEFAULTS` in `scripts/config.py` with a working default.
2. Add it to `config.example.json`.
3. If the installer should ask about it, add the question to the runbook stage.

Never require it. `DEFAULTS` is deep-merged over the user's file, so an
existing installation that predates the key keeps running without being
touched. That is what makes `git pull` safe for people who are not watching
this repo.
