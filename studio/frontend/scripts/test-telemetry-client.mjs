import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { test } from 'node:test'
import assert from 'node:assert/strict'
import ts from 'typescript'
import * as sdk from '../../../packages/client/dist/index.js'

const modules = new Map()
function load(url) {
  if (modules.has(url.href)) return modules.get(url.href)
  const exported = {}; modules.set(url.href, exported)
  const code = ts.transpileModule(readFileSync(url, 'utf8'), { compilerOptions: {
    target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, esModuleInterop: true,
  } }).outputText
  const local = createRequire(url)
  new Function('require', 'exports', code)(name => name === '@mnemion/client' ? sdk
    : name.startsWith('.') && !name.endsWith('.json') ? load(new URL(name.replace(/\.js$/, '') + '.ts', url)) : local(name), exported)
  return exported
}
const { measuredStudioClient, studioMeasurementSelection } = load(new URL('../src/workspace/measured-client.ts', import.meta.url))
const { telemetryCatalog } = load(new URL('../src/workspace/telemetry-aggregate.ts', import.meta.url))
const { TelemetryWorkflow } = load(new URL('../../electron/telemetry-workflow.ts', import.meta.url))
const methods = JSON.parse(readFileSync(new URL('../../../mnemion/product_telemetry/studio-methods.json', import.meta.url)))
const controls = JSON.parse(readFileSync(new URL('../../../mnemion/product_telemetry/control-origins.json', import.meta.url)))
const actionCoverage = JSON.parse(readFileSync(new URL('../../../mnemion/product_telemetry/workflow-coverage.json', import.meta.url))).action_coverage
const { measureUiAction, measuredLegacyClient, uiMeasurementOrigins } = load(new URL('../src/workspace/measurement-action.ts', import.meta.url))
const { api: legacyApi } = load(new URL('../src/api/client.ts', import.meta.url))

function fixture(fetch) {
  const rows = [], requests = []
  let reads = 0, enabled = true
  const stamp = { revision: 1, store_generation: 'a'.repeat(32) }
  const store = { available: true, catalog: telemetryCatalog,
    async snapshot() { reads++; return enabled ? { ...stamp } : null },
    async recordMany(values, original) {
      if (!enabled || original.revision !== stamp.revision || original.store_generation !== stamp.store_generation) return false
      for (const value of values) rows.push(...telemetryCatalog.observation(value).cells.map(cell => telemetryCatalog.describe(cell)))
      return true
    },
  }
  const raw = new sdk.MnemionClient({ baseUrl: 'https://example.invalid', apiKey: 'private-fixture-key', retries: 1, fetch: async (url, options) => {
    requests.push({ url, ...options }); return fetch(url, options, requests.length)
  } })
  return { rows, requests, store, raw, client: measuredStudioClient(raw, store, 'browser'), reads: () => reads,
    disable: () => { enabled = false; stamp.revision++ } }
}

test('every legacy Studio method and browser connection action has fixed ownership', () => {
  assert.deepEqual([...new Set(actionCoverage.actions.filter(row => row.owner === 'legacy_ui').map(row => row.action))].sort(), Object.keys(legacyApi).sort())
  assert.deepEqual([...Object.keys(uiMeasurementOrigins.legacy), ...Object.keys(uiMeasurementOrigins.legacy_excluded)].sort(), Object.keys(legacyApi).sort())
  for (const group of [uiMeasurementOrigins.browser, uiMeasurementOrigins.legacy]) for (const spec of Object.values(group)) {
    assert.ok(telemetryCatalog.workflows.includes(spec.workflow))
    assert.ok(telemetryCatalog.specification.outcomes.includes(spec.completion))
  }
  for (const reason of Object.values(uiMeasurementOrigins.legacy_excluded)) assert.ok(Object.hasOwn(uiMeasurementOrigins.exclusions, reason))
})

test('browser sign-in and connection ownership never duplicates the native controller', async () => {
  const f = fixture(() => Response.json({}))
  const result = { token: 'PRIVATE_TOKEN', workspace: 'PRIVATE_WORKSPACE' }
  for (const action of Object.keys(uiMeasurementOrigins.browser)) {
    assert.equal(await measureUiAction('browser', action, () => result, undefined, f.store, 'desktop'), result)
  }
  assert.equal(f.reads(), 0)
  assert.equal(await measureUiAction('browser', 'sign_in', () => result, undefined, f.store, 'browser'), result)
  assert.equal(f.rows.filter(row => row.metric === 'submissions').length, 1)
  assert.ok(f.rows.every(row => row.workflow === 'workspace.sign_in'))
  assert.ok(!JSON.stringify(f.rows).includes('PRIVATE'))
})

