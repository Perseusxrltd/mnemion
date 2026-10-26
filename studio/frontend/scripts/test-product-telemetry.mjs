import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { spawnSync } from 'node:child_process'
import assert from 'node:assert/strict'
import { test } from 'node:test'
import ts from 'typescript'

const path = new URL('../src/workspace/telemetry-policy.ts', import.meta.url)
const modules = new Map()
const jsonImports = new Set()
function load(url) {
  if (modules.has(url.href)) return modules.get(url.href)
  const exported = {}
  modules.set(url.href, exported)
  const code = ts.transpileModule(readFileSync(url, 'utf8'), { compilerOptions: {
    target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, esModuleInterop: true,
  } }).outputText
  const local = createRequire(url)
  new Function('require', 'exports', code)(name => {
    if (name.endsWith('.json')) jsonImports.add(name)
    return name.startsWith('.') && !name.endsWith('.json')
      ? load(new URL(name.replace(/\.js$/, '') + '.ts', url)) : local(name)
  }, exported)
  return exported
}
const exported = load(path)
const { BrowserTelemetry, choiceKey, queueKey } = exported
const { telemetryCatalog, pendingState, collect } = load(new URL('../src/workspace/telemetry-aggregate.ts', import.meta.url))
const { TelemetrySnapshotReader } = load(new URL('../src/workspace/telemetry-refusals.ts', import.meta.url))
const contract = createRequire(path)('../../../../mnemion/product_telemetry/disclosure.json')

function installation() {
  const values = new Map()
  const storage = { getItem: key => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value), removeItem: key => values.delete(key) }
  let company = { state: 'unmanaged', enabled: true, metric_groups: ['usage'] }
  const client = () => new BrowserTelemetry(() => storage, () => company, () => false, () => true)
  return { values, storage, client, company: value => { company = value } }
}

test('the app preview loads source coverage only on demand without changing privacy state', async () => {
  const { storage, values } = installation()
  assert.equal([...jsonImports].some(name => name.endsWith('/workflow-coverage.json')), false)
  const previous = Object.fromEntries(['window', 'navigator', 'document'].map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)]))
  Object.defineProperty(globalThis, 'window', { configurable: true, value: { location: { protocol: 'https:' }, localStorage: storage } })
  Object.defineProperty(globalThis, 'navigator', { configurable: true, value: { locks: {} } })
  Object.defineProperty(globalThis, 'document', { configurable: true, value: { querySelector: () => null } })
  try {
    const preview = await exported.telemetryPreview()
    assert.equal([...jsonImports].some(name => name.endsWith('/workflow-coverage.json')), true)
    const coverage = JSON.parse(readFileSync(new URL('../../../mnemion/product_telemetry/workflow-coverage.json', import.meta.url), 'utf8'))
    assert.deepEqual(preview.workflow_coverage, coverage)
    assert.deepEqual(preview.workflow_coverage.workflows.find(row => row.workflow === 'update.rollback'), {
      workflow: 'update.rollback', state: 'mapped', owners: ['host_updates'],
    })
    assert.deepEqual(preview.workflow_coverage.workflows.find(row => row.workflow === 'update.verify'), {
      workflow: 'update.verify', state: 'unmeasured', owners: [],
    })
    assert.equal(preview.outbound_body, null)
    assert.equal(preview.outbound_bytes, 0)
    assert.equal(preview.status.effective_enabled, false)
    assert.equal(values.size, 0)
  } finally {
    for (const [key, descriptor] of Object.entries(previous)) {
      if (descriptor) Object.defineProperty(globalThis, key, descriptor)
      else delete globalThis[key]
    }
  }
})

test('reading the browser policy creates nothing and requires actual disclosure', () => {
  const { client, values } = installation()
  assert.equal(client().status().reason, 'disclosure_required')
  assert.equal(client().status().user_enabled, true)
  assert.equal(values.size, 0)
  assert.equal(client().preview().outbound_bytes, 0)
})

