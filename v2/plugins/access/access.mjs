import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { integrity, registerProjectTool } from './project.mjs';
import { registerBenchmarkTool } from './benchmark.mjs';
import { guardExploreResult } from './output-guard.mjs';

export function checkProject(input, options, runner = spawnSync) {
  const root = input?.projectPath;
  if (typeof root !== 'string' || !path.isAbsolute(root) || path.normalize(root) !== root)
    throw new Error('CodeGraph: pass the explicit absolute Git/worktree root');
  if (root === path.parse(root).root || root === options.runtimeHome)
    throw new Error('CodeGraph: unsafe root');
  const indexDir = options.indexDir ?? '.codegraph';
  let current = path.parse(root).root;
  for (const part of path.relative(current, path.join(root, indexDir)).split(path.sep)) {
    current = path.join(current, part);
    try { if (fs.lstatSync(current).isSymbolicLink()) throw new Error('CodeGraph: symlinked root/index refused'); }
    catch (error) { if (error.code !== 'ENOENT') throw error; }
  }
  if (!fs.existsSync(path.join(root, indexDir)) || !fs.statSync(path.join(root, indexDir)).isDirectory())
    throw new Error('CodeGraph: no existing index; use direct file tools, no automatic init');
  const result = runner('git', ['-C', root, 'rev-parse', '--show-toplevel'], {
    env: { PATH: '/usr/bin:/bin', HOME: options.runtimeHome, GIT_CONFIG_NOSYSTEM: '1', GIT_CONFIG_GLOBAL: '/dev/null', GIT_OPTIONAL_LOCKS: '0' },
    encoding: 'utf8', timeout: 10000,
  });
  if (result.error || result.status !== 0 || result.stdout.trim() !== root)
    throw new Error('CodeGraph: projectPath must be the exact Git/worktree root, not a parent index or subdirectory');
}

export async function register(ctx) {
  if (ctx.options.maintenance) await registerProjectTool(ctx);
  if (ctx.options.benchmark) await registerBenchmarkTool(ctx);
  await ctx.tool.hook('execute.before', event => {
    if (event.tool !== ctx.options.tool) return;
    checkProject(event.input, ctx.options);
    if (ctx.options.compatibility) checkCompatibility(event.input.projectPath, ctx.options, ctx.location.directory);
  });
  await ctx.tool.hook('execute.after', event => guardExploreResult(event, ctx.options.tool));
}

export function checkCompatibility(root, options, cwd, runner = spawnSync) {
  const { script, pins } = options.compatibility;
  integrity(pins);
  const env = { PATH: '/usr/bin:/bin', HOME: options.runtimeHome, PYTHONDONTWRITEBYTECODE: '1' };
  if (process.env.OPENCODE_CODEGRAPH_ALLOW_TEMP === '1') env.OPENCODE_CODEGRAPH_ALLOW_TEMP = '1';
  const result = runner('/usr/bin/python3', ['-B', script, '--query-index'], {
    cwd, env, input: JSON.stringify({ action: 'status', projectRoot: root }), timeout: 16000, maxBuffer: 8192,
  });
  if (result.error || result.status !== 0)
    throw new Error('CodeGraph: incompatible index or protected source names; no automatic migration or rebuild');
}