test('legacy calls keep private arguments and outputs with the action, not the queue', async () => {
  const f = fixture(() => Response.json({}))
  const opaque = new Proxy({}, { get() { throw new Error('PRIVATE_PAYLOAD') } })
  let calls = 0
  const client = measuredLegacyClient({
    status: async () => { calls++; return { private: 'PRIVATE_STATUS' } },
    search: async value => { calls++; assert.equal(value, opaque); return { private: 'PRIVATE_RESULT' } },
  }, f.store, 'browser')
  await client.status()
  assert.equal(f.reads(), 0)
  assert.equal((await client.search(opaque)).private, 'PRIVATE_RESULT')
  assert.equal(calls, 2)
  assert.equal(f.rows.filter(row => row.metric === 'submissions').length, 1)
  assert.ok(!JSON.stringify(f.rows).includes('PRIVATE'))
})

test('legacy failure flags and unfamiliar results cannot report a successful action', async () => {
  const f = fixture(() => Response.json({}))
  const failed = { success: false, note: 'PRIVATE_DIAGNOSTIC' }
  assert.equal(await measureUiAction('legacy', 'installConnector', () => failed, undefined, f.store, 'desktop'), failed)
  assert.ok(f.rows.some(row => row.metric === 'outcomes' && row.bucket === 'failed'))
  const count = f.rows.length
  const unfamiliar = { get success() { throw new Error('PRIVATE_DIAGNOSTIC') } }
  assert.equal(await measureUiAction('legacy', 'installConnector', () => unfamiliar, undefined, f.store, 'desktop'), unfamiliar)
  assert.equal(f.rows.length, count)
})

test('late browser actions respect opt-out and company-login cancellation', async () => {
  const f = fixture(() => Response.json({})), controller = new AbortController()
  await measureUiAction('browser', 'sign_in', () => { controller.abort(); return 'closed' }, controller.signal, f.store, 'browser')
  assert.ok(f.rows.some(row => row.metric === 'outcomes' && row.bucket === 'cancelled'))
  const count = f.rows.length
  await measureUiAction('browser', 'connect', () => { f.disable(); return 'connected' }, undefined, f.store, 'browser')
  assert.equal(f.rows.length, count)
})

test('optional UI storage failure and fixed-name exclusions preserve the original action', async () => {
  const f = fixture(() => Response.json({}))
  await measureUiAction('legacy', 'status', () => true, undefined, f.store, 'browser')
  assert.equal(f.reads(), 0)
  f.store.snapshot = () => new Promise(() => {})
  const start = performance.now(), original = new Error('PRIVATE_ACTION_FAILURE')
  await assert.rejects(measureUiAction('browser', 'connect', () => { throw original }, undefined, f.store, 'browser'), error => error === original)
  assert.ok(performance.now() - start < 250)
  assert.equal(f.rows.length, 0)
})

test('an immediate refusal does not schedule a timer or defer the original UI action', async t => {
  const f = fixture(() => Response.json({})), result = { private: 'PRIVATE_ACTION_RESULT' }
  f.store.snapshot = () => null
  t.mock.method(globalThis, 'setTimeout', () => { throw new Error('Refused telemetry created a timer') })
  let called = false
  const pending = measureUiAction('browser', 'connect', () => { called = true; return result }, undefined, f.store, 'browser')
  assert.equal(called, true)
  assert.equal(await pending, result)
  assert.equal(f.rows.length, 0)
})

test('all current SDK methods have a reviewed Studio owner or explicit exclusion', () => {
  const names = Object.getOwnPropertyNames(sdk.MnemionClient.prototype).filter(name => name !== 'constructor')
  assert.deepEqual([...new Set(actionCoverage.actions.filter(row => row.owner === 'studio_actions').map(row => row.action))].sort(), names.sort())
  assert.deepEqual([...Object.keys(methods.methods), ...Object.keys(methods.excluded)].sort(), names.sort())
  for (const [name, operation] of Object.entries(methods.methods)) {
    assert.ok(controls.operations[operation] && !controls.operations[operation].exclusion, name)
    const spec = controls.operations[operation]
    for (const workflow of spec.variants ? Object.values(spec.variants) : [spec.workflow]) assert.ok(telemetryCatalog.workflows.includes(workflow), name)
  }
  assert.equal(studioMeasurementSelection('request', []), null)
  assert.equal(studioMeasurementSelection('decideLibrarian', ['private', 'private', 'PRIVATE_SENTINEL']), null)
})

