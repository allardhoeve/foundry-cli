# foundry-cli

CLI for managing Foundry VTT world content via Socket.io. Targets Foundry v14.

## Running

```
uv run python foundry.py [COMMAND] --help
```

Credentials are loaded from `.env` (see `.env` for required keys). The active world must match `FOUNDRY_WORLD` — the tool errors clearly if it does not.

## Data model

A **JournalEntry** is a named container in the Foundry sidebar. Each journal holds:

- **JournalEntryCategory** — named groups that organize pages (tabs/sections in the UI). Created explicitly; pages reference them by id.
- **JournalEntryPage** — content pages (text, image, pdf, video). Each page belongs to at most one category and has a `title.level` (1–6) controlling visual indentation in the page list. Level 1 is top-level; level 2 is indented beneath it.

Page ownership defaults to `INHERIT` (follows the parent journal). `--public` sets OBSERVER so players can see it.

## Command structure

```
foundry actor list [--json]
foundry actor show [--name NAME] [--json]   (read-only; Shadowdark attack inputs)

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
```

All upsert operations are idempotent — safe to re-run. Entities are matched by name.

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
