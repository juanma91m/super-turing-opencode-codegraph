#!/usr/bin/env python3
"""Exec the existing pinned MCP, without an installer, proxy or inherited secrets."""
import json
from contextlib import closing
import os
import re
from pathlib import Path
import sqlite3
import stat
import sys

VERSION = '1.6.4'
SCHEMA_VERSION = 16
EXTRACTION_VERSION = '29'
PREFIX = '.local/share/super-turing-opencode-codegraph'
RUNTIME_NAMES = (f'runtime-v2-{VERSION}', f'runtime-candidate-{VERSION}')
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
    binary = Path(binding['runtime_bin'])
    runtime = binary.parents[2] if len(binary.parents) >= 3 else None
    if runtime not in (home / PREFIX / name for name in RUNTIME_NAMES) or binding['runtime_bin'] != str(runtime / 'node_modules/.bin/codegraph'):
        raise ValueError('Unreviewed CodeGraph runtime; reconcile explicitly')
    if runtime.resolve() != runtime or not binary.is_file() or not os.access(binary, os.X_OK) or not binary.resolve().is_relative_to(runtime):
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
               CODEGRAPH_NO_UPDATE_CHECK='1', DO_NOT_TRACK='1', CODEGRAPH_NO_DOWNLOAD='1',
               CODEGRAPH_DIR='.codegraph')
    env.update(binding.get('environment', {}))
    return env


def check_index(index, *, allow_absent=False, allow_stale_extraction=False):
    """Only checkpointed metadata; never start the engine to probe compatibility."""
    if not os.path.lexists(index):
        if allow_absent:
            return False
        raise ValueError('Existing index required; no automatic init')
    try:
        if index.resolve(strict=True) != index or not index.is_dir():
            raise ValueError()
        db = index / 'codegraph.db'
        for f in (db, index / 'codegraph.db-wal', index / 'codegraph.db-shm'):
            if f != db and not os.path.lexists(f):
                continue
            info = f.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ValueError()
        # Ignore WAL for the conservative probe. Do not use this connection
        # for queries or infer that the index is fresh from its metadata.
        with closing(sqlite3.connect(db.as_uri() + '?mode=ro&immutable=1', uri=True, timeout=2)) as con:
            con.execute('pragma query_only=on')
            con.execute('pragma trusted_schema=off')
            if con.execute('select max(version) from schema_versions').fetchone() != (SCHEMA_VERSION,):
                raise ValueError()
            state = dict(con.execute("select key,value from project_metadata where key in ('indexed_with_extraction_version','index_state')"))
            if state.get('index_state') != 'complete':
                raise ValueError()
    except (OSError, ValueError, sqlite3.Error, RuntimeError):
        raise ValueError('Existing index incompatible, incomplete, or not checkpointed; no automatic migration') from None
    if state.get('indexed_with_extraction_version') != EXTRACTION_VERSION and not allow_stale_extraction:
        raise ValueError('Stale extraction; explicit reindex or separate index required')
    return True


def require_neutral_cwd(index_name):
    # An implicit upstream startup root would open the index before the
    # OpenCode tool hook can verify projectPath.
    cwd = Path.cwd()
    names = {index_name, '.codegraph', '.codegraph-wsl'}
    if any(os.path.lexists(parent / name) for parent in (cwd, *cwd.parents) for name in names):
        raise ValueError('CodeGraph MCP requires a startup cwd without an index ancestor')


if __name__ == '__main__':
    try:
        if sys.argv[1:] != ['mcp']:
            raise ValueError('Only the existing MCP query server is available')
        binding = validate(json.loads((Path(__file__).parent / 'codegraph-runtime.json').read_text()))
        require_neutral_cwd(binding.get('environment', {}).get('CODEGRAPH_DIR', '.codegraph'))
        binary = binding['runtime_bin']
        os.execve(binary, [binary, 'serve', '--mcp'], runtime_env(binding, os.environ))
    except (ValueError, KeyError, TypeError, OSError):
        print('CodeGraph runtime unavailable; values suppressed; no install/index/repair attempted', file=sys.stderr)
        raise SystemExit(2)
