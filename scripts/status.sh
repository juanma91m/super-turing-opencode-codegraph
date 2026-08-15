#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)"
TARGET_DIR="${HOME}/.config/opencode"
RUNTIME_DIR="${HOME}/.local/share/super-turing-opencode-codegraph/runtime"
PROJECT_ROOT=""
MANAGED_FILES=()

while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --target-dir) TARGET_DIR="$2"; shift 2 ;;
    --runtime-dir) RUNTIME_DIR="$2"; shift 2 ;;
    --project-root) PROJECT_ROOT="$2"; shift 2 ;;
    -h|--help)
      printf 'Usage: status.sh [--target-dir <path>] [--runtime-dir <path>] [--project-root <path>]\n'
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

expected_version="$(python3 - "$REPO_DIR/CODEGRAPH-MANIFEST.json" <<'PY'
import json, pathlib, sys
print(json.loads(pathlib.Path(sys.argv[1]).read_text())["upstream"]["version"])
PY
)"
bin="$RUNTIME_DIR/node_modules/.bin/codegraph"
missing=0
mismatched=0
for rel in "${MANAGED_FILES[@]}"; do
  if [[ ! -e "$TARGET_DIR/$rel" ]]; then
    missing=$((missing + 1))
  elif ! cmp -s "$REPO_DIR/$rel" "$TARGET_DIR/$rel"; then
    mismatched=$((mismatched + 1))
  fi
done

printf 'target_dir=%s\n' "$TARGET_DIR"
printf 'runtime_dir=%s\n' "$RUNTIME_DIR"
printf 'runtime_present=%s\n' "$([[ -x "$bin" ]] && printf yes || printf no)"
if [[ -x "$bin" ]]; then
  actual_version="$(env CODEGRAPH_TELEMETRY=0 CODEGRAPH_NO_UPDATE_CHECK=1 DO_NOT_TRACK=1 "$bin" --version)"
  printf 'runtime_version=%s\n' "$actual_version"
  printf 'runtime_version_expected=%s\n' "$expected_version"
  printf 'runtime_version_matches=%s\n' "$([[ "$actual_version" == "$expected_version" ]] && printf yes || printf no)"
else
  printf 'runtime_version=missing\n'
  printf 'runtime_version_expected=%s\n' "$expected_version"
  printf 'runtime_version_matches=no\n'
fi
printf 'managed_files_total=%s\n' "${#MANAGED_FILES[@]}"
printf 'managed_files_missing=%s\n' "$missing"
printf 'managed_files_mismatched=%s\n' "$mismatched"
printf 'install_marker_present=%s\n' "$([[ -f "$TARGET_DIR/.opencode-codegraph-addon.json" ]] && printf yes || printf no)"

python3 - "$TARGET_DIR/opencode.json" "$bin" <<'PY'
import json, pathlib, sys
path = pathlib.Path(sys.argv[1])
bin_path = sys.argv[2]
expected = {
    "type": "local",
    "command": [bin_path, "serve", "--mcp"],
    "enabled": True,
    "environment": {
        "CODEGRAPH_MCP_TOOLS": "explore",
        "CODEGRAPH_TELEMETRY": "0",
        "CODEGRAPH_NO_UPDATE_CHECK": "1",
        "DO_NOT_TRACK": "1",
    },
}
try:
    data = json.loads(path.read_text())
except Exception:
    data = {}
current = data.get("mcp", {}).get("codegraph")
print(f"mcp_configured={'yes' if current == expected else 'no'}")
print(f"mcp_enabled={'yes' if isinstance(current, dict) and current.get('enabled') is True else 'no'}")
env = current.get("environment", {}) if isinstance(current, dict) else {}
print(f"mcp_tools={env.get('CODEGRAPH_MCP_TOOLS', 'missing')}")
disabled = env.get("CODEGRAPH_TELEMETRY") == "0" and env.get("DO_NOT_TRACK") == "1"
print(f"telemetry_disabled={'yes' if disabled else 'no'}")
PY

if [[ -n "$PROJECT_ROOT" && -x "$bin" ]]; then
  printf '\n## Project index\n'
  OPENCODE_CODEGRAPH_BIN="$bin" OPENCODE_CODEGRAPH_RUNTIME_DIR="$RUNTIME_DIR" \
    bash "$REPO_DIR/scripts/codegraph_project_status.sh" --project-root "$PROJECT_ROOT"
fi
