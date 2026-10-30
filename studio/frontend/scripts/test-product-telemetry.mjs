import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { spawnSync } from 'node:child_process'
import assert from 'node:assert/strict'
import { test } from 'node:test'
import ts from 'typescript'

const path = new URL('../src/workspace/telemetry-policy.ts', import.meta.url)
const modules = new Map()
const jsonImports = new Set()
function load(url, cache = modules) {
  if (cache.has(url.href)) return cache.get(url.href)
  const exported = {}
  cache.set(url.href, exported)
  const code = ts.transpileModule(readFileSync(url, 'utf8'), { compilerOptions: {
    target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, esModuleInterop: true,
  } }).outputText
  const local = createRequire(url)
  new Function('require', 'exports', code)(name => {
    if (name.endsWith('.json')) jsonImports.add(name)
    return name.startsWith('.') && !name.endsWith('.json')
      ? load(new URL(name.replace(/\.js$/, '') + '.ts', url), cache) : local(name)
  }, exported)
  return exported
}
const exported = load(path)
const { BrowserTelemetry, choiceKey, queueKey } = exported
const { telemetryCatalog, pendingState, collect } = load(new URL('../src/workspace/telemetry-aggregate.ts', import.meta.url))
const { TelemetrySnapshotReader } = load(new URL('../src/workspace/telemetry-refusals.ts', import.meta.url))
const { needsTelemetrySetup, telemetrySetupChoice } = load(new URL('../src/workspace/telemetry-setup.ts', import.meta.url))
const contract = createRequire(path)('../../../../mnemion/product_telemetry/disclosure.json')

test('old browser cells and spent budgets survive catalog expansion without relabeling or a read rewrite', () => {
  const { TelemetryCatalog } = load(new URL('../../electron/telemetry-catalog.ts', import.meta.url))
  const fixture = JSON.parse(readFileSync(new URL('../../../tests/fixtures/telemetry-catalog-v1.json', import.meta.url), 'utf8'))
  const old = new TelemetryCatalog(fixture.catalog)
  assert.deepEqual(telemetryCatalog.workflows.slice(0, old.workflows.length), old.workflows)
  for (const workflow of old.workflows) for (const surface of fixture.catalog.surfaces) {
    const value = { kind: 'submission', workflow, surface }
    assert.deepEqual(telemetryCatalog.observation(value), old.observation(value))
    telemetryCatalog.validateObservation(value)
    old.validateObservation(value)
  }
  const oldValue = { kind: 'submission', workflow: 'vault.export', surface: 'browser' }
  const encoded = old.observation(oldValue)
  assert.deepEqual(encoded, { scope: 93 * 4 + 1, cells: [93 * 512 + 128] })
  old.validateObservation(oldValue)
  telemetryCatalog.validateObservation(oldValue)
  const raw = JSON.stringify({ catalog_version: 1, entries: [{ cell: encoded.cells[0], count: 64, window_day: 20000 }],
    contributions: [{ scope: encoded.scope, count: 64, window_day: 20000 }] })
  const read = pendingState(raw)
  assert.equal(JSON.stringify(read), raw)
  assert.equal(collect(read, oldValue, 20000, ['usage']).recorded, false, 'Old spent capacity is not reset')
  const added = { kind: 'submission', workflow: 'capture.split', surface: 'browser' }
  const next = collect(read, added, 20000, ['usage'])
  assert.equal(next.recorded, true)
  assert.equal(next.state.catalog_version, 2)
  assert.deepEqual(next.state.entries[0], JSON.parse(raw).entries[0])
  assert.deepEqual(next.state.contributions[0], JSON.parse(raw).contributions[0])
  assert.deepEqual(pendingState(JSON.stringify(next.state)), next.state)
  const mislabeled = { ...next.state, catalog_version: 1 }
  assert.throws(() => pendingState(JSON.stringify(mislabeled)), /telemetry_storage_unavailable/)
  mislabeled.entries = [next.state.entries[0]]
  assert.throws(() => pendingState(JSON.stringify(mislabeled)), /telemetry_storage_unavailable/, 'A new contribution cannot masquerade as an old budget slot')
})

