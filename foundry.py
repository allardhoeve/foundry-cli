#!/usr/bin/env python3
"""foundry -- CLI for Foundry VTT

Manages journal entries in a running Foundry world via Socket.io.
Credentials are loaded from .env (or env vars):
  FOUNDRY_URL, FOUNDRY_BASIC_USER, FOUNDRY_BASIC_PASS,
  FOUNDRY_WORLD, FOUNDRY_GM_USER, FOUNDRY_GM_PASSWORD
"""

import base64
import json
import os
import re
import sys
import threading
from pathlib import Path

import click
import requests
import socketio
from dotenv import load_dotenv

import hexgrid
import hexstyle

load_dotenv(Path(__file__).parent / ".env")


# ── Config ─────────────────────────────────────────────────────────────────────

def _load_config() -> dict:
    cfg = {
        "url":         os.getenv("FOUNDRY_URL", ""),
        "basic_user":  os.getenv("FOUNDRY_BASIC_USER", ""),
        "basic_pass":  os.getenv("FOUNDRY_BASIC_PASS", ""),
        "world":       os.getenv("FOUNDRY_WORLD", ""),
        "gm_user":     os.getenv("FOUNDRY_GM_USER", ""),
        "gm_password": os.getenv("FOUNDRY_GM_PASSWORD", ""),
    }
    missing = [k for k in ("url", "world", "gm_user") if not cfg[k]]
    if missing:
        raise click.ClickException(f"Missing config: {', '.join(missing)}. Check .env")
    return cfg


# ── Foundry ownership constants ────────────────────────────────────────────────

_INHERIT  = -1
_NONE     = 0
_OBSERVER = 2


# ── Shadowdark attack inputs ───────────────────────────────────────────────────

# Effect keys that can change a to-hit roll: attack/damage roll bonuses,
# item bonus blocks, and ability scores (which drive the modifier).
_ATTACK_KEY = re.compile(
    r"(^|\.)roll\.(melee|ranged|attack)\.|bonuses\..*attack|abilities\.\w+\.value",
    re.IGNORECASE,
)


