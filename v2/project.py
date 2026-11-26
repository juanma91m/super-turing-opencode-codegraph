#!/usr/bin/env python3
"""Closed native project lifecycle. No install/upgrade/uninit/unlock or shell.

Only explicit requests invoke this program. Raw backend stdout/stderr never reach
the model. Runtime and original semantic watcher/daemon settings stay owner-owned.
"""
import fcntl
import json
import os
from pathlib import Path
import signal
import selectors
import stat
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from contextlib import contextmanager

sys.dont_write_bytecode = True
if (Path(__file__).parent / 'codegraph_runtime.py').is_file():
    from codegraph_runtime import VERSION, check_index, runtime_env, validate
else:
    from runtime import VERSION, check_index, runtime_env, validate

ACTIONS = {'init', 'status', 'sync', 'reindex'}
MAX_OUTPUT = 4 * 1024 * 1024
LOCK_OWNER = {'owner': 'opencode-codegraph-native', 'schemaVersion': 1}

def no_links(path):
    for item in (*reversed(Path(path).parents), Path(path)):
        if item.is_symlink():
            raise ValueError('Symlinked lifecycle path refused')

def git(root, *args):
    result = subprocess.run(['/usr/bin/git', '--no-optional-locks', '-c', 'core.fsmonitor=false', '-c', 'core.hooksPath=/dev/null', '-C', str(root), *args],
        env={'PATH': '/usr/bin:/bin', 'HOME': '/tmp/opencode', 'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_CONFIG_NOSYSTEM': '1', 'GIT_OPTIONAL_LOCKS': '0'}, capture_output=True, text=True, timeout=15)
    if result.returncode:
        raise ValueError('Exact usable Git/worktree root required; raw Git output suppressed')
    return result.stdout

def select_root(value, home, parent):
    if not isinstance(value, str): raise ValueError('Explicit root required')
    root = Path(value)
    if not root.is_absolute() or str(root) != value or '..' in root.parts or root == Path(root.anchor) or root in (Path(home), Path.home()):
        raise ValueError('Explicit canonical non-home project root required')
    no_links(root); no_links(root / '.git')
    if not root.is_dir() or git(root, 'rev-parse', '--show-toplevel').strip() != value:
        raise ValueError('Pass the exact Git/worktree root, not subdirectory or parent index')
    if any(root == temporary or root.is_relative_to(temporary) for temporary in (Path('/tmp'), Path('/var/tmp'))):
        # Same explicit host-side test/diagnostic opt-in as V1, deliberately
        # narrowed. Not an input field and never inherited by general launcher.
        if parent.get('OPENCODE_CODEGRAPH_ALLOW_TEMP') != '1' or root == Path('/tmp/opencode') or not root.is_relative_to('/tmp/opencode'):
            raise ValueError('Temporary project root refused without operator fixture opt-in')
    return root

def config(value):
    if not isinstance(value, dict) or set(value) != {'binding', 'registry'}:
        raise ValueError('Closed native maintenance binding required')
    validate(value['binding'])
    registry = Path(value['registry'])
    if not registry.is_absolute() or '..' in registry.parts or registry.name != 'projects.json' or registry.parent == Path(registry.anchor):
        raise ValueError('Explicit owner projects.json registry required')
    no_links(registry)
    return value

def metadata(request, selected, parent):
    if not isinstance(request, dict) or set(request) - {'action', 'projectRoot', 'confirmReindex'} or request.get('action') not in ACTIONS:
        raise ValueError('Closed lifecycle operation required')
    if request['action'] == 'reindex' and request.get('confirmReindex') is not True:
        raise ValueError('Explicit confirmReindex required before reindex')
    root = select_root(request.get('projectRoot'), selected['binding']['runtime_home'], parent)
    index = root / selected['binding'].get('environment', {}).get('CODEGRAPH_DIR', '.codegraph')
    if index.name in ('.git', '.ssh', '.gnupg', 'node_modules'): raise ValueError('Unsafe index directory name; explicit owner reconciliation required')
    no_links(index)
    if index.exists() and not index.is_dir(): raise ValueError('Index path must be a directory')
    for name in ('codegraph.db', 'codegraph.db-wal', 'codegraph.db-shm'):
        file = index / name; no_links(file)
        if file.exists():
            info = file.stat()
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1: raise ValueError('Unsafe index database type or hardlink')
    return root, index