test('another tab cannot re-enable after a newer opt-out even if it was already off', () => {
  const { client, storage } = installation()
  const first = client(), second = client()
  const off = first.configure({ enabled: false, expected_revision: 0 })
  storage.setItem(queueKey, '[{"cell":7,"count":2,"window_day":20000}]')
  const repeated = second.configure({ enabled: false, expected_revision: 0 })
  assert.ok(repeated.revision > off.revision)
  assert.equal(storage.getItem(queueKey), null)
  assert.throws(() => first.configure({ enabled: true, expected_revision: off.revision }), /changed in another tab/)
  const on = first.configure({ enabled: true, expected_revision: repeated.revision, expected_generation: repeated.store_generation })
  assert.equal(on.reason, 'disclosure_required')
  assert.equal(on.pending_records, 0)
  assert.deepEqual(client().status(), on)
})

test('a permissive company policy cannot override an explicit opt-out', () => {
  const instance = installation(), client = instance.client()
  instance.company({ state: 'restricted', enabled: false, metric_groups: [] })
  assert.equal(client.status().reason, 'company_policy')
  client.configure({ enabled: false, expected_revision: 0 })
  instance.company({ state: 'restricted', enabled: true, metric_groups: ['usage'] })
  assert.equal(client.status().reason, 'user_disabled')
})

test('connection choices do not acknowledge disclosure and stale opt-out preserves newer settings', () => {
  const { client } = installation(), first = client(), second = client()
  const current = first.configure({ enabled: true, expected_revision: 0, connection_mode: 'unmetered' })
  assert.equal(current.connection_mode, 'unmetered')
  assert.equal(current.disclosure_version, 0)
  assert.equal(current.effective_enabled, false)
  const off = second.configure({ enabled: false, expected_revision: 0, connection_mode: 'metered' })
  assert.equal(off.reason, 'user_disabled')
  assert.equal(off.connection_mode, 'unmetered')
  const retained = first.configure({ enabled: true, expected_revision: off.revision, expected_generation: off.store_generation })
  assert.equal(retained.connection_mode, 'unmetered')
  assert.throws(() => first.configure({ enabled: true, expected_revision: off.revision,
    expected_generation: off.store_generation, connection_mode: 'auto' }), /changed in another tab/)
})

test('arbitrary connection choices never enter browser storage', () => {
  for (const connection_mode of [null, true, 1, [], {}, 'wifi', 'PRIVATE_SENTINEL']) {
    const { client, values } = installation()
    assert.throws(() => client().configure({ enabled: false, expected_revision: 0, connection_mode }), /Choose whether/)
    assert.equal(values.size, 0)
  }
})

test('corrupt private preference and pending bytes stay out of status and preview', () => {
  for (const key of [choiceKey, queueKey]) {
    const { storage, client } = installation()
    storage.setItem(key, 'PRIVATE_SENTINEL')
    const result = client().preview()
    assert.equal(result.status.reason, 'storage_unavailable')
    assert.equal(result.status.effective_enabled, false)
    assert.equal(result.status.pending_records, null)
    assert.ok(!JSON.stringify(result).includes('PRIVATE_SENTINEL'))
    assert.equal(storage.getItem(key), 'PRIVATE_SENTINEL')
  }
})

test('failed preference writes keep the current tab off even when reads still work', () => {
  const { storage, client } = installation()
  const current = client()
  storage.setItem = () => { throw new Error('PRIVATE_SENTINEL quota failure') }
  assert.throws(() => current.configure({ enabled: false, expected_revision: 0 }), /Product telemetry stays off/)
  assert.equal(current.status().reason, 'storage_unavailable')
  assert.equal(current.status().effective_enabled, false)
  assert.ok(!JSON.stringify(current.status()).includes('PRIVATE_SENTINEL'))
})

test('unavailable coordination and browser privacy each prevent an effective opt-in', () => {
  const { storage } = installation()
  const company = () => ({ state: 'unmanaged', enabled: true, metric_groups: ['usage'] })
  assert.equal(new BrowserTelemetry(() => storage, company, () => false, () => false).status().reason, 'coordination_unavailable')
  assert.equal(new BrowserTelemetry(() => storage, company, () => true, () => true).status().reason, 'browser_privacy')
})

test('unknown fields and a not-yet-available collector cannot be preapproved', () => {
  const { client, values } = installation()
  assert.throws(() => client().configure({ enabled: false, expected_revision: 0, token: 'PRIVATE_SENTINEL' }), /Choose whether/)
  assert.throws(() => client().configure({ enabled: true, expected_revision: 0, disclosure_version: 1 }), /Collection is not available/)
  assert.equal(values.size, 0)
})

