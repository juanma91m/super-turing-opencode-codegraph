#!/usr/bin/env bash

set -euo pipefail

failed=0
for dependency in python3 git node npm; do
  if ! command -v "$dependency" >/dev/null 2>&1; then
    printf '[codegraph-addon][preflight] missing required command: %s\n' "$dependency" >&2
    failed=1
  fi
done

[[ "$failed" -eq 0 ]] || exit 2
printf '[codegraph-addon][preflight] prerequisites OK\n'
