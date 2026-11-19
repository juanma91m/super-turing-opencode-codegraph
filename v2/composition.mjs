import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
import { CODEGRAPH_TOOL, CODEGRAPH_ROLES, enableCodeGraph } from './config.mjs';

const root = fileURLToPath(new URL('../', import.meta.url));
const access = fileURLToPath(new URL('./plugins/access/', import.meta.url));
const digest = value => createHash('sha256').update(value).digest('hex');

function read(file) {
  assert(!fs.lstatSync(file).isSymbolicLink() && fs.statSync(file).isFile(), 'CodeGraph assets must be regular files');
  return fs.readFileSync(file);
}

export function codegraphExtension({ binding, server } = {}) {
  assert(binding?.runtime_home && path.isAbsolute(binding.runtime_home), 'Explicit CodeGraph runtime identity required');
  const indexDir = binding.environment?.CODEGRAPH_DIR ?? '.codegraph';
  assert(/^[A-Za-z0-9_.-]+$/.test(indexDir) && indexDir !== '.' && !indexDir.includes('..'), 'Unreviewed CodeGraph index directory');
  return context => {
    const { document, instructions, config, assets } = context;
    const combined = new Map(assets.map(asset => [asset.file, asset]));
    const add = (relative, desired, previous) => combined.set(path.join(config, relative), {
      file: path.join(config, relative), desired, ...(previous !== undefined ? { previous, backup: true } : {}), tag: 'codegraph',
    });
    for (const role of CODEGRAPH_ROLES) {
      const file = path.join(config, 'agents', role + '.md'), prior = combined.get(file);
      assert(prior, 'Expected the current CodeGraph analysis actors');
      const original = Buffer.from(prior.desired).toString('utf8');
      const end = original.indexOf('\n---\n', 4);
      assert(end > 0, 'Expected agent frontmatter');
      const header = original.slice(0, end);
      // Preserve caller's CodeGraph-specific guards; never defeat a local deny.
      if (/^\s+["']?codegraph_[^\n:]*["']?:/m.test(header)) continue;
      assert(/^permission:\s*$/m.test(header), 'Expected explicit role permissions');
      add('agents/' + role + '.md', original.replace(/^permission:\s*$/m, `permission:\n  ${CODEGRAPH_TOOL}: allow`), prior.desired);
    }
    const skill = path.join(root, 'skills/codegraph-analisis-estructural');
    function tree(dir, relative) {
      assert(!fs.lstatSync(dir).isSymbolicLink(), 'Skill symlinks refused');
      for (const name of fs.readdirSync(dir)) {
        const file = path.join(dir, name), rel = path.join(relative, name);
        assert(!fs.lstatSync(file).isSymbolicLink(), 'Skill symlinks refused');
        if (fs.statSync(file).isDirectory()) tree(file, rel);
        else add(rel, name.endsWith('.md') ? read(file).toString('utf8').replaceAll('`codegraph_explore`', `\`${CODEGRAPH_TOOL}\``) : read(file));
      }
    }
    tree(skill, 'skills/codegraph-analisis-estructural');
    add('PLAYBOOK-CODEGRAPH.md', read(path.join(root, 'PLAYBOOK-CODEGRAPH.md')).toString('utf8').replaceAll('`codegraph_explore`', `\`${CODEGRAPH_TOOL}\``));
    add('scripts/codegraph_runtime.py', read(path.join(root, 'v2/runtime.py')));
    add('scripts/codegraph-runtime.json', JSON.stringify(binding, null, 2) + '\n');
    const selected = server ?? { type: 'local', command: ['/usr/bin/python3', path.join(config, 'scripts/codegraph_runtime.py'), 'mcp'], codemode: false };
    const next = enableCodeGraph(document, selected);
    next.plugins.push({ package: access, options: { tool: CODEGRAPH_TOOL, runtimeHome: binding.runtime_home, indexDir } });
    const boundary = next.plugins.find(plugin => typeof plugin === 'object' && plugin.package.endsWith('/workshop-guard/'));
    assert(boundary, 'Expected additive workshop boundary');
    boundary.options.additionalTools = [...(boundary.options.additionalTools ?? []), CODEGRAPH_TOOL];
    for (const asset of combined.values()) boundary.options.pinned[asset.file] = digest(asset.desired);
    return { ...context, document: next, assets: [...combined.values()], skills: [...(context.skills ?? []), 'codegraph-analisis-estructural'], tag: 'codegraph',
      previousDocument: JSON.stringify(document, null, 2) + '\n', previousInstructions: instructions,
      instructions: instructions + '\n## CodeGraph V2\nMCP de consulta sólo para roles autorizados. Usar projectPath absoluto del root Git/worktree real con índice existente; no inicializar, sincronizar ni reindexar automáticamente ni compartir índices. Seguir la skill del addon y contrastar el grafo con fuente cuando haga falta. Lifecycle y benchmark V2 aún no están habilitados en este piloto; no usar la DB V1 como si fueran métricas V2. El backend conserva su comportamiento normal de locks/SQLite/watchers; no prometer cero escrituras internas.\n' };
  };
}