function available(run) {
  const saved = { collection_available: contract.collection_available, destination: contract.destination }
  Object.assign(contract, { collection_available: true, destination: 'https://example.invalid/telemetry' })
  try { run() } finally { Object.assign(contract, saved) }
}

const measured = extra => ({ kind: 'outcome', workflow: 'memory.recall', surface: 'browser', outcome: 'success', ...extra })

test('browser format preview is read-only and never claims an actual queued packet', () => available(() => {
  contract.destination = 'https://example.invalid/v1/report'
  const instance = installation(), client = instance.client()
  const empty = client.preview()
  assert.equal(instance.values.size, 0)
  const example = empty.illustrative_packet
  assert.equal(example.kind, 'synthetic_example')
  assert.equal(example.body_encoding, 'base64')
  assert.deepEqual(Buffer.from(example.body_base64, 'base64'), Buffer.from([2, 0, 7, 0]))
  assert.equal(empty.outbound_state, 'not_inspected')
  assert.equal(empty.outbound_body, null)
  assert.equal(empty.outbound_bytes, 0)
  assert.equal(empty.status.effective_enabled, false)
  assert.equal(empty.transport_available, true)
  client.delivery.reserve = () => { assert.fail('Preview tried to reserve a delivery') }
  const current = client.configure({ enabled: true, expected_revision: 0, disclosure_version: 1 })
  assert.equal(client.record(measured(), current), true)
  const saved = [...instance.values]
  const counted = client.preview()
  assert.ok(counted.local_aggregates.length > 0)
  assert.deepEqual(counted.illustrative_packet, example)
  assert.deepEqual(client.preview(), counted)
  assert.deepEqual([...instance.values], saved)
  client.configure({ enabled: false, expected_revision: current.revision })
  const off = [...instance.values]
  const disabled = client.preview()
  assert.equal(disabled.transport_available, true)
  assert.equal(disabled.status.delivery_budget.transport_available, true)
  assert.equal(disabled.status.effective_enabled, false)
  assert.deepEqual(disabled.local_aggregates, [])
  assert.deepEqual(disabled.illustrative_packet, example)
  assert.deepEqual([...instance.values], off)
}))

test('browser capability reports only a configured HTTPS route, independent of permission', () => available(() => {
  const { client, values } = installation()
  for (const [destination, expected] of [
    ['https://example.invalid/v1/report', true], ['http://example.invalid/v1/report', false],
    ['https://secret@example.invalid/v1/report', false], ['https://example.invalid/other', false],
    ['https://example.invalid/v1/report?secret=PRIVATE_SENTINEL', false], [null, false],
  ]) {
    contract.destination = destination
    const preview = client().preview()
    assert.equal(preview.transport_available, expected)
    assert.equal(preview.status.delivery_budget.transport_available, expected)
    assert.equal(preview.status.effective_enabled, false)
  }
  assert.equal(values.size, 0)
}))

test('browser queue stores coarse cells, rejects content and obeys contribution bounds', () => available(() => {
  const instance = installation(), client = instance.client()
  instance.company({ state: 'unmanaged', enabled: true, metric_groups: ['usage', 'performance'] })
  const current = client.configure({ enabled: true, expected_revision: 0, disclosure_version: 1 })
  const day = Math.floor(Date.now() / 86400000)
  assert.equal(client.record(measured({ latency_ms: 123.456, result_items: 37 }), current, day), true)
  assert.equal(client.record(measured({ query: 'PRIVATE_SENTINEL' }), current, day), false)
  for (let index = 1; index < 80; index++) client.record(measured({ latency_ms: 123.456, result_items: 37 }), current, day)
  const queue = pendingState(instance.storage.getItem(queueKey))
  assert.equal(queue.entries.length, 3)
  assert.ok(queue.entries.every(row => row.count === 64))
  assert.equal(queue.contributions.length, 1)
  assert.ok(!instance.storage.getItem(queueKey).includes('123.456'))
  assert.ok(!instance.storage.getItem(queueKey).includes('PRIVATE_SENTINEL'))
  assert.equal(client.preview().local_aggregates.length, 3)
  const off = client.configure({ enabled: false, expected_revision: current.revision })
  assert.equal(instance.storage.getItem(queueKey), null)
  const again = client.configure({ enabled: true, expected_revision: off.revision, expected_generation: off.store_generation, disclosure_version: 1 })
  assert.equal(client.record(measured(), current, day), false)
  assert.equal(client.record(measured(), again, day), true)
}))

