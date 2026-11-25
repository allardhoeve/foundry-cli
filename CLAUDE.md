# foundry-cli

CLI for managing Foundry VTT world content via Socket.io. Targets Foundry v14.

## Running

```
uv run python foundry.py [COMMAND] --help
```

Credentials are loaded from `.env` (see `.env` for required keys). The active world must match `FOUNDRY_WORLD` — the tool errors clearly if it does not.

## Live Foundry is read-only for agents

`.env` points at the user's live game. Never write to it: no `upsert`, `delete` or `reorder` commands, no `hexmap` commands other than `list`, no write MCP tools (`*_upsert`, `*_delete`, `journal_page_reorder`, and every `hexmap_*` tool except `hexmap_list`), and no create/update/delete through `FoundryClient` internals. This also applies to "just testing" a change or fixing data you found broken. Report what needs changing and let the user do it.

Reads (`list`, `show`, `get`) against live are fine. Anything that writes runs against the Docker test instance (`tests/.env.test`, via `uv run pytest`).

## Data model

A **JournalEntry** is a named container in the Foundry sidebar. Each journal holds:

- **JournalEntryCategory** — named groups that organize pages (tabs/sections in the UI). Created explicitly; pages reference them by id.
- **JournalEntryPage** — content pages (text, image, pdf, video). Each page belongs to at most one category and has a `title.level` (1–6) controlling visual indentation in the page list. Level 1 is top-level; level 2 is indented beneath it.

Page ownership defaults to `INHERIT` (follows the parent journal). `--public` sets OBSERVER so players can see it.

## Command structure

```
foundry actor list [--json]
foundry actor show [--name NAME] [--json]   (read-only; Shadowdark attack inputs)

foundry compendium get UUID                 (read-only; raw JSON)

foundry journal list [--json]
foundry journal upsert  --title NAME [--folder FOLDER] [--public]
foundry journal delete  --title NAME

foundry journal category list   --journal NAME [--json]
foundry journal category upsert --journal NAME --name NAME
foundry journal category delete --journal NAME --name NAME

foundry journal page list    --journal NAME [--json]
foundry journal page upsert  --journal NAME --title NAME
                             [--category NAME] [--level 1-6]
                             [--before TITLE | --after TITLE]
                             [--public]
                             [--content HTML | --content-file PATH | stdin]
foundry journal page reorder --journal NAME  (titles from stdin, one per line)
foundry journal page delete  --journal NAME --title NAME

foundry hexmap init|calibrate|numbers|label|unlabel|list --scene NAME ...
                             (see `foundry hexmap --help` for the workflow)
```

All upsert operations are idempotent — safe to re-run. Entities are matched by name.

## MCP server

`foundry_mcp.py` is generated from the CLI: every click command is a tool (`foundry hexmap label` → `hexmap_label`), its help text is the tool description, and a call runs the command in a subprocess. Never hand-write MCP tools; add or change the CLI command. A command that reads its input from stdin declares it with a `stdin_param` attribute. `tests/test_mcp.py` fails if a command has no tool.

## Hex maps and the companion module

`foundry hexmap` draws labels, hex numbers and calibration anchors as Drawings tagged `flags.world.hexmap.kind` = `label` | `number` | `anchor`. The Foundry module in `module/` (released separately via `module-v*` tags) relies on that flag to toggle labels and numbers per user. Change the flag on one side and you must change it on the other: `foundry.py` / `hexstyle.py` and `module/src/hexmap.js`.

Text boxes are sized by measuring with the Shadowdark submodule's font files (`hexstyle.py`, Pillow). There is one style on purpose (bold, readable zoomed out); don't add presets without asking.

## Images: `visualize.py`

`uv run python visualize.py` paints items, characters, locations and creatures locally with FLUX.2 klein 4B (distilled, 8-bit) through mflux; the `visualize` skill drives it. It is a separate CLI from `foundry.py` and has no MCP tools. Kinds live in `visualize_kinds/<kind>.toml` (template, size, suggested moodbook). Moodbooks (`moodbooks/`) and results (`output/`) stay out of git: the repo is public and Foundry's icons are licensed art. FLUX.2 has no negative prompt in mflux, so templates are worded positively.

## Error handling

- Wrong or inactive world → explicit message naming the active world vs expected
- Authentication failure → explicit message; do not swallow Socket.io errors
- Category not found on `page upsert` → error with the exact `category upsert` command to fix it
- Journal/category/page not found on delete → clear not-found message, exit 1

## `page list` output

Default: table with columns `TITLE`, `CATEGORY`, `LEVEL`, `TYPE`.
`--json`: raw array of page objects.

## Conventions (not enforced by the tool)

- One journal per campaign, e.g. `"Revenge of the Ravens — Lore"`
- Categories map to entity types: `Settlements`, `NPCs`, `Factions`, etc.
- Settlement overview pages: level 1. District/sub-pages: level 2.
- Create categories explicitly with `category upsert` before assigning pages.
