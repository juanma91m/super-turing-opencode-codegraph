#!/usr/bin/env python3
"""Exec the existing pinned MCP, without an installer, proxy or inherited secrets."""
import json
import os
import re
from pathlib import Path
import sys

VERSION = '1.5.0'
BOOL_KEYS = {'CODEGRAPH_NO_DAEMON', 'CODEGRAPH_NO_WATCH', 'CODEGRAPH_FORCE_WATCH'}
NUMBER_KEYS = {'CODEGRAPH_WATCH_DEBOUNCE_MS', 'CODEGRAPH_CATCHUP_GATE_TIMEOUT_MS', 'CODEGRAPH_QUERY_POOL_SIZE', 'CODEGRAPH_MAX_DIR_WATCHES'}
ENV_KEYS = BOOL_KEYS | NUMBER_KEYS | {'CODEGRAPH_DIR'}


def validate(binding):
    if set(binding) not in ({'runtime_home', 'runtime_bin'}, {'runtime_home', 'runtime_bin', 'environment'}):
        raise ValueError('Unexpected CodeGraph binding fields')
    env = binding.get('environment', {})
    if not isinstance(env, dict) or not set(env).issubset(ENV_KEYS):
        raise ValueError('Unreviewed runtime environment')
    for key, value in env.items():
        if not isinstance(value, str) or (key in BOOL_KEYS and value not in ('0', '1')) or (key in NUMBER_KEYS and (not value.isascii() or not value.isdigit() or len(value) > 10)):
            raise ValueError('Invalid lifecycle tuning value (values suppressed)')
        if key == 'CODEGRAPH_DIR' and (not re.fullmatch(r'[A-Za-z0-9_.-]+', value) or value == '.' or '..' in value):
            raise ValueError('Unreviewed index directory (values suppressed)')
    home = Path(binding['runtime_home'])
    if not home.is_absolute() or not isinstance(binding['runtime_bin'], str):
        raise ValueError('Absolute runtime identity required')
    runtime = home / '.local/share/super-turing-opencode-codegraph/runtime'
    binary = runtime / 'node_modules/.bin/codegraph'
    if binding['runtime_bin'] != str(binary):
        raise ValueError('Unreviewed CodeGraph runtime; reconcile explicitly')
    if not binary.is_file() or not os.access(binary, os.X_OK) or not binary.resolve().is_relative_to(runtime.resolve()):
        raise ValueError('Existing managed runtime required; no automatic install')
    package = json.loads((runtime / 'node_modules/@colbymchenry/codegraph/package.json').read_text())
    if package.get('version') != VERSION:
        raise ValueError('Runtime pin differs; no upgrade or index repair attempted')
    return binding


def runtime_env(binding, parent):
    validate(binding)
    home = Path(binding['runtime_home'])
    env = {key: parent[key] for key in ('LANG', 'TERM', 'TMPDIR', 'TMP', 'TEMP') if key in parent}
    env.update(PATH='/usr/local/bin:/usr/bin:/bin', HOME=str(home),
               XDG_CONFIG_HOME=str(home / '.config'), XDG_DATA_HOME=str(home / '.local/share'),
               XDG_STATE_HOME=str(home / '.local/state'), XDG_CACHE_HOME=str(home / '.cache'),
               CODEGRAPH_MCP_TOOLS='explore', CODEGRAPH_TELEMETRY='0',
               CODEGRAPH_NO_UPDATE_CHECK='1', DO_NOT_TRACK='1', CODEGRAPH_NO_DOWNLOAD='1')
    env.update(binding.get('environment', {}))
    return env


if __name__ == '__main__':
    try:
        if sys.argv[1:] != ['mcp']:
            raise ValueError('Only the existing MCP query server is available')
        binding = validate(json.loads((Path(__file__).parent / 'codegraph-runtime.json').read_text()))
        binary = binding['runtime_bin']
        os.execve(binary, [binary, 'serve', '--mcp'], runtime_env(binding, os.environ))
    except (ValueError, KeyError, TypeError, OSError):
        print('CodeGraph runtime unavailable; values suppressed; no install/index/repair attempted', file=sys.stderr)
        raise SystemExit(2)
