import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { spawn } from 'node:child_process';
import { nativeMessages } from './native-messages.mjs';

export const MEASUREMENT = Object.freeze({ backend: 'opencode-public-api-2.2.7', tokens: 'normalized-exclusive-component-sum-v1', bytes: 'stored-tool-content-json-utf8-v1', history: 'stored-assistant-plus-completed-compaction-v1' });
const versionLabel = value => typeof value === 'string' && /^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.+-]+)?$/.test(value) ? value : null;
const sid = value => typeof value === 'string' && /^ses_[A-Za-z0-9]+$/.test(value);
const mid = value => typeof value === 'string' && /^msg_[A-Za-z0-9]+$/.test(value);
const hash = value => createHash('sha256').update(value).digest('hex');
const number = value => typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : null;
const info = value => value?.data?.id ? value.data : value;
function label(value) { assert(typeof value === 'string' && value.length > 0 && value.length <= 128 && !/[\x00-\x1f\x7f<>{}]/.test(value) && !/(?:password|bearer|api[_-]?key)\s*[=:]/i.test(value), 'Explicit public metadata label required; values suppressed'); return value; }
function noLinks(file) { for (let current = file; current !== path.dirname(current); current = path.dirname(current)) { try { assert(!fs.lstatSync(current).isSymbolicLink(), 'Benchmark path symlink refused'); } catch (error) { if (error.code !== 'ENOENT') throw error; } } }
function integerTime(value) { return Number.isSafeInteger(value) && value >= 0 ? value : null; }
function timestamp(value) {
  assert(typeof value === 'string' && /^\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?)?$/.test(value), 'Explicit ISO UTC window required');
  const date = value.slice(0, 10), checked = new Date(date + 'T00:00:00Z'); assert(Number.isFinite(checked.getTime()) && checked.toISOString().slice(0, 10) === date, 'Invalid calendar date');
  const milliseconds = Date.parse(value.length === 10 ? value + 'T00:00:00Z' : /(?:Z|[+-]\d{2}:\d{2})$/.test(value) ? value : value + 'Z'); assert(Number.isFinite(milliseconds), 'Invalid UTC time'); return milliseconds;
}
function measurementTokens(tokens) {
  const cache = tokens?.cache ?? {}, values = [tokens?.input, tokens?.output, tokens?.reasoning, cache.read, cache.write].map(number);
  return { total: values.some(value => value === null) ? null : values.reduce((sum, value) => sum + value, 0), input: values[0], output: values[1], reasoning: values[2], cache: { read: values[3], write: values[4] } };
}
function modelLabel(model) { if (!model || typeof model.providerID !== 'string' || typeof model.id !== 'string') return null; return { providerID: label(model.providerID), modelID: label(model.id), ...(model.variant ? { variant: label(model.variant) } : {}) }; }
export function projectMessage(row, sessionID) {
  assert(mid(row?.id) && ['assistant', 'compaction', 'user', 'synthetic', 'system', 'skill', 'shell', 'idle', 'model-switched', 'agent-switched', 'location-switched'].includes(row.type) && integerTime(row.time?.created) !== null, 'Unknown native message metadata; no incomplete capture');
  const timing = { created: row.time.created, ...(number(row.time.completed) !== null ? { completed: row.time.completed } : {}) };
  // User/other boundary lookup: ID/time only, never prompt/text/attachments.
  if (!['assistant', 'compaction'].includes(row.type)) return { id: row.id, sessionID, event_time: row.time.created, info: { time: timing, role: row.type }, parts: [] };
  const model = modelLabel(row.model), parts = [];
  if (row.type === 'assistant') for (const content of row.content ?? []) {
    if (content.type !== 'tool') continue; // No assistant text/reasoning/native blob.
    const state = content.state ?? {}, status = state.status ?? state.type;
    let bytes = null;
    if (state.output !== undefined && state.output !== null) bytes = Buffer.byteLength(typeof state.output === 'string' ? state.output : JSON.stringify(state.output), 'utf8');
    assert(typeof content.name === 'string' && /^[A-Za-z0-9_.:-]{1,128}$/.test(content.name), 'Technical tool name required');
    parts.push({ type: 'tool', tool: content.name, state: { status: ['completed', 'error', 'interrupted', 'running', 'pending'].includes(status) ? status : 'unknown', output_bytes: bytes, time: { start: integerTime(content.time?.ran ?? content.time?.created), end: integerTime(content.time?.completed) } } });
  }
  return { id: row.id, sessionID, event_time: row.time.created, info: { role: 'assistant', ...(model ?? {}), agent: row.type === 'compaction' ? 'compaction' : typeof row.agent === 'string' ? label(row.agent) : undefined, tokens: measurementTokens(row.tokens), time: timing }, parts,
    coverage: { model: model !== null, completedUsage: row.type !== 'compaction' || row.status === 'completed' } };
}