test('browser expiry, storage loss, company narrowing and write faults suppress old aggregates', () => available(() => {
  const instance = installation(), client = instance.client()
  instance.company({ state: 'unmanaged', enabled: true, metric_groups: ['usage', 'performance'] })
  const current = client.configure({ enabled: true, expected_revision: 0, disclosure_version: 1 })
  assert.equal(client.record(measured({ latency_ms: 10 }), current, 20000), true)
  instance.company({ state: 'restricted', enabled: true, metric_groups: ['usage'] })
  assert.equal(client.record(measured({ latency_ms: 10 }), current, 20000), true)
  assert.equal(pendingState(instance.storage.getItem(queueKey)).entries.length, 1)
  assert.equal(client.record(measured(), current, 20003), true)
  assert.equal(pendingState(instance.storage.getItem(queueKey)).entries[0].count, 1)
  instance.storage.removeItem(choiceKey)
  assert.equal(client.record(measured(), current, 20003), false)
  assert.equal(client.status().reason, 'disclosure_required')
  const restored = client.configure({ enabled: true, expected_revision: 0, disclosure_version: 1 })
  assert.equal(restored.pending_records, 0)
  assert.equal(restored.revision, current.revision)
  assert.notEqual(restored.store_generation, current.store_generation)
  assert.equal(client.record(measured(), current, 20003), false)
  assert.throws(() => client.configure({ enabled: true, expected_revision: current.revision,
    expected_generation: current.store_generation, disclosure_version: 1 }), /changed in another tab/)
  instance.storage.setItem = () => { throw new Error('PRIVATE_SENTINEL') }
  assert.equal(client.record(measured(), restored, 20003), false)
  assert.equal(client.status().reason, 'storage_unavailable')
}))

test('old browser preferences retain opt-out and gain a private generation on explicit choice', () => {
  const { storage, client } = installation()
  storage.setItem(choiceKey, JSON.stringify({ schema_version: 1, revision: 17, enabled: false, disclosure_version: 0 }))
  const before = client().status()
  assert.equal(before.reason, 'user_disabled')
  assert.equal(before.store_generation, null)
  const after = client().configure({ enabled: false, expected_revision: 17 })
  assert.equal(after.user_enabled, false)
  assert.match(after.store_generation, /^[0-9a-f]{32}$/)
  assert.equal(after.revision, 18)
  const invalid = JSON.parse(storage.getItem(choiceKey))
  invalid.store_generation = 'PRIVATE_SENTINEL'
  storage.setItem(choiceKey, JSON.stringify(invalid))
  assert.equal(client().status().reason, 'storage_unavailable')
  assert.ok(!JSON.stringify(client().status()).includes('PRIVATE_SENTINEL'))
})

test('the browser cannot turn invalid cells, duplicate rows or arbitrary sizes into measurements', () => {
  for (const bad of [null, true, -1, NaN, Infinity, Number.MAX_SAFE_INTEGER + 1, 'PRIVATE_SENTINEL', { secret: 'PRIVATE_SENTINEL' }]) {
    assert.throws(() => telemetryCatalog.observation(measured({ latency_ms: bad })), /^Error: telemetry_invalid_measurement$/)
  }
  for (const bad of [measured({ workflow: '__proto__' }), measured({ workflow: 'vault.write', payload_bytes_sent: 15 }), measured({ token: 'PRIVATE_SENTINEL' })]) {
    assert.throws(() => telemetryCatalog.observation(bad), /telemetry_invalid_measurement/)
  }
  assert.throws(() => pendingState(JSON.stringify({ catalog_version: 1, entries: [{ cell: 65535, count: 1, window_day: 20000 }], contributions: [] })))
  const state = collect(pendingState(null), measured(), 20000, ['usage']).state
  state.entries.push({ ...state.entries[0] })
  assert.throws(() => pendingState(JSON.stringify(state)), /telemetry_storage_unavailable/)
})

