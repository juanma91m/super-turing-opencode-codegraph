import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { test } from 'node:test';
import { codegraphContribution } from '../general.mjs';
import { prepareGeneral } from '../../../opencode-stack/v2/general/profile.mjs';
import { projectMessage, collectFamily as collect, executeBenchmark as execute, MEASUREMENT } from '../plugins/access/benchmark.mjs';
const collectFamily = (ctx, root, operator, ask, signal, boundary) => collect(ctx, root, operator, ask, signal, boundary, ctx.session.message);
const executeBenchmark = (ctx, input, context) => execute(ctx, input, context, ctx.session.message);

const usage = { input: 90, output: 14, reasoning: 3, cache: { read: 11, write: 0 } };
function session(id, directory, parentID) { return { id, parentID, title: 'PRIVATE_TITLE_NEVER_METRICS', metadata: { text: 'PRIVATE_METADATA' }, location: { directory }, time: { created: 1000, updated: 9000, busy: 1000, idle: 9000 }, model: { providerID: 'fixture', id: 'model' } }; }
function assistant(id, tool = 'read', created = 2000, tokens = usage) {
  return { id, type: 'assistant', agent: 'master-dev', model: { providerID: 'fixture', id: 'model', variant: 'medium' }, time: { created, completed: created + 100 }, tokens,
    metadata: { text: 'PRIVATE_METADATA' }, native: { text: 'PRIVATE_NATIVE' }, content: [{ type: 'text', text: 'PRIVATE_ASSISTANT_BODY' }, { type: 'reasoning', text: 'PRIVATE_REASONING' }, { type: 'tool', id: 'tool_' + id, name: tool, time: { created, ran: created + 10, completed: created + 50 }, state: { status: 'completed', input: { password: 'PRIVATE_ARGUMENTS' }, output: [{ type: 'text', text: 'PRIVATE_OUTPUT' }] } }] };
}
function fake(directory) {
  const sessions = new Map([['ses_root', session('ses_root', directory)], ['ses_child', session('ses_child', directory, 'ses_root')], ['ses_operator', session('ses_operator', directory)]]);
  const messages = new Map([['ses_root', [{ id: 'msg_user', type: 'user', time: { created: 1000 }, text: 'PRIVATE_USER_PROMPT' }, assistant('msg_a', 'codegraph_codegraph_explore'), assistant('msg_b', 'read', 3000)]], ['ses_child', [assistant('msg_c', 'grep', 2500)]], ['ses_operator', []]]);
  const page = (items, input) => { const start = Number(input.cursor ?? 0), selected = items.slice(start, start + 1); return { data: structuredClone(selected), cursor: { next: start + 1 < items.length ? String(start + 1) : null } }; };
  return { sessions, messages, api: { get: async ({ sessionID }) => structuredClone(sessions.get(sessionID)), list: async input => page([...sessions.values()].filter(row => input.parentID ? row.parentID === input.parentID : !input.directory || row.location.directory === input.directory), input),
    message: { get: async ({ sessionID, messageID }) => ({ data: structuredClone(messages.get(sessionID).find(row => row.id === messageID)) }), list: async input => page(messages.get(input.sessionID).filter(row => !input.type || row.type === input.type), input) } } };
}
function fixture(t) {
  const root = fs.mkdtempSync('/tmp/opencode/graph-benchmark-'); t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const directory = path.join(root, 'project'), home = path.join(root, 'runtime-home'); fs.mkdirSync(directory); fs.mkdirSync(home);
  const p = prepareGeneral(path.join(root, 'profile'), { project: directory, mock: 'http://127.0.0.1:1/v1', contributions: [codegraphContribution({ binding: { runtime_home: home, runtime_bin: '/fixture/not-started' }, serverVersion: '1.6.4', server: { type: 'local', command: ['/fixture/not-started'], disabled: true, codemode: false } })] });
  const options = p.document.plugins.find(plugin => typeof plugin === 'object' && plugin.package.endsWith('/codegraph/v2/plugins/access')).options;
  const data = fake(directory), permissions = [];
  const ctx = { app: { version: '2.4.1' }, options, location: { directory }, session: data.api, permission: { assert: async value => { permissions.push(value); } } };
  const context = { agent: 'code-inspector', sessionID: 'ses_operator', messageID: 'msg_operator', id: 'tool_capture' };
  return { root, directory, home, p, data, ctx, context, permissions };
}
const capture = { action: 'capture', sessionID: 'ses_root', variant: 'with-codegraph', pairID: 'pair1', project: 'fixture', taskKind: 'review', policyVersion: 'policy1', dedicatedTask: true, outcome: 'accepted', utility: 'yes', correctionsRequired: 0 };

