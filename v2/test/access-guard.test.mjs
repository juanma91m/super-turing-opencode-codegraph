import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { test } from 'node:test';
import { checkCompatibility } from '../plugins/access/access.mjs';
import { filterExploreResult, guardExploreResult, withheld } from '../plugins/access/output-guard.mjs';

test('Explore forwards only reviewed text, strips metadata and withholds protected hints', () => {
  const ordinary = { type: 'text', text: '### src/Main.java\nclass Main {}' };
  assert.deepEqual(filterExploreResult({ content: [{ ...ordinary, sidecar: 'not forwarded' }], metadata: { sidecar: true } }),
    { content: [ordinary] });
  for (const content of ['src/.env.local:2', 'src/nested/config.PEM', '-----BEGIN PRIVATE KEY-----',
    [{ type: 'text', text: '-----BEGIN PRIVATE ' }, { type: 'text', text: 'KEY-----' }], [{ type: 'image' }], undefined]) {
    assert.deepEqual(filterExploreResult({ content }), { content: withheld });
  }
  const unrelated = { tool: 'read', status: 'completed', result: { content: 'untouched', metadata: { keep: true } } };
  const before = structuredClone(unrelated);
  guardExploreResult(unrelated, 'codegraph_codegraph_explore');
  assert.deepEqual(unrelated, before);
});

test('Explore checks SHA-pinned compatibility probe and never emits raw subprocess diagnostics', t => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'codegraph-probe-test-'));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const script = path.join(root, 'probe.py');
  fs.writeFileSync(script, '# owned synthetic probe');
  const options = { runtimeHome: root, compatibility: { script,
    pins: { [script]: createHash('sha256').update(fs.readFileSync(script)).digest('hex') } } };
  let calls = 0;
  assert.throws(() => checkCompatibility(root, options, root, (binary, args, child) => {
    calls++;
    assert.equal(binary, '/usr/bin/python3');
    assert.deepEqual(args, ['-B', script, '--query-index']);
    assert.deepEqual(JSON.parse(child.input), { action: 'status', projectRoot: root });
    return { status: 2, stderr: 'SYNTHETIC_RAW_DIAGNOSTICS' };
  }), error => error.message.includes('no automatic migration') && !error.message.includes('SYNTHETIC_RAW_DIAGNOSTICS'));
  fs.appendFileSync(script, '\n# changed bytes');
  assert.throws(() => checkCompatibility(root, options, root, () => calls++), /asset changed/);
  assert.equal(calls, 1);
});