def check_sensitive(root):
    for file in git(root, 'ls-files', '--cached', '--others', '--exclude-standard', '-z', '--', '.').split('\0'):
        parts = file.lower().split('/'); name = parts[-1]
        if (name.startswith('.env') and file.split('/')[-1] != '.env.example') or any(part in ('.ssh', '.gnupg') for part in parts) or name in ('auth.json', 'credentials.json', 'token.json', 'tokens.json', 'secrets.json') or Path(name).suffix in ('.pem', '.key', '.p12', '.pfx'):
            raise ValueError('Potential sensitive indexed source; reconcile tracked/ignore policy first, no contents read')

def backend(selected, root, *args):
    env = runtime_env(selected['binding'], os.environ)
    # No stdin or transcript; cancellation reaches only this owned CLI process
    # group, never a shared daemon discovered by PID/name or an unlock operation.
    child = subprocess.Popen([selected['binding']['runtime_bin'], *args], cwd=root, env=env, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    def stop(_signal, _frame):
        if child.poll() is None: os.killpg(child.pid, signal.SIGTERM)
        raise KeyboardInterrupt()
    previous = {kind: signal.signal(kind, stop) for kind in (signal.SIGINT, signal.SIGTERM)}
    try:
        chunks, size, deadline = [], 0, time.monotonic() + 1800
        with selectors.DefaultSelector() as streams:
            streams.register(child.stdout, selectors.EVENT_READ, True); streams.register(child.stderr, selectors.EVENT_READ, False)
            while streams.get_map():
                if time.monotonic() > deadline: raise ValueError('CodeGraph CLI exceeded explicit30-minute bound; no repair fallback')
                for key, _ in streams.select(0.2):
                    data = os.read(key.fileobj.fileno(), 65536)
                    if not data: streams.unregister(key.fileobj)
                    elif key.data:
                        size += len(data)
                        if size > MAX_OUTPUT: raise ValueError('CodeGraph CLI output limit exceeded; partial work may remain')
                        chunks.append(data)
        child.wait(timeout=5)
        if child.returncode:
            raise ValueError('CodeGraph CLI operation failed; raw output suppressed; no fallback/repair')
        return b''.join(chunks).decode('utf-8')
    finally:
        if child.poll() is None:
            os.killpg(child.pid, signal.SIGTERM)
            try: child.communicate(timeout=3)
            except subprocess.TimeoutExpired: os.killpg(child.pid, signal.SIGKILL); child.communicate()
        child.stdout.close(); child.stderr.close()
        for kind, handler in previous.items(): signal.signal(kind, handler)

def status(selected, root, index):
    try: value = json.loads(backend(selected, root, 'status', str(root), '--json'))
    except json.JSONDecodeError: raise ValueError('Native CodeGraph status was not JSON; raw values suppressed')
    if not isinstance(value, dict): raise ValueError('Native status object required')
    if value.get('indexPath') and Path(value['indexPath']) != index:
        raise ValueError('Runtime index path differs from explicit worktree selection')
    return value

def compatible(value, initialized=True):
    if value.get('worktreeMismatch'): raise ValueError('Index worktree mismatch; operator reconciliation required')
    if initialized and value.get('initialized') is not True: raise ValueError('Index is not initialized; no implicit init')
    if (value.get('index') or {}).get('reindexRecommended') is True:
        raise ValueError('Explicit reindex recommended; adoption/sync stopped, never forced automatically')

def filtered(value):
    scalar = lambda item: item is None or isinstance(item, (str, bool, int, float))
    result = {key: value[key] for key in ('initialized', 'version', 'lastIndexed', 'files', 'nodes', 'edges', 'fileCount', 'nodeCount', 'edgeCount', 'dbSizeBytes', 'backend', 'journalMode', 'worktreeMismatch') if key in value and scalar(value[key])}
    if 'worktreeMismatch' in value: result['worktreeMismatch'] = bool(value['worktreeMismatch'])
    for group in ('index', 'stats', 'pendingSync', 'pendingChanges'):
        current = value.get(group)
        if isinstance(current, dict):
            allowed = ('builtWithVersion', 'builtWithExtractionVersion', 'currentExtractionVersion', 'reindexRecommended', 'state', 'pendingRefs', 'files', 'nodes', 'edges', 'count', 'pending', 'pendingFiles', 'added', 'modified', 'removed', 'deleted')
            result[group] = {key: len(item) if isinstance(item, list) else item for key, item in current.items() if key in allowed and (scalar(item) or isinstance(item, list))}
    return result

def owner_path(root, kind):
    raw = git(root, 'rev-parse', '--git-path', kind).strip(); selected = Path(raw)
    if not selected.is_absolute(): selected = root / selected
    no_links(selected)
    return selected

def write_json(file, value):
    no_links(file); file.parent.mkdir(parents=True, exist_ok=True); no_links(file.parent)
    fd, temporary = tempfile.mkstemp(prefix='.codegraph-write-', dir=file.parent)
    try:
        with os.fdopen(fd, 'w') as stream: json.dump(value, stream, indent=2); stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
        Path(temporary).replace(file)
    finally: Path(temporary).unlink(missing_ok=True)

@contextmanager
def owner_lock(file, nonblocking=False):
    no_links(file); file.parent.mkdir(parents=True, exist_ok=True); no_links(file.parent)
    try: fd = os.open(file, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600); created = True
    except FileExistsError: fd = os.open(file, os.O_RDWR | os.O_NOFOLLOW); created = False
    with os.fdopen(fd, 'r+') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 2048 or info.st_mode & 0o6022: raise ValueError('Unsafe maintenance lock metadata')
        try: fcntl.flock(stream, fcntl.LOCK_EX | (fcntl.LOCK_NB if nonblocking else 0))
        except BlockingIOError: raise ValueError('Owner maintenance already active; no unlock/kill fallback')
        if created: json.dump(LOCK_OWNER, stream); stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
        else:
            try: current = json.load(stream)
            except json.JSONDecodeError: raise ValueError('Unknown maintenance lock; no automatic adoption')
            if current != LOCK_OWNER: raise ValueError('Unknown maintenance lock owner; no automatic adoption')
        yield

def record(file, root, index, value):
    no_links(file); file.parent.mkdir(parents=True, exist_ok=True); no_links(file.parent)
    lock = file.with_name(file.name + '.lock'); no_links(lock)
    with owner_lock(lock):
        current = {'schemaVersion': 1, 'projects': {}}
        if file.exists():
            if not file.is_file() or file.stat().st_nlink != 1 or file.stat().st_size > MAX_OUTPUT: raise ValueError('Unsafe owner registry')
            try: current = json.loads(file.read_text())
            except json.JSONDecodeError: raise ValueError('Invalid owner registry; no adoption/overwrite')
            if not isinstance(current, dict) or not isinstance(current.get('projects'), dict) or current.get('schemaVersion') != 1: raise ValueError('Incompatible owner registry')
        current['projects'][str(root)] = {'root': str(root), 'indexPath': str(index), 'codegraphVersion': value.get('version'), 'builtWithVersion': (value.get('index') or {}).get('builtWithVersion'), 'lastIndexed': value.get('lastIndexed'), 'lastSeenAt': datetime.now(timezone.utc).isoformat()}
        write_json(file, current)

def registry_preflight(file):
    no_links(file)
    if file.exists():
        if not file.is_file() or file.stat().st_nlink != 1 or file.stat().st_size > MAX_OUTPUT: raise ValueError('Unsafe owner registry')
        try: current = json.loads(file.read_text())
        except json.JSONDecodeError: raise ValueError('Invalid owner registry; no adoption/overwrite')
        if not isinstance(current, dict) or current.get('schemaVersion') != 1 or not isinstance(current.get('projects'), dict): raise ValueError('Incompatible owner registry')
    with owner_lock(file.with_name(file.name + '.lock')): pass

def exclude(root, index):
    file = owner_path(root, 'info/exclude'); file.parent.mkdir(parents=True, exist_ok=True)
    with owner_lock(file.with_name('opencode-codegraph-exclude.lock')):
        if file.exists() and (not file.is_file() or file.stat().st_nlink != 1 or file.stat().st_size > MAX_OUTPUT): raise ValueError('Unsafe Git exclude metadata')
        text = file.read_text() if file.exists() else ''
        if index.name + '/' not in [line.strip() for line in text.splitlines()]:
            # Same single-line metadata effect as V1; no tracked .gitignore/source.
            fd, temporary = tempfile.mkstemp(prefix='.codegraph-exclude-', dir=file.parent)
            try:
                with os.fdopen(fd, 'w') as stream: stream.write(text + ('\n' if text and not text.endswith('\n') else '') + index.name + '/\n')
                Path(temporary).replace(file)
            finally: Path(temporary).unlink(missing_ok=True)

def execute(request, selected, parent=None, preflight=False):
    parent = os.environ if parent is None else parent
    selected = config(selected); root, index = metadata(request, selected, parent)
    action = request['action']
    if preflight: return {'action': action, 'projectRoot': str(root), 'indexPath': str(index), 'registry': selected['registry']}
    if action == 'status':
        if check_index(index, allow_absent=True):
            check_sensitive(root)
            value = status(selected, root, index)
        else:
            value = {'initialized': False, 'version': VERSION}
        return {'action': action, 'projectRoot': str(root), 'status': filtered(value), 'indexOperationIssued': False, 'registryUpdated': False}
    check_sensitive(root)
    check_index(index, allow_absent=action == 'init', allow_stale_extraction=action == 'reindex')
    registry_preflight(Path(selected['registry']))
    if action in ('sync', 'reindex') and (not index.is_dir() or not (index / 'codegraph.db').is_file()): raise ValueError('Existing index DB required; no init/repair fallback')
    lock = owner_path(root, 'opencode-codegraph-maintenance.lock'); lock.parent.mkdir(parents=True, exist_ok=True); no_links(lock)
    with owner_lock(lock, nonblocking=True):
        existed = check_index(index, allow_absent=action == 'init', allow_stale_extraction=action == 'reindex')
        if existed:
            current = status(selected, root, index)
            if current.get('worktreeMismatch'): raise ValueError('Index worktree mismatch; no adoption/rebuild')
            if action != 'reindex': compatible(current)
        if action == 'init' and not existed:
            exclude(root, index)
            backend(selected, root, 'init', str(root))
        elif action == 'sync': backend(selected, root, 'sync', str(root))
        elif action == 'reindex': backend(selected, root, 'index', str(root), '--force')
        check_index(index)
        final = status(selected, root, index); compatible(final)
        if action == 'init': exclude(root, index)
        record(Path(selected['registry']), root, index, final)
        return {'action': action, 'projectRoot': str(root), 'adoptedExisting': action == 'init' and existed, 'indexOperationIssued': action != 'init' or not existed, 'registryUpdated': True, 'status': filtered(final)}

if __name__ == '__main__':
    try:
        if sys.argv[1:] not in ([], ['--preflight'], ['--query-index']): raise ValueError('No CLI overrides allowed')
        binding = json.loads((Path(__file__).parent / 'codegraph-maintenance.json').read_text())
        request = json.load(sys.stdin)
        if sys.argv[1:] == ['--query-index']:
            if not isinstance(request, dict) or set(request) != {'action', 'projectRoot'} or request['action'] != 'status':
                raise ValueError('Closed compatibility probe required')
            root, index = metadata(request, config(binding), os.environ)
            check_sensitive(root)
            check_index(index)
        else:
            print(json.dumps(execute(request, binding, preflight=bool(sys.argv[1:]))))
    except json.JSONDecodeError:
        print('CodeGraph lifecycle metadata JSON invalid; raw values suppressed', file=sys.stderr)
        raise SystemExit(2)
    except ValueError as error:
        print('CodeGraph lifecycle refused: ' + str(error), file=sys.stderr)
        raise SystemExit(2)
    except (Exception, KeyboardInterrupt):
        print('CodeGraph native lifecycle failed; values suppressed. No install/reindex/repair fallback; interrupted work may remain.', file=sys.stderr)
        raise SystemExit(2)