test('fixed catalog work reuses definitions instead of allocating lookup arrays per cell', t => {
  const { TelemetryCatalog } = load(new URL('../../electron/telemetry-catalog.ts', import.meta.url))
  const specification = structuredClone(telemetryCatalog.specification)
  const counts = { metricEnumerations: 0, resourceEnumerations: 0, familySplits: 0, bucketCallbacks: 0 }
  const bounds = new Set([...Object.values(specification.metrics), ...Object.values(specification.resource_metrics)]
    .map(metric => metric.upper_bounds))
  for (const [field, counter] of [['metrics', 'metricEnumerations'], ['resource_metrics', 'resourceEnumerations']]) {
    specification[field] = new Proxy(specification[field], { ownKeys(target) {
      counts[counter]++
      return Reflect.ownKeys(target)
    } })
  }
  const catalog = new TelemetryCatalog(specification)
  for (const name of Object.keys(counts)) counts[name] = 0
  const split = String.prototype.split, findIndex = Array.prototype.findIndex
  t.mock.method(String.prototype, 'split', function (...args) {
    if (String(this) === 'memory.recall' && args[0] === '.') counts.familySplits++
    return split.apply(this, args)
  })
  // Node's MockTracker rejects Array.prototype as a mock target.
  t.after(() => { Array.prototype.findIndex = findIndex })
  Array.prototype.findIndex = function (...args) {
    if (bounds.has(this)) counts.bucketCallbacks++
    return findIndex.apply(this, args)
  }
  for (let index = 0; index < 128; index++) {
    const observations = [
      { kind: 'outcome', workflow: 'memory.recall', surface: 'desktop', outcome: 'success', latency_ms: index, result_items: 4 },
      { kind: 'resource', metric: 'rss_bytes', value: 262144 },
    ]
    for (const observation of observations) for (const cell of catalog.observation(observation).cells) {
      assert.equal(catalog.group(cell), catalog.describe(cell).group)
    }
  }
  assert.deepEqual(counts, { metricEnumerations: 0, resourceEnumerations: 0, familySplits: 0, bucketCallbacks: 0 })
})

function installation() {
  const values = new Map()
  const storage = { getItem: key => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value), removeItem: key => values.delete(key) }
  let company = { state: 'unmanaged', enabled: true, metric_groups: ['usage'] }
  const client = () => new BrowserTelemetry(() => storage, () => company, () => false, () => true)
  return { values, storage, client, company: value => { company = value } }
}

test('first-time setup saves the displayed disclosure only through an explicit choice', t => {
  const original = { collection_available: contract.collection_available, destination: contract.destination }
  Object.assign(contract, { collection_available: true, destination: 'https://telemetry-fixture.invalid/v3/report' })
  t.after(() => Object.assign(contract, original))
  const { client, values } = installation(), current = client()
  const shown = current.status()
  assert.equal(needsTelemetrySetup(shown), true)
  assert.equal(values.size, 0, 'Opening or deferring setup must not create a preference')
  const input = telemetrySetupChoice(shown, true)
  assert.equal(values.size, 0, 'Preparing the explicit choice is not acknowledgement')
  const saved = current.configure(input)
  assert.equal(saved.effective_enabled, true)
  assert.equal(saved.disclosure_version, shown.disclosure.version)
  assert.equal(saved.pending_records, 0)
  assert.equal(saved.delivery_budget.attempts_in_rolling_week, 0)
  assert.equal(needsTelemetrySetup(client().status()), false, 'A later app session uses the persisted choice')
})

test('first-time opt-out persists without acknowledging or collecting', t => {
  const original = { collection_available: contract.collection_available, destination: contract.destination }
  Object.assign(contract, { collection_available: true, destination: 'https://telemetry-fixture.invalid/v3/report' })
  t.after(() => Object.assign(contract, original))
  const { client } = installation(), current = client()
  current.configure(telemetrySetupChoice(current.status(), false))
  const restarted = client().status()
  assert.equal(restarted.reason, 'user_disabled')
  assert.equal(restarted.disclosure_version, 0)
  assert.equal(restarted.pending_records, 0)
  assert.equal(needsTelemetrySetup(restarted), false)
})

