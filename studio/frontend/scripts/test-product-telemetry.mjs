import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { spawnSync } from 'node:child_process'
import assert from 'node:assert/strict'
import { test } from 'node:test'
import ts from 'typescript'

const path = new URL('../src/workspace/telemetry-policy.ts', import.meta.url)
const modules = new Map()
function load(url) {
  if (modules.has(url.href)) return modules.get(url.href)
  const exported = {}
  modules.set(url.href, exported)
  const code = ts.transpileModule(readFileSync(url, 'utf8'), { compilerOptions: {
    target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, esModuleInterop: true,
  } }).outputText
  const local = createRequire(url)
  new Function('require', 'exports', code)(name => name.startsWith('.') && !name.endsWith('.json')
    ? load(new URL(name.replace(/\.js$/, '') + '.ts', url)) : local(name), exported)
  return exported
}
const exported = load(path)
const { BrowserTelemetry, choiceKey, queueKey } = exported
const { telemetryCatalog, pendingState, collect } = load(new URL('../src/workspace/telemetry-aggregate.ts', import.meta.url))
const contract = createRequire(path)('../../../../mnemion/product_telemetry/disclosure.json')

function installation() {
  const values = new Map()
  const storage = { getItem: key => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value), removeItem: key => values.delete(key) }
  let company = { state: 'unmanaged', enabled: true, metric_groups: ['usage'] }
  const client = () => new BrowserTelemetry(() => storage, () => company, () => false, () => true)
  return { values, storage, client, company: value => { company = value } }
}

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
  const on = first.configure({ enabled: true, expected_revision: repeated.revision })
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

test('browser queue stores coarse cells, rejects content and obeys contribution bounds', () => available(() => {
  const instance = installation(), client = instance.client()
  instance.company({ state: 'unmanaged', enabled: true, metric_groups: ['usage', 'performance'] })
  const current = client.configure({ enabled: true, expected_revision: 0, disclosure_version: 1 })
  const day = Math.floor(Date.now() / 86400000)
  assert.equal(client.record(measured({ latency_ms: 123.456, result_items: 37 }), current.revision, day), true)
  assert.equal(client.record(measured({ query: 'PRIVATE_SENTINEL' }), current.revision, day), false)
  for (let index = 1; index < 80; index++) client.record(measured({ latency_ms: 123.456, result_items: 37 }), current.revision, day)
  const queue = pendingState(instance.storage.getItem(queueKey))
  assert.equal(queue.entries.length, 3)
  assert.ok(queue.entries.every(row => row.count === 64))
  assert.equal(queue.contributions.length, 1)
  assert.ok(!instance.storage.getItem(queueKey).includes('123.456'))
  assert.ok(!instance.storage.getItem(queueKey).includes('PRIVATE_SENTINEL'))
  assert.equal(client.preview().local_aggregates.length, 3)
  const off = client.configure({ enabled: false, expected_revision: current.revision })
  assert.equal(instance.storage.getItem(queueKey), null)
  const again = client.configure({ enabled: true, expected_revision: off.revision, disclosure_version: 1 })
  assert.equal(client.record(measured(), current.revision, day), false)
  assert.equal(client.record(measured(), again.revision, day), true)
}))

test('browser expiry, storage loss, company narrowing and write faults suppress old aggregates', () => available(() => {
  const instance = installation(), client = instance.client()
  instance.company({ state: 'unmanaged', enabled: true, metric_groups: ['usage', 'performance'] })
  const current = client.configure({ enabled: true, expected_revision: 0, disclosure_version: 1 })
  assert.equal(client.record(measured({ latency_ms: 10 }), current.revision, 20000), true)
  instance.company({ state: 'restricted', enabled: true, metric_groups: ['usage'] })
  assert.equal(client.record(measured({ latency_ms: 10 }), current.revision, 20000), true)
  assert.equal(pendingState(instance.storage.getItem(queueKey)).entries.length, 1)
  assert.equal(client.record(measured(), current.revision, 20003), true)
  assert.equal(pendingState(instance.storage.getItem(queueKey)).entries[0].count, 1)
  instance.storage.removeItem(choiceKey)
  assert.equal(client.record(measured(), current.revision, 20003), false)
  assert.equal(client.status().reason, 'disclosure_required')
  const restored = client.configure({ enabled: true, expected_revision: 0, disclosure_version: 1 })
  assert.equal(restored.pending_records, 0)
  instance.storage.setItem = () => { throw new Error('PRIVATE_SENTINEL') }
  assert.equal(client.record(measured(), restored.revision, 20003), false)
  assert.equal(client.status().reason, 'storage_unavailable')
}))

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
