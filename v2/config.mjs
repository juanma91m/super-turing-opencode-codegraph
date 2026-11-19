import assert from 'node:assert/strict';

export const CODEGRAPH_TOOL = 'codegraph_codegraph_explore';
export const CODEGRAPH_ROLES = ['code-inspector', 'planner', 'reviewer', 'code-reviewer', 'master-dev'];

export function enableCodeGraph(base, server) {
  assert(!Object.hasOwn(base.mcp?.servers ?? {}, 'codegraph'), 'Existing CodeGraph needs explicit reconciliation');
  assert(server?.type === 'local' && server.codemode === false, 'Expected the reviewed direct local MCP');
  const next = structuredClone(base);
  next.mcp.servers.codegraph = structuredClone(server);
  next.permissions.push({ action: 'codegraph_*', resource: '*', effect: 'deny' });
  next.policies.push({ action: 'mcp.use', resource: 'codegraph', effect: 'allow' },
    { action: 'tool.use', resource: `${CODEGRAPH_TOOL}:*`, effect: 'allow' });
  return next;
}
