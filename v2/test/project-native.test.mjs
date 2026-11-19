import assert from 'node:assert/strict';
import fs from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { test } from 'node:test';
import { codegraphContribution } from '../general.mjs';
import { prepareGeneral, generalEnvironment } from '../../../opencode-stack/v2/general/profile.mjs';
import { officialRuntime } from '../../../opencode-stack/v2/general/lifecycle.mjs';
import { startOwnedServer, until } from '../../../opencode-stack/v2/general/owned-server.mjs';
import { decodeList } from '../../../opencode-stack/v2/general/audit.mjs';

test('official2.2.7 native lifecycle routes metadata/index writes without shell expansion, requires permission and blocks actor/session bypass', async t => {
  const root = fs.mkdtempSync('/tmp/opencode/graph-native-project-'); t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const project = path.join(root, 'project'), home = path.join(root, 'runtime-home'), control = path.join(root, 'control'); fs.mkdirSync(project); fs.mkdirSync(control);
  assert.equal(spawnSync('/usr/bin/git', ['init', '--quiet', '-b', 'main'], { cwd: project, env: { PATH: '/usr/bin:/bin', HOME: root, GIT_CONFIG_GLOBAL: '/dev/null', GIT_CONFIG_NOSYSTEM: '1' } }).status, 0);
  fs.writeFileSync(path.join(project, 'fixture.py'), 'def public_fixture():\n    return 1\n');
  const binary = path.join(home, '.local/share/super-turing-opencode-codegraph/runtime/node_modules/.bin/codegraph'), calls = path.join(root, 'cli-calls.jsonl');
  fs.mkdirSync(path.dirname(binary), { recursive: true }); fs.mkdirSync(path.join(path.dirname(path.dirname(binary)), '@colbymchenry/codegraph'), { recursive: true });
  fs.writeFileSync(path.join(path.dirname(path.dirname(binary)), '@colbymchenry/codegraph/package.json'), '{"version":"1.5.0"}');
  fs.writeFileSync(binary, '#!/usr/bin/python3\nimport json,os,sys\nfrom pathlib import Path\naction,raw=sys.argv[1:3];root=Path(raw);index=root/".codegraph"\nwith open(' + JSON.stringify(calls) + ',"a") as stream:stream.write(json.dumps({"action":action,"secret":"OPENCODE_PASSWORD" in os.environ})+"\\n")\nif action in ("init","sync","index"):\n index.mkdir(exist_ok=True);(index/"codegraph.db").write_text("SYNTHETIC_ONLY")\nelse:print(json.dumps({"initialized":(index/"codegraph.db").is_file(),"version":"1.5.0","indexPath":str(index),"fileCount":1,"nodeCount":2,"edgeCount":1,"index":{"builtWithVersion":"1.5.0","reindexRecommended":False}}))\n', { mode: 0o700 });
  fs.writeFileSync(path.join(control, 'package.json'), '{"type":"module"}'); fs.writeFileSync(path.join(control, 'index.ts'), 'import {Plugin} from "@opencode/plugin";export default Plugin.define({id:"fixture.graph-project",async setup(ctx){await ctx.session.hook("title",e=>{e.result="Lifecycle fixture"})}});');
  const trace = new Map(); let providerError, server;
  const unpack = value => { if (typeof value === 'string') { try { return unpack(JSON.parse(value)); } catch { return value; } } if (Array.isArray(value)) return value.map(unpack).join('\n'); if (value?.error) return JSON.stringify(value.error); if (value?.text !== undefined) return unpack(value.text); if (value?.content !== undefined) return unpack(value.content); return JSON.stringify(value); };
  const model = http.createServer(async (request, response) => {
    try {
      let raw = ''; for await (const chunk of request) { raw += chunk; assert(raw.length < 8 * 1024 * 1024); }
      const body = JSON.parse(raw), user = JSON.stringify(body.messages.filter(row => row.role === 'user').at(-1)), kind = user.match(/PROJECT_([A-Z_]+)/)?.[1] ?? (user.includes('codegraph-project action status') ? 'COMMAND_STATUS' : undefined); assert(kind);
      const system = JSON.stringify(body.messages.filter(row => row.role === 'system'));
      const results = body.messages.filter(row => row.role === 'tool' && row.tool_call_id === kind).map(row => unpack(row.content)); trace.set(kind, { results, finished: results.length > 0, inspector: system.includes('currently operating as the \\"code-inspector\\" agent') });
      const action = ['INIT', 'REJECT', 'RO_BYPASS'].includes(kind) ? 'init' : kind === 'SYNC' ? 'sync' : kind.startsWith('REINDEX') ? 'reindex' : 'status';
      const args = { action, projectRoot: kind === 'SUBDIR' ? path.join(project, 'sub') : project, ...(kind === 'REINDEX' ? { confirmReindex: true } : {}) };
      response.writeHead(200, { 'Content-Type': 'text/event-stream' });
      const delta = results.length ? { role: 'assistant', content: 'SYNTHETIC_PROJECT_DONE' } : { role: 'assistant', tool_calls: [{ index: 0, id: kind, type: 'function', function: { name: 'codegraph-project', arguments: JSON.stringify(args) } }] };
      response.end('data: ' + JSON.stringify({ id: 'graph-project', object: 'chat.completion.chunk', created: 1, model: 'mock', choices: [{ index: 0, delta, finish_reason: results.length ? 'stop' : 'tool_calls' }] }) + '\n\ndata: [DONE]\n\n');
    } catch { providerError = 'Synthetic lifecycle provider failed; content suppressed'; response.writeHead(500); response.end('Fixture failure'); }
  });
  await new Promise(resolve => model.listen(0, '127.0.0.1', resolve));
  try {
    const binding = { runtime_home: home, runtime_bin: binary }, registry = path.join(home, '.local/state/super-turing-opencode-codegraph/projects.json');
    const p = prepareGeneral(path.join(root, 'profile'), { project, mock: 'http://127.0.0.1:' + model.address().port + '/v1', contributions: [codegraphContribution({ binding, server: { type: 'local', command: ['/not-started-fixture-mcp'], disabled: true, codemode: false } })], plugins: [control] });
    assert.equal(p.commands.length, 14); assert(p.commands.includes('codegraph-status') && p.commands.includes('codegraph-reindex')); assert(p.commands.includes('codegraph-benchmark'));
    server = await startOwnedServer(officialRuntime(path.join(os.homedir(), '.local/share/opencode-v2-clean')).binary, p, value => ({ ...generalEnvironment(value), OPENCODE_CODEGRAPH_ALLOW_TEMP: '1' }));
    const allow = [{ action: 'codegraph-project-write', resource: '*', effect: 'allow' }];
    const execute = async (kind, agent = 'master-dev', permissions = allow) => {
      const created = await server.request('POST', '/api/session', { agent, title: 'Synthetic lifecycle ' + kind, location: { directory: project }, model: { providerID: 'workshop-mock', id: 'mock' }, permissions }); assert.equal(created.status, 200);
      const id = created.value.data.id; await server.request('POST', '/api/session/' + id + '/prompt', { text: 'PROJECT_' + kind + '\nOnly the owned synthetic repository; do not operate any other index.' });
      if (kind === 'REJECT') {
        const permission = await until(async () => decodeList((await server.request('GET', '/api/session/' + id + '/permission')).value)[0], 'Index write permission');
        assert.equal(permission.action, 'codegraph-project-write');
        await server.request('POST', '/api/session/' + id + '/permission/' + permission.id + '/reply', { decision: 'reject', message: 'Synthetic explicit rejection; leave index untouched' });
      }
      await until(() => { if (providerError) throw new Error(providerError); return trace.get(kind)?.finished; }, kind, 30000);
      return trace.get(kind).results.join('\n');
    };
    const currentCalls = () => fs.existsSync(calls) ? fs.readFileSync(calls, 'utf8').trim().split('\n').map(JSON.parse) : [];
    assert((await execute('STATUS', 'code-inspector')).includes('"initialized":false')); assert(!fs.existsSync(registry));
    const before = currentCalls().length; assert((await execute('RO_BYPASS', 'code-inspector')).includes('Read-only actor')); assert.equal(currentCalls().length, before);
    assert((await execute('REJECT', 'master-dev', [])).includes('rejected')); assert(!fs.existsSync(path.join(project, '.codegraph')));
    assert((await execute('INIT')).includes('"registryUpdated":true')); assert(fs.existsSync(registry));
    assert((await execute('SYNC')).includes('"initialized":true'));
    const beforeConfirm = currentCalls().length; assert((await execute('REINDEX_NO_CONFIRM')).includes('confirmation')); assert.equal(currentCalls().length, beforeConfirm);
    assert((await execute('REINDEX')).includes('"initialized":true'));
    const commandSession = await server.request('POST', '/api/session', { agent: 'master-dev', title: 'Synthetic slash command', location: { directory: project }, model: { providerID: 'workshop-mock', id: 'mock' } });
    const commandResult = await server.request('POST', '/api/session/' + commandSession.value.data.id + '/command', { name: 'codegraph-status', text: project }); assert(commandResult.status >= 200 && commandResult.status < 300);
    await until(() => { if (providerError) throw new Error(providerError); return trace.get('COMMAND_STATUS')?.finished; }, 'Native status command route');
    assert(trace.get('COMMAND_STATUS').inspector, 'Status command must route to native read-only inspector');
    fs.mkdirSync(path.join(project, 'sub')); assert((await execute('SUBDIR')).includes('exact Git/worktree root'));
    const script = path.join(p.config, 'opencode/scripts/codegraph_project_v2.py'), bytes = fs.readFileSync(script); fs.appendFileSync(script, '\n# Unknown fixture edit\n');
    const beforeTamper = currentCalls().length; assert((await execute('TAMPER')).includes('Trusted CodeGraph maintenance asset changed')); assert.equal(currentCalls().length, beforeTamper); fs.writeFileSync(script, bytes);
    assert(currentCalls().every(row => !row.secret)); assert.equal(currentCalls().filter(row => row.action === 'init').length, 1); assert.equal(currentCalls().filter(row => row.action === 'sync').length, 1); assert.equal(currentCalls().filter(row => row.action === 'index').length, 1);
    assert.equal(fs.readFileSync(path.join(project, 'fixture.py'), 'utf8'), 'def public_fixture():\n    return 1\n');
  } finally { await server?.close(); model.closeAllConnections(); await new Promise(resolve => model.close(resolve)); }
});