test('a displayed setup choice cannot override a later opt-out or store generation', t => {
  const original = { collection_available: contract.collection_available, destination: contract.destination }
  Object.assign(contract, { collection_available: true, destination: 'https://telemetry-fixture.invalid/v3/report' })
  t.after(() => Object.assign(contract, original))
  const { client } = installation(), current = client()
  const shown = current.status(), input = telemetrySetupChoice(shown, true)
  const off = client().configure({ enabled: false, expected_revision: shown.revision })
  assert.throws(() => current.configure(input), /changed in another tab/)
  assert.equal(current.status().reason, 'user_disabled')
  assert.equal(current.status().store_generation, off.store_generation)
  assert.equal(needsTelemetrySetup(current.status()), false)
})

test('setup offers no acknowledgement for unavailable, restricted or unreadable state', t => {
  const original = { collection_available: contract.collection_available, destination: contract.destination }
  t.after(() => Object.assign(contract, original))
  const { client, company, values } = installation()
  Object.assign(contract, { collection_available: false, destination: null })
  assert.equal(telemetrySetupChoice(client().status(), true), null)
  Object.assign(contract, { collection_available: true, destination: 'https://telemetry-fixture.invalid/v3/report' })
  company({ state: 'restricted', enabled: false, metric_groups: [] })
  assert.equal(telemetrySetupChoice(client().status(), true), null)
  company({ state: 'unmanaged', enabled: true, metric_groups: ['usage'] })
  const shown = client().status()
  assert.equal(telemetrySetupChoice({ ...shown, disclosure: { ...shown.disclosure, version: shown.required_disclosure_version + 1 } }, true), null)
  values.set(choiceKey, 'broken settings')
  assert.equal(client().status().reason, 'storage_unavailable')
  assert.equal(telemetrySetupChoice(client().status(), true), null)
})

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
      workflow: 'update.verify', state: 'mapped', owners: ['local_maintenance', 'host_updates'],
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
  assert.throws(() => client().configure({ enabled: true, expected_revision: 0, disclosure_version: contract.version }), /Collection is not available/)
  assert.equal(values.size, 0)
})

function available(run) {
  const saved = { collection_available: contract.collection_available, destination: contract.destination }
  Object.assign(contract, { collection_available: true, destination: 'https://example.invalid/telemetry' })
  try { run() } finally { Object.assign(contract, saved) }
}

const measured = extra => ({ kind: 'outcome', workflow: 'memory.recall', surface: 'browser', outcome: 'success', ...extra })

test('browser format preview is read-only and never claims an actual queued packet', () => available(() => {
  contract.destination = 'https://example.invalid/v3/report'
  const instance = installation(), client = instance.client()
  const empty = client.preview()
  assert.equal(instance.values.size, 0)
  const example = empty.illustrative_packet
  assert.equal(example.kind, 'synthetic_example')
  assert.equal(example.body_encoding, 'base64')
  assert.equal(example.schema_version, 3)
  assert.equal(example.body_bytes, 25)
  assert.equal(example.view, 'bounded_summary')
  assert.equal(example.coordinate, 0)
  assert.equal(example.randomized_sign, null)
  assert.equal(example.aggregation, 'bounded_summary_publication_noise')
  assert.equal(example.privacy_bound_scope, 'publication_closed_week')
  assert.deepEqual([...Buffer.from(example.body_base64, 'base64')], [3, 1, 4, 46, 53, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1])
  assert.equal(empty.outbound_state, 'not_inspected')
  assert.equal(empty.outbound_body, null)
  assert.equal(empty.outbound_bytes, 0)
  assert.equal(empty.status.effective_enabled, false)
  assert.equal(empty.transport_available, true)
  client.delivery.reserve = () => { assert.fail('Preview tried to reserve a delivery') }
  const current = client.configure({ enabled: true, expected_revision: 0, disclosure_version: contract.version })
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
    ['https://example.invalid/v3/report', true], ['https://example.invalid/v1/report', false],
    ['http://example.invalid/v3/report', false], ['https://secret@example.invalid/v3/report', false],
    ['https://example.invalid/other', false], ['https://example.invalid/v3/report?secret=PRIVATE_SENTINEL', false],
    [null, false],
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
  const current = client.configure({ enabled: true, expected_revision: 0, disclosure_version: contract.version })
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
  const again = client.configure({ enabled: true, expected_revision: off.revision, expected_generation: off.store_generation, disclosure_version: contract.version })
  assert.equal(client.record(measured(), current, day), false)
  assert.equal(client.record(measured(), again, day), true)
}))