async function pages(api, input, signal, limit = 100) {
  const rows = [], seen = new Set(), cursors = new Set(); let cursor;
  for (let page = 0; page < limit; page++) {
    signal?.throwIfAborted();
    const result = await api(cursor ? { ...input, cursor, order: undefined } : input);
    assert(Array.isArray(result.data) && result.cursor, 'Native pagination contract changed; no partial telemetry');
    for (const item of result.data) { assert(item.id && !seen.has(item.id), 'Duplicate native telemetry ID'); seen.add(item.id); rows.push(item); }
    if (!result.cursor.next) return rows;
    assert(!cursors.has(result.cursor.next), 'Native pagination did not advance'); cursors.add(result.cursor.next); cursor = result.cursor.next;
  }
  throw new Error('Native telemetry read bound reached; narrow the scope');
}
function snapshot(session) { return hash(JSON.stringify([session.parentID, session.location?.directory, session.time?.updated, session.time?.busy, session.time?.idle, session.revert, session.fork, session.model, session.agent, session.tokens, session.cost])); }
function idle(session) { return !session.time?.busy || number(session.time.idle) !== null && session.time.idle >= session.time.busy; }
async function authorizeDirectory(ctx, session, ask) {
  const directory = session.location?.directory; assert(typeof directory === 'string' && path.isAbsolute(directory), 'Native session location required');
  if (directory !== ctx.location.directory) await ask('external_directory', [directory]);
}
async function recheckFamily(ctx, catalog, signal) {
  for (const prior of catalog) {
    signal?.throwIfAborted();
    assert(snapshot(info(await ctx.session.get({ sessionID: prior.id }))) === prior.stamp, 'Measured session changed during collection/approval; retry explicitly');
    const children = await pages(input => ctx.session.list(input), { parentID: prior.id, limit: 100 }, signal);
    const expected = catalog.filter(session => session.parentID === prior.id).map(session => session.id).sort();
    assert(JSON.stringify(children.map(child => child.id).sort()) === JSON.stringify(expected), 'Changed/new descendant during telemetry/approval; no partial capture');
  }
}
export async function collectFamily(ctx, rootID, operatorID, ask, signal, boundary = {}, messages = nativeMessages()) {
  assert(sid(rootID) && sid(operatorID), 'Explicit measured/operator session IDs required');
  const catalog = [], visited = new Set(), queue = [rootID];
  while (queue.length) {
    const id = queue.shift(); assert(!visited.has(id) && visited.size < 100, 'Invalid/oversized measured family'); visited.add(id);
    assert(id !== operatorID, 'Benchmark operator must be outside the measured family');
    if (id !== rootID) await ask('codegraph-benchmark-read', ['session:' + id]);
    const session = info(await ctx.session.get({ sessionID: id })); assert(session.id === id && !session.fork && !session.revert && idle(session), 'Measured session is active/forked/reverted or changed identity; no comparable capture');
    await authorizeDirectory(ctx, session, ask); catalog.push({ id: session.id, parentID: session.parentID, location: { directory: session.location.directory }, time: { created: session.time?.created, updated: session.time?.updated, busy: session.time?.busy, idle: session.time?.idle }, stamp: snapshot(session) });
    const children = await pages(input => ctx.session.list(input), { parentID: id, limit: 100 }, signal);
    for (const child of children) { assert(child.parentID === id, 'Unverified parent relation'); queue.push(child.id); }
  }
  const projected = [];
  let from = null, to = null;
  if (boundary.fromMessage || boundary.toMessage) {
    assert(mid(boundary.fromMessage) && mid(boundary.toMessage), 'Both message boundaries required');
    const left = info(await messages.get({ sessionID: rootID, messageID: boundary.fromMessage }, signal)), right = info(await messages.get({ sessionID: rootID, messageID: boundary.toMessage }, signal));
    from = projectMessage(left, rootID); to = projectMessage(right, rootID); assert(from.event_time <= to.event_time, 'Reversed native message range');
  }
  let rootIDs;
  if (from) {
    const timeline = [], cursors = new Set(); let cursor;
    for (let page = 0; page < 100; page++) {
      const result = await messages.list({ sessionID: rootID, limit: 100, ...(cursor ? { cursor } : { order: 'asc' }) }, signal);
      assert(Array.isArray(result.data) && result.cursor, 'Boundary timeline unavailable');
      for (const row of result.data) { assert(mid(row.id) && integerTime(row.time?.created) !== null, 'Boundary metadata invalid'); timeline.push(row.id); }
      assert(timeline.length <= 10000, 'Boundary read too broad');
      if (!result.cursor.next) break;
      assert(page < 99 && !cursors.has(result.cursor.next), 'Boundary pagination incomplete'); cursors.add(result.cursor.next); cursor = result.cursor.next;
    }
    const left = timeline.indexOf(from.id), right = timeline.indexOf(to.id);
    assert(left >= 0 && right >= left && new Set(timeline).size === timeline.length, 'Invalid/reversed message boundary order'); rootIDs = new Set(timeline.slice(left, right + 1));
  }
  for (const session of catalog) {
    for (const type of ['assistant', 'compaction']) {
      // Materialization stays in this server process. Project each page immediately;
      // no raw message API result crosses to Python, files, tool result or model.
      let cursor; const cursors = new Set(), messageIDs = new Set();
      for (let page = 0; page < 100; page++) {
        signal?.throwIfAborted();
        const result = await messages.list({ sessionID: session.id, type, limit: 100, ...(cursor ? { cursor } : { order: 'asc' }) }, signal);
        assert(Array.isArray(result.data) && result.cursor, 'Native message page invalid');
        for (const row of result.data) {
          assert(row.type === type && !messageIDs.has(row.id), 'Native type/order/ID coverage changed'); messageIDs.add(row.id);
          const metric = projectMessage(row, session.id);
          if (!from || (session.id === rootID ? rootIDs.has(metric.id) : metric.event_time >= from.event_time && metric.event_time <= (to.info.time.completed ?? to.event_time))) projected.push(metric);
          assert(projected.length <= 10000, 'Message budget exceeded; narrow task');
        }
        if (!result.cursor.next) break;
        assert(page < 99 && !cursors.has(result.cursor.next), 'Message pagination incomplete'); cursors.add(result.cursor.next); cursor = result.cursor.next;
      }
    }
  }
  await recheckFamily(ctx, catalog, signal);
  projected.sort((a, b) => a.event_time - b.event_time || a.id.localeCompare(b.id));
  assert(projected.length > 0 || boundary.allowEmpty === true, 'Selected task has no usage events');
  return { catalog, projected, export: { info: { id: rootID }, messages: projected }, scope: { boundary_kind: from ? 'message-range' : 'dedicated-task-session', from_message: boundary.fromMessage ?? null, to_message: boundary.toMessage ?? null,
    linked_sessions: catalog.map(session => session.id), descendant_attribution: 'native parentID only; temporal clipping for message ranges', unlinked_work_complete: null, deleted_work_complete: null, complete: projected.every(message => !message.coverage || message.coverage.model && message.coverage.completedUsage) } };
}

