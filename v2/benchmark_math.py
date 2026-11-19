#!/usr/bin/env python3
"""Metadata-only worker: fixed stdin and pinned sibling code, no task/DB/network I/O."""
import json
import sys
import types
from collections import defaultdict
from pathlib import Path

# Python -I excludes cwd/script-directory from implicit imports. Load only the
# separately SHA-pinned arithmetic asset, never an adjacent json.py/PYTHONPATH.
math_file = Path(__file__).with_name('codegraph_metrics_math_v2.py')
core = types.ModuleType('codegraph_metrics_math_v2')
exec(compile(math_file.read_bytes(), str(math_file), 'exec'), core.__dict__)

MEASUREMENT = {'backend': 'opencode-public-api-2.2.7', 'tokens': 'normalized-exclusive-component-sum-v1', 'bytes': 'stored-tool-content-json-utf8-v1', 'history': 'stored-assistant-plus-completed-compaction-v1'}
original_pair = core.compatible_pair
def pair(left, right):
    if left.get('measurement') != right.get('measurement') or left.get('measurement') != MEASUREMENT:
        return 'backend/measurement distintos; no mezclar V1/V2 o definiciones'
    return original_pair(left, right)
core.compatible_pair = pair
core.is_codegraph_tool = lambda name: str(name) == 'codegraph_codegraph_explore'

def execute(value):
    if not isinstance(value, dict) or set(value) != {'operation', 'data'}: raise ValueError('Closed metadata math request required')
    if value['operation'] == 'metrics':
        result = core.compute_session_metrics(value['data'])
        result['tokens']['reported_total'] = None
        result['measurement'] = MEASUREMENT
        return result
    if value['operation'] == 'report':
        records = value['data']
        if not isinstance(records, list) or len(records) > 1000: raise ValueError('Bounded records required')
        result = core.build_report(records)
        result['measurement'] = MEASUREMENT
        result['schema_version'] = 3
        note = 'Medición V2: suma de componentes normalizados exclusivos (input/output/reasoning/cache read/write); NO total reportado del proveedor ni costo facturado. Sin mezcla V1/V2.\n\n'
        return {'report': result, 'markdown': note + core.report_markdown(result).replace('Tokens totales', 'Tokens derivados (componentes exclusivos)')}
    if value['operation'] == 'history':
        groups = defaultdict(list)
        for row in value['data']:
            metric = row['metrics']; models = tuple(sorted(metric['models']))
            cohort = 'with-codegraph' if metric['search']['codegraph']['calls'] else 'without-codegraph'
            groups[(row['project'], row['project_key'], models, cohort)].append(metric)
        rows = []
        for (project, key, models, cohort), units in sorted(groups.items()):
            fields = {name: [unit['tokens'][name] for unit in units] for name in ('total', 'input', 'output', 'reasoning', 'cache_read', 'cache_write')}
            fields.update({name: [unit['search'][group][field] for unit in units] for name, group, field in [('codegraph_calls', 'codegraph', 'calls'), ('codegraph_output_bytes', 'codegraph', 'output_bytes'), ('manual_calls', 'manual', 'calls'), ('search_output_bytes', 'combined', 'output_bytes')]})
            rows.append({'project': project, 'project_key': key, 'models': list(models), 'cohort': cohort, 'families': len(units), 'metrics': {name: core.distribution(values) for name, values in fields.items()}})
        return {'schema_version': 3, 'kind': 'observational-history', 'measurement': MEASUREMENT, 'families': len(value['data']), 'groups': rows, 'causalSavings': False, 'qualityInferred': False}
    raise ValueError('Unsupported metadata math operation')

if __name__ == '__main__':
    try:
        if sys.argv[1:]: raise ValueError('No math CLI arguments allowed')
        print(json.dumps(execute(json.load(sys.stdin))))
    except Exception:
        print('Native benchmark arithmetic refused invalid metadata; values suppressed', file=sys.stderr)
        raise SystemExit(2)