def _ability_mod(score: int) -> int:
    return max(-4, min(4, (score - 10) // 2))


def _effect_changes(effect: dict) -> list:
    # v14 stores changes under effect.system.changes; older data uses effect.changes.
    return effect.get("changes") or (effect.get("system") or {}).get("changes") or []


def _attack_effects(effects: list, source: str, source_type: str) -> list[dict]:
    rows = []
    for e in effects:
        for c in _effect_changes(e):
            if _ATTACK_KEY.search(c.get("key", "")):
                rows.append({
                    "source":     source,
                    "sourceType": source_type,
                    "effect":     e.get("name", ""),
                    "key":        c["key"],
                    "type":       c.get("type", c.get("mode")),
                    "value":      c.get("value"),
                    "disabled":   bool(e.get("disabled")),
                    # Item effects with transfer=false never reach the actor.
                    "transfer":   source_type == "Actor" or e.get("transfer", True) is not False,
                })
    return rows


def _attack_inputs(actor: dict) -> dict:
    s = actor.get("system", {})
    items = actor.get("items", [])
    effects = _attack_effects(actor.get("effects", []), actor["name"], "Actor")
    for i in items:
        effects += _attack_effects(i.get("effects", []), i["name"], i["type"])
    return {
        "name":  actor["name"],
        "type":  actor.get("type"),
        "level": (s.get("level") or {}).get("value"),
        "abilities": {
            k: {"value": v["value"], "mod": _ability_mod(v["value"])}
            for k, v in (s.get("abilities") or {}).items() if "value" in v
        },
        "weapons": [
            {
                "name":     i["name"],
                "type":     i["system"].get("type", ""),
                "range":    i["system"].get("range", ""),
                "equipped": bool(i["system"].get("equipped")),
                "bonuses":  {k: v for k, v in (i["system"].get("bonuses") or {}).items()
                             if "attack" in k.lower() and v},
            }
            for i in items if i["type"] == "Weapon"
        ],
        "effects": effects,
    }


# ── Foundry client ─────────────────────────────────────────────────────────────

class FoundryClient:
    def __init__(self, cfg: dict):
        self._url = cfg["url"].rstrip("/")
        self._basic = (cfg["basic_user"], cfg["basic_pass"])
        self._world = cfg["world"]
        self._gm_user = cfg["gm_user"]
        self._gm_password = cfg["gm_password"]

        self._http = requests.Session()
        if self._basic[0]:
            self._http.auth = self._basic

        self._sio = socketio.Client(logger=False, engineio_logger=False)
        self._ready = threading.Event()

        @self._sio.event
        def connect():
            self._ready.set()

    def _socket_headers(self) -> dict:
        headers = {"Cookie": "; ".join(f"{k}={v}" for k, v in self._http.cookies.items())}
        if self._basic[0]:
            token = base64.b64encode(f"{self._basic[0]}:{self._basic[1]}".encode()).decode()
            headers["Authorization"] = f"Basic {token}"
        return headers

    def _check_world(self):
        r = self._http.get(f"{self._url}/api/status")
        r.raise_for_status()
        status = r.json()
        if not status.get("active"):
            raise click.ClickException("No world is active on this Foundry instance")
        active = status.get("world", "")
        if active != self._world:
            raise click.ClickException(
                f"Expected world '{self._world}' but '{active}' is active")

    def _discover_user_id(self) -> str:
        result: list = [None]
        done = threading.Event()
        sio = socketio.Client(logger=False, engineio_logger=False)

        @sio.event
        def connect():
            def on_data(data):
                result[0] = data
                done.set()
            sio.emit("getJoinData", callback=on_data)

        sio.connect(self._url, headers=self._socket_headers(), transports=["websocket"])
        done.wait(timeout=10)
        sio.disconnect()

        data = result[0]
        if not data:
            raise click.ClickException("getJoinData returned no data")

        users = data.get("users", [])
        for u in users:
            if u.get("name", "").lower() == self._gm_user.lower():
                return u["_id"]

        names = [u.get("name") for u in users]
        raise click.ClickException(f"User '{self._gm_user}' not found. Available: {names}")

    def connect(self):
        self._check_world()
        self._http.get(f"{self._url}/join")
        user_id = self._user_id = self._discover_user_id()
        # v14 rejects the join POST without a same-origin fetch header, and
        # expects username + userId in place of the old lowercase userid.
        r = self._http.post(f"{self._url}/join",
                            headers={"Sec-Fetch-Site": "same-origin"},
                            json={"action": "join", "username": self._gm_user,
                                  "userId": user_id,
                                  "password": self._gm_password})
        r.raise_for_status()
        self._sio.connect(self._url, headers=self._socket_headers(), transports=["websocket"])
        if not self._ready.wait(timeout=10):
            raise click.ClickException("Socket.io connection timed out")

    def disconnect(self):
        self._sio.disconnect()

    def _emit(self, payload: dict) -> dict:
        result: list = [None]
        done = threading.Event()

        def ack(response):
            result[0] = response
            done.set()

        self._sio.emit("modifyDocument", payload, callback=ack)
        if not done.wait(timeout=15):
            raise click.ClickException("No response from Foundry (timeout)")
        r = result[0]
        if r.get("error"):
            raise click.ClickException(r["error"].get("message", str(r["error"])))
        return r

    def _get(self, doc_type: str, query: dict | None = None, pack: str | None = None) -> list:
        operation: dict = {"query": query or {}}
        if pack is not None:
            operation["pack"] = pack
        r = self._emit({
            "type": doc_type,
            "action": "get",
            "operation": operation,
        })
        return r.get("result", [])

    def _find_journal(self, name: str) -> dict:
        for j in self._get("JournalEntry"):
            if j["name"] == name:
                return j
        raise click.ClickException(f"Journal '{name}' not found")

    def _find_or_create_folder(self, name: str) -> str:
        for f in self._get("Folder", {"type": "JournalEntry"}):
            if f["name"].lower() == name.lower():
                return f["_id"]
        r = self._emit({
            "type": "Folder",
            "action": "create",
            "operation": {"data": [{"name": name, "type": "JournalEntry"}]},
        })
        return r["result"][0]["_id"]

    # ── Actor ─────────────────────────────────────────────────────────────────

    def get_actors(self) -> list:
        return self._get("Actor")

    def actor_show(self, name: str | None = None) -> list[dict]:
        """Attack-relevant inputs per Player actor (Shadowdark). Raw values, no math."""
        actors = self.get_actors()
        if name is not None:
            actors = [a for a in actors if a["name"] == name]
            if not actors:
                raise click.ClickException(f"Actor '{name}' not found")
        else:
            actors = [a for a in actors if a.get("type") == "Player"]
        return [_attack_inputs(a) for a in sorted(actors, key=lambda a: a["name"])]

    # ── Compendium ────────────────────────────────────────────────────────────

    def compendium_get(self, uuid: str) -> dict:
        """Fetch one raw document by compendium UUID, e.g.
        Compendium.shadowdark.properties.Item.jq0m0lGb7QOCSJXL"""
        parts = uuid.split(".")
        if len(parts) != 5 or parts[0] != "Compendium":
            raise click.ClickException(
                f"Not a compendium UUID: '{uuid}'. "
                "Expected Compendium.<package>.<pack>.<Type>.<id>")
        _, package, pack_name, doc_type, doc_id = parts
        pack = f"{package}.{pack_name}"
        try:
            docs = self._get(doc_type, {"_id": doc_id}, pack=pack)
        except click.ClickException as e:
            # Foundry reports an unknown pack as a JS TypeError on packData.
            if "packData" in e.message:
                raise click.ClickException(f"Compendium pack '{pack}' not found") from None
            raise
        if not docs:
            raise click.ClickException(f"Document '{doc_id}' not found in compendium '{pack}'")
        return docs[0]

    # ── Journal ───────────────────────────────────────────────────────────────

    def get_journals(self) -> list:
        return self._get("JournalEntry")

    def journal_upsert(self, title: str, folder: str | None, public: bool) -> dict:
        folder_id = self._find_or_create_folder(folder) if folder else None
        ownership = {"default": _OBSERVER if public else _NONE}
        existing = [j for j in self.get_journals() if j["name"] == title]

        if existing:
            update: dict = {"_id": existing[0]["_id"], "ownership": ownership}
            if folder_id is not None:
                update["folder"] = folder_id
            r = self._emit({
                "type": "JournalEntry",
                "action": "update",
                "operation": {"updates": [update]},
            })
            return r["result"][0]

        data: dict = {"name": title, "ownership": ownership}
        if folder_id is not None:
            data["folder"] = folder_id
        r = self._emit({
            "type": "JournalEntry",
            "action": "create",
            "operation": {"data": [data]},
        })
        return r["result"][0]

    def journal_delete(self, title: str) -> bool:
        matches = [j for j in self.get_journals() if j["name"] == title]
        if not matches:
            return False
        self._emit({
            "type": "JournalEntry",
            "action": "delete",
            "operation": {"ids": [j["_id"] for j in matches]},
        })
        return True

    # ── Category ──────────────────────────────────────────────────────────────

    def category_list(self, journal_name: str) -> list:
        return self._find_journal(journal_name).get("categories", [])

    def category_upsert(self, journal_name: str, name: str) -> dict:
        j = self._find_journal(journal_name)
        for cat in j.get("categories", []):
            if cat["name"] == name:
                return cat
        r = self._emit({
            "type": "JournalEntryCategory",
            "action": "create",
            "operation": {
                "data": [{"name": name}],
                "parentUuid": f"JournalEntry.{j['_id']}",
            },
        })
        return r["result"][0]

    def category_delete(self, journal_name: str, name: str) -> bool:
        j = self._find_journal(journal_name)
        matches = [c for c in j.get("categories", []) if c["name"] == name]
        if not matches:
            return False
        self._emit({
            "type": "JournalEntryCategory",
            "action": "delete",
            "operation": {
                "ids": [c["_id"] for c in matches],
                "parentUuid": f"JournalEntry.{j['_id']}",
            },
        })
        return True

    # ── Page ──────────────────────────────────────────────────────────────────

    def page_list(self, journal_name: str) -> list:
        j = self._find_journal(journal_name)
        cat_map = {c["_id"]: c["name"] for c in j.get("categories", [])}
        pages = j.get("pages", [])
        for p in pages:
            p["_category_name"] = cat_map.get(p.get("category"), "")
        return pages

    def page_upsert(self, journal_name: str, title: str, category_name: str | None,
                    level: int, public: bool, content: str,
                    index: int | None = None,
                    before: str | None = None,
                    after: str | None = None) -> dict:
        j = self._find_journal(journal_name)
        parent_uuid = f"JournalEntry.{j['_id']}"

        category_id = None
        if category_name:
            matched = [c for c in j.get("categories", []) if c["name"] == category_name]
            if not matched:
                cmd = (f'foundry journal category upsert'
                       f' --journal "{journal_name}" --name "{category_name}"')
                raise click.ClickException(
                    f"Category '{category_name}' not found. Create it first:\n  {cmd}")
            category_id = matched[0]["_id"]

        page_data: dict = {
            "name": title,
            "type": "text",
            "title": {"show": True, "level": level},
            "text": {"content": content, "format": 1},
            "ownership": {"default": _OBSERVER if public else _INHERIT},
        }
        if category_id is not None:
            page_data["category"] = category_id

        if before is not None or after is not None:
            ref = before or after
            ref_pages = sorted(
                [p for p in j.get("pages", [])
                 if p.get("category") == category_id and p["name"] != title],
                key=lambda p: p.get("sort", 0),
            )
            names = [p["name"] for p in ref_pages]
            if ref not in names:
                raise click.ClickException(f"Reference page '{ref}' not found in category")
            pos = names.index(ref)
            index = pos if before else pos + 1

        sort_updates: list[dict] = []
        if index is not None:
            cat_pages = sorted(
                [p for p in j.get("pages", []) if p.get("category") == category_id],
                key=lambda p: p.get("sort", 0),
            )
            cat_pages = [p for p in cat_pages if p["name"] != title]
            n = max(0, min(index, len(cat_pages)))
            ordered = cat_pages[:n] + [None] + cat_pages[n:]
            for i, p in enumerate(ordered):
                sort_val = (i + 1) * 100000
                if p is None:
                    page_data["sort"] = sort_val
                else:
                    sort_updates.append({"_id": p["_id"], "sort": sort_val})

        existing = [p for p in j.get("pages", []) if p["name"] == title]
        if existing:
            r = self._emit({
                "type": "JournalEntryPage",
                "action": "update",
                "operation": {
                    "updates": [{"_id": existing[0]["_id"], **page_data}],
                    "parentUuid": parent_uuid,
                },
            })
        else:
            r = self._emit({
                "type": "JournalEntryPage",
                "action": "create",
                "operation": {
                    "data": [page_data],
                    "parentUuid": parent_uuid,
                },
            })

        if sort_updates:
            self._emit({
                "type": "JournalEntryPage",
                "action": "update",
                "operation": {"updates": sort_updates, "parentUuid": parent_uuid},
            })

        return r["result"][0]

    def page_reorder(self, journal_name: str, titles: list[str]) -> int:
        j = self._find_journal(journal_name)
        parent_uuid = f"JournalEntry.{j['_id']}"
        by_name = {p["name"]: p for p in j.get("pages", [])}
        missing = [t for t in titles if t not in by_name]
        if missing:
            raise click.ClickException(f"Pages not found: {', '.join(missing)}")
        updates = [
            {"_id": by_name[t]["_id"], "sort": (i + 1) * 100000}
            for i, t in enumerate(titles)
        ]
        self._emit({
            "type": "JournalEntryPage",
            "action": "update",
            "operation": {"updates": updates, "parentUuid": parent_uuid},
        })
        return len(updates)

    def page_delete(self, journal_name: str, title: str) -> bool:
        j = self._find_journal(journal_name)
        matches = [p for p in j.get("pages", []) if p["name"] == title]
        if not matches:
            return False
        self._emit({
            "type": "JournalEntryPage",
            "action": "delete",
            "operation": {
                "ids": [p["_id"] for p in matches],
                "parentUuid": f"JournalEntry.{j['_id']}",
            },
        })
        return True

    # ── Hex map ───────────────────────────────────────────────────────────────
    # Everything the tool draws on a scene is a Drawing tagged with
    # flags.world.hexmap = {"kind": "anchor" | "number" | "label", "hex": "CCRR"}.
    # The scene keeps its setup and calibration in flags.world.hexmap.

    def _find_scene(self, name: str) -> dict:
        scenes = self._get("Scene")
        matches = [s for s in scenes if s["name"] == name]
        if not matches:
            names = ", ".join(sorted(s["name"] for s in scenes)) or "(none)"
            raise click.ClickException(f"Scene '{name}' not found. Scenes: {names}")
        if len(matches) > 1:
            raise click.ClickException(
                f"{len(matches)} scenes are named '{name}'; rename one so the name is unique")
        scene = matches[0]
        grid_type = scene.get("grid", {}).get("type")
        try:
            hexgrid.orientation_for(grid_type)
        except ValueError:
            raise click.ClickException(
                f"Scene '{name}' does not use a hex grid (grid type {grid_type}). "
                "Set a hexagonal grid in the scene's Grid settings first.") from None
        return scene

    @staticmethod
    def _hexmap_cfg(scene: dict) -> dict:
        return scene.get("flags", {}).get("world", {}).get("hexmap", {})

    @staticmethod
    def _hexmap_drawings(scene: dict, kind: str) -> list[dict]:
        return [d for d in scene.get("drawings", [])
                if d.get("flags", {}).get("world", {}).get("hexmap", {}).get("kind") == kind]

    def _require_calibration(self, scene: dict) -> dict:
        cfg = self._hexmap_cfg(scene)
        if "calibration" not in cfg:
            n = scene["name"]
            if "size" not in cfg:
                raise click.ClickException(
                    f"Scene '{n}' has no hex map setup yet. Start with:\n"
                    f'  foundry hexmap init --scene "{n}" --size COLSxROWS')
            raise click.ClickException(
                f"Scene '{n}' is not calibrated yet. Drag the two anchor hexagons onto "
                f"their printed hexes, then run:\n  foundry hexmap calibrate --scene \"{n}\"")
        return cfg

    def _scene_emit(self, scene: dict, action: str, operation: dict) -> dict:
        operation["parentUuid"] = f"Scene.{scene['_id']}"
        return self._emit({"type": "Drawing", "action": action, "operation": operation})

    def _drawing_base(self, scene: dict, kind: str, hex_id: str) -> dict:
        data = {"author": self._user_id,
                "flags": {"world": {"hexmap": {"kind": kind, "hex": hex_id}}}}
        level = scene.get("initialLevel")
        if level:
            data["levels"] = [level]
        return data

    def _boxed_drawing(self, scene: dict, kind: str, hex_id: str, text: str,
                       x: float, y: float, style: dict, hidden: bool) -> dict:
        """Text in a filled box, visibly centred on (x, y)."""
        return (self._drawing_base(scene, kind, hex_id)
                | hexstyle.boxed_text(text, x, y, style) | {"hidden": hidden})

    def _scene_update_cfg(self, scene: dict, cfg: dict) -> None:
        self._emit({
            "type": "Scene", "action": "update",
            "operation": {"updates": [{"_id": scene["_id"],
                                       "flags": {"world": {"hexmap": cfg}}}]},
        })

    def hexmap_init(self, scene_name: str, size: tuple[int, int], shifted: str) -> list[dict]:
        """Place (or keep) the two anchor hexagons. Returns the anchors."""
        scene = self._find_scene(scene_name)
        grid = scene["grid"]
        orientation = hexgrid.orientation_for(grid["type"])
        cols, rows = size
        wanted = [(1, 1), (cols, rows)]
        wanted_ids = [hexgrid.fmt_hex(c, r) for c, r in wanted]

        existing = {d["flags"]["world"]["hexmap"]["hex"]: d
                    for d in self._hexmap_drawings(scene, "anchor")}
        stale = [d["_id"] for h, d in existing.items() if h not in wanted_ids]
        if stale:
            self._scene_emit(scene, "delete", {"ids": stale})

        w, h = hexgrid.hex_dims(grid["size"], orientation)
        rx, ry, rw, rh = hexgrid.scene_rect(scene["width"], scene["height"],
                                            scene.get("padding", 0), grid["size"], orientation)
        # Rough first guess: one hex in from the scene's top-left and bottom-right.
        guesses = {wanted_ids[0]: (rx + w, ry + h), wanted_ids[1]: (rx + rw - w, ry + rh - h)}
        new = []
        for hex_id in wanted_ids:
            if hex_id in existing:
                continue
            cx, cy = guesses[hex_id]
            new.append(self._drawing_base(scene, "anchor", hex_id) | {
                "x": round(cx - w / 2), "y": round(cy - h / 2),
                "shape": {"type": "p", "width": round(w), "height": round(h),
                          "points": hexgrid.hexagon_points(round(w), round(h), orientation)},
                "strokeWidth": 6, "strokeColor": "#ff00ff", "strokeAlpha": 1,
                "fillType": 0, "fillAlpha": 0,
                "text": f"ANCHOR\n{hex_id}", "fontSize": 36, "textColor": "#ff00ff",
                "textAlpha": 1, "hidden": True,
            })
        if new:
            self._scene_emit(scene, "create", {"data": new})

        cfg = dict(self._hexmap_cfg(scene))
        cfg.update({"size": [cols, rows], "shifted": shifted})
        self._scene_update_cfg(scene, cfg)
        scene = self._find_scene(scene_name)
        return self._hexmap_drawings(scene, "anchor")

    def hexmap_calibrate(self, scene_name: str, label_pos: str | None = None) -> dict:
        scene = self._find_scene(scene_name)
        cfg = dict(self._hexmap_cfg(scene))
        if "size" not in cfg:
            raise click.ClickException(
                f"Scene '{scene_name}' has no anchors yet. Start with:\n"
                f'  foundry hexmap init --scene "{scene_name}" --size COLSxROWS')
        cols, rows = cfg["size"]
        anchor_ids = [hexgrid.fmt_hex(1, 1), hexgrid.fmt_hex(cols, rows)]
        anchors = {d["flags"]["world"]["hexmap"]["hex"]: d
                   for d in self._hexmap_drawings(scene, "anchor")}
        missing = [h for h in anchor_ids if h not in anchors]
        if missing:
            raise click.ClickException(
                f"Anchor(s) {', '.join(missing)} not found on '{scene_name}' (deleted?). "
                f"Recreate them with:\n  foundry hexmap init --scene \"{scene_name}\" "
                f"--size {cols}x{rows}")

        def centre(d):
            return d["x"] + d["shape"]["width"] / 2, d["y"] + d["shape"]["height"] / 2

        grid = scene["grid"]
        orientation = hexgrid.orientation_for(grid["type"])
        a, b = (anchors[h] for h in anchor_ids)
        cal = hexgrid.calibrate((1, 1), centre(a), (cols, rows), centre(b),
                                orientation, cfg["shifted"])
        exp_col, exp_row = hexgrid.expected_steps(grid["size"], orientation)
        warnings = []
        for what, got, exp in (("column", cal["col_step"], exp_col),
                               ("row", cal["row_step"], exp_row)):
            if abs(got - exp) / exp > 0.03:
                warnings.append(
                    f"{what} step is {got:.1f}px but the scene grid implies {exp:.1f}px. "
                    "An anchor may be on the wrong hex, or the grid size doesn't match the map.")
        cfg["calibration"] = cal
        cfg["label_pos"] = label_pos or cfg.get("label_pos", "bottom")
        self._scene_update_cfg(scene, cfg)
        return {"calibration": cal, "expected": {"col_step": exp_col, "row_step": exp_row},
                "label_pos": cfg["label_pos"], "warnings": warnings}

    def hexmap_numbers(self, scene_name: str, remove: bool = False) -> int:
        """Replace the hex-number layer (or just remove it). Returns hexes drawn.

        Numbers aren't secret: they're visible to players too, and each user
        switches them on or off with the homebrew module's toolbar toggle."""
        scene = self._find_scene(scene_name)
        old = [d["_id"] for d in self._hexmap_drawings(scene, "number")]
        if old:
            self._scene_emit(scene, "delete", {"ids": old})
        if remove:
            return 0
        cfg = self._require_calibration(scene)
        cal, (cols, rows) = cfg["calibration"], cfg["size"]
        data = []
        for c in range(1, cols + 1):
            for r in range(1, rows + 1):
                x, y = hexgrid.number_point(cal, c, r)
                hex_id = hexgrid.fmt_hex(c, r)
                data.append(self._boxed_drawing(scene, "number", hex_id, hex_id, x, y,
                                                hexstyle.NUMBER_STYLE, hidden=False))
        self._scene_emit(scene, "create", {"data": data})
        return len(data)

    def hexmap_label(self, scene_name: str, hex_str: str, text: str | None,
                     public: bool | None, pos: str | None) -> dict:
        scene = self._find_scene(scene_name)
        cfg = self._require_calibration(scene)
        try:
            col, row = hexgrid.parse_hex(hex_str, tuple(cfg["size"]))
        except ValueError as e:
            raise click.ClickException(str(e)) from None
        hex_id = hexgrid.fmt_hex(col, row)
        existing = [d for d in self._hexmap_drawings(scene, "label")
                    if d["flags"]["world"]["hexmap"]["hex"] == hex_id]
        cal = cfg["calibration"]

        if existing:
            d = existing[0]
            update: dict = {"_id": d["_id"]}
            if public is not None:
                update["hidden"] = not public
            if text is not None or pos is not None:
                # Re-box around the label's current centre (which may have been
                # dragged by hand), or around the requested position.
                x, y = (hexgrid.label_point(cal, col, row, pos) if pos is not None
                        else hexstyle.box_centre(d))
                box = hexstyle.boxed_text(text if text is not None else d.get("text", ""),
                                          x, y, hexstyle.LABEL_STYLE)
                update |= {k: box[k] for k in ("x", "y", "shape", "text")}
            self._scene_emit(scene, "update", {"updates": [update]})
            return d | update | {"_hex": hex_id, "_created": False}

        if text is None:
            raise click.ClickException(
                f"Hex {hex_id} has no label yet; give its text, e.g.\n"
                f'  foundry hexmap label {hex_id} "POI name" --scene "{scene_name}"')
        x, y = hexgrid.label_point(cal, col, row, pos or cfg["label_pos"])
        data = self._boxed_drawing(scene, "label", hex_id, text, x, y,
                                   hexstyle.LABEL_STYLE, hidden=not public)
        r = self._scene_emit(scene, "create", {"data": [data]})
        return r["result"][0] | {"_hex": hex_id, "_created": True}

    def hexmap_list(self, scene_name: str) -> list[dict]:
        scene = self._find_scene(scene_name)
        labels = self._hexmap_drawings(scene, "label")
        return sorted(({"hex": d["flags"]["world"]["hexmap"]["hex"], "text": d.get("text", ""),
                        "hidden": d.get("hidden", False), "_id": d["_id"]} for d in labels),
                      key=lambda l: l["hex"])

    def hexmap_unlabel(self, scene_name: str, hex_str: str) -> bool:
        scene = self._find_scene(scene_name)
        try:
            hex_id = hexgrid.fmt_hex(*hexgrid.parse_hex(hex_str))
        except ValueError as e:
            raise click.ClickException(str(e)) from None
        ids = [d["_id"] for d in self._hexmap_drawings(scene, "label")
               if d["flags"]["world"]["hexmap"]["hex"] == hex_id]
        if not ids:
            return False
        self._scene_emit(scene, "delete", {"ids": ids})
        return True


# ── CLI ─────────────────────────────────────────────────────────────────────────

def _make_client() -> FoundryClient:
    client = FoundryClient(_load_config())
    client.connect()
    return client


_COMMAND_TREE = """\
  actor list  [--json]
  actor show  [--name NAME]  [--json]

  compendium get UUID

  journal list    [--json]
  journal upsert  --title NAME  [--folder FOLDER]  [--public]
  journal delete  --title NAME

  journal category list    --journal NAME  [--json]
  journal category upsert  --journal NAME  --name NAME
  journal category delete  --journal NAME  --name NAME

  journal page list    --journal NAME  [--json]
  journal page upsert  --journal NAME  --title NAME
                       [--category NAME]  [--level 1-6]  [--public]
                       [--before TITLE | --after TITLE]
                       [--content HTML | --content-file PATH | stdin]
  journal page reorder --journal NAME  (titles from stdin, one per line)
  journal page delete  --journal NAME  --title NAME

  hexmap init      --scene NAME  --size COLSxROWS  [--shifted even|odd]
  hexmap calibrate --scene NAME  [--label-pos top|center|bottom]
  hexmap numbers   --scene NAME  [--remove]
  hexmap label     HEX [TEXT]  --scene NAME  [--public | --hidden]  [--pos POS]
  hexmap unlabel   HEX  --scene NAME
  hexmap list      --scene NAME  [--json]
"""


class _VerbatimEpilog(click.Group):
    def format_epilog(self, ctx, formatter):
        if self.epilog:
            formatter.write_paragraph()
            formatter.write("Commands:\n")
            formatter.write(self.epilog)


@click.group(cls=_VerbatimEpilog, epilog=_COMMAND_TREE)
def cli():
    """Foundry VTT CLI — manage world content via Socket.io."""


@cli.group()
def actor():
    """Manage actors."""


@actor.command("list")
@click.option("--json", "as_json", is_flag=True)
def actor_list(as_json: bool):
    """List all actors."""
    client = _make_client()
    try:
        actors = client.get_actors()
        if as_json:
            click.echo(json.dumps(actors, indent=2))
        else:
            if not actors:
                click.echo("No actors.")
                return
            click.echo(f"{'NAME':<40}  {'TYPE':<10}  ID")
            click.echo("-" * 72)
            for a in sorted(actors, key=lambda x: x["name"]):
                click.echo(f"{a['name']:<40}  {a.get('type', ''):<10}  {a['_id']}")
    finally:
        client.disconnect()


@actor.command("show")
@click.option("--name", default=None, help="Actor name (default: all Player actors)")
@click.option("--json", "as_json", is_flag=True)
def actor_show(name: str | None, as_json: bool):
    """Show attack-relevant inputs: abilities, weapons, and effects.

    Values are shown as stored. Ability scores are base values before
    effects, and effect formulas are not evaluated.
    """
    client = _make_client()
    try:
        rows = client.actor_show(name)
        if as_json:
            click.echo(json.dumps(rows, indent=2))
            return
        if not rows:
            click.echo("No player actors.")
            return
        for r in rows:
            click.echo(f"== {r['name']}  (level {r['level']})")
            click.echo("  abilities: " + "  ".join(
                f"{k.upper()} {v['value']} ({v['mod']:+d})" for k, v in r["abilities"].items()))
            click.echo("  weapons:")
            for w in r["weapons"]:
                kind = f"{w['type']}/{w['range']}"
                click.echo(f"    {w['name']:<28} {kind:<14} equipped={w['equipped']}  {w['bonuses'] or ''}".rstrip())
            if not r["weapons"]:
                click.echo("    (none)")
            click.echo("  effects touching roll.* / bonuses.*attack* / abilities:")
            for e in r["effects"]:
                src = "(actor)" if e["sourceType"] == "Actor" else f"{e['source']} [{e['sourceType']}]"
                click.echo(f"    {src:<44} {e['effect']:<32} {e['key']} {e['type']} {e['value']}"
                           + ("  [DISABLED]" if e["disabled"] else "")
                           + ("  [NOT TRANSFERRED]" if not e["transfer"] else ""))
            if not r["effects"]:
                click.echo("    (none)")
            click.echo()
    finally:
        client.disconnect()


@cli.group()
def compendium():
    """Read compendium documents."""


@compendium.command("get")
@click.argument("uuid")
def compendium_get(uuid: str):
    """Print one raw compendium document as JSON.

    UUID is a compendium link as it appears in actor data, e.g.
    Compendium.shadowdark.properties.Item.jq0m0lGb7QOCSJXL
    """
    client = _make_client()
    try:
        click.echo(json.dumps(client.compendium_get(uuid), indent=2))
    finally:
        client.disconnect()


@cli.group()
def journal():
    """Manage journal entries."""


# ── journal list / upsert / delete ────────────────────────────────────────────

@journal.command("list")
@click.option("--json", "as_json", is_flag=True)
def journal_list(as_json: bool):
    """List all journal entries."""
    client = _make_client()
    try:
        entries = client.get_journals()
        if as_json:
            click.echo(json.dumps(entries, indent=2))
        else:
            if not entries:
                click.echo("No journal entries.")
                return
            for e in sorted(entries, key=lambda x: x["name"]):
                click.echo(f"{e['name']:<40}  {e['_id']}")
    finally:
        client.disconnect()


@journal.command("upsert")
@click.option("--title", required=True, help="Journal entry name")
@click.option("--folder", default=None, help="Folder (created if absent)")
@click.option("--public", is_flag=True, help="Set OBSERVER ownership")
def journal_upsert_cmd(title: str, folder: str | None, public: bool):
    """Create or update a journal entry."""
    client = _make_client()
    try:
        result = client.journal_upsert(title, folder=folder, public=public)
        click.echo(f"OK  {result['name']}  ({result['_id']})")
    finally:
        client.disconnect()


@journal.command("delete")
@click.option("--title", required=True, help="Exact journal entry name")
@click.confirmation_option(prompt="Delete this journal entry?")
def journal_delete_cmd(title: str):
    """Delete a journal entry."""
    client = _make_client()
    try:
        if client.journal_delete(title):
            click.echo(f"Deleted: {title}")
        else:
            click.echo(f"Not found: {title}", err=True)
            sys.exit(1)
    finally:
        client.disconnect()


# ── journal category ──────────────────────────────────────────────────────────

@journal.group()
def category():
    """Manage journal categories."""


@category.command("list")
@click.option("--journal", "journal_name", required=True)
@click.option("--json", "as_json", is_flag=True)
def category_list(journal_name: str, as_json: bool):
    """List categories in a journal."""
    client = _make_client()
    try:
        cats = client.category_list(journal_name)
        if as_json:
            click.echo(json.dumps(cats, indent=2))
        else:
            if not cats:
                click.echo("No categories.")
                return
            for c in cats:
                click.echo(f"{c['name']:<40}  {c['_id']}")
    finally:
        client.disconnect()


@category.command("upsert")
@click.option("--journal", "journal_name", required=True)
@click.option("--name", required=True, help="Category name")
def category_upsert_cmd(journal_name: str, name: str):
    """Create a category (idempotent)."""
    client = _make_client()
    try:
        result = client.category_upsert(journal_name, name)
        click.echo(f"OK  {result['name']}  ({result['_id']})")
    finally:
        client.disconnect()


@category.command("delete")
@click.option("--journal", "journal_name", required=True)
@click.option("--name", required=True, help="Category name")
@click.confirmation_option(prompt="Delete this category?")
def category_delete_cmd(journal_name: str, name: str):
    """Delete a category."""
    client = _make_client()
    try:
        if client.category_delete(journal_name, name):
            click.echo(f"Deleted: {name}")
        else:
            click.echo(f"Not found: {name}", err=True)
            sys.exit(1)
    finally:
        client.disconnect()


# ── journal page ──────────────────────────────────────────────────────────────

@journal.group()
def page():
    """Manage journal pages."""


@page.command("list")
@click.option("--journal", "journal_name", required=True)
@click.option("--json", "as_json", is_flag=True)
def page_list(journal_name: str, as_json: bool):
    """List pages in a journal."""
    client = _make_client()
    try:
        pages = client.page_list(journal_name)
        if as_json:
            click.echo(json.dumps(pages, indent=2))
        else:
            if not pages:
                click.echo("No pages.")
                return
            click.echo(f"{'TITLE':<40}  {'CATEGORY':<20}  {'LEVEL':>5}  TYPE")
            click.echo("-" * 76)
            for p in pages:
                click.echo(
                    f"{p.get('name', ''):<40}"
                    f"  {p.get('_category_name', ''):<20}"
                    f"  {p.get('title', {}).get('level', ''):>5}"
                    f"  {p.get('type', '')}"
                )
    finally:
        client.disconnect()


@page.command("upsert")
@click.option("--journal", "journal_name", required=True)
@click.option("--title", required=True, help="Page name")
@click.option("--category", "category_name", default=None, help="Category name")
@click.option("--level", default=1, type=click.IntRange(1, 6), show_default=True,
              help="Sidebar indentation level (1=top)")
@click.option("--public", is_flag=True, help="Set OBSERVER ownership on this page")
@click.option("--content", default=None, help="HTML content (inline)")
@click.option("--before", default=None, metavar="TITLE",
              help="Insert before this page (reindexes category)")
@click.option("--after", default=None, metavar="TITLE",
              help="Insert after this page (reindexes category)")
@click.option("--content-file", type=click.Path(exists=True), default=None,
              help="Path to HTML file")
def page_upsert_cmd(journal_name: str, title: str, category_name: str | None,
                    level: int, public: bool, before: str | None, after: str | None,
                    content: str | None, content_file: str | None):
    """Create or update a journal page.

    \b
    HTML content is read from --content, --content-file, or stdin.
    --category must name an existing category (use category upsert first).
    --before/--after reindex all pages in the category around the target.
    """
    if before and after:
        raise click.UsageError("Use --before or --after, not both")
    if content_file:
        content = Path(content_file).read_text()
    elif content is None:
        # Empty stdin counts as no content: never blank a page by accident
        # (the MCP server runs this command with an empty stdin).
        content = "" if sys.stdin.isatty() else sys.stdin.read()
        if not content.strip():
            raise click.UsageError(
                "Provide --content, --content-file, or pipe HTML to stdin")

    client = _make_client()
    try:
        result = client.page_upsert(journal_name, title, category_name, level, public, content,
                                    before=before, after=after)
        click.echo(f"OK  {result['name']}  ({result['_id']})")
    finally:
        client.disconnect()


@page.command("delete")
@click.option("--journal", "journal_name", required=True)
@click.option("--title", required=True, help="Exact page name")
@click.confirmation_option(prompt="Delete this page?")
def page_delete_cmd(journal_name: str, title: str):
    """Delete a journal page."""
    client = _make_client()
    try:
        if client.page_delete(journal_name, title):
            click.echo(f"Deleted: {title}")
        else:
            click.echo(f"Not found: {title}", err=True)
            sys.exit(1)
    finally:
        client.disconnect()


@page.command("reorder")
@click.option("--journal", "journal_name", required=True)
def page_reorder_cmd(journal_name: str):
    """Set page sort order from stdin (one title per line).

    \b
    Assigns sort values 100000, 200000, ... to the listed pages in order.
    Pages not listed are left untouched. Resolves any sort conflicts.
    """
    if sys.stdin.isatty():
        raise click.UsageError("Pipe page titles (one per line) to stdin")
    titles = [line.strip() for line in sys.stdin if line.strip()]
    if not titles:
        raise click.UsageError("No titles provided")
    client = _make_client()
    try:
        n = client.page_reorder(journal_name, titles)
        click.echo(f"Reordered {n} pages.")
    finally:
        client.disconnect()


# Commands that read their main input from stdin tell the MCP server how to
# expose it: (parameter name, description).
page_reorder_cmd.stdin_param = ("titles", "Page titles in the new order, one per line.")


# ── hexmap ────────────────────────────────────────────────────────────────────

_HEXMAP_HELP = """\
  Hex numbers are CCRR: column then row, both from 01, as printed on the
  map. 0816 = column 08, row 16; "816" means the same.

  One-time setup per scene:

  1. foundry hexmap init --scene Landel --size 10x17
       Places two magenta anchor hexagons (GM-only) for the corner
       hexes 0101 and 1017. --size is the map's columns x rows.
  2. In Foundry, drag each anchor until its outline sits exactly on
       the printed hex with that number. Move only; don't resize.
       If the scene's grid is aligned to the map, the anchor snaps
       onto the hex for you.
  3. foundry hexmap calibrate --scene Landel
       Reads the anchors and stores the grid on the scene.
  4. foundry hexmap numbers --scene Landel
       Puts a number tag in the top of every hex. Check they all sit
       in their hexes; if not, drag the anchors, calibrate, and run
       numbers again (it replaces the old ones).
       Numbers are visible to players too. Remove them with --remove.

  Labels (one per hex; new labels start hidden from players):

    foundry hexmap label 0816 "Wormden Keep" --scene Landel
    foundry hexmap label 0816 --public --scene Landel     (reveal)
    foundry hexmap label 0816 --hidden --scene Landel     (hide again)
    foundry hexmap unlabel 0816 --scene Landel
    foundry hexmap list --scene Landel

  Labels are ordinary Foundry Drawings: you can also drag them and
  hide/reveal them by hand (right-click > eye). The CLI never moves a
  label or changes its visibility unless you ask it to. Changing a
  label's text resizes its box around where the label is now.

  Optional companion module "Foundry CLI Companion", in module/ of
  this repository: adds "Hex labels" and "Hex numbers" toggles to the
  Tokens toolbar, so each user can show or hide them on their own screen.
  Labels start switched off. Without it, labels are always shown.
"""


class _WorkflowGroup(click.Group):
    """A group whose epilog is a verbatim workflow description. The MCP server
    adds the same text to the description of every tool in the group."""
    def format_epilog(self, ctx, formatter):
        if self.epilog:
            formatter.write_paragraph()
            formatter.write("Workflow:\n\n")
            formatter.write(self.epilog)


_scene_opt = click.option("--scene", "scene_name", required=True,
                          help="Scene name, exactly as in Foundry's sidebar.")


@cli.group(cls=_WorkflowGroup, epilog=_HEXMAP_HELP)
def hexmap():
    """Put labels on a hex map scene (POI names, GM-only or public)."""


@hexmap.command("init")
@_scene_opt
@click.option("--size", required=True, metavar="COLSxROWS",
              help="Columns x rows of the printed map, e.g. 10x17.")
@click.option("--shifted", type=click.Choice(["even", "odd"]), default="even",
              show_default=True,
              help="Which rows (pointy-top) or columns (flat-top) are pushed half a hex.")
def hexmap_init_cmd(scene_name: str, size: str, shifted: str):
    """Place the two anchor hexagons used for calibration.

    \b
    Example:
      foundry hexmap init --scene Landel --size 10x17
    Safe to re-run: anchors you already dragged stay where they are.
    Then drag the anchors onto their printed hexes and run calibrate.
    """
    try:
        cols_rows = hexgrid.parse_size(size)
    except ValueError as e:
        raise click.BadParameter(str(e), param_hint="--size") from None
    client = _make_client()
    try:
        anchors = client.hexmap_init(scene_name, cols_rows, shifted)
        hexes = sorted(d["flags"]["world"]["hexmap"]["hex"] for d in anchors)
        click.echo(f"Anchors on '{scene_name}': {', '.join(hexes)} (GM-only, magenta).")
        click.echo("Next: in Foundry, drag each anchor so its outline sits exactly on the")
        click.echo("printed hex with that number, then run:")
        click.echo(f'  foundry hexmap calibrate --scene "{scene_name}"')
    finally:
        client.disconnect()


@hexmap.command("calibrate")
@_scene_opt
@click.option("--label-pos", type=click.Choice(list(hexgrid.LABEL_POSITIONS)),
              help="Where labels sit within a hex (default: bottom, or the previous choice).")
def hexmap_calibrate_cmd(scene_name: str, label_pos: str | None):
    """Read the anchors and store the hex grid on the scene.

    \b
    Example:
      foundry hexmap calibrate --scene Landel
    Re-run any time after moving the anchors. Existing labels and
    numbers are not moved; re-run numbers, and re-place a label with:
    hexmap label HEX --pos bottom
    """
    client = _make_client()
    try:
        r = client.hexmap_calibrate(scene_name, label_pos)
        cal, exp = r["calibration"], r["expected"]
        click.echo(f"Calibrated '{scene_name}': hex 0101 centre at "
                   f"({cal['origin'][0]:.0f}, {cal['origin'][1]:.0f})")
        click.echo(f"  column step {cal['col_step']:.1f}px (grid: {exp['col_step']:.1f})")
        click.echo(f"  row step    {cal['row_step']:.1f}px (grid: {exp['row_step']:.1f})")
        click.echo(f"  labels at   {r['label_pos']}")
        for w in r["warnings"]:
            click.echo(f"WARNING: {w}", err=True)
        click.echo(f'Check it: foundry hexmap numbers --scene "{scene_name}"')
    finally:
        client.disconnect()


@hexmap.command("numbers")
@_scene_opt
@click.option("--remove", is_flag=True, help="Remove the numbers instead of drawing them.")
def hexmap_numbers_cmd(scene_name: str, remove: bool):
    """Put a number tag in the top of every hex (visible to everyone).

    \b
    Examples:
      foundry hexmap numbers --scene Landel           draw (replaces old ones)
      foundry hexmap numbers --scene Landel --remove  remove them
    Also the check after calibrating. Labels are never touched.
    """
    client = _make_client()
    try:
        n = client.hexmap_numbers(scene_name, remove)
        if remove:
            click.echo(f"Removed hex numbers from '{scene_name}'.")
        else:
            click.echo(f"Drew {n} hex numbers on '{scene_name}' (visible to players). "
                       "Remove them with:")
            click.echo(f'  foundry hexmap numbers --scene "{scene_name}" --remove')
    finally:
        client.disconnect()


@hexmap.command("label")
@click.argument("hex_id", metavar="HEX")
@click.argument("text", required=False)
@_scene_opt
@click.option("--public/--hidden", "public", default=None,
              help="Show to players / hide from players. Omit to leave as is "
                   "(new labels start hidden).")
@click.option("--pos", type=click.Choice(list(hexgrid.LABEL_POSITIONS)),
              help="Re-place the label within its hex (default: the scene's label position).")
def hexmap_label_cmd(hex_id: str, text: str | None, scene_name: str,
                     public: bool | None, pos: str | None):
    """Create or update the label on one hex.

    \b
    Examples:
      foundry hexmap label 0816 "Wormden Keep" --scene Landel   (new, GM-only)
      foundry hexmap label 0816 --public --scene Landel         (reveal)
      foundry hexmap label 1015 "Wormden" --scene Landel        (another hex)
    Changing the text keeps the label's position and visibility.
    """
    if text is None and public is None and pos is None:
        raise click.UsageError("Give TEXT, --public/--hidden, or --pos")
    client = _make_client()
    try:
        d = client.hexmap_label(scene_name, hex_id, text, public, pos)
        state = "GM only" if d.get("hidden") else "players"
        verb = "Created" if d["_created"] else "Updated"
        click.echo(f"{verb} {d['_hex']}  {d.get('text', '')!r}  ({state})")
    finally:
        client.disconnect()


@hexmap.command("unlabel")
@click.argument("hex_id", metavar="HEX")
@_scene_opt
def hexmap_unlabel_cmd(hex_id: str, scene_name: str):
    """Remove the label from one hex.

    \b
    Example:
      foundry hexmap unlabel 0816 --scene Landel
    """
    client = _make_client()
    try:
        if not client.hexmap_unlabel(scene_name, hex_id):
            raise click.ClickException(f"No label on hex {hex_id} in '{scene_name}'")
        click.echo(f"Removed label from {hex_id}.")
    finally:
        client.disconnect()


@hexmap.command("list")
@_scene_opt
@click.option("--json", "as_json", is_flag=True)
def hexmap_list_cmd(scene_name: str, as_json: bool):
    """List the labels on a scene, with who can see them."""
    client = _make_client()
    try:
        labels = client.hexmap_list(scene_name)
        if as_json:
            click.echo(json.dumps(labels, indent=2))
            return
        if not labels:
            click.echo("No labels.")
            return
        click.echo(f"{'HEX':<6}{'VISIBLE':<10}TEXT")
        for l in labels:
            vis = "GM only" if l["hidden"] else "players"
            click.echo(f"{l['hex']:<6}{vis:<10}{l['text']}")
    finally:
        client.disconnect()


if __name__ == "__main__":
    cli()
