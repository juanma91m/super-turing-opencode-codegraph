#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def run_git(path: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(path), *args],
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "unknown git error"
        raise SystemExit(f"Not a usable Git repository: {path}: {message}")
    return result.stdout.strip()


def resolve_root(raw_path: str) -> Path:
    candidate = Path(raw_path).expanduser().resolve(strict=True)
    if not candidate.is_dir():
        raise SystemExit(f"Project path is not a directory: {candidate}")

    root = Path(run_git(candidate, "rev-parse", "--show-toplevel")).resolve(strict=True)
    home = Path.home().resolve()
    if root == Path(root.anchor) or root == home:
        raise SystemExit(f"Unsafe CodeGraph root rejected: {root}")

    temp_roots = [Path("/tmp"), Path("/var/tmp")]
    allow_temp = os.environ.get("OPENCODE_CODEGRAPH_ALLOW_TEMP") == "1"
    if not allow_temp and any(root == temp or temp in root.parents for temp in temp_roots):
        raise SystemExit(f"Temporary CodeGraph root rejected: {root}")

    index_path = root / ".codegraph"
    if index_path.is_symlink():
        raise SystemExit(f"Symlinked .codegraph directory rejected: {index_path}")
    return root


def git_exclude_path(root: Path) -> Path:
    raw = run_git(root, "rev-parse", "--git-path", "info/exclude")
    result = Path(raw)
    if not result.is_absolute():
        result = root / result
    return result.resolve()


def ensure_exclude(root: Path) -> Path:
    path = git_exclude_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text().splitlines() if path.exists() else []
    if ".codegraph/" not in [line.strip() for line in existing]:
        content = path.read_text() if path.exists() else ""
        if content and not content.endswith("\n"):
            content += "\n"
        content += ".codegraph/\n"
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(content)
        tmp.replace(path)
    return path


def load_status(path: Path) -> dict:
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Invalid CodeGraph status JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit("Invalid CodeGraph status JSON: expected object")
    return data


def validate_status(data: dict, require_initialized: bool = True) -> None:
    if require_initialized and data.get("initialized") is not True:
        raise SystemExit("CodeGraph index is not initialized")
    index = data.get("index") or {}
    if index.get("reindexRecommended") is True:
        built = index.get("builtWithExtractionVersion", "unknown")
        current = index.get("currentExtractionVersion", "unknown")
        raise SystemExit(
            "CodeGraph recommends an explicit reindex "
            f"(extraction version {built} -> {current}); automatic adoption stopped"
        )
    if data.get("worktreeMismatch"):
        raise SystemExit(f"CodeGraph worktree mismatch: {data['worktreeMismatch']}")


def record_project(registry_path: Path, root: Path, status: dict) -> None:
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    current: dict = {"schemaVersion": 1, "projects": {}}
    if registry_path.exists():
        try:
            parsed = json.loads(registry_path.read_text())
            if isinstance(parsed, dict) and isinstance(parsed.get("projects"), dict):
                current = parsed
        except json.JSONDecodeError:
            raise SystemExit(f"Refusing to overwrite invalid registry: {registry_path}")

    current["schemaVersion"] = 1
    current["projects"][str(root)] = {
        "root": str(root),
        "indexPath": status.get("indexPath", str(root / ".codegraph")),
        "codegraphVersion": status.get("version"),
        "builtWithVersion": (status.get("index") or {}).get("builtWithVersion"),
        "lastIndexed": status.get("lastIndexed"),
        "lastSeenAt": datetime.now(timezone.utc).isoformat(),
    }
    tmp = registry_path.with_name(registry_path.name + ".tmp")
    tmp.write_text(json.dumps(current, indent=2) + "\n")
    tmp.replace(registry_path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Safe CodeGraph project state helper")
    sub = parser.add_subparsers(dest="command", required=True)

    resolve = sub.add_parser("resolve-root")
    resolve.add_argument("--path", required=True)

    exclude = sub.add_parser("ensure-exclude")
    exclude.add_argument("--root", required=True)

    validate = sub.add_parser("validate-status")
    validate.add_argument("--status-file", required=True)
    validate.add_argument("--allow-uninitialized", action="store_true")

    record = sub.add_parser("record")
    record.add_argument("--registry", required=True)
    record.add_argument("--root", required=True)
    record.add_argument("--status-file", required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "resolve-root":
        print(resolve_root(args.path))
        return 0
    if args.command == "ensure-exclude":
        root = resolve_root(args.root)
        print(ensure_exclude(root))
        return 0
    if args.command == "validate-status":
        data = load_status(Path(args.status_file))
        validate_status(data, require_initialized=not args.allow_uninitialized)
        return 0
    if args.command == "record":
        root = resolve_root(args.root)
        data = load_status(Path(args.status_file))
        validate_status(data)
        record_project(Path(args.registry).expanduser(), root, data)
        return 0
    raise SystemExit(f"Unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
