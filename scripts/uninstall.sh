#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)"
TARGET_DIR="${HOME}/.config/opencode"
RUNTIME_DIR="${HOME}/.local/share/super-turing-opencode-codegraph/runtime"
DRY_RUN=0
KEEP_RUNTIME=0
MANAGED_FILES=()

run() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    printf '[dry-run] %s\n' "$*"
    return 0
  fi
  "$@"
}

while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --target-dir) TARGET_DIR="$2"; shift 2 ;;
    --runtime-dir) RUNTIME_DIR="$2"; shift 2 ;;
    --keep-runtime) KEEP_RUNTIME=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help)
      printf 'Usage: uninstall.sh [--target-dir <path>] [--runtime-dir <path>] [--keep-runtime] [--dry-run]\n'
      exit 0
      ;;
    *) printf 'Unknown option: %s\n' "$1" >&2; exit 1 ;;
  esac
done

mapfile -t MANAGED_FILES < <(
  python3 - "$REPO_DIR/CODEGRAPH-MANIFEST.json" <<'PY'
import json, pathlib, sys
data = json.loads(pathlib.Path(sys.argv[1]).read_text())
for item in data.get("managedFiles", []):
    print(item)
PY
)

config="$TARGET_DIR/opencode.json"
marker="$TARGET_DIR/.opencode-codegraph-addon.json"
bin="$RUNTIME_DIR/node_modules/.bin/codegraph"
timestamp="$(date +%Y%m%d-%H%M%S)"
backup_dir="$TARGET_DIR/.codegraph-addon-backups/uninstall-$timestamp"

if [[ -f "$config" && -f "$marker" ]]; then
  run cp "$config" "$config.codegraph-uninstall-backup-$timestamp"
  if [[ "$DRY_RUN" -eq 1 ]]; then
    printf '[dry-run] remove CodeGraph MCP and owned tool rules from %s\n' "$config"
  else
    python3 "$REPO_DIR/scripts/manage_opencode_config.py" remove \
      --config "$config" --marker "$marker" --codegraph-bin "$bin"
  fi
fi

for rel in "${MANAGED_FILES[@]}"; do
  current="$TARGET_DIR/$rel"
  if [[ ! -e "$current" ]]; then
    continue
  fi
  run mkdir -p "$(dirname -- "$backup_dir/$rel")"
  run cp "$current" "$backup_dir/$rel"
  run rm -f "$current"
done

if [[ "$KEEP_RUNTIME" -eq 0 && -d "$RUNTIME_DIR" ]]; then
  run rm -rf "$RUNTIME_DIR"
fi

printf '[codegraph-addon] global integration removed\n'
printf '[codegraph-addon] project .codegraph indexes and codegraph.json files were preserved\n'
