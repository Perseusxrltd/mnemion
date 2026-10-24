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

test('all current SDK methods have a reviewed Studio owner or explicit exclusion', () => {
  const names = Object.getOwnPropertyNames(sdk.MnemionClient.prototype).filter(name => name !== 'constructor')
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
