#!/usr/bin/env python3
"""Build-only pure-math extraction. No V1 CLI/SQLite/export reaches V2 runtime."""
import ast
from pathlib import Path

FUNCTIONS = {'now_iso', 'ms_to_iso', 'safe_slug', 'serialized_size', 'canonical_tool_name', 'is_codegraph_tool', 'tool_duration_ms', 'observed_sum', 'model_label', 'summarize_tools', 'compute_session_metrics', 'interval_union_ms', 'validate_variant', 'percentile', 'distribution', 'nested_number', 'improvement_percent', 'latest_by_variant', 'compatible_pair', 'build_report', 'summarize_pairs', 'format_value', 'report_markdown'}
CONSTANTS = {'VARIANTS', 'OUTCOMES', 'UTILITIES', 'MANUAL_SEARCH_TOOLS', 'REPORT_METRICS'}
CALLS = FUNCTIONS | {'aggregate', 'Path', 'Counter', 'ValueError', 'str', 'bool', 'len', 'isinstance', 'dict', 'int', 'float', 'sum', 'sorted', 'set', 'list', 'tuple', 'max', 'min', 'any', 'all', 'next', 'iter', 'enumerate', 'zip', 'filter', 'median'}
METHODS = {'now', 'replace', 'isoformat', 'fromtimestamp', 'sub', 'strip', 'lower', 'split', 'join', 'dumps', 'encode', 'get', 'append', 'values', 'items', 'removeprefix', 'startswith', 'ceil', 'setdefault', 'extend'}

def render():
    source = Path(__file__).resolve().parents[1] / 'scripts/codegraph_metrics.py'
    if source.is_symlink(): raise ValueError('Canonical math source symlink refused')
    tree = ast.parse(source.read_text())
    nodes, names = [], set()
    for node in tree.body:
        name = node.name if isinstance(node, ast.FunctionDef) else node.targets[0].id if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) else None
        if name not in FUNCTIONS | CONSTANTS: continue
        if name in names: raise ValueError('Duplicate canonical math definition')
        for child in ast.walk(node):
            if isinstance(child, (ast.Import, ast.ImportFrom, ast.Global, ast.Nonlocal, ast.With, ast.AsyncFunctionDef, ast.Await)):
                raise ValueError('Math source acquired unreviewed I/O or side effects')
            if isinstance(child, ast.Call) and isinstance(child.func, ast.Name) and child.func.id in {'open', 'exec', 'eval', 'compile', '__import__', 'getattr', 'setattr', 'globals', 'locals'}:
                raise ValueError('Unreviewed math execution primitive')
            if isinstance(child, ast.Call) and not (isinstance(child.func, ast.Name) and child.func.id in CALLS or isinstance(child.func, ast.Attribute) and child.func.attr in METHODS):
                raise ValueError('Math call contract changed; explicit review required')
        names.add(name); nodes.append(node)
    if names != FUNCTIONS | CONSTANTS: raise ValueError('Math contract changed; explicit extraction review required')
    return '# Generated pure metric functions from owner canonical source; no CLI/DB/export.\nfrom __future__ import annotations\nimport json,math,re\nfrom collections import Counter\nfrom datetime import datetime,timezone\nfrom pathlib import Path\nfrom statistics import median\nfrom typing import Any\n\n' + '\n\n'.join(ast.unparse(node) for node in nodes) + '\n'

if __name__ == '__main__':
    try: print(render(), end='')
    except Exception: raise SystemExit('Native metric math extraction failed; source values suppressed')