test('browser expiry, storage loss, company narrowing and write faults suppress old aggregates', () => available(() => {
  const instance = installation(), client = instance.client()
  instance.company({ state: 'unmanaged', enabled: true, metric_groups: ['usage', 'performance'] })
  const current = client.configure({ enabled: true, expected_revision: 0, disclosure_version: contract.version })
  assert.equal(client.record(measured({ latency_ms: 10 }), current, 20000), true)
  instance.company({ state: 'restricted', enabled: true, metric_groups: ['usage'] })
  assert.equal(client.record(measured({ latency_ms: 10 }), current, 20000), true)
  assert.equal(pendingState(instance.storage.getItem(queueKey)).entries.length, 1)
  assert.equal(client.record(measured(), current, 20003), true)
  assert.equal(pendingState(instance.storage.getItem(queueKey)).entries[0].count, 1)
  instance.storage.removeItem(choiceKey)
  assert.equal(client.record(measured(), current, 20003), false)
  assert.equal(client.status().reason, 'disclosure_required')
  const restored = client.configure({ enabled: true, expected_revision: 0, disclosure_version: contract.version })
  assert.equal(restored.pending_records, 0)
  assert.equal(restored.revision, current.revision)
  assert.notEqual(restored.store_generation, current.store_generation)
  assert.equal(client.record(measured(), current, 20003), false)
  assert.throws(() => client.configure({ enabled: true, expected_revision: current.revision,
    expected_generation: current.store_generation, disclosure_version: contract.version }), /changed in another tab/)
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
    assert.throws(() => telemetryCatalog.validateObservation(measured({ latency_ms: bad })), /^Error: telemetry_invalid_measurement$/)
  }
  for (const bad of [measured({ workflow: '__proto__' }), measured({ workflow: 'vault.write', payload_bytes_sent: 15 }), measured({ token: 'PRIVATE_SENTINEL' }), measured({ reason: 'authorization' })]) {
    assert.throws(() => telemetryCatalog.observation(bad), /telemetry_invalid_measurement/)
    assert.throws(() => telemetryCatalog.validateObservation(bad), /telemetry_invalid_measurement/)
  }
  const { TelemetryCatalog } = load(new URL('../../electron/telemetry-catalog.ts', import.meta.url))
  const tight = new TelemetryCatalog(structuredClone(telemetryCatalog.specification))
  tight.specification.limits.cells_per_observation = 2
  const counted = { kind: 'outcome', workflow: 'memory.recall', surface: 'desktop', outcome: 'failed', reason: 'offline' }
  tight.validateObservation(counted)
  assert.deepEqual(tight.observation(counted), { scope: 48, cells: [6151, 6159] })
  assert.throws(() => tight.validateObservation({ ...counted, latency_ms: 0 }), /^Error: telemetry_invalid_measurement$/)
  assert.throws(() => tight.observation({ ...counted, latency_ms: 0 }), /^Error: telemetry_invalid_measurement$/)
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
  const client = instance.client(), original = client.configure({ enabled: true, expected_revision: 0, disclosure_version: contract.version })
  const input = measured({ latency_ms: 123.456 })
  const pending = exported.recordBrowserTelemetry(input, original)
  input.latency_ms = 'PRIVATE_SENTINEL'
  instance.release({ name: choiceKey })
  assert.equal(await pending, true)
  assert.ok(!instance.storage.getItem(queueKey).includes('PRIVATE_SENTINEL'))
  const next = exported.recordBrowserTelemetry(measured(), original)
  const off = client.configure({ enabled: false, expected_revision: original.revision })
  const on = client.configure({ enabled: true, expected_revision: off.revision, expected_generation: off.store_generation, disclosure_version: contract.version })
  Object.assign(original, on)
  instance.release({ name: choiceKey })
  assert.equal(await next, false)
  assert.equal(instance.storage.getItem(queueKey), null)
}))