test('generic SDK calls and automatic UI queries never acquire a telemetry owner', async () => {
  const instance = fixture(() => Response.json({ items: [], hits: [], nodes: [] }))
  await instance.raw.search({ query: 'PRIVATE_SENTINEL' })
  await instance.client.list('private-space')
  await instance.client.knowledge({ space_ids: ['private-space'] })
  await instance.client.request('POST', '/v1/recall', { body: { query: 'PRIVATE_SENTINEL' } })
  assert.equal(instance.reads(), 0)
  assert.deepEqual(instance.rows, [])
  assert.equal(instance.requests.length, 4)
})

test('capture admin actions count only their fresh response and preserve private request data', async () => {
  for (const surface of ['desktop', 'browser']) for (const disposition of ['new', 'replayed', null, 'PRIVATE_UNKNOWN']) {
    const instance = fixture(() => Response.json({ source: { name: 'PRIVATE_SOURCE' }, review_token: 'PRIVATE_REVIEW' }, {
      headers: disposition ? { 'X-Mnemion-Idempotency': disposition } : {},
    }))
    const client = measuredStudioClient(instance.raw, instance.store, surface)
    const input = { expected_version: 2, review_token: 'PRIVATE_REVIEW', capture_policy: { include: ['PRIVATE_PATH'] }, previous_grants: 'retain', confirm: true }
    const result = await client.changeCapturePolicy('PRIVATE_CONNECTOR', 'PRIVATE_SOURCE', 'PRIVATE_TRANSITION', input)
    await client.revokeCaptureGrant('PRIVATE_GRANT')
    assert.equal(result.source.name, 'PRIVATE_SOURCE')
    assert.deepEqual(JSON.parse(instance.requests[0].body), input)
    assert.equal(instance.requests.length, 2)
    const submissions = instance.rows.filter(row => row.metric === 'submissions')
    assert.deepEqual(submissions.map(row => row.workflow).sort(), disposition === 'new' ? ['capture.configure', 'capture.remove'] : [])
    assert.ok(instance.rows.every(row => row.surface === surface))
    assert.ok(!JSON.stringify(instance.rows).includes('PRIVATE'))
  }
})

test('capture admin opt-out, legacy replies and generic transport do not create an owner', async () => {
  const instance = fixture(() => Response.json({ private: 'PRIVATE_CAPTURE' }, { headers: { 'X-Mnemion-Idempotency': 'new' } }))
  await instance.raw.revokeCaptureGrant('PRIVATE_GRANT')
  await instance.client.request('DELETE', '/v1/capture-grants/PRIVATE_GRANT')
  assert.equal(instance.reads(), 0)
  instance.disable()
  await instance.client.revokeCaptureGrant('PRIVATE_GRANT')
  assert.deepEqual(instance.rows, [])
})

test('capture admin completion cannot revive a choice disabled while its request was pending', async () => {
  let resolve
  const instance = fixture(() => new Promise(done => { resolve = done }))
  const pending = instance.client.revokeCaptureGrant('PRIVATE_GRANT')
  while (!resolve) await new Promise(done => setImmediate(done))
  instance.disable()
  resolve(Response.json({ revoked_at: 'PRIVATE_TIME' }, { headers: { 'X-Mnemion-Idempotency': 'new' } }))
  assert.equal((await pending).revoked_at, 'PRIVATE_TIME')
  assert.deepEqual(instance.rows, [])
})

test('an explicit Studio search measures fixed outcome and result-count buckets only', async () => {
  const instance = fixture(() => Response.json({ query: 'PRIVATE_SENTINEL', request_id: 'PRIVATE_ID', hits: [{ text: 'PRIVATE_MEMORY' }] }))
  const result = await instance.client.search({ query: 'PRIVATE_SENTINEL', all_accessible: true })
  assert.equal(result.hits[0].text, 'PRIVATE_MEMORY')
  assert.equal(instance.requests[0].headers.Authorization, 'Bearer private-fixture-key')
  assert.equal(JSON.parse(instance.requests[0].body).query, 'PRIVATE_SENTINEL')
  assert.equal(instance.reads(), 1)
  assert.ok(instance.rows.some(row => row.workflow === 'memory.recall' && row.metric === 'result_items'))
  assert.ok(instance.rows.some(row => row.metric === 'outcomes' && row.bucket === 'success'))
  assert.ok(!JSON.stringify(instance.rows).includes('PRIVATE'))
  assert.equal(measuredStudioClient(instance.client, instance.store, 'browser'), instance.client)
  assert.equal(instance.client.constructor, sdk.MnemionClient)
})

