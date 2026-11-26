#!/usr/bin/env python3
"""Inspect only known current wiring. Never serialize arbitrary config/auth data."""
import importlib.util
import fnmatch
import json
import os
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('codegraph_wiring', ROOT / 'scripts/manage_opencode_config.py')
wiring = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wiring)
from runtime import validate, ENV_KEYS, PREFIX, RUNTIME_NAMES, VERSION


def select(home, config, parent=None):
    parent = os.environ if parent is None else parent
    home, config = Path(home), Path(config)
    if not home.is_absolute() or not config.is_absolute():
        raise ValueError('Absolute runtime paths required')
    binaries = [home / PREFIX / name / 'node_modules/.bin/codegraph' for name in RUNTIME_NAMES]
    # The candidate name was used by an earlier rollout of the SAME pin.
    # A broken standard installation is not silently replaced by it.
    binary = str(binaries[0] if os.path.lexists(binaries[0].parents[2]) else binaries[1])
    tuning = {key: parent[key] for key in ENV_KEYS if key in parent}
    binding = validate({'runtime_home': str(home), 'runtime_bin': binary, **({'environment': tuning} if tuning else {})})
    source = json.loads((config / 'opencode.json').read_text())
    # The V1 document is authorization metadata, not the executable binding
    # for V2. No V1 binary has to be installed or opened.
    legacy = str(home / PREFIX / 'runtime/node_modules/.bin/codegraph')
    if source.get('mcp', {}).get('codegraph') not in (wiring.expected_mcp(legacy), wiring.expected_mcp(binary)):
        raise ValueError('CodeGraph wiring differs; do not copy arbitrary values')
    if source.get('tools', {}).get('codegraph_*') is not False:
        raise ValueError('Expected the global CodeGraph deny baseline')
    permissions = source.get('permission', {})
    if isinstance(permissions, str):
        permissions = {'*': permissions}
    if not isinstance(permissions, dict):
        raise ValueError('Unsupported current permission shape')
    for tool in ('codegraph_explore', 'codegraph_codegraph_explore'):
        for pattern, value in permissions.items():
            if fnmatch.fnmatchcase(tool, pattern) and value != 'allow':
                raise ValueError('CodeGraph permission overrides require reconciliation')
    actors = source.get('agent', {})
    if not isinstance(actors, dict) or any(not isinstance(data, dict) for data in actors.values()):
        raise ValueError('Unsupported actor configuration')
    for actor in wiring.AGENTS:
        if actors.get(actor, {}).get('tools', {}).get('codegraph_*') is not True:
            raise ValueError('Current CodeGraph role grants need explicit reconciliation')
    for actor, data in actors.items():
        if actor not in wiring.AGENTS and any(key.startswith('codegraph_') and value is True for key, value in data.get('tools', {}).items()):
            raise ValueError('Additional current CodeGraph actors require reconciliation')
        overrides = data.get('permission', {})
        if isinstance(overrides, str):
            if actor in wiring.AGENTS and overrides != 'allow':
                raise ValueError('Inline CodeGraph permissions require reconciliation')
        elif isinstance(overrides, dict):
            if any(fnmatch.fnmatchcase('codegraph_codegraph_explore', key) and value != 'allow' for key, value in overrides.items()):
                raise ValueError('Inline CodeGraph permissions require reconciliation')
        else:
            raise ValueError('Unsupported inline permissions')
    state = Path(parent.get('OPENCODE_CODEGRAPH_STATE_DIR', str(home / '.local/state/super-turing-opencode-codegraph')))
    registry = Path(parent.get('OPENCODE_CODEGRAPH_REGISTRY', str(state / 'projects.json')))
    if not state.is_absolute() or '..' in state.parts or not registry.is_absolute() or '..' in registry.parts or registry.name != 'projects.json' or registry.parent == Path(registry.anchor):
        raise ValueError('Maintenance registry path needs explicit reconciliation')
    for current in (*reversed(registry.parents), registry):
        if current.is_symlink(): raise ValueError('Maintenance registry symlink refused')
    return {'binding': binding, 'maintenanceRegistry': str(registry), 'roles': list(wiring.AGENTS), 'version': VERSION, 'tools': ['explore']}


if __name__ == '__main__':
    try:
        options = json.load(sys.stdin)
        print(json.dumps(select(options['home'], options['config'])))
    except (ValueError, KeyError, TypeError, OSError):
        print('Current CodeGraph wiring could not be selected safely; values suppressed; backend not started', file=sys.stderr)
        raise SystemExit(2)