test('an unavailable browser lock drops a paired observation without retry or storage changes', async () => browserGlobals(async instance => {
  const current = instance.client().configure({ enabled: true, expected_revision: 0, disclosure_version: contract.version })
  const values = [{ kind: 'submission', workflow: 'memory.recall', surface: 'browser' }, measured()]
  const pending = exported.recordBrowserTelemetryMany(values, current)
  instance.release(null)
  assert.equal(await pending, false)
  assert.equal(instance.attempts(), 1)
  assert.equal(instance.storage.getItem(queueKey), null)
  assert.equal(await exported.recordBrowserTelemetry(measured({ secret: 'PRIVATE_SENTINEL' }), current), false)
  assert.equal(instance.attempts(), 1)
}))

test('invalid measurements never reach a browser lock or the desktop recording port', async () => browserGlobals(async instance => {
  const client = instance.client()
  const current = client.configure({ enabled: true, expected_revision: 0, disclosure_version: contract.version })
  const ipc = []
  window.mnemion = {
    productTelemetrySnapshot: async () => ({ revision: 4, store_generation: 'c'.repeat(32) }),
    productTelemetryRecord: async values => { ipc.push(values); return true },
  }
  const { TelemetryWorkflow } = load(new URL('../../electron/telemetry-workflow.ts', import.meta.url))
  const refused = await TelemetryWorkflow.begin(exported.productWorkflowStore, 'memory.recall', 'desktop', () => 10)
  assert.ok(refused)
  await refused.resources([{ metric: 'rss_bytes', value: 1024 }, { metric: 'rss_bytes', value: Number.POSITIVE_INFINITY }])
  await refused.finish('failed', 'invalid_input', { result_items: -1 })
  const wrongFamily = await TelemetryWorkflow.begin(exported.productWorkflowStore, 'vault.write', 'desktop', () => 10)
  await wrongFamily.finish('failed', 'other_failure', { reported_tokens: 3 })
  const wrongReason = await TelemetryWorkflow.begin(exported.productWorkflowStore, 'memory.recall', 'desktop', () => 10)
  await wrongReason.finish('accepted', 'conflict')
  assert.deepEqual(ipc, [])
  const admitted = await TelemetryWorkflow.begin(exported.productWorkflowStore, 'memory.recall', 'desktop', () => 10)
  await admitted.resources([{ metric: 'rss_bytes', value: 1024 }])
  await admitted.finish('success')
  assert.equal(ipc.length, 2)
  assert.deepEqual(ipc[0], [{ kind: 'resource', metric: 'rss_bytes', value: 1024 }])
  assert.equal(ipc[1][0].kind, 'submission')
  assert.equal(ipc[1][1].outcome, 'success')
  assert.equal(ipc[1][1].latency_ms, 0)
  const submission = { kind: 'submission', workflow: 'memory.recall', surface: 'browser' }
  for (const values of [
    [submission, measured({ token: 'PRIVATE_SENTINEL' })],
    [submission, measured({ workflow: 'vault.write', payload_bytes_sent: 15 })],
    [submission, measured({ reason: 'authorization' })],
    [submission, measured({ latency_ms: -1 })],
    [submission, measured({ latency_ms: NaN })],
    [submission, measured({ latency_ms: Infinity })],
    [submission, measured({ latency_ms: Number.MAX_SAFE_INTEGER + 1 })],
    [{ kind: 'resource', metric: 'rss_bytes', value: 1024 }, { kind: 'resource', metric: 'queue_drops', value: Number.MAX_SAFE_INTEGER + 2 }],
  ]) assert.equal(await exported.recordBrowserTelemetryMany(values, current), false)
  assert.equal(instance.attempts(), 0)
  assert.equal(instance.storage.getItem(queueKey), null)
  assert.equal(client.recordMany([submission, measured({ secret: 'PRIVATE_SENTINEL' })], current), false)
  assert.equal(instance.storage.getItem(queueKey), null)
  assert.equal(client.recordMany([submission, measured()], current), true)
  assert.equal(pendingState(instance.storage.getItem(queueKey)).contributions.length, 1)
}))

