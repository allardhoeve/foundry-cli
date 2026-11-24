# foundry-cli

CLI and MCP server for managing [Foundry VTT](https://foundryvtt.com/) world content via Socket.io. Targets Foundry v14.

## Scope

This tool manages the **journal layer** of a Foundry world: journal entries, their categories, and their pages. It also puts **labels on hex-map scenes**, lists actors, reads raw compendium documents, and can show a read-only view of a Shadowdark character's attack inputs for debugging. It is intentionally narrow — no general scene management, no compendium editing, no editing of system-specific mechanics.

The primary use case is AI-assisted world-building: an LLM writes lore entries via the MCP server while a GM reviews them in the Foundry UI in real time.

## Setup

**Requirements:** Python 3.12+, [uv](https://docs.astral.sh/uv/), a running Foundry v14 instance with an active world.

```
git clone --recurse-submodules <repo>
cd foundry-cli
cp .env.example .env   # fill in credentials
```

The Shadowdark system is a git submodule under `third_party/`; the hex-map label styles measure text with its fonts.

`.env` keys:

| Key | Description |
|-----|-------------|
| `FOUNDRY_URL` | Base URL of the Foundry instance, e.g. `https://foundry.example.com` |
| `FOUNDRY_BASIC_USER` | HTTP Basic Auth username (if Foundry is behind a proxy) |
| `FOUNDRY_BASIC_PASS` | HTTP Basic Auth password |
| `FOUNDRY_WORLD` | The world name that must be active |
| `FOUNDRY_GM_USER` | Foundry user to authenticate as (must have GM role) |
| `FOUNDRY_GM_PASSWORD` | Password for that user |

## CLI usage

```
uv run python foundry.py [COMMAND] --help
```

### Actors

```
foundry actor list [--json]
foundry actor show [--name NAME] [--json]
```

`actor show` is a read-only debugging view for Shadowdark characters. It shows what feeds the to-hit and damage numbers: ability scores and modifiers, equipped weapons and their attack bonuses, and every effect that touches `roll.*`, `bonuses.*attack*` or ability scores, along with the item each effect comes from. Without `--name` it lists all Player actors. Values are shown as stored: ability scores are before effects and formulas are not evaluated. The final bonus is computed in the browser and is never stored, so it isn't shown.

### Compendiums

```
foundry compendium get UUID
```

Prints one raw compendium document as JSON, embedded effects included. `UUID` is a link as it appears in actor data, e.g. `Compendium.shadowdark.properties.Item.jq0m0lGb7QOCSJXL`.

### Journals

```
foundry journal list [--json]
foundry journal upsert --title NAME [--folder FOLDER] [--public]
foundry journal delete --title NAME
```

### Categories

Categories are named tabs that group pages within a journal. Create them before assigning pages.

```
foundry journal category list   --journal NAME [--json]
foundry journal category upsert --journal NAME --name NAME
foundry journal category delete --journal NAME --name NAME
```

### Pages

```
foundry journal page list    --journal NAME [--json]
foundry journal page upsert  --journal NAME --title NAME
                             [--category NAME] [--level 1-6]
                             [--before TITLE | --after TITLE]
                             [--public]
                             [--content HTML | --content-file PATH | stdin]
foundry journal page reorder --journal NAME   # titles from stdin, one per line
foundry journal page delete  --journal NAME --title NAME
```

**Content input** — exactly one of:
- `--content '<p>HTML</p>'` — inline string
- `--content-file path/to/page.html` — read from file
- stdin — pipe HTML directly: `cat page.html | foundry journal page upsert ...`

**Positioning** — `--before TITLE` / `--after TITLE` insert the page relative to an existing page within the same category. All pages in the category are reindexed with clean sort values.

**Level** — controls sidebar indentation (1 = top-level, 2 = indented beneath the preceding level-1 page).

**`--public`** — sets OBSERVER ownership so players can see the entry/page. Default is INHERIT (follows the parent journal).

All upsert operations are **idempotent** — matched by name, safe to re-run.

### Example workflow

```bash
# Create journal and categories
foundry journal upsert --title "Ravens — Lore"
foundry journal category upsert --journal "Ravens — Lore" --name "Settlements"
foundry journal category upsert --journal "Ravens — Lore" --name "NPCs"

# Add pages
echo "<p>A walled city on the northern coast.</p>" | \
  foundry journal page upsert \
    --journal "Ravens — Lore" --title "Thornwall" \
    --category "Settlements" --level 1

echo "<p>The merchant district.</p>" | \
  foundry journal page upsert \
    --journal "Ravens — Lore" --title "Thornwall — Docks Quarter" \
    --category "Settlements" --level 2 --after "Thornwall"

# Reorder pages
printf "Thornwall\nThornwall — Docks Quarter\nThornwall — Temple Quarter\n" | \
  foundry journal page reorder --journal "Ravens — Lore"
```

### Hex maps

Labels on a hex-map scene, placed by the hex number printed on the map (`0816` = column 08, row 16). Labels are ordinary Foundry Drawings: GM-only until revealed, and the GM can drag them or hide/reveal them by hand with the eye toggle.

```
foundry hexmap init      --scene NAME --size COLSxROWS [--shifted even|odd]
foundry hexmap calibrate --scene NAME [--label-pos top|center|bottom]
foundry hexmap numbers   --scene NAME [--remove]
foundry hexmap label     HEX [TEXT] --scene NAME [--public | --hidden] [--pos POS]
foundry hexmap unlabel   HEX --scene NAME
foundry hexmap list      --scene NAME [--json]
```

**Setup, once per scene:** `init` places two magenta anchor hexagons. Drag each onto the printed hex it names (they snap to the scene grid when the grid is aligned to the map), then run `calibrate`. Check with `numbers`, which puts a number tag in every hex. `foundry hexmap --help` walks through it step by step.

**Look:** labels are Shadowdark blackletter, white on a near-solid black box, big enough to read when zoomed out; numbers are small Montserrat Bold tags. Both use the Shadowdark system's fonts.

### Companion module: Foundry CLI Companion

Optional. Foundry has no per-user show/hide for Drawings, so `module/` holds a small Foundry module that adds **Name labels** and **Hex labels** (the numbers) toggles to the Tokens toolbar. Each user shows or hides them on their own screen, or presses **L** (name labels) and **H** (hex labels); nothing is written to the world. Labels start hidden on every load. The keys can be rebound under Configure Controls.

Install it in Foundry with this manifest URL:

```
https://raw.githubusercontent.com/allardhoeve/foundry-cli/main/module/module.json
```

**Releasing the module:** bump `version` and `download` (`.../releases/download/module-vX.Y.Z/module.zip`) in `module/module.json` on `main`, then push the tag `module-vX.Y.Z`. The `Release module` workflow checks that the two agree, zips `module/` and publishes the GitHub release.

## MCP server

The MCP server exposes every CLI command as a tool, generated from the CLI itself, so the two can't drift apart. `foundry hexmap label` becomes `hexmap_label`, `foundry journal page upsert` becomes `journal_page_upsert`, and so on. Each tool's parameters are the command's arguments and options, its description is the command's help text (including the hex-map workflow), and calling it runs the command.

```
uv run python foundry_mcp.py
```

Register in an MCP client config:

```json
{
  "mcpServers": {
    "foundry": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/foundry-cli", "python", "foundry_mcp.py"]
    }
  }
}
```

List commands always return JSON, and delete commands skip their confirmation prompt. `journal_page_reorder` takes the titles as a `titles` parameter, one per line.

## Testing

Tests run against a real Foundry instance spun up via Docker Compose. The test fixture starts the container, waits for the world to become active, then runs against it.

```
uv run pytest
```

The Docker environment lives in `docker/`. Tests create journals with a `_pytest_` prefix and clean up on teardown.

## Architecture vs foundryvtt-mcp

[foundryvtt-mcp](https://github.com/evandecker/foundryvtt-mcp) is a JavaScript MCP server that runs inside Foundry as a module, calling the Foundry API directly from within the same process.

This project takes the opposite approach:

| | foundry-cli | foundryvtt-mcp |
|---|---|---|
| **Runtime** | External Python process | Foundry module (in-process JS) |
| **Protocol** | Socket.io `modifyDocument` | Direct Foundry API calls |
| **Install footprint** | Nothing installed in Foundry | Requires a Foundry module |
| **Interface** | CLI + MCP server | MCP server only |
| **Scope** | Journals and actors | Broader (scenes, actors, items, …) |

**Why Socket.io instead of a Foundry module?**

- No Foundry module to maintain across Foundry version updates — the Socket.io wire protocol is stable.
- Works with a remote or hosted Foundry instance without SSH or file system access.
- The CLI is useful on its own for scripting and automation, independent of any AI tooling.

**Trade-offs:** The Socket.io `modifyDocument` API is not officially documented for external use, so it may break across major Foundry versions. Operations are limited to what that API surface exposes — complex queries or compendium access require a different approach.