function math(ctx, operation, data, signal) {
  const config = ctx.options.benchmark;
  for (const [file, expected] of Object.entries(config.pins)) { noLinks(file); assert(hash(fs.readFileSync(file)) === expected, 'Trusted native benchmark arithmetic changed'); }
  assert(!signal?.aborted, 'Benchmark cancelled before arithmetic');
  return new Promise((resolve, reject) => {
    const child = spawn('/usr/bin/python3', ['-I', '-B', config.script], { cwd: ctx.location.directory, env: { PATH: '/usr/local/bin:/usr/bin:/bin' }, stdio: ['pipe', 'pipe', 'pipe'] });
    let output = '', overflow = false; const abort = () => child.kill('SIGTERM'); signal?.addEventListener('abort', abort, { once: true }); child.stderr.resume(); child.stdin.on('error', () => {});
    child.stdin.end(JSON.stringify({ operation, data })); child.stdout.on('data', bytes => { if (output.length < 4 * 1024 * 1024) output += bytes; else { overflow = true; abort(); } });
    child.once('error', () => reject(new Error('Native metric worker unavailable')));
    child.once('close', code => { signal?.removeEventListener('abort', abort); if (code !== 0 || signal?.aborted || overflow) { reject(new Error('Native metric arithmetic failed; raw values suppressed')); return; } try { resolve(JSON.parse(output)); } catch { reject(new Error('Native metric result invalid; raw values suppressed')); } });
  });
}
const STORE = { owner: 'opencode-codegraph', kind: 'native-benchmark-metadata', schemaVersion: 1, measurement: MEASUREMENT };
function store(directory, create = false) {
  assert(path.isAbsolute(directory), 'Fixed owner benchmark directory required'); noLinks(directory);
  if (!fs.existsSync(directory)) { if (!create) return false; fs.mkdirSync(directory, { recursive: true, mode: 0o700 }); fs.writeFileSync(path.join(directory, 'owner.json'), JSON.stringify(STORE), { flag: 'wx', mode: 0o600 }); }
  const stat = fs.statSync(directory); assert(stat.isDirectory() && stat.uid === process.getuid() && (stat.mode & 0o777) === 0o700, 'Unsafe benchmark store');
  const marker = path.join(directory, 'owner.json'); noLinks(marker); let value; try { const markerStat = fs.statSync(marker); assert(markerStat.isFile() && markerStat.nlink === 1 && markerStat.uid === process.getuid() && (markerStat.mode & 0o777) === 0o600 && markerStat.size <= 2048); value = JSON.parse(fs.readFileSync(marker)); } catch { throw new Error('Unknown native benchmark store; no adoption'); }
  assert(JSON.stringify(value) === JSON.stringify(STORE), 'Benchmark store measurement/owner mismatch'); return true;
}
function validateRecord(record) {
  const allowed = ['schema_version', 'experiment', 'captured_at', 'pair_id', 'project', 'variant', 'task_kind', 'task_id', 'policy_version', 'scope', 'outcome', 'evaluation', 'runtime', 'runtime_provenance', 'budget', 'metrics', 'measurement'];
  assert(record?.schema_version === 3 && record.experiment === 'codegraph-ab' && Object.keys(record).every(key => allowed.includes(key)) && JSON.stringify(record.measurement) === JSON.stringify(MEASUREMENT), 'Unknown/legacy benchmark record; do not mix measurements');
  for (const key of ['pair_id', 'project', 'task_kind', 'task_id', 'policy_version']) label(record[key]);
  assert(['with-codegraph', 'without-codegraph'].includes(record.variant) && ['accepted', 'partial', 'reworked', 'incorrect', 'pending'].includes(record.outcome), 'Invalid benchmark evaluation');
  assert(!record.project.startsWith('/') && record.evaluation && ['yes', 'partial', 'no', 'not-evaluated', 'not-applicable'].includes(record.evaluation.utility) && (record.evaluation.corrections_required === null || Number.isInteger(record.evaluation.corrections_required) && record.evaluation.corrections_required >= 0), 'Invalid explicit public evaluation');
  assert(record.scope?.complete === true && ['message-range', 'dedicated-task-session'].includes(record.scope.boundary_kind) && record.metrics?.tokens?.reported_total === null && JSON.stringify(record.metrics.measurement) === JSON.stringify(MEASUREMENT), 'Unreviewed metric coverage or measurement');
  const keys = new Set([...allowed, 'boundary_kind', 'from_message', 'to_message', 'linked_sessions', 'descendant_attribution', 'unlinked_work_complete', 'deleted_work_complete', 'complete', 'utility', 'corrections_required', 'source', 'codegraph_version', 'opencode_version', 'applicable', 'recommended_max_calls', 'recommended_max_output_bytes', 'calls_compliant', 'output_compliant', 'session', 'id', 'created_at', 'updated_at', 'duration_ms', 'tokens', 'total', 'input', 'output', 'reasoning', 'cache_read', 'cache_write', 'reported_total', 'models', 'agents', 'token_coverage', 'observations', 'missing', 'timing', 'assistant_wall_ms', 'assistant_active_union_ms', 'tools', 'count', 'by_name', 'search', 'codegraph', 'manual', 'combined', 'first_codegraph_tool_position', 'calls', 'output_bytes', 'wall_ms', 'latency_ms', 'by_status', 'before_first_codegraph', 'after_first_codegraph', 'available', 'sum', 'mean', 'median', 'p75', 'p90', 'backend', 'bytes', 'history']);
  // Generated metric DTO is counts/labels/IDs only. Reject manual body-shaped
  // additions anywhere, including nested outputs disguised as metadata.
  const inspect = (value, parents = []) => {
    if (!value || typeof value !== 'object') { if (typeof value === 'string') assert(value.length <= 512 && !/[\x00-\x1f\x7f<>{}]/.test(value), 'Unreviewed record text refused'); if (typeof value === 'number') assert(number(value) !== null, 'Invalid metric number'); return; }
    if (Array.isArray(value)) { assert(parents.at(-1) === 'linked_sessions' && value.length <= 100 && value.every(sid), 'Unknown metric array refused'); return; }
    if (['models', 'agents', 'by_name', 'by_status'].includes(parents.at(-1))) { for (const [key, count] of Object.entries(value)) { label(key); assert(Number.isSafeInteger(count) && count >= 0, 'Only numeric metric catalog counts allowed'); } return; }
    for (const [key, item] of Object.entries(value)) {
      assert(keys.has(key), 'Unreviewed nested record field refused');
      assert(!['prompt', 'text', 'content', 'arguments', 'messages', 'native', 'summary'].includes(key), 'Raw benchmark content refused');
      if (['input', 'output', 'reasoning'].includes(key) && item !== null) {
        const coverage = parents.at(-1) === 'token_coverage' && item && Object.keys(item).every(field => ['observations', 'missing'].includes(field)) && Object.values(item).every(value => Number.isInteger(value) && value >= 0);
        assert(typeof item === 'number' || coverage, 'Raw benchmark tool arguments/output refused');
      }
      inspect(item, [...parents, key]);
    }
  }; inspect(record); return record;
}
function records(directory) {
  if (!store(directory)) return []; const folder = path.join(directory, 'runs'); noLinks(folder); if (!fs.existsSync(folder)) return [];
  const stat = fs.statSync(folder); assert(stat.isDirectory() && stat.uid === process.getuid() && (stat.mode & 0o777) === 0o700, 'Unsafe metric directory');
  const files = fs.readdirSync(folder); assert(files.length <= 1000, 'Benchmark report too broad');
  return files.map(name => { assert(/^[a-f0-9]{64}\.json$/.test(name), 'Unmanaged benchmark record'); const file = path.join(folder, name); noLinks(file); const info = fs.statSync(file); assert(info.isFile() && info.nlink === 1 && info.uid === process.getuid() && (info.mode & 0o777) === 0o600 && info.size <= 1024 * 1024, 'Unsafe metric record'); let value; try { value = JSON.parse(fs.readFileSync(file)); } catch { throw new Error('Benchmark record JSON invalid; raw values suppressed'); } return validateRecord(value); });
}
export async function executeBenchmark(ctx, input, context, messages = nativeMessages()) {
  assert(ctx.options.benchmark.actors.includes(context.agent), 'Benchmark outside this actor contract');
  const ask = (action, resources) => ctx.permission.assert({ sessionID: context.sessionID, agent: context.agent, source: { type: 'tool', messageID: context.messageID, id: context.id }, action, resources });
  const directory = ctx.options.benchmark.directory;
  if (input.action === 'report') {
    await ask('codegraph-benchmark-read', ['store:' + directory]); const report = await math(ctx, 'report', records(directory), context.signal);
    return input.format === 'markdown' ? report.markdown : report.report;
  }
  if (input.action === 'capture') {
    assert(sid(input.sessionID) && ['with-codegraph', 'without-codegraph'].includes(input.variant), 'Explicit session and variant required');
    for (const key of ['pairID', 'project', 'taskKind', 'policyVersion']) label(input[key]);
    assert(!input.project.startsWith('/'), 'Project is a comparison label, not a private full path');
    assert(['accepted', 'partial', 'reworked', 'incorrect', 'pending'].includes(input.outcome), 'Explicit outcome required');
    assert(input.utility === undefined || ['yes', 'partial', 'no', 'not-evaluated', 'not-applicable'].includes(input.utility), 'Explicit utility enum required');
    assert(input.correctionsRequired === undefined || Number.isInteger(input.correctionsRequired) && input.correctionsRequired >= 0, 'Corrections must be explicit nonnegative integer');
    const bounded = Boolean(input.fromMessage || input.toMessage); assert(bounded ? mid(input.fromMessage) && mid(input.toMessage) && !input.dedicatedTask : input.dedicatedTask === true, 'Declare dedicated task OR both message boundaries');
    await ask('codegraph-benchmark-read', ['session:' + input.sessionID]);
    const collected = await collectFamily(ctx, input.sessionID, context.sessionID, ask, context.signal, input, messages); assert(collected.scope.complete, 'Usage/model coverage incomplete; do not capture a comparable pair');
    const metric = await math(ctx, 'metrics', collected.export, context.signal), graph = metric.search.codegraph;
    assert(input.variant === 'with-codegraph' ? graph.calls > 0 : graph.calls === 0, 'Variant does not match observed explore calls; do not relabel');
    const maxCalls = /review/i.test(input.taskKind) ? 1 : 3;
    const record = validateRecord({ schema_version: 3, experiment: 'codegraph-ab', captured_at: new Date().toISOString(), measurement: MEASUREMENT, pair_id: input.pairID, project: input.project, variant: input.variant, task_kind: input.taskKind,
      task_id: input.taskID ? label(input.taskID) : input.pairID, policy_version: input.policyVersion, scope: collected.scope, outcome: input.outcome, evaluation: { utility: input.utility ?? 'not-evaluated', corrections_required: input.correctionsRequired ?? null, source: 'explicit-operator-input' },
      runtime: { codegraph_version: versionLabel(ctx.options.benchmark.codegraphVersion), opencode_version: versionLabel(ctx.app?.version) },
      runtime_provenance: 'configured binding at capture; historical execution version unknown', budget: { applicable: input.variant === 'with-codegraph', recommended_max_calls: maxCalls, recommended_max_output_bytes: 10240, calls_compliant: input.variant === 'with-codegraph' ? graph.calls <= maxCalls : null, output_compliant: input.variant === 'with-codegraph' && graph.output_bytes !== null ? graph.output_bytes <= 10240 : null }, metrics: metric });
    const id = hash(JSON.stringify([input.pairID, input.variant, input.sessionID, input.taskID ?? input.pairID, input.fromMessage, input.toMessage]));
    await ask('codegraph-benchmark-capture', ['store:' + directory, 'record:' + id]); context.signal?.throwIfAborted();
    await recheckFamily(ctx, collected.catalog, context.signal);
    store(directory, true); const folder = path.join(directory, 'runs'); noLinks(folder); fs.mkdirSync(folder, { recursive: true, mode: 0o700 });
    const folderStat = fs.statSync(folder); assert(folderStat.isDirectory() && folderStat.uid === process.getuid() && (folderStat.mode & 0o777) === 0o700, 'Unsafe metric directory');
    const stage = fs.mkdtempSync(path.join(directory, '.capture-')), temporary = path.join(stage, 'record.json');
    try {
      const fd = fs.openSync(temporary, 'wx', 0o600);
      try { fs.writeFileSync(fd, JSON.stringify(record, null, 2) + '\n'); fs.fsyncSync(fd); } finally { fs.closeSync(fd); }
      // V1 atomic_write_json replaces the SAME identity, allowing an operator to
      // correct outcome/utility/corrections without creating a duplicate run.
      const target = path.join(folder, id + '.json'); noLinks(target);
      if (fs.existsSync(target)) { const prior = fs.statSync(target); assert(prior.isFile() && prior.nlink === 1, 'Unsafe capture destination'); }
      fs.renameSync(temporary, target);
      const folderFD = fs.openSync(folder, 'r'); try { fs.fsyncSync(folderFD); } finally { fs.closeSync(folderFD); }
    } finally { if (fs.existsSync(temporary)) fs.unlinkSync(temporary); fs.rmdirSync(stage); }
    return { status: 'captured', recordID: id, measurement: MEASUREMENT, metrics: metric, scope: collected.scope, evaluation: record.evaluation,
      captureRuntime: record.runtime, historicalRuntimeVerified: false, legacyRecordsImported: false };
  }
  assert(input.action === 'history', 'Closed benchmark action required');
  const since = timestamp(input.since), until = timestamp(input.until); assert(since < until, 'Explicit valid since/until UTC window required');
  await ask('codegraph-benchmark-read', ['history:' + ctx.location.directory, input.since + '/' + input.until]);
  const catalog = await pages(value => ctx.session.list(value), { directory: ctx.location.directory, limit: 100 }, context.signal);
  const map = new Map(catalog.map(session => [session.id, session])); const roots = new Set();
  for (const session of catalog) {
    let id = session.id; const seen = new Set();
    while (map.get(id)?.parentID && map.has(map.get(id).parentID)) { assert(!seen.has(id), 'Session relation cycle'); seen.add(id); id = map.get(id).parentID; }
    if (!map.get(id)?.parentID) roots.add(id);
  }
  let operatorRoot = context.sessionID; const operatorSeen = new Set();
  while (map.get(operatorRoot)?.parentID) { assert(!operatorSeen.has(operatorRoot), 'Operator relation cycle'); operatorSeen.add(operatorRoot); operatorRoot = map.get(operatorRoot).parentID; }
  const units = [], excluded = [];
  for (const id of roots) {
    if (id === operatorRoot) { excluded.push({ reason: 'operator-family' }); continue; }
    const root = map.get(id); if (root.fork || root.revert || !idle(root)) { excluded.push({ reason: 'active-forked-or-reverted-family' }); continue; }
    if (number(root.time?.created) !== null && root.time.created >= until) continue;
    const result = await collectFamily(ctx, id, context.sessionID, ask, context.signal, { allowEmpty: true }, messages);
    const selectedMessages = result.projected.filter(message => message.event_time >= since && message.event_time < until); if (!selectedMessages.length) continue;
    const metrics = await math(ctx, 'metrics', { info: {}, messages: selectedMessages }, context.signal);
    if (metrics.tools.by_name['codegraph-benchmark']) { excluded.push({ reason: 'benchmark-operator-family' }); continue; }
    if (input.model && (Object.keys(metrics.models).length !== 1 || !Object.hasOwn(metrics.models, input.model))) continue;
    units.push({ project: path.basename(root.location.directory), project_key: hash(root.location.directory).slice(0, 12), metrics });
  }
  return { ...await math(ctx, 'history', units, context.signal), window: { since_inclusive: new Date(since).toISOString(), until_exclusive: new Date(until).toISOString() }, excluded,
    methodology: { unit: 'root session family, NOT accepted task', operatorExcluded: true, bodiesPersisted: false, historicalQualityOrPolicyInferred: false, unknownWork: 'unlinked/external/deleted work not proven', usage: 'derived exclusive normalized components, not reported total or billing' } };
}

