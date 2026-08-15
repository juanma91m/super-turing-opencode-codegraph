#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/codegraph_env.sh"

PROJECT_ROOT="${PWD}"

while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --project-root)
      PROJECT_ROOT="$2"
      shift 2
      ;;
    -h|--help)
      printf 'Usage: codegraph_project_init.sh [--project-root <path>]\n'
      exit 0
      ;;
    *)
      printf 'Unknown option: %s\n' "$1" >&2
      exit 1
      ;;
  esac
done

ROOT="$(python3 "$SCRIPT_DIR/codegraph_project.py" resolve-root --path "$PROJECT_ROOT")"
python3 "$SCRIPT_DIR/codegraph_project.py" ensure-exclude --root "$ROOT" >/dev/null
codegraph_require_bin

if [[ -d "$ROOT/.codegraph" ]]; then
  printf '[codegraph-project] adopting existing index at %s/.codegraph\n' "$ROOT"
else
  printf '[codegraph-project] initializing index at %s/.codegraph\n' "$ROOT"
  codegraph_run init "$ROOT"
fi

STATUS_FILE="$(mktemp)"
trap 'rm -f "$STATUS_FILE"' EXIT
codegraph_run status "$ROOT" --json >"$STATUS_FILE"
python3 "$SCRIPT_DIR/codegraph_project.py" validate-status --status-file "$STATUS_FILE"
python3 "$SCRIPT_DIR/codegraph_project.py" record --registry "$CODEGRAPH_REGISTRY" --root "$ROOT" --status-file "$STATUS_FILE"
cat "$STATUS_FILE"
