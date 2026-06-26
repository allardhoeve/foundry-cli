# foundry-cli

CLI and MCP server for managing [Foundry VTT](https://foundryvtt.com/) world content via Socket.io. Targets Foundry v14.

## Scope

This tool manages the **journal layer** of a Foundry world: journal entries, their categories, and their pages. It also lists actors. It is intentionally narrow — no scene management, no compendium access, no system-specific mechanics.

The primary use case is AI-assisted world-building: an LLM writes lore entries via the MCP server while a GM reviews them in the Foundry UI in real time.

## Setup

**Requirements:** Python 3.12+, [uv](https://docs.astral.sh/uv/), a running Foundry v14 instance with an active world.

```
git clone <repo>
cd foundry-cli
cp .env.example .env   # fill in credentials
```

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
```

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

## MCP server

The MCP server exposes the same operations as tools so LLMs can manage journal content directly.

```
uv run python foundry_mcp.py
```

Register in an MCP client config:

```json
{
  "mcpServers": {
    "foundry": {
      "command": "uv",
      "args": ["run", "python", "/path/to/foundry_mcp.py"]
    }
  }
}
```

Available tools: `actor_list`, `journal_list`, `journal_upsert`, `journal_delete`, `category_list`, `category_upsert`, `category_delete`, `page_list`, `page_upsert`, `page_reorder`, `page_delete`.

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