export async function registerBenchmarkTool(ctx) {
  await ctx.tool.transform(editor => editor.add({ name: 'codegraph-benchmark', description: 'Explicit native history/capture/report over authorized stored sessions; projects in server RAM, returns/persists metadata only. No A/B generation, SQL/export, graph/index operation or real model call. Total is versioned normalized component sum, not provider-reported/billing.',
    options: { codemode: false }, input: { type: 'object', properties: { action: { type: 'string', enum: ['history', 'capture', 'report'] }, sessionID: { type: 'string' }, variant: { type: 'string', enum: ['with-codegraph', 'without-codegraph'] }, pairID: { type: 'string' }, project: { type: 'string' }, taskKind: { type: 'string' }, taskID: { type: 'string' }, policyVersion: { type: 'string' }, dedicatedTask: { type: 'boolean' }, fromMessage: { type: 'string' }, toMessage: { type: 'string' }, outcome: { type: 'string', enum: ['accepted', 'partial', 'reworked', 'incorrect', 'pending'] }, utility: { type: 'string', enum: ['yes', 'partial', 'no', 'not-evaluated', 'not-applicable'] }, correctionsRequired: { type: 'integer', minimum: 0 }, since: { type: 'string' }, until: { type: 'string' }, model: { type: 'string' }, format: { type: 'string', enum: ['json', 'markdown'] } }, required: ['action'], additionalProperties: false },
    execute: async (input, context) => { const result = await executeBenchmark(ctx, input, context); return { content: typeof result === 'string' ? result : JSON.stringify(result) }; } }));
}