test('Python and TypeScript agree on all workflow coordinates and numeric bucket boundaries', () => {
  const catalog = telemetryCatalog.specification, values = []
  for (const workflow of telemetryCatalog.workflows) for (const surface of catalog.surfaces) {
    values.push({ kind: 'submission', workflow, surface })
    values.push(measured({ workflow, surface, latency_ms: 123 }))
  }
  for (const [name, metric] of Object.entries(catalog.metrics)) {
    const family = metric.families === 'all' ? 'memory' : metric.families[0]
    const workflow = `${family}.${catalog.workflows[family][0]}`
    for (const value of [0, ...metric.upper_bounds.flatMap(bound => [bound, bound + 0.5]), Number.MAX_SAFE_INTEGER]) values.push(measured({ workflow, [name]: value }))
  }
  for (const [metric, spec] of Object.entries(catalog.resource_metrics)) for (const value of [0, ...spec.upper_bounds, Number.MAX_SAFE_INTEGER]) values.push({ kind: 'resource', metric, value })
  const program = `import json,sys\nfrom mnemion.product_telemetry.catalog import observation,describe\nresults=[]\nfor value in json.load(sys.stdin):\n scope,cells=observation(value)\n results.append({'scope':scope,'cells':list(cells),'descriptions':[describe(cell) for cell in cells]})\nprint(json.dumps(results))\n`
  const result = spawnSync(process.platform === 'win32' ? 'python' : 'python3', ['-c', program], {
    cwd: new URL('../../../', import.meta.url), input: JSON.stringify(values), encoding: 'utf8', maxBuffer: 2 * 1024 * 1024, timeout: 30000,
  })
  assert.equal(result.status, 0, result.stderr)
  const expected = values.map(value => {
    const encoded = telemetryCatalog.observation(value)
    return { ...encoded, descriptions: encoded.cells.map(cell => telemetryCatalog.describe(cell)) }
  })
  assert.deepEqual(JSON.parse(result.stdout), expected)
})

async function browserGlobals(run) {
  const instance = installation()
  const original = { collection_available: contract.collection_available, destination: contract.destination }
  const globals = Object.fromEntries(['window', 'document', 'navigator'].map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)]))
  let release, attempts = 0
  const locks = { request(_name, _options, callback) {
    attempts++
    return new Promise(resolve => { release = lock => resolve(callback(lock)) })
  } }
  Object.defineProperty(globalThis, 'window', { configurable: true, value: { location: { protocol: 'https:' }, localStorage: instance.storage } })
  Object.defineProperty(globalThis, 'document', { configurable: true, value: { querySelector: () => null } })
  Object.defineProperty(globalThis, 'navigator', { configurable: true, value: { locks } })
  Object.assign(contract, { collection_available: true, destination: 'https://example.invalid/telemetry' })
  try { await run({ ...instance, release: value => release(value), attempts: () => attempts }) }
  finally {
    Object.assign(contract, original)
    for (const [key, descriptor] of Object.entries(globals)) {
      if (descriptor) Object.defineProperty(globalThis, key, descriptor)
      else delete globalThis[key]
    }
  }
}

test('desktop UI snapshots forward the fixed workflow and cannot choose another producer surface', async () => {
  await browserGlobals(async () => {
    const calls = [], stamp = { revision: 1, store_generation: 'a'.repeat(32) }
    window.mnemion = { productTelemetrySnapshot: async workflow => { calls.push(workflow); return stamp } }
    assert.equal(await exported.productWorkflowStore.snapshot('memory.recall', 'desktop'), stamp)
    assert.equal(await exported.productWorkflowStore.snapshot('memory.recall', 'native_agent'), null)
    assert.equal(await exported.productWorkflowStore.snapshot('memory.recall', 'browser'), null)
    assert.deepEqual(calls, ['memory.recall'])
  })
})

test('desktop refusal hints are scoped, expire within a second and never reuse permission', async () => {
  let now = 1000, result = null, calls = 0
  const reader = new TelemetrySnapshotReader(async () => { calls++; return result }, ['memory.recall', 'memory.save'], () => now)
  assert.equal(await reader.read('memory.recall'), null)
  now = 1999
  assert.equal(reader.read('memory.recall'), null)
  assert.equal(calls, 1)
  await reader.read('memory.save')
  assert.equal(calls, 2)
  now = 2000
  result = { revision: 1, store_generation: 'a'.repeat(32) }
  assert.equal(await reader.read('memory.recall'), result)
  result = { revision: 2, store_generation: 'b'.repeat(32) }
  assert.equal(await reader.read('memory.recall'), result)
  assert.equal(calls, 4)
})