test('cached and legacy writes do not become new workflow counts', async () => {
  const instance = fixture((_url, _input, count) => Response.json({ state: 'accepted', memory_id: 'PRIVATE_SENTINEL' }, {
    headers: count === 3 ? {} : { 'X-Mnemion-Idempotency': count === 1 ? 'new' : 'replayed' },
  }))
  await instance.client.save('private-space', { content: 'PRIVATE_SENTINEL' }, 'private-request')
  const count = instance.rows.length
  assert.ok(count > 0)
  await instance.client.save('private-space', { content: 'PRIVATE_SENTINEL' }, 'private-request')
  await instance.client.save('private-space', { content: 'PRIVATE_SENTINEL' }, 'new-private-request')
  assert.equal(instance.rows.length, count)
  assert.ok(instance.rows.some(row => row.metric === 'outcomes' && row.bucket === 'accepted'))
})

test('an SDK retry preserves its idempotency key and suppresses the replayed receipt', async () => {
  const instance = fixture((_url, _input, count) => {
    if (count === 1) throw new TypeError('PRIVATE_SENTINEL lost response')
    return Response.json({ state: 'accepted' }, { headers: { 'X-Mnemion-Idempotency': 'replayed' } })
  })
  await instance.client.save('space', { content: 'PRIVATE_SENTINEL' }, 'one-request')
  assert.equal(instance.requests.length, 2)
  assert.ok(instance.requests.every(row => row.headers['Idempotency-Key'] === 'one-request'))
  assert.deepEqual(instance.rows, [])
})

test('fixed variant enums and binary exports do not disclose vault values or sizes', async () => {
  const instance = fixture(url => url.includes('/vault/export') ? Response.json({ ciphertext: 'PRIVATE_SENTINEL', size: 125678 })
    : Response.json({ state: 'ready' }, { headers: { 'X-Mnemion-Idempotency': 'new' } }))
  await instance.client.decideLibrarian('space', 'proposal', 'accept', 1, 'request')
  await instance.client.controlReindex('space', 'run', 'pause', 1)
  await instance.client.exportVault(['private-entry'], 'private-key')
  assert.ok(instance.rows.some(row => row.workflow === 'librarian.accept'))
  assert.ok(instance.rows.some(row => row.workflow === 'models.pause'))
  assert.ok(instance.rows.some(row => row.workflow === 'vault.export'))
  assert.ok(instance.rows.filter(row => row.workflow === 'vault.export').every(row => ['submissions', 'outcomes', 'latency_ms'].includes(row.metric)))
  assert.ok(!JSON.stringify(instance.rows).includes('PRIVATE_SENTINEL'))
})

test('app failures preserve the original diagnostic but measure only fixed status categories', async () => {
  const instance = fixture(() => Response.json({ request_id: 'PRIVATE_ID', error: { code: 'denied', message: 'PRIVATE_SENTINEL' } }, { status: 403 }))
  await assert.rejects(instance.client.search({ query: 'PRIVATE_QUERY' }), error => error instanceof sdk.MnemionError && error.message === 'PRIVATE_SENTINEL')
  assert.ok(instance.rows.some(row => row.metric === 'reasons' && row.bucket === 'authorization'))
  assert.ok(!JSON.stringify(instance.rows).includes('PRIVATE'))
  const count = instance.rows.length
  await assert.rejects(instance.client.save('space', { content: 'private' }), /PRIVATE_SENTINEL/)
  assert.equal(instance.rows.length, count, 'an uncertain keyed-write failure is not a fresh receipt')
})

test('an opt-out during a real request prevents its eventual result being measured', async () => {
  let release
  const ready = new Promise(resolve => { release = resolve })
  const instance = fixture(async () => { await ready; return Response.json({ hits: [] }) })
  const pending = instance.client.search({ query: 'PRIVATE_SENTINEL' })
  while (!instance.requests.length) await new Promise(resolve => setTimeout(resolve, 1))
  instance.disable(); release()
  await pending
  assert.deepEqual(instance.rows, [])
})

test('blocked privacy storage adds only a bounded startup wait and leaves the action usable', async () => {
  const instance = fixture(() => Response.json({ hits: [] }))
  instance.store.snapshot = () => new Promise(() => {})
  const started = performance.now()
  const result = await instance.client.search({ query: 'private' })
  assert.deepEqual(result.hits, [])
  assert.ok(performance.now() - started < 250)
  assert.deepEqual(instance.rows, [])
})

function refuse(store, mode) {
  if (mode === 'unavailable') store.available = false
  else if (mode === 'immediate') store.snapshot = () => null
  else if (mode === 'asynchronous') store.snapshot = async () => null
  else if (mode === 'failed') store.snapshot = async () => { throw new Error('PRIVATE_POLICY_FAILURE') }
  else store.snapshot = () => new Promise(() => {})
}

