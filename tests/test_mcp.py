"""The MCP server is generated from the CLI; check the mapping and run it for real."""

import json
import os
import sys
from pathlib import Path

import anyio
import click
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

import foundry
import foundry_mcp
from test_hexmap import _setup, scene  # noqa: F401  (scene is a fixture)

SPECS = {s.name: s for s in foundry_mcp.build_specs()}


def _leaf_paths(cmd, path=()):
    if isinstance(cmd, click.Group):
        for name, sub in cmd.commands.items():
            yield from _leaf_paths(sub, path + (name,))
    else:
        yield path


def test_every_cli_command_is_a_tool():
    assert sorted(SPECS) == sorted("_".join(p) for p in _leaf_paths(foundry.cli))


def test_parameters_map_back_to_cli():
    label = SPECS["hexmap_label"]
    assert label.argv({"hex": "816", "text": "Wormden Keep", "scene": "Landel"}) == (
        ["hexmap", "label", "816", "Wormden Keep", "--scene", "Landel"], None)
    assert label.argv({"hex": "816", "scene": "Landel", "public": True})[0][-1] == "--public"
    assert label.argv({"hex": "816", "scene": "Landel", "public": False})[0][-1] == "--hidden"


def test_forced_flags_and_stdin():
    assert SPECS["hexmap_list"].argv({"scene": "X"})[0][-1] == "--json"
    assert SPECS["journal_delete"].argv({"title": "X"})[0][-1] == "--yes"
    args, stdin = SPECS["journal_page_reorder"].argv({"journal": "J", "titles": "A\nB"})
    assert stdin == "A\nB" and "titles" not in " ".join(args)


def test_schemas_are_typed():
    props = SPECS["hexmap_label"].input_schema()["properties"]
    assert props["public"]["type"] == "boolean"
    assert props["pos"]["enum"] == ["top", "center", "bottom"]
    level = SPECS["journal_page_upsert"].input_schema()["properties"]["level"]
    assert (level["type"], level["minimum"], level["maximum"]) == ("integer", 1, 6)


def test_hexmap_tools_carry_the_workflow():
    assert "calibrate" in SPECS["hexmap_label"].description
    assert "CCRR" in SPECS["hexmap_list"].description
    assert "\b" not in SPECS["hexmap_label"].description


def _call(tool: str, args: dict) -> tuple[bool, str, list[str]]:
    """Start the real MCP server over stdio, list tools, call one."""
    async def go():
        params = StdioServerParameters(command=sys.executable,
                                       args=[str(Path(foundry_mcp.__file__))],
                                       env=dict(os.environ))
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                names = [t.name for t in (await session.list_tools()).tools]
                result = await session.call_tool(tool, args)
                return not result.isError, result.content[0].text, names
    return anyio.run(go)


def test_mcp_round_trip_hexmap(client, scene):  # noqa: F811
    _setup(client, scene)
    ok, text, names = _call("hexmap_label", {"hex": "816", "text": "Wormden Keep", "scene": scene})
    assert ok, text
    assert "hexmap_label" in names and "journal_page_upsert" in names
    ok, text, _ = _call("hexmap_label", {"hex": "816", "scene": scene, "public": True})
    assert ok, text
    ok, text, _ = _call("hexmap_list", {"scene": scene})
    assert ok
    assert json.loads(text)[0] | {"_id": None} == {
        "hex": "0816", "text": "Wormden Keep", "hidden": False, "_id": None}


def test_mcp_errors_come_back_as_tool_errors(client):
    ok, text, _ = _call("hexmap_list", {"scene": "_pytest_no_such_scene"})
    assert not ok
    assert "not found" in text


def test_page_upsert_without_content_refuses(client, journal):
    ok, text, _ = _call("journal_page_upsert", {"journal": journal, "title": "Empty"})
    assert not ok
    assert "content" in text
