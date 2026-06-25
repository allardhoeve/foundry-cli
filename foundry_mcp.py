#!/usr/bin/env python3
"""MCP server for Foundry VTT — exposes journal/category/page tools.

Run with:
    uv run python foundry_mcp.py

Or register in an MCP client config:
    {"command": "uv", "args": ["run", "python", "/path/to/foundry_mcp.py"]}
"""

from contextlib import contextmanager
from typing import Optional

from mcp.server.fastmcp import FastMCP

from foundry import FoundryClient, _load_config

mcp = FastMCP("foundry")


@contextmanager
def _client():
    c = FoundryClient(_load_config())
    c.connect()
    try:
        yield c
    finally:
        c.disconnect()


# ── Journal ────────────────────────────────────────────────────────────────────

@mcp.tool()
def journal_list() -> list:
    """List all journal entries in the active Foundry world."""
    with _client() as c:
        return c.get_journals()


@mcp.tool()
def journal_upsert(title: str, folder: Optional[str] = None, public: bool = False) -> dict:
    """Create or update a journal entry by title. Idempotent.

    public=True sets OBSERVER ownership so players can see the journal.
    folder is created automatically if it does not exist.
    """
    with _client() as c:
        return c.journal_upsert(title, folder=folder, public=public)


@mcp.tool()
def journal_delete(title: str) -> bool:
    """Delete a journal entry by title. Returns False if not found."""
    with _client() as c:
        return c.journal_delete(title)


# ── Category ───────────────────────────────────────────────────────────────────

@mcp.tool()
def category_list(journal: str) -> list:
    """List all categories in a journal."""
    with _client() as c:
        return c.category_list(journal)


@mcp.tool()
def category_upsert(journal: str, name: str) -> dict:
    """Create a category within a journal. Idempotent.

    Categories must exist before pages can reference them.
    Common names: NPCs, Settlements, Factions, Locations.
    """
    with _client() as c:
        return c.category_upsert(journal, name)


@mcp.tool()
def category_delete(journal: str, name: str) -> bool:
    """Delete a category from a journal by name. Returns False if not found."""
    with _client() as c:
        return c.category_delete(journal, name)


# ── Page ───────────────────────────────────────────────────────────────────────

@mcp.tool()
def page_list(journal: str) -> list:
    """List all pages in a journal.

    Each page includes _category_name, title.level, and type fields.
    """
    with _client() as c:
        return c.page_list(journal)


@mcp.tool()
def page_upsert(
    journal: str,
    title: str,
    content: str,
    category: Optional[str] = None,
    level: int = 1,
    public: bool = False,
) -> dict:
    """Create or update a journal page. Idempotent.

    content is HTML. level controls sidebar indentation (1=top, 2=indented under
    the preceding level-1 page). category must already exist — call category_upsert
    first. public=True sets OBSERVER ownership so players can see this page.
    """
    with _client() as c:
        return c.page_upsert(journal, title, category, level, public, content)


@mcp.tool()
def page_delete(journal: str, title: str) -> bool:
    """Delete a page from a journal by title. Returns False if not found."""
    with _client() as c:
        return c.page_delete(journal, title)


if __name__ == "__main__":
    mcp.run()
