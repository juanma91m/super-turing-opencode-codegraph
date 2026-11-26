// Public pin contract only: synthetic session, no benchmark A/B or original DB.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import { test } from 'node:test';
import { prepareGeneral, generalEnvironment } from '../../../opencode-stack/v2/general/profile.mjs';
import { npmRuntime } from '../../../opencode-stack/v2/general/npm-runtime.mjs';
import { startOwnedServer, until } from '../../../opencode-stack/v2/general/owned-server.mjs';

test('native stored assistant history paginates; stats aggregate and public usage has no reported total/projection', async t => {
  const root = fs.mkdtempSync('/tmp/opencode/codegraph-telemetry-contract-'); t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const project = path.join(root, 'project'), control = path.join(root, 'control'); fs.mkdirSync(project); fs.mkdirSync(control);
  fs.writeFileSync(path.join(project, 'fixture.txt'), 'SYNTHETIC_TOOL_BODY_NOT_METRICS\n');
  fs.writeFileSync(path.join(control, 'package.json'), '{"type":"module"}');
  fs.writeFileSync(path.join(control, 'index.ts'), 'import {Plugin} from "@opencode/plugin";export default Plugin.define({id:"fixture.telemetry-contract",async setup(ctx){await ctx.session.hook("title",e=>{e.result="Telemetry fixture"})}});');
  let requests = 0, error;
  const mock = http.createServer(async (request, response) => {
    try {
      let raw = ''; for await (const chunk of request) { raw += chunk; assert(raw.length < 8 * 1024 * 1024); } const body = JSON.parse(raw); requests++;
      const tool = !body.messages.some(message => message.role === 'tool');
      response.writeHead(200, { 'Content-Type': 'text/event-stream' });
      const send = (delta, finish_reason = null, usage) => response.write('data: ' + JSON.stringify({ id: 'telemetry-fixture', object: 'chat.completion.chunk', created: 1, model: 'mock', choices: [{ index: 0, delta, finish_reason }], ...(usage ? { usage } : {}) }) + '\n\n');
      send(tool ? { role: 'assistant', tool_calls: [{ index: 0, id: 'read_fixture', type: 'function', function: { name: 'read', arguments: JSON.stringify({ path: 'fixture.txt' }) } }] } : { role: 'assistant', content: 'SYNTHETIC_ASSISTANT_BODY_NOT_METRICS' });
      // Deliberately non-derivable fixture total: prove it is not preserved in
      // public TokenUsage, instead of silently relabeling a component sum.
      send({}, tool ? 'tool_calls' : 'stop', { prompt_tokens: 101, completion_tokens: 17, total_tokens: 999, prompt_tokens_details: { cached_tokens: 11 }, completion_tokens_details: { reasoning_tokens: 3 } });
      response.end('data: [DONE]\n\n');
    } catch { error = 'Synthetic telemetry provider failed; content suppressed'; response.writeHead(500); response.end('Fixture failure'); }
  });
  await new Promise(resolve => mock.listen(0, '127.0.0.1', resolve)); let server;
  try {
    const p = prepareGeneral(path.join(root, 'profile'), { project, mock: 'http://127.0.0.1:' + mock.address().port + '/v1', plugins: [control] });
    server = await startOwnedServer(npmRuntime(path.join(os.homedir(), '.local/share/opencode-v2-clean')).binary, p, generalEnvironment);
    const spec = (await server.request('GET', '/openapi.json')).value;
    const messages = spec.paths['/api/session/{sessionID}/message'].get;
    assert.equal(messages.operationId, 'session.message.list');
    const parameters = messages.parameters.map(value => value.name); assert(parameters.includes('type') && parameters.includes('cursor'));
    assert(!parameters.some(value => /fields|projection|content|metadataOnly/i.test(value)), 'Public projection contract changed; reassess privacy adapter');
    const statsParameters = spec.paths['/api/experimental/session/stats'].get.parameters.map(value => value.name);
    assert(!statsParameters.includes('sessionID'), 'If per-session stats is added, prefer that projection');
    assert(!Object.hasOwn(spec.components.schemas['TokenUsage.Info'].properties, 'total'));
    const created = await server.request('POST', '/api/session', { agent: 'master-dev', title: 'Synthetic telemetry only', location: { directory: project }, model: { providerID: 'workshop-mock', id: 'mock' } }); assert.equal(created.status, 200); const id = created.value.data.id;
    await server.request('POST', '/api/session/' + id + '/prompt', { text: 'SYNTHETIC_USER_BODY_NOT_METRICS. Read fixture.txt once and reply briefly.' });
    await until(async () => { if (error) throw new Error(error); const response = await server.request('GET', '/api/session/' + id + '/context'); return requests >= 2 && response.value?.data?.at(-1)?.type === 'idle'; }, 'Synthetic telemetry completion');
    const before = (await server.request('GET', '/api/session/' + id)).value.data;
    assert(!Object.hasOwn(before.tokens, 'total'));
    const rows = [], visited = new Set(); let cursor;
    for (let page = 0; page < 10; page++) {
      const query = new URLSearchParams({ type: 'assistant', limit: '1', ...(cursor ? { cursor } : { order: 'asc' }) });
      const response = await server.request('GET', '/api/session/' + id + '/message?' + query); assert.equal(response.status, 200);
      assert(Array.isArray(response.value.data) && response.value.cursor);
      for (const item of response.value.data) { assert.equal(item.type, 'assistant'); assert(!visited.has(item.id)); visited.add(item.id); rows.push(item); }
      if (!response.value.cursor.next) break;
      assert.notEqual(response.value.cursor.next, cursor); cursor = response.value.cursor.next;
    }
    assert.equal(rows.length, 2); assert(rows.every(row => row.tokens && !Object.hasOwn(row.tokens, 'total')));
    assert(rows.every(row => row.tokens.input === 90 && row.tokens.output === 14 && row.tokens.reasoning === 3 && row.tokens.cache.read === 11 && row.tokens.cache.write === 0), 'Pinned normalized partitions must stay exclusive; reassess derived metric if parser changes');
    assert(rows.some(row => row.content.some(content => content.type === 'tool' && JSON.stringify(content.state).includes('SYNTHETIC_TOOL_BODY_NOT_METRICS'))), 'Assistant history response contains full tool bodies: not a server-side metadata projection');
    const stats = await server.request('GET', '/api/experimental/session/stats?tools=detail'); assert.equal(stats.status, 200);
    assert.equal(stats.value.data.tools.mode, 'detail'); assert(stats.value.data.tools.usage.some(tool => tool.name === 'read' && tool.calls === 1)); assert(!Object.hasOwn(stats.value.data.tokens, 'total'));
    assert(!JSON.stringify(stats.value).includes('SYNTHETIC_TOOL_BODY_NOT_METRICS')); assert(!JSON.stringify(stats.value).includes('SYNTHETIC_USER_BODY_NOT_METRICS'));
    console.log(JSON.stringify({ publicAssistantPaginationVerified: true, assistantPages: rows.length, assistantBodiesReturnedByAPI: true, publicReportedTotalAvailable: false, aggregateToolStatsAvailable: true, realModelRequests: 0, originalStoreOpened: false }));
  } finally { await server?.close(); mock.closeAllConnections(); await new Promise(resolve => mock.close(resolve)); }
});
