#!/usr/bin/env python3
"""MCP server for Foundry VTT, generated from the foundry CLI.

Every CLI command becomes one MCP tool, so the two never drift apart: add a
command to foundry.py and it is a tool here too. `foundry hexmap label`
becomes `hexmap_label`; its arguments and options become the tool's
parameters; its help text (plus its group's workflow, if any) becomes the
tool's description. Calling a tool runs the command in a subprocess.

Generic handling:
  --json          always passed when the command has it; the result is JSON.
  --yes           (delete confirmations) always passed.
  --flag/--other  boolean switches with no default become an optional boolean.
  stdin           commands with a `stdin_param` attribute get that parameter,
                  and its value is piped to the command.

Run with:
    uv run python foundry_mcp.py

Or register in an MCP client config:
    {"command": "uv", "args": ["run", "python", "/path/to/foundry_mcp.py"]}
"""

import inspect
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import anyio
import click
import mcp.types as types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

import foundry

CLI_PATH = Path(foundry.__file__).resolve()

INSTRUCTIONS = """\
Tools for a Foundry VTT world: journals, actors, compendiums, and labels on
hex-map scenes. Each tool runs the matching `foundry` CLI command, so help
texts show CLI syntax: `--scene Landel` is the `scene` parameter, and
`foundry hexmap label 0816 "Wormden Keep"` is hexmap_label(hex="0816",
text="Wormden Keep")."""

_FORCED_FLAGS = {"as_json": "--json", "yes": "--yes"}


@dataclass
class _Param:
    name: str                 # MCP parameter name
    param: click.Parameter
    schema: dict
    required: bool


@dataclass
class ToolSpec:
    name: str
    path: list[str]           # CLI words, e.g. ["hexmap", "label"]
    description: str
    params: list[_Param] = field(default_factory=list)
    forced: list[str] = field(default_factory=list)   # flags always passed
    stdin: tuple[str, str] | None = None
    json_output: bool = False

    def input_schema(self) -> dict:
        props = {p.name: p.schema for p in self.params}
        required = [p.name for p in self.params if p.required]
        if self.stdin:
            props[self.stdin[0]] = {"type": "string", "description": self.stdin[1]}
            required.append(self.stdin[0])
        return {"type": "object", "properties": props, "required": required,
                "additionalProperties": False}

    def argv(self, arguments: dict) -> tuple[list[str], str | None]:
        """CLI arguments and stdin text for a tool call."""
        args = list(self.path)
        for p in self.params:
            value = arguments.get(p.name)
            if value is None:
                continue
            cp = p.param
            if isinstance(cp, click.Argument):
                args.append(str(value))
            elif cp.is_flag and cp.secondary_opts:          # --public/--hidden
                args.append(_long(cp.opts) if value else _long(cp.secondary_opts))
            elif cp.is_flag:
                if value:
                    args.append(_long(cp.opts))
            else:
                args += [_long(cp.opts), str(value)]
        args += self.forced
        stdin = arguments.get(self.stdin[0]) if self.stdin else None
        return args, stdin


def _long(opts: list[str]) -> str:
    return max(opts, key=len)


def _clean_help(text: str | None) -> str:
    """Click help text, dedented, without its \\b (backspace) no-rewrap markers."""
    lines = [ln for ln in inspect.cleandoc(text or "").splitlines() if ln.strip() != "\b"]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _schema(p: click.Parameter) -> dict:
    t = p.type
    if isinstance(p, click.Option) and p.is_flag:
        schema = {"type": "boolean"}
    elif isinstance(t, click.Choice):
        schema = {"type": "string", "enum": list(t.choices)}
    elif isinstance(t, click.IntRange):
        schema = {"type": "integer"}
        if t.min is not None:
            schema["minimum"] = t.min
        if t.max is not None:
            schema["maximum"] = t.max
    elif isinstance(t, click.types.IntParamType):
        schema = {"type": "integer"}
    elif isinstance(t, click.types.FloatParamType):
        schema = {"type": "number"}
    else:
        schema = {"type": "string"}
    help_text = getattr(p, "help", None)
    if isinstance(p, click.Option) and p.is_flag and p.secondary_opts:
        help_text = (f"true = {_long(p.opts)}, false = {_long(p.secondary_opts)}, "
                     f"omit to leave as is. {help_text or ''}").strip()
    if help_text:
        schema["description"] = help_text
    return schema


def _param_name(p: click.Parameter) -> str:
    if isinstance(p, click.Argument):
        return (p.metavar or p.name).lower()
    return _long(p.opts).lstrip("-").replace("-", "_")


def build_specs(group: click.Group = foundry.cli) -> list[ToolSpec]:
    """One ToolSpec per leaf command of the CLI."""
    specs = []

    def walk(cmd: click.Command, path: list[str], workflows: list[str]):
        if isinstance(cmd, click.Group):
            # The root group's epilog is the command overview; skip it.
            flow = workflows + ([cmd.epilog] if path and cmd.epilog else [])
            for name, sub in cmd.commands.items():
                walk(sub, path + [name], flow)
            return
        spec = ToolSpec(name="_".join(path), path=path, description="")
        for p in cmd.params:
            if p.name in _FORCED_FLAGS:
                spec.forced.append(_FORCED_FLAGS[p.name])
                spec.json_output |= p.name == "as_json"
                continue
            tri_state = isinstance(p, click.Option) and p.is_flag and p.secondary_opts
            spec.params.append(_Param(
                name=_param_name(p), param=p, schema=_schema(p),
                required=bool(p.required) and not tri_state))
        spec.stdin = getattr(cmd.callback, "stdin_param", None) or getattr(cmd, "stdin_param", None)
        parts = [_clean_help(cmd.help)] + [_clean_help(w) for w in workflows]
        spec.description = "\n\n".join(x for x in parts if x)
        specs.append(spec)

    walk(group, [], [])
    return specs


def run_tool(spec: ToolSpec, arguments: dict) -> tuple[bool, str]:
    """Run the CLI command for a tool call. Returns (ok, output)."""
    args, stdin = spec.argv(arguments)
    proc = subprocess.run([sys.executable, str(CLI_PATH), *args],
                          input=stdin or "", capture_output=True, text=True)
    out = proc.stdout.strip()
    if proc.returncode != 0:
        return False, "\n".join(x for x in (out, proc.stderr.strip()) if x)
    return True, out


def make_server() -> Server:
    specs = {s.name: s for s in build_specs()}
    server = Server("foundry", instructions=INSTRUCTIONS)

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [types.Tool(name=s.name, description=s.description,
                           inputSchema=s.input_schema()) for s in specs.values()]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
        spec = specs.get(name)
        if spec is None:
            raise ValueError(f"Unknown tool: {name}")
        ok, out = await anyio.to_thread.run_sync(run_tool, spec, arguments or {})
        if not ok:
            raise RuntimeError(out or f"foundry {' '.join(spec.path)} failed")
        if spec.json_output and out:
            out = json.dumps(json.loads(out), indent=2)
        return [types.TextContent(type="text", text=out or "OK")]

    return server


async def _main():
    server = make_server()
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    anyio.run(_main)