test('explicit choice changes invalidate hints and prevent late responses from rebuilding them', async () => {
  let resolve, calls = 0
  const reader = new TelemetrySnapshotReader(() => { calls++; return new Promise(done => { resolve = done }) }, ['memory.recall'], () => 1000)
  const pending = reader.read('memory.recall')
  reader.clear()
  resolve(null)
  await pending
  const fresh = reader.read('memory.recall')
  assert.equal(calls, 2)
  resolve(null)
  await fresh
  assert.equal(reader.read('memory.recall'), null)
})

test('slow refusals and clock reversals cannot extend an old denial window', async () => {
  let now = 0, resolve, calls = 0
  const reader = new TelemetrySnapshotReader(() => { calls++; return new Promise(done => { resolve = done }) }, ['memory.recall'], () => now)
  const slow = reader.read('memory.recall')
  now = 1001
  resolve(null)
  await slow
  const fresh = reader.read('memory.recall')
  assert.equal(calls, 2)
  resolve(null)
  await fresh
  now = 1000
  const reversed = reader.read('memory.recall')
  assert.equal(calls, 3)
  resolve(null)
  await reversed
})

test('unknown and excess scopes receive fresh checks without expanding refusal storage', async () => {
  let calls = 0
  const scopes = Array.from({ length: 130 }, (_, index) => 'workflow.' + index)
  const reader = new TelemetrySnapshotReader(async () => { calls++; return null }, scopes, () => 1000)
  await reader.read(scopes[0])
  for (const workflow of [scopes[128], 'PRIVATE_UNKNOWN_WORKFLOW', undefined]) {
    await reader.read(workflow)
    await reader.read(workflow)
  }
  assert.equal(reader.read(scopes[0]), null)
  assert.equal(calls, 7)
})

test('the app choice control clears desktop refusal hints before the next action', async () => browserGlobals(async () => {
  let enabled = false, calls = 0
  const stamp = { revision: 2, store_generation: 'a'.repeat(32) }
  window.mnemion = {
    productTelemetrySnapshot: async () => { calls++; return enabled ? stamp : null },
    productTelemetry: async action => { assert.equal(action, 'telemetry.configure'); enabled = true; return {} },
  }
  assert.equal(await exported.productWorkflowStore.snapshot('memory.recall', 'desktop'), null)
  assert.equal(exported.productWorkflowStore.snapshot('memory.recall', 'desktop'), null)
  assert.equal(calls, 1)
  await exported.telemetryConfigure({ enabled: true, expected_revision: 1, expected_generation: 'a'.repeat(32) })
  assert.equal(await exported.productWorkflowStore.snapshot('memory.recall', 'desktop'), stamp)
  assert.equal(calls, 2)
}))

test('a browser lock wait retains the original validated primitives and privacy stamp', async () => browserGlobals(async instance => {
  const client = instance.client(), original = client.configure({ enabled: true, expected_revision: 0, disclosure_version: 1 })
  const input = measured({ latency_ms: 123.456 })
  const pending = exported.recordBrowserTelemetry(input, original)
  input.latency_ms = 'PRIVATE_SENTINEL'
  instance.release({ name: choiceKey })
  assert.equal(await pending, true)
  assert.ok(!instance.storage.getItem(queueKey).includes('PRIVATE_SENTINEL'))
  const next = exported.recordBrowserTelemetry(measured(), original)
  const off = client.configure({ enabled: false, expected_revision: original.revision })
  const on = client.configure({ enabled: true, expected_revision: off.revision, expected_generation: off.store_generation, disclosure_version: 1 })
  Object.assign(original, on)
  instance.release({ name: choiceKey })
  assert.equal(await next, false)
  assert.equal(instance.storage.getItem(queueKey), null)
}))

test('an unavailable browser lock drops a paired observation without retry or storage changes', async () => browserGlobals(async instance => {
  const current = instance.client().configure({ enabled: true, expected_revision: 0, disclosure_version: 1 })
  const values = [{ kind: 'submission', workflow: 'memory.recall', surface: 'browser' }, measured()]
  const pending = exported.recordBrowserTelemetryMany(values, current)
  instance.release(null)
  assert.equal(await pending, false)
  assert.equal(instance.attempts(), 1)
  assert.equal(instance.storage.getItem(queueKey), null)
  assert.equal(await exported.recordBrowserTelemetry(measured({ secret: 'PRIVATE_SENTINEL' }), current), false)
  assert.equal(instance.attempts(), 1)
}))
