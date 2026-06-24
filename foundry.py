#!/usr/bin/env python3
"""
foundry -- CLI for Foundry VTT

Manages journal entries in a running Foundry world via Socket.io.

Credentials are loaded from tools/foundry/.env (or env vars):
  FOUNDRY_URL, FOUNDRY_BASIC_USER, FOUNDRY_BASIC_PASS,
  FOUNDRY_WORLD, FOUNDRY_GM_USER, FOUNDRY_GM_PASSWORD

Usage:
  uv run python foundry.py journal list [--json]
  uv run python foundry.py journal upsert --title NAME --folder FOLDER [--public] [--content HTML | --content-file PATH]
  uv run python foundry.py journal delete --title NAME
"""

import base64
import json
import os
import sys
import threading
from pathlib import Path

import click
import requests
import socketio
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")


# ── Config ────────────────────────────────────────────────────────────────────

def _load_config() -> dict:
    cfg = {
        "url":          os.getenv("FOUNDRY_URL", ""),
        "basic_user":   os.getenv("FOUNDRY_BASIC_USER", ""),
        "basic_pass":   os.getenv("FOUNDRY_BASIC_PASS", ""),
        "world":        os.getenv("FOUNDRY_WORLD", ""),
        "gm_user":      os.getenv("FOUNDRY_GM_USER", ""),
        "gm_password":  os.getenv("FOUNDRY_GM_PASSWORD", ""),
    }
    required = ["url", "world", "gm_user"]
    missing = [k for k in required if not cfg[k]]
    if missing:
        raise click.ClickException(f"Missing config: {', '.join(missing)}. Check tools/foundry/.env")
    return cfg


# ── Foundry client ────────────────────────────────────────────────────────────

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
        """Connect unauthenticated, call getJoinData to resolve user name → internal ID."""
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
        raise click.ClickException(
            f"User '{self._gm_user}' not found. Available: {names}")

    def connect(self):
        self._check_world()
        self._http.get(f"{self._url}/join")  # create session cookie
        user_id = self._discover_user_id()
        r = self._http.post(f"{self._url}/join",
                            json={"action": "join", "userid": user_id,
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

    # ── Document helpers ──────────────────────────────────────────────────────

    def _get(self, doc_type: str, query: dict | None = None) -> list:
        r = self._emit({
            "type": doc_type,
            "action": "get",
            "operation": {"query": query or {}},
        })
        return r.get("result", [])

    def get_journals(self) -> list:
        return self._get("JournalEntry")

    def _find_or_create_folder(self, name: str) -> str:
        folders = self._get("Folder", {"type": "JournalEntry"})
        for f in folders:
            if f["name"].lower() == name.lower():
                return f["_id"]
        r = self._emit({
            "type": "Folder",
            "action": "create",
            "operation": {"data": [{"name": name, "type": "JournalEntry"}]},
        })
        return r["result"][0]["_id"]

    # ── Public operations ─────────────────────────────────────────────────────

    def journal_upsert(self, title: str, content: str, folder: str | None, public: bool) -> dict:
        folder_id = self._find_or_create_folder(folder) if folder else None
        ownership = {"default": 2 if public else 0}  # 2=OBSERVER, 0=NONE

        existing = [j for j in self.get_journals() if j["name"] == title]

        if existing:
            j = existing[0]
            pages = j.get("pages", [])
            text_pages = [p for p in pages if p.get("type") == "text"]
            parent_uuid = f"JournalEntry.{j['_id']}"

            if text_pages:
                self._emit({
                    "type": "JournalEntryPage",
                    "action": "update",
                    "operation": {
                        "updates": [{"_id": text_pages[0]["_id"], "text.content": content}],
                        "parentUuid": parent_uuid,
                    },
                })
            else:
                self._emit({
                    "type": "JournalEntryPage",
                    "action": "create",
                    "operation": {
                        "data": [{"name": "Main", "type": "text",
                                  "text": {"content": content, "format": 1}}],
                        "parentUuid": parent_uuid,
                    },
                })

            update = {"_id": j["_id"], "ownership": ownership}
            if folder_id is not None:
                update["folder"] = folder_id
            r = self._emit({
                "type": "JournalEntry",
                "action": "update",
                "operation": {"updates": [update]},
            })
            return r["result"][0]

        else:
            r = self._emit({
                "type": "JournalEntry",
                "action": "create",
                "operation": {
                    "data": [{
                        "name": title,
                        "folder": folder_id,
                        "ownership": ownership,
                        "pages": [{
                            "name": "Main",
                            "type": "text",
                            "text": {"content": content, "format": 1},
                        }],
                    }]
                },
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


# ── CLI ───────────────────────────────────────────────────────────────────────

@click.group()
def cli():
    """Foundry VTT CLI — manage world content via Socket.io.

    Reads credentials from tools/foundry/.env. Override with env vars:
    FOUNDRY_URL, FOUNDRY_BASIC_USER, FOUNDRY_BASIC_PASS,
    FOUNDRY_WORLD, FOUNDRY_GM_USER, FOUNDRY_GM_PASSWORD.
    """


@cli.group()
def journal():
    """Create, update, list, and delete journal entries."""


@journal.command("list")
@click.option("--json", "as_json", is_flag=True, help="Output raw JSON")
def journal_list(as_json: bool):
    """List all journal entries in the active world."""
    cfg = _load_config()
    client = FoundryClient(cfg)
    try:
        client.connect()
        entries = client.get_journals()
        if as_json:
            click.echo(json.dumps(entries, indent=2))
        else:
            if not entries:
                click.echo("No journal entries.")
                return
            for e in sorted(entries, key=lambda x: x["name"]):
                folder = e.get("folder") or "(none)"
                click.echo(f"{e['name']:<40}  {e['_id']}  folder={folder}")
    finally:
        client.disconnect()


@journal.command("upsert")
@click.option("--title", required=True, help="Journal entry name")
@click.option("--content", default=None, help="HTML content (inline)")
@click.option("--content-file", type=click.Path(exists=True), default=None,
              help="Path to HTML file")
@click.option("--folder", default=None, help="Folder name (created if it does not exist)")
@click.option("--public", is_flag=True, help="Make visible to all players (OBSERVER)")
def journal_upsert(title: str, content: str | None, content_file: str | None,
                   folder: str | None, public: bool):
    """Create or update a journal entry.

    HTML content is read from --content, --content-file, or stdin.

    \b
    Examples:
      foundry journal upsert --title "Grimlash" --folder "NPCs" --public \\
          --content "<p>Orc warlord of the eastern marches.</p>"
    """
    if content_file:
        content = Path(content_file).read_text()
    elif content is None:
        if not sys.stdin.isatty():
            content = sys.stdin.read()
        else:
            raise click.UsageError(
                "Provide --content, --content-file, or pipe HTML to stdin")

    cfg = _load_config()
    client = FoundryClient(cfg)
    try:
        client.connect()
        result = client.journal_upsert(title, content, folder=folder, public=public)
        click.echo(f"OK  {result['name']}  ({result['_id']})")
    finally:
        client.disconnect()


@journal.command("delete")
@click.option("--title", required=True, help="Exact name of the journal entry to delete")
@click.confirmation_option(prompt="Delete this journal entry?")
def journal_delete(title: str):
    """Delete a journal entry by exact name."""
    cfg = _load_config()
    client = FoundryClient(cfg)
    try:
        client.connect()
        if client.journal_delete(title):
            click.echo(f"Deleted: {title}")
        else:
            click.echo(f"Not found: {title}", err=True)
            sys.exit(1)
    finally:
        client.disconnect()


if __name__ == "__main__":
    cli()
