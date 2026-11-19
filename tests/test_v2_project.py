import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'v2'))
spec = importlib.util.spec_from_file_location('native_project', ROOT / 'v2/project.py')
native = importlib.util.module_from_spec(spec); spec.loader.exec_module(native)


class ProjectLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='codegraph-project-', dir='/tmp/opencode'); self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name); self.home = self.base / 'home'; self.repo = self.base / 'repo'; self.repo.mkdir()
        self.git('init', '--quiet', '-b', 'main')
        self.binary = self.home / '.local/share/super-turing-opencode-codegraph/runtime/node_modules/.bin/codegraph'
        self.binary.parent.mkdir(parents=True)
        package = self.binary.parent.parent / '@colbymchenry/codegraph/package.json'; package.parent.mkdir(parents=True)
        package.write_text('{"version":"1.5.0"}')
        self.binary.write_text('''#!/usr/bin/python3
import json,os,sys
from pathlib import Path
action,root=sys.argv[1:3];root=Path(root);index=root/os.environ.get('CODEGRAPH_DIR','.codegraph')
with (Path(__file__).parent/'calls.jsonl').open('a') as f:f.write(json.dumps({'action':action,'args':sys.argv[1:],'secret':'OPENCODE_PASSWORD' in os.environ,'tuning':os.environ.get('CODEGRAPH_NO_WATCH')})+'\\n')
if action in ('init','sync','index'):
 index.mkdir(exist_ok=True);(index/'codegraph.db').write_text('SYNTHETIC_INDEX')
else:
 print(json.dumps({'initialized':(index/'codegraph.db').is_file(),'version':'1.5.0','indexPath':str(index),'files':2,'nodes':3,'edges':1,'rawCode':'MUST_NOT_RETURN','index':{'builtWithVersion':'1.5.0','reindexRecommended':(root/'recommend').exists()},'worktreeMismatch':(root/'mismatch').exists()}))
'''); self.binary.chmod(0o700)
        self.selected = {'binding': {'runtime_home': str(self.home), 'runtime_bin': str(self.binary), 'environment': {'CODEGRAPH_NO_WATCH': '1'}}, 'registry': str(self.home / '.local/state/super-turing-opencode-codegraph/projects.json')}
        self.host = {'OPENCODE_CODEGRAPH_ALLOW_TEMP': '1'}
        (self.repo / 'application.py').write_text('def public_fixture():\n    return 1\n')

    def git(self, *args, cwd=None):
        result = subprocess.run(['/usr/bin/git', '-C', str(cwd or self.repo), *args], env={'PATH': '/usr/bin:/bin', 'HOME': str(self.base), 'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_CONFIG_NOSYSTEM': '1'}, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, 'Owned Git fixture command failed'); return result.stdout.strip()

    def request(self, action, **extra): return {'action': action, 'projectRoot': str(self.repo), **extra}
    def execute(self, action, **extra): return native.execute(self.request(action, **extra), self.selected, self.host)
    def calls(self):
        file = self.binary.parent / 'calls.jsonl'
        return [json.loads(line) for line in file.read_text().splitlines()] if file.exists() else []

    def test_preflight_is_metadata_only_and_status_never_initializes_or_updates_registry(self):
        native.execute(self.request('status'), self.selected, self.host, preflight=True)
        self.assertEqual(self.calls(), []); self.assertFalse((self.repo / '.codegraph').exists())
        result = self.execute('status'); self.assertFalse(result['status']['initialized'])
        self.assertFalse(result['registryUpdated']); self.assertFalse(Path(self.selected['registry']).exists()); self.assertFalse((self.repo / '.codegraph').exists())
        self.assertNotIn('MUST_NOT_RETURN', json.dumps(result))

    def test_init_adopts_compatible_existing_sync_and_confirmed_reindex_have_exact_effects(self):
        before = (self.repo / 'application.py').read_bytes()
        self.assertFalse(self.execute('init')['adoptedExisting']); self.assertTrue(self.execute('init')['adoptedExisting'])
        self.execute('sync'); self.execute('reindex', confirmReindex=True)
        actions = [call['action'] for call in self.calls()]
        self.assertEqual(actions.count('init'), 1); self.assertEqual(actions.count('sync'), 1); self.assertEqual(actions.count('index'), 1)
        index_call = next(call for call in self.calls() if call['action'] == 'index'); self.assertEqual(index_call['args'], ['index', str(self.repo), '--force'])
        self.assertTrue(all(not call['secret'] and call['tuning'] == '1' for call in self.calls()))
        self.assertEqual((self.repo / 'application.py').read_bytes(), before)
        registry = json.loads(Path(self.selected['registry']).read_text()); self.assertIn(str(self.repo), registry['projects'])
        exclude = Path(self.git('rev-parse', '--git-path', 'info/exclude'))
        if not exclude.is_absolute(): exclude = self.repo / exclude
        self.assertEqual(exclude.read_text().splitlines().count('.codegraph/'), 1)

    def test_missing_incompatible_incomplete_and_worktree_mismatch_never_trigger_fallback(self):
        with self.assertRaisesRegex(ValueError, 'Existing index'): self.execute('sync')
        with self.assertRaisesRegex(ValueError, 'confirmReindex'): self.execute('reindex')
        self.assertEqual(self.calls(), [])
        (self.repo / '.codegraph').mkdir()
        with self.assertRaisesRegex(ValueError, 'not initialized'): self.execute('init')
        self.assertNotIn('init', [call['action'] for call in self.calls()])
        (self.repo / '.codegraph/codegraph.db').write_text('SYNTHETIC')
        (self.repo / 'recommend').touch()
        with self.assertRaisesRegex(ValueError, 'Explicit reindex'): self.execute('sync')
        with self.assertRaisesRegex(ValueError, 'Explicit reindex'): self.execute('init')
        self.assertNotIn('sync', [call['action'] for call in self.calls()])
        (self.repo / 'mismatch').touch()
        with self.assertRaisesRegex(ValueError, 'mismatch'): self.execute('reindex', confirmReindex=True)
        self.assertNotIn('index', [call['action'] for call in self.calls()])

    def test_roots_symlinks_temp_flag_and_sensitive_sources_fail_without_runtime_work(self):
        sub = self.repo / 'sub'; sub.mkdir()
        for value in [str(sub), str(self.repo / '..' / 'repo'), 'relative']:
            with self.assertRaises(ValueError): native.execute({'action': 'status', 'projectRoot': value}, self.selected, self.host)
        with self.assertRaisesRegex(ValueError, 'Temporary'): native.execute(self.request('init'), self.selected, {})
        (self.repo / '.env.synthetic').write_text('SYNTHETIC_MUST_NOT_READ')
        with self.assertRaisesRegex(ValueError, 'sensitive'): self.execute('init')
        self.assertEqual(self.calls(), [])
        (self.repo / '.env.synthetic').unlink(); target = self.base / 'elsewhere'; target.mkdir(); (self.repo / '.codegraph').symlink_to(target)
        with self.assertRaisesRegex(ValueError, 'Symlink'): self.execute('status')

    def test_worktrees_have_distinct_roots_and_index_metadata(self):
        worktree = self.base / 'linked'
        self.git('worktree', 'add', '--quiet', '--orphan', '-b', 'fixture-linked', str(worktree))
        self.execute('init')
        result = native.execute({'action': 'init', 'projectRoot': str(worktree)}, self.selected, self.host)
        self.assertEqual(result['projectRoot'], str(worktree)); self.assertTrue((worktree / '.codegraph/codegraph.db').is_file())
        registry = json.loads(Path(self.selected['registry']).read_text())['projects']
        self.assertNotEqual(registry[str(self.repo)]['indexPath'], registry[str(worktree)]['indexPath'])

    def test_explicit_index_directory_and_registry_failure_do_not_silently_fork_or_overwrite(self):
        self.selected['binding']['environment']['CODEGRAPH_DIR'] = '.codegraph-secondary'
        self.execute('init')
        self.assertFalse((self.repo / '.codegraph').exists()); self.assertTrue((self.repo / '.codegraph-secondary/codegraph.db').exists())
        file = Path(self.selected['registry']); file.write_text('INVALID_SYNTHETIC_REGISTRY')
        before = len(self.calls())
        with self.assertRaisesRegex(ValueError, 'Invalid owner registry'): self.execute('sync')
        self.assertEqual(len(self.calls()), before); self.assertEqual(file.read_text(), 'INVALID_SYNTHETIC_REGISTRY')


