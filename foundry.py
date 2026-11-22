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
        user_id = self._discover_user_id()
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
        if not sys.stdin.isatty():
            content = sys.stdin.read()
        else:
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


if __name__ == "__main__":
    cli()
