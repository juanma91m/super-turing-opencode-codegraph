import assert from 'node:assert/strict';
import http from 'node:http';
import { spawn } from 'node:child_process';
import { test } from 'node:test';

test('owned public-history transport rejects foreign hosts/identities, HTTP errors and redirects without secret/body output', async () => {
  let mode = 'ok', requests = 0;
  const host = http.createServer((request, response) => {
    requests++; assert.equal(request.url, '/api/session/ses_fixture/message?type=assistant&limit=1');
    assert.equal(request.headers.authorization, 'Basic ' + Buffer.from('opencode:fixture-private-token-only').toString('base64'));
    if (mode === 'redirect') { response.writeHead(302, { Location: 'http://outside.invalid/PRIVATE_BODY' }); response.end(); return; }
    response.writeHead(mode === 'error' ? 500 : 200, { 'Content-Type': 'application/json' });
    response.end(mode === 'error' ? 'PRIVATE_BODY_WITH_CREDENTIAL' : '{"data":[],"cursor":{"next":null}}');
  });
  await new Promise(resolve => host.listen(0, '127.0.0.1', resolve));
  const url = 'http://127.0.0.1:' + host.address().port;
  const invoke = async (kind, changes = {}) => {
    const script = 'import {nativeMessages} from ' + JSON.stringify(new URL('../plugins/access/native-messages.mjs', import.meta.url).href) + ';try{const input={sessionID:"ses_fixture",type:"assistant",limit:1};const value=await nativeMessages().list(input);' + (kind==='bundled-clone' ? 'const shared=Object.getOwnPropertyDescriptor(globalThis,Symbol.for("opencode-stack.owned-stored-history.v1"));if(typeof shared?.value!=="function"||shared.enumerable||shared.writable||Object.keys(shared.value).length)throw new Error("Unexpected shared service");const clone=await import('+JSON.stringify(new URL('../../../opencode-stack/v2/native-history.mjs?isolated-bundle',import.meta.url).href)+');await clone.nativeMessages().list(input);' : '') + 'console.log(JSON.stringify({ok:true,count:value.data.length}))}catch{console.log(JSON.stringify({ok:false,error:"transport-refused"}))}';
    const child = spawn(process.execPath, ['--input-type=module', '-e', script], { env: { PATH: '/usr/bin:/bin', ...(kind === 'missing' ? {} : { OPENCODE_STACK_TRANSPORT_FD: '3' }) }, stdio: ['ignore', 'pipe', 'ignore', 'pipe'] });
    child.stdio[3].on('error', () => {}); child.stdio[3].end(JSON.stringify({ version: 1, pid: child.pid, url, password: 'fixture-private-token-only', ...changes }));
    let output = ''; child.stdout.on('data', bytes => { output += bytes; });
    assert.equal(await new Promise(resolve => child.once('exit', resolve)), 0);
    assert(!/PRIVATE|fixture-private-token|Authorization/i.test(output)); return JSON.parse(output);
  };
  try {
    for (const [kind, changes] of [['missing', {}], ['foreign', { pid: 1 }], ['remote', { url: 'http://outside.invalid' }], ['query', { url: url + '/?secret=PRIVATE' }]]) assert.equal((await invoke(kind, changes)).ok, false);
    assert.equal(requests, 0, 'Unowned transports must not make HTTP requests');
    assert.equal((await invoke('owned')).count, 0);
    assert.equal((await invoke('bundled-clone')).count, 0, 'Separate bundled module state must reuse the RAM service, not read closed fd3');
    for (mode of ['error', 'redirect']) assert.equal((await invoke('owned')).ok, false);
    assert.equal(requests, 5, 'No redirect follow or fallback endpoint; cloned module uses the same owned host');
  } finally { host.closeAllConnections(); await new Promise(resolve => host.close(resolve)); }
});
