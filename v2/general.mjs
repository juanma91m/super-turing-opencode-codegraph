import assert from 'node:assert/strict';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import fs from 'node:fs';
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { CODEGRAPH_TOOL, CODEGRAPH_ROLES, enableCodeGraph } from './config.mjs';
const root = fileURLToPath(new URL('../', import.meta.url));

export function codegraphContribution({ binding, server, maintenanceRegistry }) {
  return { id: 'codegraph', apply(ctx) {
    assert(ctx.version === 1 && ctx.kind === 'general' && path.isAbsolute(binding.runtime_home));
    const indexDir = binding.environment?.CODEGRAPH_DIR ?? '.codegraph';
    assert(/^[A-Za-z0-9_.-]+$/.test(indexDir) && indexDir !== '.' && !indexDir.includes('..'));
    for (const role of CODEGRAPH_ROLES) {
      const agent = ctx.agents[role]; assert(agent);
      if (!agent.permissions.some(rule => rule.action.startsWith('codegraph_'))) agent.permissions.push({ action: CODEGRAPH_TOOL, resource: '*', effect: 'allow' });
    }
    const nativeText = bytes => bytes.toString().replaceAll('`codegraph_explore`', '`' + CODEGRAPH_TOOL + '`');
    ctx.copyConfigTree(path.join(root, 'skills/codegraph-analisis-estructural'), 'skills/codegraph-analisis-estructural', (name, bytes) => name.endsWith('.md') ? nativeText(bytes) : bytes);
    ctx.addConfig('PLAYBOOK-CODEGRAPH.md', '# Alcance de plataforma — candidato OpenCode V2\n\nConsulta MCP por codegraph_codegraph_explore; lifecycle explícito por codegraph-project, benchmark por codegraph-benchmark. No wrappers shell/SQL/export V1 como bypass. Métricas V2 usan API pública y suma derivada de componentes normalizados exclusivos, NO total reportado V1; backend/bytes/cobertura versionados, sin mezclar pares V1/V2. Cuerpos sólo RAM servidor, no reportes/archivos/modelo. No iniciar corridas A/B, modelo o índice sin autorización/budget; capturar desde otro operador, tarea/política/calidad explícitas. La referencia histórica más abajo describe backend V1 (schema de métricas v2 NO es plataforma OpenCode V2); campos/flags trasladarlos a la tool nativa, nunca ejecutar su SQL en V2.\n\n' + nativeText(ctx.readAsset(path.join(root, 'PLAYBOOK-CODEGRAPH.md'))));
    ctx.addConfig('scripts/codegraph_runtime.py', ctx.readAsset(path.join(root, 'v2/runtime.py')));
    ctx.addConfig('scripts/codegraph-runtime.json', JSON.stringify(binding, null, 2) + '\n');
    const registry = maintenanceRegistry ?? path.join(binding.runtime_home, '.local/state/super-turing-opencode-codegraph/projects.json');
    assert(path.isAbsolute(registry) && path.normalize(registry) === registry && path.basename(registry) === 'projects.json', 'Explicit native registry path required');
    const pins = {}, script = path.join(ctx.config, 'scripts/codegraph_project_v2.py');
    const maintenanceAssets = { 'scripts/codegraph_project_v2.py': ctx.readAsset(path.join(root, 'v2/project.py')), 'scripts/codegraph-maintenance.json': Buffer.from(JSON.stringify({ binding, registry }, null, 2) + '\n') };
    for (const [file, bytes] of Object.entries(maintenanceAssets)) { ctx.addConfig(file, bytes); pins[path.join(ctx.config, file)] = createHash('sha256').update(bytes).digest('hex'); }
    pins[path.join(ctx.config, 'scripts/codegraph_runtime.py')] = createHash('sha256').update(ctx.readAsset(path.join(root, 'v2/runtime.py'))).digest('hex');
    const statusActors = ['master-dev', 'agent-design', 'code-inspector', 'build'].filter(id => ctx.agents[id]);
    const writeActors = statusActors.filter(id => id !== 'code-inspector');
    for (const id of statusActors) ctx.agents[id].permissions.push({ action: 'codegraph-project', resource: '*', effect: 'allow' }, { action: 'codegraph-project-status', resource: '*', effect: 'allow' });
    for (const id of writeActors) ctx.agents[id].permissions.push({ action: 'codegraph-project-write', resource: '*', effect: 'ask' });
    for (const action of ['init', 'status', 'sync', 'reindex']) ctx.addConfig('commands/codegraph-' + action + '.md', ctx.readAsset(path.join(root, 'v2/commands/codegraph-' + action + '.md')));
    const generated = spawnSync('/usr/bin/python3', [path.join(root, 'v2/math_assets.py')], { encoding: 'utf8', timeout: 10000, maxBuffer: 2 * 1024 * 1024, env: { PATH: '/usr/bin:/bin', PYTHONDONTWRITEBYTECODE: '1' } });
    assert(!generated.error && generated.status === 0, 'Native benchmark pure-math extraction failed; no CLI/DB export fallback');
    const benchmarkPins = {}, benchmarkAssets = { 'scripts/codegraph_metrics_math_v2.py': Buffer.from(generated.stdout), 'scripts/codegraph_benchmark_v2.py': ctx.readAsset(path.join(root, 'v2/benchmark_math.py')) };
    for (const [file, bytes] of Object.entries(benchmarkAssets)) { ctx.addConfig(file, bytes); benchmarkPins[path.join(ctx.config, file)] = createHash('sha256').update(bytes).digest('hex'); }
    for (const id of statusActors) ctx.agents[id].permissions.push({ action: 'codegraph-benchmark', resource: '*', effect: 'allow' }, { action: 'codegraph-benchmark-read', resource: '*', effect: 'ask' }, { action: 'codegraph-benchmark-capture', resource: '*', effect: 'ask' });
    ctx.addConfig('commands/codegraph-benchmark.md', ctx.readAsset(path.join(root, 'v2/commands/codegraph-benchmark.md')));
    const selected = server ?? { type: 'local', command: ['/usr/bin/python3', path.join(ctx.config, 'scripts/codegraph_runtime.py'), 'mcp'], cwd: ctx.paths.cache, codemode: false };
    if (!server) for (let current = ctx.paths.cache;; current = path.dirname(current)) {
      assert(!fs.existsSync(path.join(current, indexDir, 'codegraph.db')), 'CodeGraph host cwd has an index ancestor; choose a neutral candidate root');
      if (path.dirname(current) === current) break;
    }
    Object.assign(ctx.document, enableCodeGraph(ctx.document, selected));
    ctx.copyBundleTree('codegraph', path.join(root, 'v2/plugins/access'), 'v2/plugins/access');
    ctx.document.plugins.push({ package: ctx.bundlePath('codegraph', 'v2/plugins/access'), options: { tool: CODEGRAPH_TOOL, runtimeHome: binding.runtime_home, indexDir, maintenance: { script, pins, statusActors, writeActors }, benchmark: { script: path.join(ctx.config, 'scripts/codegraph_benchmark_v2.py'), pins: benchmarkPins, directory: path.join(binding.runtime_home, '.local/state/super-turing-opencode-codegraph/benchmarks-v2'), actors: statusActors } } });
    ctx.closeTools('codegraph_*', [CODEGRAPH_TOOL]);
    ctx.closeTools('codegraph-project', ['codegraph-project']);
    ctx.closeTools('codegraph-benchmark', ['codegraph-benchmark']);
    ctx.appendInstructions('## CodeGraph general V2\nMCP sólo explore, root absoluto Git/worktree con índice existente. Lifecycle por codegraph-project sólo ante pedido explícito, sin shell general; mutadores con permiso/reindex confirmado, sin automatismo o fallback. Runtime conserva locks/watchers/catch-up. Benchmark explícito por API pública, cuerpos sólo RAM servidor, proyección metadata, no DB/export V1; tokens V2 = suma DERIVADA de componentes normalizados exclusivos, no total reportado/billing; no mezclar backend/bytes/versión. No lanzar sesiones A/B/consultas/índices para medir por reflejo; operador distinto, tarea y evaluación explícitas, faltantes null, no ahorro causal de history.');
    ctx.metadata.codegraph = { queryOnly: true, roles: CODEGRAPH_ROLES.length, lifecycle: true, commands: 5, benchmark: true, measurement: 'opencode-public-api-2.2.7 normalized component sum, not provider total' };
  } };
}
