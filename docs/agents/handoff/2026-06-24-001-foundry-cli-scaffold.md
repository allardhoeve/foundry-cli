# Handoff: foundry-cli scaffold

**Date:** 2026-06-24  
**Project:** ~/devel/foundry-cli

## What was accomplished

- Moved the original Foundry CLI tool from `~/devel/foundry-homebrew/tools/foundry/` into a new dedicated repo at `~/devel/foundry-cli/`
- Wrote `CLAUDE.md` documenting the full target command structure and data model
- Scaffolded `docker/` for a self-contained Foundry test instance (port 30001)
- Created `tests/.env.test` pointing at the test container

Files in repo:
```
foundry.py           # current tool — journal list/upsert/delete only (needs rewrite)
pyproject.toml
uv.lock
CLAUDE.md            # spec: target commands, data model, error handling conventions
docker/
  compose.yml        # name: foundry-cli, port 30001:30000, own data volume
  secrets.json.tmpl  # template — credentials not committed
  data/              # world data will live here after one-time setup
tests/
  .env.test          # FOUNDRY_URL=http://localhost:30001, FOUNDRY_WORLD=foundry-cli-test
```

## Key decisions

**Command structure** (not yet implemented — this is the target):
```
foundry journal list/upsert/delete
foundry journal category list/upsert/delete  --journal NAME
foundry journal page list/upsert/delete      --journal NAME [--category NAME]
```
- `journal` is the top-level namespace for all subcommands; everything is about journals
- Categories are first-class: create them explicitly with `category upsert` before assigning pages
- `page upsert` errors if `--category` names a category that doesn't exist — no auto-create
- All upsert operations are idempotent, matched by name
- `--json` flag on all list commands
- `page list` outputs a table: TITLE / CATEGORY / LEVEL / TYPE
- `--public` sets OBSERVER ownership; pages default to INHERIT from the journal

**Foundry v14 data model** (from source at `~/devel/foundry-homebrew/third_party/foundryvtt-14.360/`):
- `JournalEntry` contains `pages[]` and `categories[]` (categories are new in v14)
- `JournalEntryPage.category` is a foreign key to a `JournalEntryCategory._id`
- `JournalEntryPage.title.level` (1–6) controls visual indentation in the page list sidebar
- Page ownership defaults to `INHERIT`

**Docker isolation:** The `foundry-cli` Docker instance is fully independent from `~/devel/foundry-homebrew/docker/`. No shared mounts. Both dirs are named `docker/` which caused a project name collision — fixed with `name: foundry-cli` at the top of `compose.yml`. Uses port 30001 on the host to avoid conflicting with the homebrew container on 30000.

**Test world:** Named `foundry-cli-test`, world id `foundry-cli-test`, Shadowdark system. **Not yet created** — requires one-time manual setup (see below).

## What is NOT done yet

1. **One-time Docker world setup** — still needed:
   - Copy `docker/secrets.json.tmpl` → `docker/secrets.json`, fill in real Foundry credentials
   - `docker compose -f docker/compose.yml up`
   - Go to `http://localhost:30001/setup`, install Shadowdark, create world `foundry-cli-test`
   - Set up Gamemaster user (no password, or update `tests/.env.test`)
   - Commit `docker/data/Data/worlds/foundry-cli-test/`

2. **`foundry.py` rewrite** — the current file only has `journal list/upsert/delete` with old single-page logic. The full command structure from CLAUDE.md is not implemented.

3. **Tests** — `tests/conftest.py` and test files not written yet. Agreed approach:
   - Session-scoped pytest fixture starts `docker/compose.yml`, polls `/api/status` until `foundry-cli-test` world is active, yields a `FoundryClient`, tears down after session
   - Integration tests cover full round-trips and idempotency
   - Error path tests: missing category on page upsert, wrong world, bad password

## Error handling spec (for the rewrite)

- Wrong/inactive world → name the active world vs expected world explicitly
- Auth failure → explicit message, do not swallow Socket.io errors
- Category not found on `page upsert` → error and print the exact `category upsert` command to fix it
- Not-found on delete → clear message, exit 1

## Running the current tool

```bash
cd ~/devel/foundry-cli
uv run python foundry.py --help
uv run python foundry.py journal list
```

Credentials are read from `.env` in the repo root (gitignored). See `.env` for current values pointing at the live campaign world.
