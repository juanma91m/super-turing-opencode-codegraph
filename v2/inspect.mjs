import assert from 'node:assert/strict';
import { CODEGRAPH_ROLES, CODEGRAPH_TOOL } from './config.mjs';

const matches = (pattern, value) => new RegExp('^' + pattern.replace(/[.+^${}()|[\]\\]/g, '\\$&').replaceAll('*', '.*').replaceAll('?', '.') + '$').test(value);
export const effect = (rules, action) => rules.findLast(rule => rule.resource === '*' && matches(rule.action, action))?.effect;

export async function inspectCodeGraph(get, roles) {
  const agents = await get('/api/agent');
  for (const role of roles) {
    const agent = agents.find(item => item.id === role);
    assert(agent, 'CodeGraph actor missing');
    assert.equal(effect(agent.permissions, CODEGRAPH_TOOL), CODEGRAPH_ROLES.includes(role) ? 'allow' : 'deny', role + ' CodeGraph access');
    assert.equal(effect(agent.permissions, 'codegraph_codegraph_unreviewed'), 'deny', 'Unknown tools must remain denied');
  }
  const skills = await get('/api/skill');
  assert(skills.some(item => item.id === 'codegraph-analisis-estructural'), 'Missing CodeGraph skill');
  const mcp = (await get('/api/mcp')).find(item => item.name === 'codegraph');
  assert(mcp, 'CodeGraph MCP not registered');
  return { codegraphStatus: mcp.status?.status, codegraphTool: CODEGRAPH_TOOL, codegraphActors: CODEGRAPH_ROLES.length,
    lifecycleEnabled: false, benchmarkV2Enabled: false, actualIndexQueries: 0 };
}
