# Foundry VTT v14 — HTTP & Socket.io API Reference

Foundry v14, system `shadowdark`. Extracted from `foundry.py`, `foundry_mcp.py`,
and the Shadowdark system source in `third_party/`.

---

## Table of Contents

1. Overview
2. Authentication Flow
3. HTTP Endpoints
4. Socket.io Core Events
5. modifyDocument Universal CRUD
6. Document Types and Schemas
   - Top-Level Documents
   - Embedded Documents
7. Sorting and Ordering
8. Ownership and Permissions
9. parentUuid Format
10. System Socket Channel
11. Error Handling
12. Constants

---

## Overview

Foundry VTT exposes two transport layers:

| Layer | Purpose |
|-------|---------|
| HTTP | Auth only: session cookies, user join |
| Socket.io | Everything else: all document CRUD, world events |

The Socket.io transport uses a **single event** for all document operations: `modifyDocument`. It handles create, read, update, and delete for every document type in the system.

Connect using the `websocket` transport only (no polling):

```python
sio.connect(url, headers={"Cookie": "...", ...}, transports=["websocket"])
```

---

## Authentication Flow

Sequential — each step depends on the previous.

### Step 1 — GET `/join`

Establishes a session and collects cookies. Use Basic Auth if the instance is behind HTTP auth.

```
GET /join
Authorization: Basic <base64(user:pass)>   # if configured
```

Response: HTML page (ignored). Sets session cookies on the HTTP client.

### Step 2 — Socket.io connect

Open the WebSocket connection, forwarding the session cookies as a `Cookie` header.

```python
headers = {
    "Cookie": "; ".join(f"{k}={v}" for k, v in http_session.cookies.items()),
    # include Authorization header here too if using Basic Auth
}
sio.connect(url, headers=headers, transports=["websocket"])
```

### Step 3 — emit `getJoinData`

Immediately after the `connect` event fires, emit `getJoinData` to discover users.

```python
sio.emit("getJoinData", callback=on_data)
```

Response (callback):

```json
{
  "users": [
    { "_id": "userId", "name": "GM", "role": 4, ... },
    { "_id": "userId2", "name": "Player1", "role": 1, ... }
  ]
}
```

User `role` values: `1` = Player, `2` = Trusted, `3` = Assistant GM, `4` = GM.

### Step 4 — POST `/join`

Authenticate as a specific user. Uses the session cookies from Step 1.

```
POST /join
Content-Type: application/json
Sec-Fetch-Site: same-origin

{
  "action": "join",
  "username": "<user name>",
  "userId": "<user _id from getJoinData>",
  "password": "<user password>"
}
```

Since v14 the server answers a bare `400 {"error":"The request could not be processed."}` to any join POST without `Sec-Fetch-Site: same-origin`, whatever the body. The old lowercase `userid` field gets a 401.

After this, the socket session is authenticated and `modifyDocument` calls will execute with that user's permissions.

**Timeout:** Allow 15 seconds for the socket to become ready after connect.

---

## HTTP Endpoints

### `GET /api/status`

Check whether a world is active.

```
GET /api/status
```

Response:
```json
{
  "active": true,
  "world": "my-world-name",
  "version": "14.x.x"
}
```

Use this before connecting to verify the correct world is active.

### `GET /join`

