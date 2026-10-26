import test from 'node:test'
import assert from 'node:assert/strict'
import { desktopActions } from '../dist/desktop-actions.js'
import { desktopIpcOrigins, desktopIpcSelection, desktopTelemetryOrigins, desktopTelemetrySelection, measureDesktop } from '../dist/desktop-measurement.js'
import { nativeTelemetryDefinitions } from '../dist/telemetry-store.js'
import { TelemetryCatalog } from '../dist/telemetry-catalog.js'
import { windowsTelemetryPrivateExecutable } from '../dist/telemetry-private-store.js'
import { TelemetryWorkflow } from '../dist/telemetry-workflow.js'

const catalog = new TelemetryCatalog(nativeTelemetryDefinitions().catalog)
function fixture() {
  const values = [], reads = []
  const store = { available: true, catalog,
    async snapshot() { reads.push(true); return { revision: 1, store_generation: 'a'.repeat(32) } },
    async recordMany(inputs) { values.push(...inputs.flatMap(value => catalog.observation(value).cells.map(cell => catalog.describe(cell)))); return true },
  }
  return { store, values, reads }
}

test('a synchronous refusal starts the original action without a timer or an await boundary', async t => {
  const f = fixture(), result = { private: 'PRIVATE_ACTION_RESULT' }
  f.store.snapshot = () => null
  assert.equal(TelemetryWorkflow.begin(f.store, 'memory.recall', 'desktop'), null)
  t.mock.method(globalThis, 'setTimeout', () => { throw new Error('Refused telemetry created a timer') })
  let called = false
  const pending = measureDesktop(f.store, 'local.create', {}, 'desktop', () => { called = true; return result })
  assert.equal(called, true)
  assert.equal(await pending, result)
  assert.equal(f.values.length, 0)
})

test('every native operator action and supported UI entry has a reviewed classification', () => {
  assert.deepEqual(Object.keys(desktopTelemetryOrigins.operations).sort(), Object.keys(desktopActions).sort())
  for (const [action, spec] of Object.entries(desktopTelemetryOrigins.operations)) {
    if (spec.exclusion) assert.ok(Object.hasOwn(desktopTelemetryOrigins.exclusions, spec.exclusion), action)
    else for (const name of spec.variants ? Object.values(spec.variants) : [spec.workflow]) assert.ok(catalog.workflows.includes(name), action)
  }
  for (const action of Object.values(desktopIpcOrigins)) assert.ok(desktopTelemetrySelection(action, {}), action)
  assert.equal(desktopIpcSelection('service:request', ['PRIVATE_SENTINEL']), null)
  assert.equal(desktopIpcSelection('telemetry:action', ['telemetry.configure', { enabled: false }]), null)
  assert.equal(desktopIpcSelection('sources:status', []), null)
})

test('the installed privacy helper is executable outside the ASAR archive', async () => {
  const base = process.platform === 'win32' ? 'file:///C:/Mnemion/resources/' : 'file:///tmp/Mnemion/resources/'
  const executable = windowsTelemetryPrivateExecutable(base + 'app.asar/dist/telemetry-private-store.js')
  assert.ok(executable.replaceAll('\\', '/').endsWith('/app.asar.unpacked/dist/telemetry-private-store.exe'))
  const { default: build } = await import('../builder.config.cjs')
  assert.ok(build.asarUnpack.includes('dist/telemetry-private-store.exe'))
})

test('source resume reads only its fixed boolean and never labels a host receipt as new work', () => {
  const input = new Proxy({ enabled: true }, { get(_target, key) { if (key === 'enabled') return true; throw new Error('PRIVATE_SENTINEL') } })
  const selected = desktopIpcSelection('sources:control', ['pause', input])
  assert.equal(desktopTelemetrySelection(selected.action, selected.input).workflow, 'sources.resume')
  assert.equal(desktopTelemetrySelection('source.pause', { enabled: 'PRIVATE_SENTINEL' }), null)
  assert.equal(desktopIpcSelection('hosts:action', ['host.request', { request: 'PRIVATE_SENTINEL' }]), null)
})

test('privacy controls, status and a disabled build touch no measurement store', async () => {
  const f = fixture()
  for (const action of ['telemetry.configure', 'status', 'source.status', 'host.inspect']) {
    assert.equal(await measureDesktop(f.store, action, {}, 'native_agent', () => 7), 7)
  }
  f.store.available = false
  assert.equal(await measureDesktop(f.store, 'local.create', {}, 'desktop', () => 8), 8)
  assert.deepEqual(f.reads, [])
  assert.deepEqual(f.values, [])
})

test('owned app actions preserve values and report asynchronous acceptance and fixed failures', async () => {
  const f = fixture()
  const response = { state: 'starting', message: 'PRIVATE_SENTINEL' }
  assert.equal(await measureDesktop(f.store, 'local.create', {}, 'desktop', () => response), response)
  assert.ok(f.values.some(value => value.metric === 'outcomes' && value.bucket === 'accepted'))
  await measureDesktop(f.store, 'local.start', {}, 'native_agent', () => ({ state: 'error', message: 'PRIVATE_SENTINEL' }))
  assert.ok(f.values.some(value => value.workflow === 'host.start' && value.metric === 'outcomes' && value.bucket === 'failed'))
  const original = new Error('PRIVATE_SENTINEL')
  await assert.rejects(measureDesktop(f.store, 'agent.install', {}, 'desktop', () => { throw original }), error => error === original)
  assert.ok(!JSON.stringify(f.values).includes('PRIVATE'))
})

test('unexpected results and unavailable privacy checks cannot change the original action', async () => {
  const f = fixture()
  const response = { get state() { throw new Error('PRIVATE_SENTINEL') } }
  assert.equal(await measureDesktop(f.store, 'local.create', {}, 'desktop', () => response), response)
  f.store.snapshot = () => new Promise(() => {})
  const started = performance.now()
  assert.equal(await measureDesktop(f.store, 'local.start', {}, 'native_agent', () => 'started'), 'started')
  assert.ok(performance.now() - started < 250)
})