test('refused telemetry leaves Studio results opaque on desktop and browser', async () => {
  for (const surface of ['desktop', 'browser']) for (const mode of ['unavailable', 'immediate', 'asynchronous', 'failed', 'timeout']) {
    const f = fixture(() => Response.json({}))
    refuse(f.store, mode)
    let calls = 0, inspected = 0
    const result = { get hits() { inspected++; return [{ content: 'PRIVATE_RESULT' }] } }
    f.raw.search = async input => { calls++; assert.equal(input.query, 'PRIVATE_QUERY'); return result }
    f.raw.idempotencyOf = () => { inspected++; return 'new' }
    const client = measuredStudioClient(f.raw, f.store, surface)
    assert.equal(await client.search({ query: 'PRIVATE_QUERY' }), result)
    assert.equal(calls, 1)
    assert.equal(inspected, 0, `${surface}/${mode} inspected an unmeasured result`)
    assert.deepEqual(f.rows, [])
  }
})

test('refused telemetry leaves Studio errors opaque and never retries the callback', async () => {
  for (const surface of ['desktop', 'browser']) for (const mode of ['unavailable', 'immediate', 'asynchronous', 'failed', 'timeout']) {
    const f = fixture(() => Response.json({}))
    refuse(f.store, mode)
    let calls = 0, inspected = 0
    const original = new Error('PRIVATE_ACTION_ERROR')
    f.raw.save = () => { calls++; throw original }
    f.raw.idempotencyOf = () => { inspected++; return 'new' }
    const client = measuredStudioClient(f.raw, f.store, surface)
    await assert.rejects(client.save('PRIVATE_SPACE', { content: 'PRIVATE_MEMORY' }), error => error === original)
    assert.equal(calls, 1)
    assert.equal(inspected, 0, `${surface}/${mode} classified an unmeasured error`)
    assert.deepEqual(f.rows, [])
  }
})

test('refused telemetry leaves legacy success flags opaque and preserves callback errors', async () => {
  for (const surface of ['desktop', 'browser']) for (const mode of ['unavailable', 'immediate', 'asynchronous', 'failed', 'timeout']) {
    const f = fixture(() => Response.json({}))
    refuse(f.store, mode)
    let calls = 0, inspected = 0
    const result = { get success() { inspected++; return true } }
    assert.equal(await measureUiAction('legacy', 'installConnector', () => { calls++; return result }, undefined, f.store, surface), result)
    const original = new Error('PRIVATE_LEGACY_FAILURE')
    await assert.rejects(measureUiAction('legacy', 'installConnector', () => { calls++; throw original }, undefined, f.store, surface), error => error === original)
    assert.equal(calls, 2)
    assert.equal(inspected, 0, `${surface}/${mode} inspected an unmeasured success flag`)
    assert.deepEqual(f.rows, [])
  }
})

test('refused telemetry is not revived by a snapshot that finishes after the action', async () => {
  for (const owner of ['studio', 'legacy']) {
    const f = fixture(() => Response.json({}))
    let complete, calls = 0, inspected = 0
    f.store.snapshot = () => new Promise(resolve => { complete = resolve })
    const result = { get hits() { inspected++; return [] }, get success() { inspected++; return true } }
    f.raw.search = async () => { calls++; return result }
    f.raw.idempotencyOf = () => { inspected++; return 'new' }
    const pending = owner === 'studio' ? f.client.search({ query: 'PRIVATE_QUERY' })
      : measureUiAction('legacy', 'installConnector', () => { calls++; return result }, undefined, f.store, 'browser')
    assert.equal(await pending, result)
    complete({ revision: 1, store_generation: 'a'.repeat(32) })
    await new Promise(resolve => setImmediate(resolve))
    assert.equal(calls, 1)
    assert.equal(inspected, 0, `${owner} inspected an action after the measurement timed out`)
    assert.deepEqual(f.rows, [])
  }
})

test('a workflow finishes once and rejects private fields before counting a submission', async () => {
  const instance = fixture(() => Response.json({}))
  const first = await TelemetryWorkflow.begin(instance.store, 'memory.recall', 'browser')
  await first.finish('success', 'none', { private_text: 'PRIVATE_SENTINEL' })
  assert.deepEqual(instance.rows, [])
  const second = await TelemetryWorkflow.begin(instance.store, 'memory.recall', 'browser')
  await second.finish('success')
  const count = instance.rows.length
  await second.finish('failed', 'other_failure')
  assert.equal(instance.rows.length, count)
})
