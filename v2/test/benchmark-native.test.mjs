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

const unpack = value => { if (typeof value === 'string') { try { return unpack(JSON.parse(value)); } catch { return value; } } if (Array.isArray(value)) return unpack(value[0]); if (value?.text !== undefined) return unpack(value.text); if (value?.content !== undefined && !value.error) return unpack(value.content); return value; };
test('official native capture/report/history use stored public pages and persist metadata only, without extra inference or raw body transport', async t => {
  const root = fs.mkdtempSync('/tmp/opencode/benchmark-native-'); t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const project = path.join(root, 'project'), home = path.join(root, 'runtime-home'), control = path.join(root, 'control'); fs.mkdirSync(project); fs.mkdirSync(home); fs.mkdirSync(control); fs.mkdirSync(path.join(project, '.codegraph'));
  fs.writeFileSync(path.join(project, 'fixture.txt'), 'MEASURED_BODY_MUST_NOT_LEAVE_PROJECTION\n');
  assert.equal(spawnSync('/usr/bin/git', ['init', '--quiet'], { cwd: project, env: { PATH: '/usr/bin:/bin', HOME: root, GIT_CONFIG_GLOBAL: '/dev/null', GIT_CONFIG_NOSYSTEM: '1' } }).status, 0);
  fs.writeFileSync(path.join(control, 'package.json'), '{"type":"module"}'); fs.writeFileSync(path.join(control, 'index.ts'), 'import {Plugin} from "@opencode/plugin";export default Plugin.define({id:"fixture.benchmark",async setup(ctx){await ctx.session.hook("title",e=>{e.result="Benchmark fixture"});await ctx.session.hook("compaction",e=>{e.result={summary:"PRIVATE_COMPACTION_SUMMARY",tokens:{input:5,output:2,reasoning:0,cache:{read:0,write:0}}}})}});');
  const trace = new Map(), measured = {}, operations = new Map(); let providerError, server, requestCount = 0;
  const mock = http.createServer(async (request, response) => {
    try {
      let raw = ''; for await (const chunk of request) raw += chunk;
      const body = JSON.parse(raw), kind = JSON.stringify(body.messages.filter(row => row.role === 'user').at(-1)).match(/BCASE_([A-Z_]+)/)?.[1]; assert(kind); requestCount++;
      const outputs = body.messages.filter(row => row.role === 'tool' && row.tool_call_id?.startsWith(kind + '_'));
      let call;
      if (kind === 'WITH' && outputs.length === 0) call = ['codegraph_codegraph_explore', { projectPath: project, query: 'Synthetic relationship only' }];
      else if ((kind === 'WITH' && outputs.length === 1) || kind === 'WITHOUT' && !outputs.length) call = ['read', { path: 'fixture.txt' }];
      else if (kind.startsWith('OP_') && !outputs.length) {
        const input = operations.get(kind) ?? (kind === 'OP_REPORT' ? { action: 'report' } : kind === 'OP_HISTORY' ? { action: 'history', since: '2026-01-01', until: '2027-12-31' } : { action: 'capture', sessionID: measured[kind === 'OP_WITH' ? 'WITH' : 'WITHOUT'], variant: kind === 'OP_WITH' ? 'with-codegraph' : 'without-codegraph', pairID: 'native-pair', project: 'fixture', taskKind: 'review', policyVersion: 'same-policy', dedicatedTask: true, outcome: 'accepted', utility: kind === 'OP_WITH' ? 'yes' : 'not-applicable', correctionsRequired: 0 });
        call = ['codegraph-benchmark', input];
      }
      if (kind.startsWith('OP_')) for (const result of outputs) assert(!/MEASURED_BODY_MUST_NOT_LEAVE_PROJECTION|PRIVATE_COMPACTION_SUMMARY/.test(JSON.stringify(result.content)), 'Raw measured output reached benchmark operator model');
      trace.set(kind, { finished: !call, outputs: outputs.map(row => unpack(row.content)) });
      response.writeHead(200, { 'Content-Type': 'text/event-stream' });
      const emit = (delta, finish_reason = null, usage) => response.write('data: ' + JSON.stringify({ id: 'benchmark-native', object: 'chat.completion.chunk', created: 1, model: 'mock', choices: [{ index: 0, delta, finish_reason }], ...(usage ? { usage } : {}) }) + '\n\n');
      emit(call ? { role: 'assistant', tool_calls: [{ index: 0, id: kind + '_' + outputs.length, type: 'function', function: { name: call[0], arguments: JSON.stringify(call[1]) } }] } : { role: 'assistant', content: 'FIXTURE_DONE' });
      emit({}, call ? 'tool_calls' : 'stop', { prompt_tokens: 101, completion_tokens: 17, total_tokens: 999, prompt_tokens_details: { cached_tokens: 11 }, completion_tokens_details: { reasoning_tokens: 3 } }); response.end('data: [DONE]\n\n');
    } catch { providerError = 'Native benchmark fixture provider failed; bodies suppressed'; response.writeHead(500); response.end('Fixture failure'); }
  });
  await new Promise(resolve => mock.listen(0, '127.0.0.1', resolve));
  try {
    const serverFixture = { type: 'local', command: [process.execPath, new URL('../../../opencode-stack/migrations/v2/fixtures/general-addon-mcp.mjs', import.meta.url).pathname], environment: { FIXTURE_TOOLS: '["codegraph_explore"]', FIXTURE_LOG: path.join(root, 'graph-calls.jsonl') }, codemode: false };
    const p = prepareGeneral(path.join(root, 'profile'), { project, mock: 'http://127.0.0.1:' + mock.address().port + '/v1', contributions: [codegraphContribution({ binding: { runtime_home: home, runtime_bin: '/fixture/not-used' }, server: serverFixture })], plugins: [control] });
    server = await startOwnedServer(officialRuntime(path.join(os.homedir(), '.local/share/opencode-v2-clean')).binary, p, generalEnvironment);
    const execute = async (kind, agent = 'master-dev', permissions = []) => {
      const created = await server.request('POST', '/api/session', { agent, title: 'Synthetic ' + kind, location: { directory: project }, model: { providerID: 'workshop-mock', id: 'mock' }, permissions }); assert.equal(created.status, 200); const id = created.value.data.id;
      if (!kind.startsWith('OP_')) measured[kind] = id;
      await server.request('POST', '/api/session/' + id + '/prompt', { text: 'BCASE_' + kind + '\nOnly synthetic fixture operation; no real benchmark/index/provider work.' });
      await until(async () => { if (providerError) throw new Error(providerError); const result = await server.request('GET', '/api/session/' + id + '/context'); return trace.get(kind)?.finished && result.value?.data?.at(-1)?.type === 'idle'; }, kind, 30000);
      return trace.get(kind).outputs;
    };
    await execute('WITH'); await execute('WITHOUT');
    const permissions = [{ action: 'codegraph-benchmark-read', resource: '*', effect: 'allow' }, { action: 'codegraph-benchmark-capture', resource: '*', effect: 'allow' }];
    const withRecord = (await execute('OP_WITH', 'code-inspector', permissions))[0]; assert(!withRecord.error, 'Native capture failed: ' + JSON.stringify(withRecord)); assert.equal(withRecord.status, 'captured'); assert.equal(withRecord.metrics.tokens.total, 354); assert.equal(withRecord.metrics.tokens.reported_total, null);
    const without = (await execute('OP_WITHOUT', 'code-inspector', permissions))[0]; assert.equal(without.metrics.tokens.total, 236);
    const report = (await execute('OP_REPORT', 'code-inspector', permissions))[0]; assert.equal(report.complete_accepted_pairs, 1); assert(report.aggregate.total_tokens.paired_improvement_pct_median < 0, 'Graph costs more in this fixture; report must not manufacture savings');
    const history = (await execute('OP_HISTORY', 'code-inspector', permissions))[0]; assert.equal(history.causalSavings, false); assert.equal(history.families, 2);
    assert.equal(requestCount, 13, 'Only measured/operator mock steps, no hidden inference from benchmark');
    const directory = path.join(home, '.local/state/super-turing-opencode-codegraph/benchmarks-v2/runs'); const files = fs.readdirSync(directory); assert.equal(files.length, 2);
    for (const name of files) { const value = fs.readFileSync(path.join(directory, name), 'utf8'); assert(!value.includes('MEASURED_BODY_MUST_NOT_LEAVE_PROJECTION')); assert(!value.includes(project)); assert(!value.includes('SYNTHETIC_USER_BODY')); }
    assert.equal(fs.readFileSync(path.join(root, 'graph-calls.jsonl'), 'utf8').trim().split('\n').length, 1, 'Benchmark must not rerun measured graph query');
    // A second user turn gives native compaction a non-tail window. The public
    // hook supplies deterministic metadata usage, not a real summarizer call.
    await server.request('POST', '/api/session/' + measured.WITH + '/prompt', { text: 'BCASE_EXTRA\nSynthetic second turn.' });
    await until(async () => trace.get('EXTRA')?.finished && (await server.request('GET', '/api/session/' + measured.WITH + '/context')).value.data.at(-1)?.type === 'idle', 'Second synthetic turn');
    assert.equal((await server.request('POST', '/api/session/' + measured.WITH + '/compact', {})).status, 200);
    await until(async () => (await server.request('GET', '/api/session/' + measured.WITH + '/message?type=compaction')).value.data.some(row => row.status === 'completed'), 'Stored native compaction');
    const captured = { action: 'capture', sessionID: measured.WITH, variant: 'with-codegraph', pairID: 'compacted', project: 'fixture', taskKind: 'review', policyVersion: 'same-policy', dedicatedTask: true, outcome: 'pending' };
    operations.set('OP_COMPACT', captured);
    const compacted = (await execute('OP_COMPACT', 'code-inspector', permissions))[0]; assert(!compacted.error, 'Compaction capture refused: ' + JSON.stringify(compacted)); assert.equal(compacted.metrics.tokens.total, 479); assert.equal(compacted.metrics.agents.compaction, 1); assert.equal(compacted.metrics.search.codegraph.calls, 1, 'Stored pre-compaction graph event retained exactly once');
    const forked = await server.request('POST', '/api/session/' + measured.WITH + '/fork', {}); assert.equal(forked.status, 200); assert(forked.value.data.fork); assert(!forked.value.data.parentID, 'Native fork provenance is distinct from subagent parentID');
    operations.set('OP_FORK', { ...captured, sessionID: forked.value.data.id, pairID: 'forked' });
    const fork = (await execute('OP_FORK', 'code-inspector', permissions))[0]; assert(fork.error && /forked/.test(fork.error.message), 'Copied fork history must not be counted as fresh spend');
    operations.set('OP_PARENT', { ...captured, pairID: 'parent-with-fork' });
    const parent = (await execute('OP_PARENT', 'code-inspector', permissions))[0]; assert(!parent.error); assert.equal(parent.metrics.tokens.total, 479, 'Source family must not absorb copied fork history');
    const boundary = (await server.request('GET', '/api/session/' + measured.WITHOUT + '/message?type=user&order=asc')).value.data[0].id;
    assert.equal((await server.request('POST', '/api/session/' + measured.WITHOUT + '/revert/stage', { messageID: boundary, files: false })).status, 200);
    operations.set('OP_REVERT', { ...captured, sessionID: measured.WITHOUT, variant: 'without-codegraph', pairID: 'reverted' });
    const reverted = (await execute('OP_REVERT', 'code-inspector', permissions))[0]; assert(reverted.error && /reverted/.test(reverted.error.message));
    assert.equal((await server.request('DELETE', '/api/session/' + measured.WITHOUT + '/revert')).status, 204);
    operations.set('OP_DENIED', { ...captured, sessionID: measured.WITHOUT, variant: 'without-codegraph', pairID: 'denied' });
    const denied = (await execute('OP_DENIED', 'code-inspector', [{ action: 'codegraph-benchmark-read', resource: '*', effect: 'deny' }]))[0]; assert(denied.error, 'Session deny must block history read/capture');
    assert.equal(fs.readdirSync(directory).length, 4, 'Fork/revert/denied reads create no records');
    const child = await server.request('POST', '/api/session', { agent: 'master-dev', parentID: measured.WITHOUT, title: 'Synthetic linked child', location: { directory: project }, model: { providerID: 'workshop-mock', id: 'mock' } }); assert.equal(child.status, 200); assert.equal(child.value.data.parentID, measured.WITHOUT);
    await server.request('POST', '/api/session/' + child.value.data.id + '/prompt', { text: 'BCASE_CHILD\nSynthetic linked work.' });
    await until(async () => trace.get('CHILD')?.finished && (await server.request('GET', '/api/session/' + child.value.data.id + '/context')).value.data.at(-1)?.type === 'idle', 'Linked synthetic child');
    operations.set('OP_CHILD', { ...captured, sessionID: measured.WITHOUT, variant: 'without-codegraph', pairID: 'linked-child' });
    const family = (await execute('OP_CHILD', 'code-inspector', permissions))[0]; assert(!family.error); assert.equal(family.metrics.tokens.total, 354); assert.equal(family.scope.linked_sessions.length, 2);
    const end = (await server.request('GET', '/api/session/' + measured.WITHOUT + '/message?type=assistant&order=asc')).value.data[0].id;
    operations.set('OP_RANGE', { ...captured, sessionID: measured.WITHOUT, variant: 'without-codegraph', pairID: 'native-range', dedicatedTask: undefined, fromMessage: boundary, toMessage: end });
    const range = (await execute('OP_RANGE', 'code-inspector', permissions))[0]; assert(!range.error, JSON.stringify(range)); assert.equal(range.metrics.tokens.total, 118); assert.equal(range.metrics.search.manual.calls, 1, 'Native exact range clips later child work');
    await server.request('POST', '/api/session', { title: 'Synthetic empty root', location: { directory: project }, model: { providerID: 'workshop-mock', id: 'mock' } });
    operations.set('OP_FINAL_HISTORY', { action: 'history', since: '2026-01-01', until: '2027-12-31' });
    const finalHistory = (await execute('OP_FINAL_HISTORY', 'code-inspector', permissions))[0]; assert(!finalHistory.error); assert.equal(finalHistory.families, 2); assert(finalHistory.excluded.some(row => row.reason === 'active-forked-or-reverted-family'));
    operations.set('OP_FINAL_REPORT', { action: 'report' });
    const frozen = (await execute('OP_FINAL_REPORT', 'code-inspector', permissions))[0]; assert.equal(frozen.complete_accepted_pairs, 1); assert.equal(frozen.pairs[0].values.total_tokens.with_codegraph, 354); assert.equal(frozen.pairs[0].values.total_tokens.without_codegraph, 236, 'Later source changes do not silently rewrite capture counters');
    assert.equal(requestCount, 33, 'Only explicit synthetic task/operator turns, no hidden benchmark inference');
    for (const name of fs.readdirSync(directory)) assert(!/PRIVATE_COMPACTION_SUMMARY|MEASURED_BODY_MUST_NOT_LEAVE_PROJECTION/.test(fs.readFileSync(path.join(directory, name), 'utf8')));
  } finally { await server?.close(); mock.closeAllConnections(); await new Promise(resolve => mock.close(resolve)); }
});
