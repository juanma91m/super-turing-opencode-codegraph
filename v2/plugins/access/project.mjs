import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { spawn } from 'node:child_process';

export function integrity(pins) {
  for (const [file, digest] of Object.entries(pins)) {
    for (let current = file; current !== path.dirname(current); current = path.dirname(current)) assert(!fs.lstatSync(current).isSymbolicLink(), 'CodeGraph maintenance asset symlink refused');
    assert(createHash('sha256').update(fs.readFileSync(file)).digest('hex') === digest, 'Trusted CodeGraph maintenance asset changed');
  }
}
function run(ctx, input, preflight, signal) {
  assert(!signal?.aborted, 'CodeGraph lifecycle cancelled before execution');
  integrity(ctx.options.maintenance.pins);
  const env = Object.fromEntries(['HOME', 'LANG', 'TERM', 'TMPDIR', 'TMP', 'TEMP'].filter(key => process.env[key] !== undefined).map(key => [key, process.env[key]]));
  Object.assign(env, { PATH: '/usr/local/bin:/usr/bin:/bin', PYTHONDONTWRITEBYTECODE: '1' });
  if (process.env.OPENCODE_CODEGRAPH_ALLOW_TEMP === '1') env.OPENCODE_CODEGRAPH_ALLOW_TEMP = '1';
  return new Promise((resolve, reject) => {
    const child = spawn('/usr/bin/python3', [ctx.options.maintenance.script, ...(preflight ? ['--preflight'] : [])], { cwd: ctx.location.directory, env, stdio: ['pipe', 'pipe', 'pipe'] });
    let output = '', errors = '', overflow = false;
    const abort = () => child.kill('SIGTERM'); signal?.addEventListener('abort', abort, { once: true });
    child.stdin.on('error', () => {}); child.stdin.end(JSON.stringify(input));
    child.stdout.on('data', bytes => { if (output.length < 4 * 1024 * 1024) output += bytes; else { overflow = true; abort(); } });
    child.stderr.on('data', bytes => { if (errors.length < 8192) errors += bytes; });
    child.once('error', () => { signal?.removeEventListener('abort', abort); reject(new Error('Could not start owned CodeGraph lifecycle process')); });
    child.once('exit', code => {
      signal?.removeEventListener('abort', abort);
      if (code !== 0 || signal?.aborted || overflow) {
        // Only our known static ValueError channel, never arbitrary backend logs.
        const reason = errors.split('\n').find(line => line.startsWith('CodeGraph lifecycle refused: '));
        reject(new Error(reason ?? 'CodeGraph lifecycle failed/cancelled; partial index may remain, no fallback or automatic repair')); return;
      }
      try { resolve(JSON.parse(output)); } catch { reject(new Error('CodeGraph lifecycle result invalid; raw values suppressed')); }
    });
  });
}
export async function registerProjectTool(ctx) {
  const approved = ctx.options.maintenance;
  const ask = (context, action, resources) => ctx.permission.assert({ sessionID: context.sessionID, agent: context.agent, source: { type: 'tool', messageID: context.messageID, id: context.id }, action, resources });
  await ctx.tool.transform(editor => {
    editor.add({ name: 'codegraph-project', description: 'Explicit CodeGraph index status/init/sync/confirmed reindex on the exact Git/worktree root. Never automatic setup, install, unlock, uninit, shared indexes or repair fallback. Status may perform normal upstream runtime writes.',
      options: { codemode: false }, input: { type: 'object', properties: { action: { type: 'string', enum: ['init', 'status', 'sync', 'reindex'] }, projectRoot: { type: 'string' }, confirmReindex: { type: 'boolean', default: false } }, required: ['action', 'projectRoot'], additionalProperties: false }, execute: async (input, context) => {
        assert(approved.statusActors.includes(context.agent), 'CodeGraph project lifecycle is outside this actor contract');
        assert(input.action === 'status' || approved.writeActors.includes(context.agent), 'Read-only actor cannot maintain/rebuild indexes even with a session allow');
        assert(input.action !== 'reindex' || input.confirmReindex === true, 'Explicit reindex explanation and confirmation required');
        const planned = await run(ctx, input, true, context.signal);
        if (ctx.location.directory !== planned.projectRoot && !ctx.location.directory.startsWith(planned.projectRoot + path.sep)) await ask(context, 'external_directory', [planned.projectRoot]);
        const mutation = input.action !== 'status';
        await ask(context, mutation ? 'codegraph-project-write' : 'codegraph-project-status', mutation ? [input.action + ':' + planned.projectRoot, 'registry:' + planned.registry] : [planned.projectRoot]);
        return { content: JSON.stringify(await run(ctx, input, false, context.signal)) };
      } });
  });
}