test('projection never transports bodies/native/arguments/titles and preserves exclusive usage accounting', async t => {
  const f = fixture(t), raw = assistant('msg_a');
  const projected = projectMessage(raw, 'ses_root'); assert.equal(projected.info.tokens.total, 118); assert.equal(projected.info.tokens.output, 14); assert.equal(projected.info.tokens.reasoning, 3);
  assert(!JSON.stringify(projected).includes('PRIVATE')); assert.equal(projected.parts[0].state.output_bytes, Buffer.byteLength(JSON.stringify(raw.content[2].state.output)));
  const selected = await collectFamily(f.ctx, 'ses_root', 'ses_operator', async () => {}, undefined);
  assert.equal(selected.projected.length, 3); assert.equal(selected.catalog.length, 2); assert(!JSON.stringify(selected).includes('PRIVATE'));
});
test('capture/report/history work without SQL, count child once, classify diagnostics outside search and report truthful native paired savings', async t => {
  const f = fixture(t); f.data.messages.get('ses_child').push(assistant('msg_diag', 'codegraph-project', 2600));
  const withGraph = await executeBenchmark(f.ctx, capture, f.context); assert.equal(withGraph.metrics.tokens.total, 472); assert.equal(withGraph.metrics.tokens.reported_total, null); assert.equal(withGraph.metrics.search.codegraph.calls, 1);
  assert.deepEqual(withGraph.captureRuntime, { codegraph_version: '1.6.4', opencode_version: '2.4.1' });
  assert.equal(withGraph.historicalRuntimeVerified, false);
  assert.equal(withGraph.metrics.search.manual.calls, 2); assert.equal(withGraph.metrics.tools.count, 4);
  f.data.sessions.set('ses_control', session('ses_control', f.directory)); f.data.messages.set('ses_control', [assistant('msg_control', 'read', 2000, { ...usage, input: 990 })]);
  await executeBenchmark(f.ctx, { ...capture, sessionID: 'ses_control', variant: 'without-codegraph' }, f.context);
  const report = await executeBenchmark(f.ctx, { action: 'report' }, f.context); assert.equal(report.complete_accepted_pairs, 1); assert.equal(report.measurement.tokens, MEASUREMENT.tokens);
  const improvement = report.aggregate.total_tokens.paired_improvement_pct_median; assert(improvement > 0 && improvement < 100);
  const text = await executeBenchmark(f.ctx, { action: 'report', format: 'markdown' }, f.context); assert(text.includes('SUMA') || text.includes('suma')); assert(text.includes('NO total reportado'));
  const history = await executeBenchmark(f.ctx, { action: 'history', since: '1970-01-01T00:00:01Z', until: '1970-01-01T00:00:04Z' }, f.context);
  assert.equal(history.families, 2); assert.equal(history.causalSavings, false); assert.equal(history.methodology.operatorExcluded, true); assert(!JSON.stringify(history).includes('ses_'));
  const store = path.join(f.ctx.options.benchmark.directory, 'runs'); const files = fs.readdirSync(store); assert.equal(files.length, 2);
  for (const file of files) { const data = fs.readFileSync(path.join(store, file), 'utf8'); assert(!data.includes('PRIVATE')); assert(!data.includes(f.directory)); assert.equal(fs.statSync(path.join(store, file)).mode & 0o777, 0o600); }
  f.ctx.app.version = '2.5.0';
  await executeBenchmark(f.ctx, { ...capture, sessionID: 'ses_control', variant: 'without-codegraph' }, f.context);
  assert((await executeBenchmark(f.ctx, { action: 'report' }, f.context)).excluded_pairs.some(pair => /bindings distintos/.test(pair.reason)));
  const recaptured = await executeBenchmark(f.ctx, { ...capture, outcome: 'incorrect', utility: 'no', correctionsRequired: 2 }, f.context);
  assert.equal(recaptured.evaluation.utility, 'no'); assert.equal(fs.readdirSync(store).length, 2);
  const revisedReport = await executeBenchmark(f.ctx, { action: 'report' }, f.context); assert.equal(revisedReport.complete_accepted_pairs, 0);
});
test('operator contamination, fork, active/mutating sessions, bad ranges and missing evaluation fail closed', async t => {
  const f = fixture(t);
  await assert.rejects(() => collectFamily(f.ctx, 'ses_root', 'ses_child', async () => {}), /operator/);
  await assert.rejects(() => executeBenchmark(f.ctx, { ...capture, dedicatedTask: undefined }, f.context), /dedicated/);
  await assert.rejects(() => executeBenchmark(f.ctx, { ...capture, policyVersion: '<private>bad</private>' }, f.context), /public metadata/);
  await assert.rejects(() => executeBenchmark(f.ctx, { ...capture, variant: 'without-codegraph' }, f.context), /Variant/);
  f.data.sessions.get('ses_child').fork = { sessionID: 'ses_root' }; await assert.rejects(() => collectFamily(f.ctx, 'ses_root', 'ses_operator', async () => {}), /forked/); delete f.data.sessions.get('ses_child').fork;
  const original = f.data.api.get; let gets = 0; f.data.api.get = async input => { const result = await original(input); if (++gets >= 3) result.time.updated++; return result; };
  await assert.rejects(() => collectFamily(f.ctx, 'ses_root', 'ses_operator', async () => {}), /changed/);
});
test('exact message order scopes main events and child temporal window; missing usage is n/a, not zero', async t => {
  const f = fixture(t);
  const result = await executeBenchmark(f.ctx, { ...capture, dedicatedTask: undefined, fromMessage: 'msg_user', toMessage: 'msg_a' }, f.context); assert.equal(result.metrics.tokens.total, 118); assert.equal(result.metrics.search.codegraph.calls, 1); assert.equal(result.scope.boundary_kind, 'message-range');
  f.data.messages.set('ses_missing', [assistant('msg_missing', 'read', 2000, undefined)]); f.data.messages.get('ses_missing')[0].tokens = undefined; f.data.sessions.set('ses_missing', session('ses_missing', f.directory));
  const missing = await executeBenchmark(f.ctx, { ...capture, sessionID: 'ses_missing', pairID: 'missing', variant: 'without-codegraph', outcome: 'pending' }, f.context); assert.equal(missing.metrics.tokens.total, null);
  await assert.rejects(() => executeBenchmark(f.ctx, { ...capture, dedicatedTask: undefined, fromMessage: 'msg_b', toMessage: 'msg_user' }, f.context), /Reversed|reversed/);
});
test('unauthorized actors, rejected permission and tampered arithmetic cannot read/persist measurements', async t => {
  const f = fixture(t);
  await assert.rejects(() => executeBenchmark(f.ctx, capture, { ...f.context, agent: 'visual-qa' }), /actor/);
  f.ctx.permission.assert = async () => { throw new Error('Synthetic permission rejected'); };
  await assert.rejects(() => executeBenchmark(f.ctx, capture, f.context), /rejected/); assert(!fs.existsSync(f.ctx.options.benchmark.directory));
  f.ctx.permission.assert = async () => {};
  const script = f.ctx.options.benchmark.script; fs.appendFileSync(script, '\n# Unknown edit\n'); await assert.rejects(() => executeBenchmark(f.ctx, capture, f.context), /Trusted native benchmark/);
});
test('history skips empty roots, missing counters stay null and descendants require their own read authorization', async t => {
  const f = fixture(t); f.data.sessions.set('ses_empty', session('ses_empty', f.directory)); f.data.messages.set('ses_empty', []);
  const result = await executeBenchmark(f.ctx, { action: 'history', since: '1970-01-01', until: '1970-01-02' }, f.context); assert.equal(result.families, 1);
  assert(f.permissions.some(row => row.action === 'codegraph-benchmark-read' && row.resources.includes('session:ses_child')));
  f.ctx.permission.assert = async row => { if (row.resources.includes('session:ses_child')) throw new Error('Child read rejected'); };
  await assert.rejects(() => executeBenchmark(f.ctx, capture, f.context), /Child read rejected/); assert(!fs.existsSync(f.ctx.options.benchmark.directory));
  f.data.sessions.get('ses_root').revert = { messageID: 'msg_b' };
  await assert.rejects(() => collectFamily(f.ctx, 'ses_root', 'ses_operator', async () => {}), /reverted/);
});
test('metadata store refuses unsafe records while recapture atomically updates the same identity as V1', async t => {
  const f = fixture(t); await executeBenchmark(f.ctx, capture, f.context);
  const folder = path.join(f.ctx.options.benchmark.directory, 'runs'), file = path.join(folder, fs.readdirSync(folder)[0]), original = fs.readFileSync(file);
  await executeBenchmark(f.ctx, { ...capture, outcome: 'incorrect' }, f.context); assert.equal(JSON.parse(fs.readFileSync(file)).outcome, 'incorrect'); assert.equal(fs.readdirSync(folder).length, 1);
  fs.writeFileSync(file, original);
  assert(!fs.readdirSync(f.ctx.options.benchmark.directory).some(name => name.startsWith('.capture-')));
  for (const mutate of [row => { row.schema_version = 2; }, row => { row.measurement.tokens = 'v1-reported-total'; }, row => { row.metrics.payload = 'PRIVATE_HIDDEN_BODY'; }, row => { row.metrics.tools.by_name.read = 'PRIVATE_HIDDEN_BODY'; }, row => { row.scope.linked_sessions = ['PRIVATE_BODY']; }]) {
    const row = JSON.parse(original); mutate(row); fs.writeFileSync(file, JSON.stringify(row)); await assert.rejects(() => executeBenchmark(f.ctx, { action: 'report' }, f.context), /Unknown|Unreviewed|numeric|array/);
  }
  fs.writeFileSync(file, original); fs.chmodSync(file, 0o644); await assert.rejects(() => executeBenchmark(f.ctx, { action: 'report' }, f.context), /Unsafe/); fs.chmodSync(file, 0o600);
  const outside = path.join(f.root, 'hardlink.json'); fs.linkSync(file, outside); await assert.rejects(() => executeBenchmark(f.ctx, { action: 'report' }, f.context), /Unsafe/); fs.unlinkSync(outside);
  fs.renameSync(file, outside); fs.symlinkSync(outside, file); await assert.rejects(() => executeBenchmark(f.ctx, { action: 'report' }, f.context), /symlink/); fs.unlinkSync(file); fs.renameSync(outside, file);
  const report = await executeBenchmark(f.ctx, { action: 'report' }, f.context); assert.equal(report.runs_total, 1);
});
test('pagination duplicates and new descendants fail closed rather than returning partial usage', async t => {
  const f = fixture(t), list = f.data.api.message.list; let calls = 0;
  f.data.api.message.list = async input => { const result = await list(input); if (input.type === 'assistant' && ++calls === 2) result.data[0].id = 'msg_a'; return result; };
  await assert.rejects(() => collectFamily(f.ctx, 'ses_root', 'ses_operator', async () => {}), /coverage/);
  f.data.api.message.list = list; const original = f.data.api.list; let reads = 0;
  f.data.api.list = async input => { const result = await original(input); if (input.parentID === 'ses_root' && ++reads >= 2) result.data.push({ ...session('ses_new', f.directory, 'ses_root') }); return result; };
  await assert.rejects(() => collectFamily(f.ctx, 'ses_root', 'ses_operator', async () => {}), /descendant/);
});
test('a change while capture approval is pending cannot publish stale measured counters', async t => {
  const f = fixture(t);
  f.ctx.permission.assert = async row => { if (row.action === 'codegraph-benchmark-capture') f.data.sessions.get('ses_child').time.updated++; };
  await assert.rejects(() => executeBenchmark(f.ctx, capture, f.context), /changed/);
  assert(!fs.existsSync(f.ctx.options.benchmark.directory));
});
test('arithmetic imports only isolated stdlib and the pinned math asset, never cwd/adjacent shadow modules', async t => {
  const f = fixture(t), scripts = path.dirname(f.ctx.options.benchmark.script);
  for (const directory of [scripts, f.directory]) fs.writeFileSync(path.join(directory, 'json.py'), 'raise RuntimeError("PRIVATE_SHADOW_MODULE_MUST_NOT_EXECUTE")\n');
  const captured = await executeBenchmark(f.ctx, capture, f.context); assert.equal(captured.metrics.tokens.total, 354);
});
