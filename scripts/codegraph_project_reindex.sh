#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/codegraph_env.sh"

PROJECT_ROOT="${PWD}"
CONFIRMED=0

while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --project-root)
      PROJECT_ROOT="$2"
      shift 2
      ;;
    --confirm-reindex)
      CONFIRMED=1
      shift
      ;;
    -h|--help)
      printf 'Usage: codegraph_project_reindex.sh [--project-root <path>] --confirm-reindex\n'
      exit 0
      ;;
    *)
      printf 'Unknown option: %s\n' "$1" >&2
      exit 1
      ;;
  esac
done

if [[ "$CONFIRMED" -ne 1 ]]; then
  printf 'Refusing reindex without --confirm-reindex.\n' >&2
  exit 1
fi

ROOT="$(python3 "$SCRIPT_DIR/codegraph_project.py" resolve-root --path "$PROJECT_ROOT")"
if [[ ! -d "$ROOT/.codegraph" ]]; then
  printf 'CodeGraph index not found at %s/.codegraph; run codegraph-init instead.\n' "$ROOT" >&2
  exit 1
fi

codegraph_run index "$ROOT" --force
STATUS_FILE="$(mktemp)"
trap 'rm -f "$STATUS_FILE"' EXIT
codegraph_run status "$ROOT" --json >"$STATUS_FILE"
python3 "$SCRIPT_DIR/codegraph_project.py" validate-status --status-file "$STATUS_FILE"
python3 "$SCRIPT_DIR/codegraph_project.py" record --registry "$CODEGRAPH_REGISTRY" --root "$ROOT" --status-file "$STATUS_FILE"
cat "$STATUS_FILE"