for (const ending of ['ready', 'opted_out', 'page_exit']) test('queued browser delivery survives refused collection: ' + ending, async t => {
  const instance = installation(), destination = 'https://telemetry-fixture.invalid/v3/report'
  const original = { collection_available: contract.collection_available, destination: contract.destination }
  const saved = Object.fromEntries(['window', 'document', 'navigator', 'fetch'].map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)]))
  const page = Object.assign(new EventTarget(), {
    location: new URL('https://workspace-fixture.invalid/studio'), localStorage: instance.storage,
  })
  const document = Object.assign(new EventTarget(), { visibilityState: 'visible', querySelector: () => null })
  // An immediate lock adapter exercises producer/owner admission here. Real
  // browser coordination and sensor qualification retain their own evidence.
  const navigator = { onLine: true, platform: 'Linux x86_64', locks: { request: async (name, options, callback = options) => callback({ name }) } }
  const requests = []
  const fetch = async (url, options) => {
    requests.push({ url, ...options, body: options.body ? [...options.body] : undefined })
    let response
    if (url === page.location.origin + '/studio/telemetry-policy') {
      const body = JSON.stringify({ state: 'unmanaged', enabled: true, metric_groups: [...contract.metric_groups] })
      response = new Response(body, { headers: { 'content-type': 'application/json',
        'content-length': String(new TextEncoder().encode(body).length), 'cache-control': 'no-store' } })
    } else {
      assert.equal(url, destination)
      response = new Response(null, { status: 204, headers: { 'content-length': '0' } })
    }
    Object.defineProperty(response, 'url', { value: url })
    return response
  }
  for (const [key, value] of Object.entries({ window: page, document, navigator, fetch }))
    Object.defineProperty(globalThis, key, { configurable: true, value })
  Object.assign(contract, { collection_available: true, destination })
  let owner, now = 0, ready = false, preparations = 0
  t.mock.method(performance, 'now', () => now)
  t.after(async () => {
    if (owner) { owner.activity.close(); await owner.activity.settled() }
    Object.assign(contract, original)
    for (const [key, descriptor] of Object.entries(saved)) {
      if (descriptor) Object.defineProperty(globalThis, key, descriptor)
      else delete globalThis[key]
    }
  })
  // A fresh module graph models a fresh page, including its genuine lifecycle
  // listeners and owner, without reusing a prior test's permission or stamp.
  const cache = new Map(), current = load(path, cache)
  const { BrowserTelemetryActivity } = cache.get(new URL('../src/workspace/telemetry-activity.ts', import.meta.url).href)
  const offer = BrowserTelemetryActivity.prototype.offer
  t.mock.method(BrowserTelemetryActivity.prototype, 'offer', function (stamp) {
    if (!owner) {
      owner = this
      t.mock.method(this.conditions, 'start', async () => { preparations++; return ready })
      t.mock.method(this.conditions, 'read', () => ({ network: 'unmetered', constrained: false }))
    }
    return offer.call(this, stamp)
  })
  const status = await current.telemetryConfigure({ enabled: true, expected_revision: 0,
    disclosure_version: contract.version, connection_mode: 'unmetered' })
  const input = { kind: 'submission', workflow: 'memory.recall', surface: 'browser' }
  for (let index = 0; index < 64; index++) {
    now = index * 500
    assert.equal(await current.recordBrowserTelemetry(input, status), true)
    await owner.activity.settled()
  }
  assert.equal(preparations, 1)
  assert.equal(requests.length, 0)
  ready = true
  if (ending === 'opted_out') await current.telemetryConfigure({ enabled: false, expected_revision: status.revision })
  if (ending === 'page_exit') page.dispatchEvent(new Event('pagehide'))
  now = 60001
  assert.equal(await current.recordBrowserTelemetry(input, status), false)
  await owner.activity.settled()
  const reports = requests.filter(request => request.method === 'POST')
  assert.equal(reports.length, ending === 'ready' ? 1 : 0)
  assert.equal(preparations, ending === 'ready' ? 2 : 1)
  if (reports.length) {
    assert.equal(reports[0].body.length, 25)
    assert.equal(reports[0].body[0], 3)
    assert.equal(reports[0].credentials, 'omit')
    assert.equal(reports[0].referrerPolicy, 'no-referrer')
  }
  assert.equal(await current.recordBrowserTelemetry(input, status), false)
  await owner.activity.settled()
  assert.equal(requests.filter(request => request.method === 'POST').length, reports.length)
  assert.equal((await current.telemetryStatus()).delivery_budget.attempts_in_rolling_week, reports.length)
})