class RealPinnedRuntimeTest(unittest.TestCase):
    def test_actual_runtime_init_adopt_sync_reindex_status_only_on_owned_temporary_index(self):
        with tempfile.TemporaryDirectory(prefix='codegraph-real-project-', dir='/tmp/opencode') as temporary:
            base = Path(temporary); home = base / 'home'; repo = base / 'repo'; repo.mkdir()
            source = Path.home() / '.local/share/super-turing-opencode-codegraph/runtime/node_modules'
            destination = home / '.local/share/super-turing-opencode-codegraph/runtime/node_modules'
            # Copy only the two public program packages; never HOME/cache/indexes,
            # auth or npm state. No download/recompile/runtime replacement.
            for name in ('codegraph', 'codegraph-linux-x64'):
                package = source / '@colbymchenry' / name
                self.assertTrue(package.is_dir(), 'Pinned public platform package required; no automatic install')
                for entry in package.rglob('*'):
                    self.assertFalse(entry.name.startswith('.env') or entry.name in ('.npmrc', '.codegraph', 'auth.json'), 'Private data is not a runtime fixture source')
                    if entry.is_symlink(): self.assertTrue(entry.resolve().is_relative_to(package.resolve()))
                shutil.copytree(package, destination / '@colbymchenry' / name, symlinks=True)
            binary = destination / '.bin/codegraph'; binary.parent.mkdir(); binary.symlink_to('../@colbymchenry/codegraph/npm-shim.js')
            self.assertTrue(binary.resolve().is_relative_to(destination))
            binding = {'runtime_home': str(home), 'runtime_bin': str(binary), 'environment': {'CODEGRAPH_NO_DAEMON': '1', 'CODEGRAPH_NO_WATCH': '1'}}
            selected = {'binding': binding, 'registry': str(home / '.local/state/super-turing-opencode-codegraph/projects.json')}
            env = {'PATH': '/usr/bin:/bin', 'HOME': str(home), 'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_CONFIG_NOSYSTEM': '1'}
            result = subprocess.run(['/usr/bin/git', '-C', str(repo), 'init', '--quiet', '-b', 'main'], env=env, capture_output=True); self.assertEqual(result.returncode, 0)
            source_file = repo / 'fixture.py'; source_file.write_text('def leaf():\n    return 1\n\ndef entry():\n    return leaf()\n')
            before = source_file.read_bytes()
            host = {'OPENCODE_CODEGRAPH_ALLOW_TEMP': '1'}
            def request(action, **extra): return native.execute({'action': action, 'projectRoot': str(repo), **extra}, selected, host)
            self.assertFalse(request('status')['status']['initialized']); self.assertFalse((repo / '.codegraph/codegraph.db').exists())
            created = request('init'); self.assertTrue(created['status']['initialized']); self.assertTrue((repo / '.codegraph/codegraph.db').is_file())
            self.assertEqual(created['status']['version'], '1.5.0')
            self.assertTrue(request('init')['adoptedExisting'])
            source_file.write_text(source_file.read_text() + '\ndef added():\n    return entry()\n')
            updated = source_file.read_bytes(); self.assertTrue(request('sync')['status']['initialized'])
            self.assertTrue(request('reindex', confirmReindex=True)['status']['initialized'])
            projected = request('status')['status']
            self.assertGreater(projected['fileCount'], 0); self.assertGreater(projected['nodeCount'], 0); self.assertGreater(projected['edgeCount'], 0)
            self.assertIn('reindexRecommended', projected['index']); self.assertIn('added', projected['pendingChanges'])
            self.assertFalse(request('status')['registryUpdated']); self.assertEqual(source_file.read_bytes(), updated)
            self.assertNotEqual(before, updated); self.assertFalse((repo / 'codegraph.json').exists())
            self.assertFalse((repo / '.gitignore').exists(), 'Lifecycle must use local Git exclude, not create tracked ignore configuration')


if __name__ == '__main__': unittest.main()
