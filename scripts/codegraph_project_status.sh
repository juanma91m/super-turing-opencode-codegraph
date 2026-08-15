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
      printf 'Usage: codegraph_project_status.sh [--project-root <path>]\n'
      exit 0
      ;;
    *)
      printf 'Unknown option: %s\n' "$1" >&2
      exit 1
      ;;
  esac
done

ROOT="$(python3 "$SCRIPT_DIR/codegraph_project.py" resolve-root --path "$PROJECT_ROOT")"
codegraph_run status "$ROOT" --json