Session bootstrap. See [Authentication Flow](#authentication-flow).

### `POST /join`

User authentication. See [Authentication Flow](#authentication-flow).

---

## Socket.io Core Events

### Event: `getJoinData` (client → server)

Payload: none.

Response (callback): world join data including user list. See [Authentication Flow](#authentication-flow).

---

### Event: `modifyDocument` (client → server)

The universal CRUD interface. All document operations go through this single event.

See the modifyDocument Universal CRUD section for full details.

---

### Broadcast events (server → all clients)

After a successful `modifyDocument` create/update/delete, Foundry broadcasts the change to all other connected clients using the same `modifyDocument` event name. The broadcast payload mirrors the operation that was performed.

---

## modifyDocument Universal CRUD

### Payload Structure

```json
{
  "type":      "<DocumentType>",
  "action":    "get | create | update | delete",
  "operation": { ... }
}
```

The `operation` object differs by action.

---

### Action: `get`

Retrieve documents. Returns all matching documents.

```json
{
  "type": "JournalEntry",
  "action": "get",
  "operation": {
    "query": {}
  }
}
```

| Field | Type | Notes |
|-------|------|-------|
| `query` | object | MongoDB-style filter. `{}` returns all. |

Supported query fields (examples):
- `{ "name": "My Journal" }` — match by name
- `{ "type": "Player" }` — match by subtype (for Actor, Item)
- `{ "type": "JournalEntry" }` — match Folder by contained type
- `{ "folder": "<folderId>" }` — match by folder

**Response:**
```json
{ "result": [ { "_id": "...", "name": "...", ... } ] }
```

---

### Action: `create`

Create one or more documents.

```json
{
  "type": "Actor",
  "action": "create",
  "operation": {
    "data": [ { "name": "Goblin", "type": "NPC", ... } ]
  }
}
```

| Field | Type | Notes |
|-------|------|-------|
| `data` | array | One or more document objects. `_id` is assigned by the server. |
| `parentUuid` | string | Required for embedded documents. See [parentUuid Format](#parentuuid-format). |

**Response:**
```json
{ "result": [ { "_id": "<new-id>", "name": "Goblin", ... } ] }
```

---

### Action: `update`

Update one or more documents. Only supply changed fields; they are shallow-merged.

```json
{
  "type": "JournalEntry",
  "action": "update",
  "operation": {
    "updates": [ { "_id": "<id>", "name": "New Name" } ]
  }
}
```

| Field | Type | Notes |
|-------|------|-------|
| `updates` | array | Each object must have `_id`. Only changed fields needed. |
| `parentUuid` | string | Required for embedded documents. |

**Response:**
```json
{ "result": [ { "_id": "...", ... updated document ... } ] }
```

---

### Action: `delete`

Delete documents by ID.

```json
{
  "type": "JournalEntry",
  "action": "delete",
  "operation": {
    "ids": [ "<id1>", "<id2>" ]
  }
}
```

| Field | Type | Notes |
|-------|------|-------|
| `ids` | array of strings | Document IDs to delete. |
| `parentUuid` | string | Required for embedded documents. |

**Response:**
```json
{ "result": [] }
```

---

### Compendium Operations

To operate on documents inside a compendium pack, add the `pack` field to the operation:

```json
{
  "type": "Item",
  "action": "get",
  "operation": {
    "query": {},
    "pack": "shadowdark.spells"
  }
}
```

Pack IDs follow the format `<system-or-module>.<pack-name>`.

---

## Document Types and Schemas

### Top-Level Documents

These are queried and modified directly (no `parentUuid`). All share a common base:

| Field | Type | Notes |
|-------|------|-------|
| `_id` | string | Server-assigned UUID. |
| `name` | string | Display name. |
| `flags` | object | Module-specific metadata. Keyed by module/system id. |
| `ownership` | object | Permission map. See Ownership and Permissions section. |
| `folder` | string \| null | ID of containing Folder, or null. |
| `sort` | number | Sort order within folder or sidebar. |

---

#### Actor

Represents a character, NPC, creature, or other entity. System defines subtypes.

| Field | Type | Notes |
|-------|------|-------|
| `name` | string | |
| `type` | string | Subtype: `Player`, `NPC`, `Light` (Shadowdark). |
| `img` | string | Image path. |
| `system` | object | System-specific data. See `shadowdark-data-model.md`. |
| `items` | array | Embedded Item documents. Read-only in get result; modify via embedded ops. |
| `effects` | array | Embedded ActiveEffect documents. |
| `prototypeToken` | object | Default token settings (see Token fields). |

**Prototype Token fields (inside `prototypeToken`):**

| Field | Type | Notes |
|-------|------|-------|
| `name` | string | Token display name. |
| `actorLink` | boolean | Linked tokens share actor data. |
| `sight.enabled` | boolean | Whether the token has vision. |
| `sight.range` | number | Vision range in grid units. |
| `sight.visionMode` | string | e.g. `"basic"`, `"darkvision"`. |
| `light.dim` | number | Dim light radius. |
| `light.bright` | number | Bright light radius. |
| `light.color` | string | Hex color string. |
| `width` | number | Token width in grid squares. |
| `height` | number | Token height in grid squares. |
| `disposition` | number | `-1` hostile, `0` neutral, `1` friendly, `2` secret. |
| `displayName` | number | When name is shown: `0`=never, `10`=hover(owner), `20`=hover, `30`=always(owner), `40`=always, `50`=always all. |
| `displayBars` | number | Same scale as displayName. |
| `bar1.attribute` | string | e.g. `"attributes.hp"`. |
| `bar2.attribute` | string | Secondary bar attribute. |

---

#### Item

Equipment, spells, abilities, and other game objects. System defines subtypes.

| Field | Type | Notes |
|-------|------|-------|
| `name` | string | |
| `type` | string | Subtype: see Shadowdark item types in `shadowdark-data-model.md`. |
| `img` | string | Image path. |
| `system` | object | System-specific data. See `shadowdark-data-model.md`. |
| `effects` | array | Embedded ActiveEffect documents. |

---

#### JournalEntry

A named container in the sidebar. Holds pages and categories.

| Field | Type | Notes |
|-------|------|-------|
| `name` | string | |
| `pages` | array | Embedded JournalEntryPage documents (read-only in get result). |
| `categories` | array | Embedded JournalEntryCategory documents (read-only in get result). |

---

#### Scene

A map or encounter area.

| Field | Type | Notes |
|-------|------|-------|
| `name` | string | |
| `active` | boolean | Whether this is the currently viewed scene. |
| `navigation` | boolean | Whether scene appears in navigation bar. |
| `navOrder` | number | Position in the navigation bar. Ascending. |
| `navName` | string | Override name shown in the nav bar (defaults to `name`). |
| `background.src` | string | Path to background image. |
| `width` | number | Scene width in pixels. |
| `height` | number | Scene height in pixels. |
| `padding` | number | Padding fraction around the scene. |
| `initial.x` | number | Initial view x position. |
| `initial.y` | number | Initial view y position. |
| `initial.scale` | number | Initial view scale. |
| `grid.type` | number | `0`=gridless, `1`=square, `2`=hex rows odd (HEXODDR, pointy-top), `3`=hex rows even (HEXEVENR), `4`=hex columns odd (HEXODDQ, flat-top), `5`=hex columns even (HEXEVENQ). |
| `grid.size` | number | Pixels per grid unit. |
| `grid.distance` | number | Real-world distance per grid unit. |
| `grid.units` | string | Distance unit label (e.g. `"ft"`). |
| `grid.color` | string | Hex color of grid lines. |
| `grid.alpha` | number | Grid line opacity (0–1). |
| `darkness` | number | Ambient darkness level (0–1). |
| `globalLight` | boolean | Whether global illumination is on. |
| `fogExploration` | boolean | Whether fog of war is active. |
| `fogReset` | number | Timestamp of last fog reset. |
| `tokens` | array | Embedded Token documents. |
| `lights` | array | Embedded AmbientLight documents. |
| `sounds` | array | Embedded AmbientSound documents. |
| `walls` | array | Embedded Wall documents. |
| `notes` | array | Embedded Note documents. |
| `tiles` | array | Embedded Tile documents. |
| `drawings` | array | Embedded Drawing documents. |
| `templates` | array | Embedded MeasuredTemplate documents. |
| `regions` | array | Embedded Region documents (v12+). |

---

#### RollTable

A rollable table that produces random results.

| Field | Type | Notes |
|-------|------|-------|
| `name` | string | |
| `img` | string | Image path. |
| `description` | string | HTML description. |
| `results` | array | Embedded TableResult documents. |
| `formula` | string | Dice formula (e.g. `"1d20"`). |
| `replacement` | boolean | Whether results are replaced after rolling. |
| `displayRoll` | boolean | Whether roll is shown in chat. |

---

#### Playlist

A collection of audio tracks.

| Field | Type | Notes |
|-------|------|-------|
| `name` | string | |
| `description` | string | |
| `sounds` | array | Embedded PlaylistSound documents. |
| `mode` | number | `0`=sequential, `1`=shuffle, `2`=simultaneous, `3`=soundboard. |
| `playing` | boolean | Whether the playlist is currently playing. |
| `fade` | number | Fade duration in ms. |
| `channel` | string | `"interface"`, `"music"`, `"environment"`, `"voice"`. |

---

#### Combat

An active combat encounter.

| Field | Type | Notes |
|-------|------|-------|
| `scene` | string \| null | ID of linked scene. |
| `combatants` | array | Embedded Combatant documents. |
| `active` | boolean | Whether this combat is active. |
| `round` | number | Current round (0 = not started). |
| `turn` | number | Index of the current combatant's turn. |

---

#### ChatMessage

A message in the chat log.

| Field | Type | Notes |
|-------|------|-------|
| `type` | number | `0`=other, `1`=OOC, `2`=IC, `3`=emote, `4`=whisper, `5`=roll. |
| `user` | string | ID of the user who sent it. |
| `timestamp` | number | Unix timestamp in ms. |
| `flavor` | string | Short HTML header text. |
| `content` | string | HTML body. |
| `speaker.scene` | string | Scene ID. |
| `speaker.actor` | string | Actor ID. |
| `speaker.token` | string | Token ID. |
| `speaker.alias` | string | Display name of the speaker. |
| `whisper` | array of strings | User IDs for whisper recipients. |
| `blind` | boolean | Whether only the GM can see the roll result. |
| `rolls` | array | Serialized Roll objects. |
| `sound` | string | Path to sound played with this message. |

---

#### Macro

A script or chat command.

| Field | Type | Notes |
|-------|------|-------|
| `name` | string | |
| `type` | string | `"chat"` or `"script"`. |
| `img` | string | Image for the hotbar. |
| `scope` | string | `"global"` or `"actor"`. |
| `command` | string | The chat command or JavaScript to execute. |
| `author` | string | User ID of the creator. |

---

#### Folder

Organizes top-level documents in the sidebar.

| Field | Type | Notes |
|-------|------|-------|
| `name` | string | |
| `type` | string | The document type it contains: `"Actor"`, `"Item"`, `"JournalEntry"`, `"Scene"`, `"RollTable"`, `"Playlist"`, `"Macro"`, `"Cards"`. |
| `color` | string | Hex color for the folder label. |
| `parent` | string \| null | ID of parent folder (for nesting). |
| `sorting` | string | `"a"` = alphabetical (ignores `sort` field), `"m"` = manual (uses `sort` field). |

---

#### User

A connected user account.

| Field | Type | Notes |
|-------|------|-------|
| `name` | string | |
| `role` | number | `1`=Player, `2`=Trusted, `3`=Assistant GM, `4`=GM. |
| `avatar` | string | Image path. |
| `character` | string \| null | ID of the linked Actor. |
| `color` | string | Hex color used in UI. |
| `pronouns` | string | Optional pronouns string. |

---

#### Cards

A deck or hand of cards.

| Field | Type | Notes |
|-------|------|-------|
| `name` | string | |
| `type` | string | `"deck"`, `"hand"`, `"pile"`. |
| `img` | string | |
| `description` | string | HTML description. |
| `cards` | array | Embedded Card documents. |
| `width` | number | Card width in px. |
| `height` | number | Card height in px. |

---

#### Adventure

A packaged adventure module document.

| Field | Type | Notes |
|-------|------|-------|
| `name` | string | |
| `img` | string | Cover image. |
| `description` | string | HTML. |
| `actors` | array | Actor documents bundled in the adventure. |
| `items` | array | Item documents. |
| `scenes` | array | Scene documents. |
| `journal` | array | JournalEntry documents. |
| `tables` | array | RollTable documents. |
| `macros` | array | Macro documents. |
| `playlists` | array | Playlist documents. |
| `cards` | array | Cards documents. |
| `folders` | array | Folder documents. |

---

### Embedded Documents

Embedded documents require a `parentUuid` in the operation. They do not have a `folder` or `ownership` field (they inherit from the parent), though some (like JournalEntryPage) have their own `ownership` override.

See [parentUuid Format](#parentuuid-format) for how to construct the value.

---

#### JournalEntryPage

Embedded in: `JournalEntry`

| Field | Type | Notes |
|-------|------|-------|
| `name` | string | Page name (shown in sidebar list). |
| `type` | string | `"text"`, `"image"`, `"pdf"`, `"video"`. |
| `title.show` | boolean | Whether to display the title above the content. |
| `title.level` | number | Heading level 1–6. Controls sidebar indentation: 1=top, 2=indented. |
| `text.content` | string | HTML content (type `"text"` only). |
| `text.format` | number | `1`=HTML, `2`=Markdown. |
| `image.src` | string | Image path (type `"image"` only). |
| `image.caption` | string | Caption text. |
| `video.src` | string | Video path or URL (type `"video"` only). |
| `video.timestamp` | number | Start time in seconds. |
| `video.loop` | boolean | |
| `video.autoplay` | boolean | |
| `video.volume` | number | 0–1. |
| `src` | string | PDF path (type `"pdf"` only). |
| `category` | string \| null | ID of a JournalEntryCategory, or null. |
| `ownership` | object | Overrides parent journal ownership. |

---

#### JournalEntryCategory

Embedded in: `JournalEntry`

| Field | Type | Notes |
|-------|------|-------|
| `name` | string | Category label shown as a tab/section header. |

---

#### ActiveEffect

Embedded in: `Actor`, `Item`

| Field | Type | Notes |
|-------|------|-------|
| `name` | string | Display name. |
| `img` | string | Icon path. |
| `origin` | string | UUID of the item that created this effect. |
| `disabled` | boolean | Whether the effect is suppressed. |
| `transfer` | boolean | Whether the effect transfers from item to actor. |
| `statuses` | array of strings | Status condition ids (e.g. `["dead", "prone"]`). |
| `duration.startTime` | number | World time when effect started. |
| `duration.seconds` | number | Total duration in seconds. |
| `duration.combat` | string | Combat ID if combat-based. |
| `duration.rounds` | number | Duration in rounds. |
| `duration.turns` | number | Duration in turns. |
| `duration.startRound` | number | Round when effect started. |
| `duration.startTurn` | number | Turn when effect started. |
| `changes` | array | Effect change entries (see below). |

**Change entry:**

| Sub-field | Type | Notes |
|-----------|------|-------|
| `key` | string | Dot-path to the target field (e.g. `"system.abilities.str.value"`). |
| `mode` | number | `0`=Custom, `1`=Multiply, `2`=Add, `3`=Downgrade, `4`=Upgrade, `5`=Override. |
| `value` | string | Value to apply (always a string, even for numbers). |
| `priority` | number | Order of application. Higher = later. |

---

#### Token

Embedded in: `Scene`

| Field | Type | Notes |
|-------|------|-------|
| `name` | string | Display name. |
| `x` | number | Canvas x position in pixels. |
| `y` | number | Canvas y position in pixels. |
| `elevation` | number | Z elevation value. |
| `width` | number | Width in grid squares. |
| `height` | number | Height in grid squares. |
| `texture.src` | string | Token image path. |
| `texture.scaleX` | number | Horizontal scale. |
| `texture.scaleY` | number | Vertical scale. |
| `actorId` | string | ID of the linked Actor. |
| `actorLink` | boolean | Whether the token is linked to its actor. |
| `delta` | object | Overrides from the prototype token (only on unlinked tokens). |
| `sight.enabled` | boolean | |
| `sight.range` | number | |
| `sight.visionMode` | string | |
| `light.dim` | number | |
| `light.bright` | number | |
| `light.color` | string | |
| `light.alpha` | number | |
| `disposition` | number | `-1`=hostile, `0`=neutral, `1`=friendly, `2`=secret. |
| `displayName` | number | See Actor prototypeToken.displayName. |
| `displayBars` | number | |
| `bar1.attribute` | string | |
| `bar2.attribute` | string | |
| `hidden` | boolean | Whether the token is hidden from players. |
| `locked` | boolean | |

---

#### AmbientLight

Embedded in: `Scene`

| Field | Type | Notes |
|-------|------|-------|
| `x` | number | Canvas x position. |
| `y` | number | Canvas y position. |
| `rotation` | number | Light rotation in degrees. |
| `walls` | boolean | Whether light is blocked by walls. |
| `vision` | boolean | Whether light grants vision. |
| `config.dim` | number | Dim light radius in grid units. |
| `config.bright` | number | Bright light radius. |
| `config.color` | string | Hex color. |
| `config.alpha` | number | Opacity of the colored light. |
| `config.angle` | number | Emission angle (360 = full circle). |
| `config.luminosity` | number | Luminosity value. |
| `hidden` | boolean | |

---

#### AmbientSound

Embedded in: `Scene`

| Field | Type | Notes |
|-------|------|-------|
| `x` | number | |
| `y` | number | |
| `radius` | number | Sound radius in grid units. |
| `path` | string | Audio file path. |
| `repeat` | boolean | |
| `volume` | number | 0–1. |
| `walls` | boolean | Whether sound is blocked by walls. |
| `easing` | boolean | Whether volume eases with distance. |
| `hidden` | boolean | |

---

#### Wall

Embedded in: `Scene`

| Field | Type | Notes |
|-------|------|-------|
| `c` | array | `[x0, y0, x1, y1]` — start and end coordinates. |
| `light` | number | Light blocking: `0`=none, `1`=normal, `2`=limited. |
| `move` | number | Movement blocking: same scale. |
| `sight` | number | Sight blocking: same scale. |
| `sound` | number | Sound blocking: same scale. |
| `dir` | number | Directional: `0`=both, `1`=left, `2`=right. |
| `door` | number | Door type: `0`=none, `1`=door, `2`=secret. |
| `ds` | number | Door state: `0`=closed, `1`=open, `2`=locked. |
| `threshold.light` | number | Proximity threshold for attenuation. |
| `threshold.sight` | number | |
| `threshold.sound` | number | |
| `threshold.attenuation` | boolean | |

---

#### Tile

Embedded in: `Scene`

| Field | Type | Notes |
|-------|------|-------|
| `x` | number | |
| `y` | number | |
| `width` | number | Pixel width. |
| `height` | number | Pixel height. |
| `rotation` | number | Rotation in degrees. |
| `alpha` | number | Opacity (0–1). |
| `texture.src` | string | Image path. |
| `texture.scaleX` | number | |
| `texture.scaleY` | number | |
| `hidden` | boolean | |
| `locked` | boolean | |
| `overhead` | boolean | Whether the tile renders above tokens. |
| `roof` | boolean | Whether tile acts as a roof. |
| `video.loop` | boolean | |
| `video.autoplay` | boolean | |
| `video.volume` | number | |
| `occlusion.mode` | number | Occlusion behavior. |
| `occlusion.alpha` | number | Alpha when occluded. |

---

#### Note

Embedded in: `Scene` (map pins)

| Field | Type | Notes |
|-------|------|-------|
| `x` | number | |
| `y` | number | |
| `entryId` | string | ID of the linked JournalEntry. |
| `pageId` | string | ID of the linked JournalEntryPage. |
| `icon.src` | string | Pin icon path. |
| `icon.size` | number | Icon size in pixels. |
| `icon.tint` | string | Hex color tint. |
| `text.content` | string | Tooltip text (overrides journal name if set). |
| `text.fontSize` | number | |
| `text.fontFamily` | string | |
| `text.anchor` | number | Text anchor: `0`=center, `1`=top-left, `2`=top, `3`=top-right, `4`=right, `5`=bottom-right, `6`=bottom, `7`=bottom-left, `8`=left. |
| `global` | boolean | Whether note is visible without map vision. |

---

#### MeasuredTemplate

Embedded in: `Scene`

| Field | Type | Notes |
|-------|------|-------|
| `x` | number | Origin x. |
| `y` | number | Origin y. |
| `direction` | number | Direction in degrees. |
| `distance` | number | Template distance in grid units. |
| `angle` | number | Angle for cone templates. |
| `width` | number | Width for ray templates. |
| `t` | string | Shape: `"circle"`, `"cone"`, `"rect"`, `"ray"`. |
| `user` | string | Creator user ID. |
| `texture` | string | Fill texture path. |
| `fillColor` | string | Hex fill color. |
| `borderColor` | string | Hex border color. |
| `hidden` | boolean | |

---

#### Drawing

Embedded in: `Scene`

| Field | Type | Notes |
|-------|------|-------|
| `x` | number | |
| `y` | number | |
| `shape.type` | string | `"r"` rect, `"e"` ellipse, `"p"` polygon, `"f"` freehand, `"t"` text. |
| `shape.width` | number | |
| `shape.height` | number | |
| `shape.points` | array | `[x, y, ...]` pairs for polygon/freehand. |
| `rotation` | number | Degrees. |
| `fillType` | number | `0`=none, `1`=solid, `2`=pattern. |
| `fillColor` | string | |
| `fillAlpha` | number | |
| `strokeWidth` | number | |
| `strokeColor` | string | |
| `strokeAlpha` | number | |
| `text` | string | Text content for type `"t"`. |
| `fontFamily` | string | |
| `fontSize` | number | |
| `textColor` | string | |
| `textAlpha` | number | |
| `hidden` | boolean | |
| `locked` | boolean | |
| `author` | string | User ID. |

---

#### Region

Embedded in: `Scene` (v12+)

| Field | Type | Notes |
|-------|------|-------|
| `name` | string | |
| `color` | string | Hex color. |
| `shapes` | array | Shape definitions (each has `type`, geometry fields). |
| `elevation.bottom` | number | Bottom elevation. |
| `elevation.top` | number | Top elevation. |
| `behaviors` | array | Embedded RegionBehavior documents. |
| `visibility` | number | `0`=always, `1`=light, `2`=GM. |
| `locked` | boolean | |

---

#### Combatant

Embedded in: `Combat`

| Field | Type | Notes |
|-------|------|-------|
| `actorId` | string | ID of the linked Actor. |
| `tokenId` | string | ID of the linked Token. |
| `sceneId` | string | ID of the Scene. |
| `name` | string | Display name override. |
| `img` | string | Image override. |
| `initiative` | number \| null | Rolled initiative value. |
| `hidden` | boolean | Whether hidden from players. |
| `defeated` | boolean | Whether marked as defeated. |

---

#### TableResult

Embedded in: `RollTable`

| Field | Type | Notes |
|-------|------|-------|
| `type` | number | `0`=text, `1`=document, `2`=compendium. |
| `text` | string | Result text. |
| `img` | string | Result image. |
| `documentCollection` | string | Collection name for type 1/2. |
| `documentId` | string | Document ID for type 1/2. |
| `weight` | number | Relative weight for random selection. |
| `range` | array | `[min, max]` roll range. |
| `drawn` | boolean | Whether this result has been drawn (no-replacement tables). |

---

#### PlaylistSound

Embedded in: `Playlist`

| Field | Type | Notes |
|-------|------|-------|
| `name` | string | |
| `description` | string | |
| `path` | string | Audio file path. |
| `playing` | boolean | |
| `volume` | number | 0–1. |
| `repeat` | boolean | |
| `fade` | number | Fade duration in ms. |
| `channel` | string | `"interface"`, `"music"`, `"environment"`, `"voice"`. |

---

#### Card

Embedded in: `Cards`

| Field | Type | Notes |
|-------|------|-------|
| `name` | string | |
| `type` | string | Card type (e.g. `"base"`). |
| `description` | string | HTML. |
| `suit` | string | |
| `value` | number | |
| `faces` | array | Array of `{img, name, text}` face objects. |
| `face` | number \| null | Index of the currently shown face, or null (back showing). |
| `back.img` | string | Back face image. |
| `back.name` | string | Back face name. |
| `back.text` | string | Back face text. |
| `drawn` | boolean | Whether the card has been drawn. |
| `origin` | string | ID of the source deck. |

---

## Sorting and Ordering

### The `sort` field

Every document type — top-level and embedded — has a `sort` field:

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `sort` | integer | `0` | Ascending. Lower values appear first. Present on all document types. |

There is no dedicated reorder operation. Sorting is purely a field update:

```json
{
  "type": "JournalEntryPage",
  "action": "update",
  "operation": {
    "updates": [{ "_id": "pageId", "sort": 200000 }],
    "parentUuid": "JournalEntry.journalId"
  }
}
```

`sort` is accepted in both `create` (inside `data[]`) and `update` (inside `updates[]`) payloads. The server stores whatever integer you send — no validation.

Documents with equal `sort` values (e.g. all 0) fall back to creation-time order, which is not guaranteed to be stable from the client's perspective. Assign explicit sort values if order matters.

### Midpoint algorithm

The Foundry UI uses an integer midpoint algorithm (client-side only, `SortingHelpers.performIntegerSort`). The server has no knowledge of it. The convention:

| Operation | Sort value |
|-----------|-----------|
| First item | `100000` |
| Append after last (sort = L) | `L + 100000` |
| Insert between A and B | `Math.round((A + B) / 2)` |
| Re-number all (gap too small) | Reassign as `100000, 200000, 300000, ...` |

The constant `100000` is `SORT_INTEGER_DENSITY` in the Foundry client. For CLI/MCP use, `position * 100000` is a safe strategy when building an ordered list from scratch.

### Context-specific ordering

Different document types use different ordering mechanisms:

| Document | Field | Direction | Notes |
|----------|-------|-----------|-------|
| All documents | `sort` | ascending | The universal ordering field. |
| Folder contents | `sort` | ascending | Only used when `Folder.sorting = "m"` (manual). Ignored when `"a"` (alphabetical). |
| Scene navigation bar | `navOrder` | ascending | Controls position in the nav bar. Separate from `sort`. |
| Scene nav visibility | `navigation` | — | Boolean. `false` hides the scene from the nav bar regardless of `navOrder`. |
| Token z-order on canvas | `sort` | descending | Higher sort = rendered on top, hit-tested first. |
| Combatant turn order | `initiative` | descending | Float. Higher initiative = earlier turn. Not related to `sort`. |
| Items inside Actor | `sort` | ascending | The Shadowdark system's `_sortByUserOrder()` reads this field directly. |

### Combatant initiative updates

Initiative is set via a batch embedded-document update (not a special initiative-roll event):

```json
{
  "type": "Combatant",
  "action": "update",
  "operation": {
    "updates": [
      { "_id": "combatant1Id", "initiative": 5 },
      { "_id": "combatant2Id", "initiative": 3 }
    ],
    "parentUuid": "Combat.combatId"
  }
}
```

The combat tracker re-renders sorted by `initiative` descending. The current turn is tracked by `Combat.turn` (index into the sorted list). To advance the turn, update `Combat.turn` directly.

### Scene navigation order

```json
{
  "type": "Scene",
  "action": "update",
  "operation": {
    "updates": [
      { "_id": "sceneId", "navOrder": 1, "navigation": true }
    ]
  }
}
```

---

## Ownership and Permissions

The `ownership` field is present on all top-level documents and on JournalEntryPage.

```json
{
  "default": 0,
  "userId1": 3,
  "userId2": 2
}
```

### Permission Level Values

| Value | Constant | Meaning |
|-------|----------|---------|
| `-1` | `INHERIT` | Inherit from parent document. Used on embedded docs. |
| `0` | `NONE` | No access (private). |
| `1` | `LIMITED` | Limited view (system-dependent; e.g. see actor name but not sheet). |
| `2` | `OBSERVER` | Can view. |
| `3` | `OWNER` | Full control. |

The `"default"` key sets the baseline for all users not listed individually.

---

## parentUuid Format

Embedded document operations require a `parentUuid` that identifies the parent document.

**Format:** `"<DocumentType>.<documentId>"`

**Examples:**

| Operation | parentUuid |
|-----------|-----------|
| Page inside JournalEntry | `"JournalEntry.abc123def456"` |
| Category inside JournalEntry | `"JournalEntry.abc123def456"` |
| Item inside Actor | `"Actor.xyz789"` |
| ActiveEffect inside Item | `"Item.itemId"` |
| Token inside Scene | `"Scene.sceneId"` |
| Combatant inside Combat | `"Combat.combatId"` |

**For compendium-owned documents:**
`"Compendium.shadowdark.actors.Actor.documentId"`

---

## System Socket Channel

The Shadowdark system uses a named channel for system-specific events:

```javascript
game.socket.on("system.shadowdark", handler)
game.socket.emit("system.shadowdark", payload)
```

All payloads have a `type` discriminator field.

| `type` | Direction | Purpose |
|--------|-----------|---------|
| `createCharacter` | player → GM | Request character creation. |
| `openNewCharacter` | GM → player | Notify player their character is ready. |
| `dropLightSourceOnScene` | player → GM | Drop a light source as a scene token. |
| `pickupLightSourceFromScene` | player → GM | Pick up a light source from the scene. |
| `toggleLightSource` | player → GM | Toggle a light source on/off. |

See `shadowdark-data-model.md` § Socket Events for per-event payload schemas.

Other systems and modules register their own channels using the same pattern:
`game.socket.on("system.<systemId>", ...)` or `game.socket.on("module.<moduleId>", ...)`.

---

## Error Handling

### modifyDocument error response

```json
{
  "error": {
    "message": "Human-readable error description"
  }
}
```

Check for `result.get("error")` before using the result.

### Timeout

`modifyDocument` callbacks have a 15-second timeout. No response within that window means the socket connection is broken or the server is overloaded.

### Common error conditions

| Condition | Message pattern |
|-----------|----------------|
| No world active | `"No world is active"` |
| Wrong world active | Contains active world name |
| Document not found | `"not found"` or `"does not exist"` |
| Permission denied | `"You do not have permission"` |
| Invalid data | Validation error from Foundry's data model |

---

## Constants

| Constant | Value | Description |
|----------|-------|-------------|
| `INHERIT` | `-1` | Ownership: inherit from parent |
| `NONE` | `0` | Ownership: no access |
| `LIMITED` | `1` | Ownership: limited view |
| `OBSERVER` | `2` | Ownership: view only |
| `OWNER` | `3` | Ownership: full control |
| Page text format HTML | `1` | `text.format = 1` |
| Page text format Markdown | `2` | `text.format = 2` |
| Socket timeout | `15s` | modifyDocument callback timeout |
| Socket transport | `"websocket"` | Must use WebSocket, not polling |
