#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)"
TARGET_DIR="${HOME}/.config/opencode"
RUNTIME_DIR="${HOME}/.local/share/super-turing-opencode-codegraph/runtime"
DRY_RUN=0
VALIDATE=1
ASSETS_ONLY=0
MANAGED_FILES=()

usage() {
  cat <<'EOF'
Usage: install.sh [options]

Options:
  --target-dir <path>    Target OpenCode config dir (default: ~/.config/opencode)
  --runtime-dir <path>   Managed CodeGraph runtime prefix
  --assets-only          Copy assets and wire an existing managed runtime
  --dry-run              Show actions without writing files
  --no-validate          Skip opencode debug config
  -h, --help             Show this help
EOF
}

log() { printf '[codegraph-addon] %s\n' "$*"; }
warn() { printf '[codegraph-addon][warn] %s\n' "$*" >&2; }

run() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    printf '[dry-run] %s\n' "$*"
    return 0
  fi
  "$@"
}

manifest_value() {
  python3 - "$REPO_DIR/CODEGRAPH-MANIFEST.json" "$1" <<'PY'
import json, pathlib, sys
data = json.loads(pathlib.Path(sys.argv[1]).read_text())
value = data
for part in sys.argv[2].split('.'):
    value = value[part]
print(value)
PY
}

load_managed_files() {
  mapfile -t MANAGED_FILES < <(
    python3 - "$REPO_DIR/CODEGRAPH-MANIFEST.json" <<'PY'
import json, pathlib, sys
data = json.loads(pathlib.Path(sys.argv[1]).read_text())
for item in data.get("managedFiles", []):
    print(item)
PY
  )
}

copy_assets() {
  local timestamp backup_dir rel src dst
  timestamp="$(date +%Y%m%d-%H%M%S)"
  backup_dir="$TARGET_DIR/.codegraph-addon-backups/$timestamp"
  for rel in "${MANAGED_FILES[@]}"; do
    src="$REPO_DIR/$rel"
    dst="$TARGET_DIR/$rel"
    if [[ ! -f "$src" ]]; then
      printf 'Managed source missing: %s\n' "$src" >&2
      exit 1
    fi
    if [[ -e "$dst" ]] && ! cmp -s "$src" "$dst"; then
      run mkdir -p "$(dirname -- "$backup_dir/$rel")"
      run cp "$dst" "$backup_dir/$rel"
    fi
    run mkdir -p "$(dirname -- "$dst")"
    run cp "$src" "$dst"
  done
}

install_runtime() {
  local package version bin
  package="$(manifest_value upstream.package)"
  version="$(manifest_value upstream.version)"
  bin="$RUNTIME_DIR/node_modules/.bin/codegraph"

  if [[ "$ASSETS_ONLY" -eq 0 ]]; then
    if ! command -v npm >/dev/null 2>&1; then
      printf 'npm is required to install CodeGraph %s\n' "$version" >&2
      exit 1
    fi
    run mkdir -p "$RUNTIME_DIR"
    run npm install --prefix "$RUNTIME_DIR" --ignore-scripts=false --no-audit --no-fund --save-exact "$package@$version"
  fi

  if [[ "$DRY_RUN" -eq 0 ]]; then
    if [[ ! -x "$bin" ]]; then
      printf 'Managed CodeGraph binary not found: %s\n' "$bin" >&2
      exit 1
    fi
    actual="$(env CODEGRAPH_TELEMETRY=0 CODEGRAPH_NO_UPDATE_CHECK=1 DO_NOT_TRACK=1 "$bin" --version)"
    if [[ "$actual" != "$version" ]]; then
      printf 'CodeGraph version mismatch: expected %s, got %s\n' "$version" "$actual" >&2
      exit 1
    fi
  fi
}

configure_opencode() {
  local config marker bin addon_version codegraph_version
  config="$TARGET_DIR/opencode.json"
  marker="$TARGET_DIR/.opencode-codegraph-addon.json"
  bin="$RUNTIME_DIR/node_modules/.bin/codegraph"
  addon_version="$(manifest_value version)"
  codegraph_version="$(manifest_value upstream.version)"

  if [[ "$DRY_RUN" -eq 1 ]]; then
    log "Dry-run: would merge CodeGraph MCP into $config"
    return 0
  fi
  python3 "$REPO_DIR/scripts/manage_opencode_config.py" apply \
    --config "$config" \
    --marker "$marker" \
    --codegraph-bin "$bin" \
    --addon-version "$addon_version" \
    --codegraph-version "$codegraph_version"
}

validate_config() {
  if [[ "$VALIDATE" -ne 1 || "$DRY_RUN" -eq 1 ]]; then
    return 0
  fi
  if [[ "$TARGET_DIR" != "$HOME/.config/opencode" ]]; then
    warn "Target is not the active global config; skipping opencode debug config"
    return 0
  fi
  if command -v opencode >/dev/null 2>&1; then
    opencode debug config >/dev/null
  else
    warn "opencode not found; configuration was not runtime-validated"
  fi
}

while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --target-dir) TARGET_DIR="$2"; shift 2 ;;
    --runtime-dir) RUNTIME_DIR="$2"; shift 2 ;;
    --assets-only) ASSETS_ONLY=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    --no-validate) VALIDATE=0; shift ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'Unknown option: %s\n' "$1" >&2; usage >&2; exit 1 ;;
  esac
done

for dependency in python3 git; do
  command -v "$dependency" >/dev/null 2>&1 || { printf '%s is required\n' "$dependency" >&2; exit 1; }
done

load_managed_files
log "Repo dir: $REPO_DIR"
log "Target dir: $TARGET_DIR"
log "Runtime dir: $RUNTIME_DIR"
run mkdir -p "$TARGET_DIR"
install_runtime
copy_assets
configure_opencode
validate_config
log "CodeGraph addon installation finished; restart OpenCode to load the MCP"
