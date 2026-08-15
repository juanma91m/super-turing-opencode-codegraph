#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


AGENTS = ("code-inspector", "planner", "reviewer", "code-reviewer", "master-dev")
TOOL_PATTERN = "codegraph_*"


def expected_mcp(codegraph_bin: str) -> dict:
    return {
        "type": "local",
        "command": [codegraph_bin, "serve", "--mcp"],
        "enabled": True,
        "environment": {
            "CODEGRAPH_MCP_TOOLS": "explore",
            "CODEGRAPH_TELEMETRY": "0",
            "CODEGRAPH_NO_UPDATE_CHECK": "1",
            "DO_NOT_TRACK": "1",
        },
    }


def load_json(path: Path, default: dict | None = None) -> dict:
    if not path.exists():
        if default is None:
            raise SystemExit(f"JSON file not found: {path}")
        return default
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit(f"Expected JSON object in {path}")
    return data


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n")
    tmp.replace(path)


def apply(config: dict, marker: dict, codegraph_bin: str) -> tuple[dict, dict]:
    ownership = marker.setdefault("configOwnership", {})
    mcp = config.setdefault("mcp", {})
    expected = expected_mcp(codegraph_bin)
    existing_mcp = mcp.get("codegraph")
    if existing_mcp is not None and existing_mcp != expected:
        raise SystemExit("Refusing to overwrite an incompatible existing MCP entry: mcp.codegraph")
    if existing_mcp is None:
        mcp["codegraph"] = expected
        ownership["mcpCreated"] = True
    else:
        ownership.setdefault("mcpCreated", False)

    tools = config.setdefault("tools", {})
    existing_global = tools.get(TOOL_PATTERN)
    if existing_global is not None and existing_global is not False:
        raise SystemExit(f"Refusing to overwrite incompatible tools.{TOOL_PATTERN}")
    if TOOL_PATTERN not in tools:
        tools[TOOL_PATTERN] = False
        ownership["globalToolCreated"] = True
    else:
        ownership.setdefault("globalToolCreated", False)

    agent_root = config.setdefault("agent", {})
    created_agents = set(ownership.get("agentToolsCreated", []))
    for name in AGENTS:
        agent = agent_root.setdefault(name, {})
        agent_tools = agent.setdefault("tools", {})
        existing = agent_tools.get(TOOL_PATTERN)
        if existing is not None and existing is not True:
            raise SystemExit(f"Refusing to overwrite incompatible agent.{name}.tools.{TOOL_PATTERN}")
        if TOOL_PATTERN not in agent_tools:
            agent_tools[TOOL_PATTERN] = True
            created_agents.add(name)
    ownership["agentToolsCreated"] = sorted(created_agents)
    return config, marker


def remove(config: dict, marker: dict, codegraph_bin: str) -> dict:
    ownership = marker.get("configOwnership", {})
    expected = expected_mcp(codegraph_bin)
    mcp = config.get("mcp")
    if ownership.get("mcpCreated") and isinstance(mcp, dict):
        if mcp.get("codegraph") == expected:
            mcp.pop("codegraph", None)
        elif "codegraph" in mcp:
            print("Preserving modified mcp.codegraph during uninstall", file=sys.stderr)
        if not mcp:
            config.pop("mcp", None)

    tools = config.get("tools")
    if ownership.get("globalToolCreated") and isinstance(tools, dict):
        if tools.get(TOOL_PATTERN) is False:
            tools.pop(TOOL_PATTERN, None)
        elif TOOL_PATTERN in tools:
            print(f"Preserving modified tools.{TOOL_PATTERN} during uninstall", file=sys.stderr)
        if not tools:
            config.pop("tools", None)

    agent_root = config.get("agent")
    if isinstance(agent_root, dict):
        for name in ownership.get("agentToolsCreated", []):
            agent = agent_root.get(name)
            if not isinstance(agent, dict):
                continue
            agent_tools = agent.get("tools")
            if isinstance(agent_tools, dict):
                if agent_tools.get(TOOL_PATTERN) is True:
                    agent_tools.pop(TOOL_PATTERN, None)
                elif TOOL_PATTERN in agent_tools:
                    print(f"Preserving modified agent.{name}.tools.{TOOL_PATTERN}", file=sys.stderr)
                if not agent_tools:
                    agent.pop("tools", None)
            if not agent:
                agent_root.pop(name, None)
        if not agent_root:
            config.pop("agent", None)
    return config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage CodeGraph MCP wiring in OpenCode")
    sub = parser.add_subparsers(dest="command", required=True)

    apply_cmd = sub.add_parser("apply")
    apply_cmd.add_argument("--config", required=True)
    apply_cmd.add_argument("--marker", required=True)
    apply_cmd.add_argument("--codegraph-bin", required=True)
    apply_cmd.add_argument("--addon-version", required=True)
    apply_cmd.add_argument("--codegraph-version", required=True)

    remove_cmd = sub.add_parser("remove")
    remove_cmd.add_argument("--config", required=True)
    remove_cmd.add_argument("--marker", required=True)
    remove_cmd.add_argument("--codegraph-bin", required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    config_path = Path(args.config).expanduser()
    marker_path = Path(args.marker).expanduser()
    config = load_json(config_path, {"$schema": "https://opencode.ai/config.json"})
    marker = load_json(marker_path, {})

    if args.command == "apply":
        marker.update(
            {
                "schemaVersion": 1,
                "addonId": "super-turing-opencode-codegraph",
                "version": args.addon_version,
                "codegraphVersion": args.codegraph_version,
                "runtimeBin": args.codegraph_bin,
                "installedAt": marker.get("installedAt") or datetime.now(timezone.utc).isoformat(),
                "updatedAt": datetime.now(timezone.utc).isoformat(),
            }
        )
        config, marker = apply(config, marker, args.codegraph_bin)
        write_json(config_path, config)
        write_json(marker_path, marker)
        return 0

    if args.command == "remove":
        config = remove(config, marker, args.codegraph_bin)
        write_json(config_path, config)
        marker_path.unlink(missing_ok=True)
        return 0

    raise SystemExit(f"Unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
