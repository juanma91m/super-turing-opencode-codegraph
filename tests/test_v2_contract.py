import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(name, file):
    sys.path.insert(0, str(ROOT / 'v2'))
    spec = importlib.util.spec_from_file_location(name, file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class V2ContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.runtime = load('codegraph_runtime', ROOT / 'v2/runtime.py')
        self.selector = load('codegraph_selector', ROOT / 'v2/selected-runtime.py')
        prefix = self.home / '.local/share/super-turing-opencode-codegraph/runtime-v2-1.6.4/node_modules'
        self.binary = prefix / '.bin/codegraph'
        self.binary.parent.mkdir(parents=True)
        self.binary.write_text('#!/bin/sh\nexit 99\n')
        self.binary.chmod(0o700)
        package = prefix / '@colbymchenry/codegraph/package.json'
        package.parent.mkdir(parents=True)
        package.write_text(json.dumps({'version': '1.6.4'}))
        self.binding = {'runtime_home': str(self.home), 'runtime_bin': str(self.binary)}
        self.config = self.home / '.config/opencode'
        self.config.mkdir(parents=True)
        legacy = self.home / '.local/share/super-turing-opencode-codegraph/runtime/node_modules/.bin/codegraph'
        self.source = {'mcp': {'codegraph': self.selector.wiring.expected_mcp(str(legacy)), 'other': {'headers': {'Authorization': 'FIXTURE_NOT_FOR_OUTPUT'}}},
                       'tools': {'codegraph_*': False}, 'agent': {role: {'tools': {'codegraph_*': True}} for role in self.selector.wiring.AGENTS}}

    def save(self):
        (self.config / 'opencode.json').write_text(json.dumps(self.source))

    def test_selection_is_metadata_only_and_does_not_start_runtime(self):
        self.save()
        value = self.selector.select(str(self.home), str(self.config))
        self.assertEqual(value['binding'], self.binding)
        self.assertEqual(value['version'], json.loads((ROOT / 'CODEGRAPH-MANIFEST.json').read_text())['nativeV2']['version'])
        self.assertEqual(len(value['roles']), 5)
        self.assertNotIn('FIXTURE_NOT_FOR_OUTPUT', json.dumps(value))
        self.assertFalse((self.home / '.codegraph').exists())

    def test_selection_refuses_unknown_wiring_and_permission_drift(self):
        for change in ('headers', 'environment', 'actor', 'permission'):
            with self.subTest(change=change):
                original = json.loads(json.dumps(self.source))
                if change == 'headers': self.source['mcp']['codegraph']['headers'] = {'Authorization': 'FIXTURE_NOT_FOR_OUTPUT'}
                if change == 'environment': self.source['mcp']['codegraph']['environment']['CODEGRAPH_MCP_TOOLS'] = '*'
                if change == 'actor': self.source['agent']['planner']['tools']['codegraph_*'] = False
                if change == 'permission': self.source['permission'] = {'codegraph_*': 'deny'}
                self.save()
                with self.assertRaises(ValueError): self.selector.select(str(self.home), str(self.config))
                self.source = original

    def test_runtime_restores_identity_without_host_credentials_or_injection(self):
        env = self.runtime.runtime_env(self.binding, {'HOME': '/wrong', 'OPENAI_API_KEY': 'FIXTURE_NOT_FOR_OUTPUT', 'NODE_OPTIONS': '--require fixture', 'PYTHONPATH': 'fixture', 'CODEGRAPH_MCP_TOOLS': '*', 'CODEGRAPH_NO_DAEMON': '1', 'CODEGRAPH_NO_WATCH': '1'})
        self.assertEqual(env['HOME'], str(self.home))
        self.assertEqual(env['CODEGRAPH_MCP_TOOLS'], 'explore')
        self.assertEqual(env['CODEGRAPH_NO_DOWNLOAD'], '1')
        for key in ('OPENAI_API_KEY', 'NODE_OPTIONS', 'PYTHONPATH', 'CODEGRAPH_NO_DAEMON', 'CODEGRAPH_NO_WATCH'):
            self.assertNotIn(key, env)

    def test_runtime_does_not_install_or_accept_unknown_bindings(self):
        with self.assertRaises(ValueError): self.runtime.validate({**self.binding, 'token': 'fixture'})
        self.binary.unlink()
        with self.assertRaises(ValueError): self.runtime.validate(self.binding)
        self.assertFalse(self.binary.exists())

    def test_runtime_refuses_implicit_startup_index(self):
        neutral = self.home / 'neutral'; neutral.mkdir()
        with patch.object(Path, 'cwd', return_value=neutral):
            self.runtime.require_neutral_cwd('.codegraph-alt')
            (self.home / '.codegraph-alt').mkdir()
            with self.assertRaisesRegex(ValueError, 'index ancestor'):
                self.runtime.require_neutral_cwd('.codegraph-alt')

    def test_selection_preserves_explicit_watch_tuning_without_inheriting_arbitrary_values(self):
        self.save()
        selected = self.selector.select(str(self.home), str(self.config), {'CODEGRAPH_DIR': '.codegraph-existing', 'CODEGRAPH_NO_WATCH': '1', 'CODEGRAPH_QUERY_POOL_SIZE': '0', 'OPENAI_API_KEY': 'FIXTURE_NOT_FOR_OUTPUT'})
        env = self.runtime.runtime_env(selected['binding'], {})
        self.assertEqual(env['CODEGRAPH_NO_WATCH'], '1')
        self.assertEqual(env['CODEGRAPH_QUERY_POOL_SIZE'], '0')
        self.assertEqual(env['CODEGRAPH_DIR'], '.codegraph-existing')
        self.assertNotIn('OPENAI_API_KEY', env)
        with self.assertRaises(ValueError): self.selector.select(str(self.home), str(self.config), {'CODEGRAPH_FORCE_WATCH': 'FIXTURE_NOT_FOR_OUTPUT'})
        with self.assertRaises(ValueError): self.selector.select(str(self.home), str(self.config), {'CODEGRAPH_DIR': '../outside'})

    def test_selection_preserves_explicit_registry_reference_without_reading_or_creating_it(self):
        self.save()
        registry = self.home / 'custom-state/projects.json'
        selected = self.selector.select(str(self.home), str(self.config), {'OPENCODE_CODEGRAPH_REGISTRY': str(registry)})
        self.assertEqual(selected['maintenanceRegistry'], str(registry)); self.assertFalse(registry.exists())
        with self.assertRaises(ValueError): self.selector.select(str(self.home), str(self.config), {'OPENCODE_CODEGRAPH_REGISTRY': '/unreviewed/auth.json'})

    def test_benchmark_extraction_only_carries_reviewed_math_not_v1_sql_export_or_cli(self):
        extractor = load('benchmark_math_assets', ROOT / 'v2/math_assets.py')
        text = extractor.render()
        for forbidden in ('run_export', 'capture_record', 'load_records', 'subprocess', 'sqlite', 'argparse', 'atomic_write_json'):
            self.assertNotIn(forbidden, text)
        namespace = {}; exec(compile(text, '<reviewed-math-fixture>', 'exec'), namespace)
        self.assertEqual(namespace['improvement_percent'](354, 236), -50)
        self.assertIsNone(namespace['observed_sum']([118, None]))

    def test_benchmark_extraction_refuses_new_calls_or_imports_in_canonical_functions(self):
        extractor = load('benchmark_math_assets', ROOT / 'v2/math_assets.py')
        original = (ROOT / 'scripts/codegraph_metrics.py').read_text()
        for addition in ('Path("UNREVIEWED").write_text("BODY")', 'import subprocess', 'eval("UNREVIEWED")'):
            changed = original.replace('    return datetime.now', '    ' + addition + '\n    return datetime.now', 1)
            with patch.object(Path, 'read_text', return_value=changed):
                with self.assertRaises(ValueError): extractor.render()


if __name__ == '__main__': unittest.main()
