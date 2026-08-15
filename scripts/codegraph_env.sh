#!/usr/bin/env bash

set -euo pipefail

CODEGRAPH_RUNTIME_DIR="${OPENCODE_CODEGRAPH_RUNTIME_DIR:-${HOME}/.local/share/super-turing-opencode-codegraph/runtime}"
CODEGRAPH_BIN="${OPENCODE_CODEGRAPH_BIN:-${CODEGRAPH_RUNTIME_DIR}/node_modules/.bin/codegraph}"
CODEGRAPH_STATE_DIR="${OPENCODE_CODEGRAPH_STATE_DIR:-${HOME}/.local/state/super-turing-opencode-codegraph}"
CODEGRAPH_REGISTRY="${OPENCODE_CODEGRAPH_REGISTRY:-${CODEGRAPH_STATE_DIR}/projects.json}"

export CODEGRAPH_TELEMETRY=0
export CODEGRAPH_NO_UPDATE_CHECK=1
export DO_NOT_TRACK=1

codegraph_require_bin() {
  if [[ ! -x "$CODEGRAPH_BIN" ]]; then
    printf 'CodeGraph runtime not found: %s\n' "$CODEGRAPH_BIN" >&2
    printf 'Install or repair super-turing-opencode-codegraph first.\n' >&2
    exit 1
  fi
}

codegraph_run() {
  codegraph_require_bin
  "$CODEGRAPH_BIN" "$@"
}
