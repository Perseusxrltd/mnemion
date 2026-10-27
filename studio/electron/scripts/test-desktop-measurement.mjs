import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { desktopActions } from '../dist/desktop-actions.js'
import { desktopIpcOrigins, desktopIpcSelection, desktopTelemetryOrigins, desktopTelemetrySelection, measureDesktop } from '../dist/desktop-measurement.js'
import { nativeTelemetryDefinitions } from '../dist/telemetry-store.js'
import { TelemetryCatalog } from '../dist/telemetry-catalog.js'
import { windowsTelemetryPrivateExecutable } from '../dist/telemetry-private-store.js'
import { TelemetryWorkflow, TelemetryWorkflowChoice } from '../dist/telemetry-workflow.js'
import { markWorkspaceSelection, takeWorkspaceSelection } from '../dist/workspace-selection.js'
import { desktopUpdateMenu } from '../dist/update-menu.js'
import { desktopAppAction } from '../dist/desktop-app-actions.js'

const catalog = new TelemetryCatalog(nativeTelemetryDefinitions().catalog)
function fixture() {
  const values = [], reads = []
  const store = { available: true, catalog,
    async snapshot() { reads.push(true); return { revision: 1, store_generation: 'a'.repeat(32) } },
    async recordMany(inputs) { values.push(...inputs.flatMap(value => catalog.observation(value).cells.map(cell => catalog.describe(cell)))); return true },
  }
  return { store, values, reads }
}

test('delayed privacy admission cannot erase time already spent in the observed work', async () => {
  for (const selected of [false, true]) {
    const f = fixture(), rows = []
    let now = 10, release
    f.store.snapshot = () => new Promise(resolve => { release = resolve })
    f.store.recordMany = async values => { rows.push(...values); return true }
    const pending = selected
      ? TelemetryWorkflowChoice.choose(f.store, ['workspace.open', 'workspace.switch'], 'desktop', () => now)
      : TelemetryWorkflow.begin(f.store, 'update.verify', 'desktop', () => now)
    now = 400
    release({ revision: 1, store_generation: 'a'.repeat(32) })
    const active = await pending
    now = 650
    if (selected) await active.finishChoice('workspace.switch', 'success')
    else await active.finish('success')
    assert.equal(rows.find(row => row.kind === 'outcome').latency_ms, 640)
  }
})

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
  const coverage = JSON.parse(readFileSync(new URL('../../../mnemion/product_telemetry/workflow-coverage.json', import.meta.url)))
  assert.deepEqual([...new Set(coverage.action_coverage.actions.filter(row => row.owner === 'native_commands').map(row => row.action))].sort(), Object.keys(desktopActions).sort())
  for (const [action, spec] of Object.entries(desktopTelemetryOrigins.operations)) {
    if (spec.exclusion) assert.ok(Object.hasOwn(desktopTelemetryOrigins.exclusions, spec.exclusion), action)
    else for (const name of spec.variants ? Object.values(spec.variants) : [spec.workflow]) assert.ok(catalog.workflows.includes(name), action)
  }
  for (const action of Object.values(desktopIpcOrigins)) assert.ok(desktopTelemetrySelection(action, {}), action)
  assert.equal(desktopIpcSelection('service:request', ['PRIVATE_SENTINEL']), null)
  assert.equal(desktopIpcSelection('telemetry:action', ['telemetry.configure', { enabled: false }]), null)
  assert.equal(desktopIpcSelection('sources:status', []), null)
})

test('every shipped desktop channel is classified and excludes automatic reconnection before private input access', () => {
  const preload = readFileSync(new URL('../preload.ts', import.meta.url), 'utf8')
  const channels = [...preload.matchAll(/(?:transfer|ipcRenderer\.invoke)\('([^']+)'/g)].map(match => match[1])
  assert.deepEqual(Object.keys(desktopTelemetryOrigins.ipc).sort(), [...new Set(channels)].sort())
  const privateInput = new Proxy({}, { get() { throw new Error('PRIVATE_INPUT_READ') } })
  for (const [channel, spec] of Object.entries(desktopTelemetryOrigins.ipc)) {
    if (spec.exclusion) assert.equal(desktopIpcSelection(channel, [privateInput]), null, channel)
    if (spec.actions) for (const [variant, action] of Object.entries(spec.actions)) {
      const native = desktopTelemetryOrigins.operations[action]
      assert.ok(native, channel + '/' + variant)
      if (native.exclusion) assert.equal(desktopIpcSelection(channel, [variant, privateInput]), null)
      else if (action !== 'host.request') {
        const selected = desktopIpcSelection(channel, [variant, { enabled: true }])
        assert.equal(selected.action, action)
        assert.ok(desktopTelemetrySelection(selected.action, selected.input))
      }
    }
  }
  assert.equal(desktopIpcSelection('workspaces:resume', []), null)
  assert.deepEqual(desktopIpcSelection('workspaces:restore', ['PRIVATE_BOOKMARK']), { action: 'workspace.restore', input: {} })
  assert.deepEqual(desktopIpcSelection('workspaces:reset', []), { action: 'workspace.forget', input: {} })
})

test('the installed privacy helper is executable outside the ASAR archive', async () => {
  const base = process.platform === 'win32' ? 'file:///C:/Mnemion/resources/' : 'file:///tmp/Mnemion/resources/'
  const executable = windowsTelemetryPrivateExecutable(base + 'app.asar/dist/telemetry-private-store.js')
  assert.ok(executable.replaceAll('\\', '/').endsWith('/app.asar.unpacked/dist/telemetry-private-store.exe'))
  const { default: build } = await import('../builder.config.cjs')
  assert.ok(build.asarUnpack.includes('dist/telemetry-private-store.exe'))
})

test('source resume and host selection read only the reviewed primitive selectors', () => {
  const input = new Proxy({ enabled: true }, { get(_target, key) { if (key === 'enabled') return true; throw new Error('PRIVATE_SENTINEL') } })
  const selected = desktopIpcSelection('sources:control', ['pause', input])
  assert.equal(desktopTelemetrySelection(selected.action, selected.input).workflow, 'sources.resume')
  assert.equal(desktopTelemetrySelection('source.pause', { enabled: 'PRIVATE_SENTINEL' }), null)
  assert.equal(desktopIpcSelection('hosts:action', ['host.request', { request: 'PRIVATE_SENTINEL' }]), null)
  const request = new Proxy({ action: 'backup.verify' }, { get(_target, key) { if (key === 'action') return 'backup.verify'; throw new Error('PRIVATE_HOST_FIELD_READ') } })
  assert.deepEqual(desktopIpcSelection('hosts:action', ['host.request', { request }]), {
    action: 'host.request', input: { request: { action: 'backup.verify' } },
  })
  for (const action of ['host.status', 'operations.get', 'operations.list', 'operators.list', 'PRIVATE_ACTION']) {
    assert.equal(desktopIpcSelection('hosts:action', ['host.request', { request: { action } }]), null)
  }
})

test('explicit app and native capture previews own no private selection or result fields', async () => {
  const input = new Proxy({}, { get() { throw new Error('PRIVATE_PREVIEW_INPUT') } })
  const result = new Proxy({}, { get(_target, key) { if (key === 'then') return undefined; throw new Error('PRIVATE_PREVIEW_RESULT') } })
  const selection = desktopIpcSelection('sources:preview', [input])
  assert.deepEqual(selection, { action: 'source.preview', input: {} })
  for (const surface of ['desktop', 'native_agent']) {
    const f = fixture()
    let calls = 0
    assert.equal(await measureDesktop(f.store, 'source.preview', input, surface, () => { calls++; return result }), result)
    assert.equal(calls, 1)
    assert.equal(f.values.filter(row => row.metric === 'submissions').length, 1)
    assert.ok(f.values.every(row => row.workflow === 'capture.preview' && row.surface === surface))
    assert.equal(f.values.find(row => row.metric === 'outcomes').bucket, 'success')
    assert.equal(JSON.stringify(f.values).includes('PRIVATE'), false)
  }
})

test('explicit backup inventory observes only its completion, never file names or result fields', async () => {
  const input = new Proxy({}, { get() { throw new Error('PRIVATE_INVENTORY_INPUT') } })
  const result = new Proxy({}, { get(_target, key) { if (key === 'then') return undefined; throw new Error('PRIVATE_BACKUP_LIST') } })
  assert.deepEqual(desktopIpcSelection('local:backup-inventory', [input]), { action: 'backup.inventory', input: {} })
  for (const surface of ['desktop', 'native_agent']) {
    const f = fixture()
    assert.equal(await measureDesktop(f.store, 'backup.inventory', input, surface, () => result), result)
    assert.equal(f.values.filter(row => row.metric === 'submissions').length, 1)
    assert.ok(f.values.every(row => row.workflow === 'backup.list' && row.surface === surface))
    assert.equal(f.values.find(row => row.metric === 'outcomes').bucket, 'success')
  }
})

test('workspace selection needs the exact fresh controller result and keeps its original snapshot', async () => {
  const f = fixture(), stamps = [], original = f.store.recordMany
  f.store.recordMany = async (values, stamp) => { stamps.push(stamp); return original(values) }
  const input = new Proxy({}, { get() { throw new Error('PRIVATE_WORKSPACE_INPUT') } })
  const result = new Proxy({}, { get(_target, key) { if (key === 'then') return undefined; throw new Error('PRIVATE_WORKSPACE_RESULT') } })
  assert.equal(await measureDesktop(f.store, 'workspace.restore', input, 'desktop', () => {
    f.store.snapshot = async () => { throw new Error('A completion must not read another privacy choice') }
    return markWorkspaceSelection(result, 'switched')
  }), result)
  assert.equal(f.reads.length, 1)
  assert.equal(stamps.length, 1)
  assert.deepEqual(stamps[0], { revision: 1, store_generation: 'a'.repeat(32) })
  assert.ok(f.values.every(row => row.workflow === 'workspace.switch'))
  assert.equal(takeWorkspaceSelection(result), null)
  f.store.snapshot = async () => ({ revision: 2, store_generation: 'b'.repeat(32) })
  for (const reused of [result, { workspaceSelection: 'switched' }]) {
    assert.equal(await measureDesktop(f.store, 'workspace.restore', {}, 'desktop', () => reused), reused)
  }
  assert.equal(stamps.length, 1, 'reused and unbranded results cannot add usage')
})

test('unavailable and late selection measurements consume their result without retaining a future use', async () => {
  for (const mode of ['unavailable', 'late']) {
    const f = fixture(), result = { private: 'PRIVATE_WORKSPACE_RESULT' }
    let release
    if (mode === 'unavailable') f.store.available = false
    else f.store.snapshot = () => new Promise(resolve => { release = resolve })
    assert.equal(await measureDesktop(f.store, 'workspace.restore', {}, 'desktop', () => markWorkspaceSelection(result, 'opened')), result)
    release?.({ revision: 1, store_generation: 'a'.repeat(32) })
    await Promise.resolve()
    f.store.available = true
    f.store.snapshot = async () => ({ revision: 1, store_generation: 'a'.repeat(32) })
    assert.equal(await measureDesktop(f.store, 'workspace.restore', {}, 'desktop', () => result), result)
    assert.deepEqual(f.values, [])
    assert.equal(takeWorkspaceSelection(result), null)
  }
})

test('fresh independent host mutations record one fixed accepted workflow at each owned surface', async () => {
  const selected = desktopTelemetryOrigins.operations['host.request'].variants
  assert.equal(Object.keys(selected).length, 9)
  for (const surface of ['desktop', 'native_agent']) {
    for (const [action, workflow] of Object.entries(selected)) {
      const f = fixture(), response = { ok: true, host_id: 'PRIVATE_HOST', operator_id: 'PRIVATE_OPERATOR',
        request_id: 'PRIVATE_REQUEST', result: { request_disposition: 'new', phase: 'queued', content: 'PRIVATE_RESULT' } }
      const input = { request: { action, private_key: 'PRIVATE_KEY', path: 'PRIVATE_PATH' } }
      assert.equal(await measureDesktop(f.store, 'host.request', input, surface, () => response), response)
      assert.equal(f.values.filter(row => row.metric === 'submissions').length, 1)
      assert.equal(f.values.filter(row => row.metric === 'outcomes').length, 1)
      assert.ok(f.values.every(row => row.workflow === workflow && row.surface === surface))
      assert.ok(f.values.some(row => row.metric === 'outcomes' && row.bucket === 'accepted'))
      assert.equal(JSON.stringify(f.values).includes('PRIVATE'), false)
    }
  }
})

test('legacy hosts, replays, unknown dispositions and refused replies never add host usage', async () => {
  const f = fixture(), input = { request: { action: 'backup.verify' } }
  for (const disposition of ['replayed', undefined, null, true, 1, 'PRIVATE_DISPOSITION']) {
    const response = { ok: true, result: { request_disposition: disposition } }
    assert.equal(await measureDesktop(f.store, 'host.request', input, 'desktop', () => response), response)
  }
  for (const response of [
    { ok: false, result: { request_disposition: 'new' } },
    { ok: true, result: Object.create({ request_disposition: 'new' }) },
    { ok: true, result: null },
  ]) assert.equal(await measureDesktop(f.store, 'host.request', input, 'native_agent', () => response), response)
  const original = new Error('PRIVATE_LOST_REPLY')
  await assert.rejects(measureDesktop(f.store, 'host.request', input, 'native_agent', () => { throw original }), error => error === original)
  assert.deepEqual(f.values, [])
})

test('host readbacks, disabled choices and late privacy reads preserve the original action without counts', async () => {
  const f = fixture(), result = { ok: true, result: { request_disposition: 'new' } }
  for (const action of ['host.status', 'operations.get', 'operations.list', 'operators.list']) {
    assert.equal(await measureDesktop(f.store, 'host.request', { request: { action } }, 'desktop', () => result), result)
  }
  assert.deepEqual(f.reads, [])
  f.store.available = false
  assert.equal(await measureDesktop(f.store, 'host.request', { request: { action: 'upgrade.apply' } }, 'desktop', () => result), result)
  assert.deepEqual(f.reads, [])
  f.store.available = true
  let release
  f.store.snapshot = () => new Promise(resolve => { release = resolve })
  assert.equal(await measureDesktop(f.store, 'host.request', { request: { action: 'upgrade.apply' } }, 'desktop', () => result), result)
  release({ revision: 1, store_generation: 'a'.repeat(32) })
  await Promise.resolve()
  assert.deepEqual(f.values, [])
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

test('actual app and tray menu callbacks own one acknowledgement without waiting for update completion', async () => {
  const f = fixture(), calls = []
  const updates = { status: { state: 'Ready', version: '4.46.18' }, enabled: true, canRequestRestart: true,
    preferences: { automaticUpdates: true, startAtLogin: true, background: true }, policyManaged: false,
    check() { calls.push('check'); return new Promise(() => {}) },
    restartIfSafe(requested) { calls.push(['restart', requested]); return new Promise(() => {}) },
    setPreference(key, enabled) { calls.push([key, enabled]); this.preferences[key] = enabled },
  }
  const menu = desktopUpdateMenu(updates, (action, run) => measureDesktop(f.store, action, {}, 'desktop', run))
  assert.equal(menu[0].enabled, false)
  for (const item of menu.slice(1)) await item.click({ checked: false })
  assert.deepEqual(calls, ['check', ['restart', true], ['automaticUpdates', false], ['startAtLogin', false], ['background', false]])
  const submitted = f.values.filter(row => row.metric === 'submissions')
  assert.deepEqual(submitted.map(row => row.workflow), ['update.check', 'update.restart', 'setup.configure', 'setup.configure', 'setup.configure'])
  assert.ok(f.values.every(row => row.surface === 'desktop'))
  assert.deepEqual(f.values.filter(row => row.metric === 'outcomes').map(row => row.bucket), ['accepted', 'accepted', 'success', 'success', 'success'])
})

test('menu refresh, missing update controller and disabled collection do not acquire usage', async () => {
  const f = fixture(), calls = []
  f.store.available = false
  const observe = (action, run) => measureDesktop(f.store, action, {}, 'desktop', run)
  const missing = desktopUpdateMenu(null, observe)
  for (const item of missing.slice(1)) await item.click({ checked: false })
  const updates = { status: { state: 'Current' }, enabled: true, canRequestRestart: false,
    preferences: { automaticUpdates: true, startAtLogin: true, background: true }, policyManaged: true,
    check() { calls.push('check') }, setPreference() { calls.push('preference') },
  }
  const menu = desktopUpdateMenu(updates, observe)
  desktopUpdateMenu(updates, observe)
  assert.equal(menu[2].enabled, false)
  assert.equal(menu[3].enabled, false)
  assert.deepEqual(calls, [])
  await menu[1].click({})
  await menu[4].click({ checked: false })
  assert.deepEqual(calls, ['check', 'preference'])
  assert.deepEqual(f.reads, [])
  assert.deepEqual(f.values, [])
})

test('a preference persistence failure is not reported as success by either menu or agent controls', async () => {
  const updates = { status: { state: 'Current' }, enabled: true, canRequestRestart: false,
    preferences: { automaticUpdates: true, startAtLogin: true, background: true }, policyManaged: false,
    setPreference() { this.status.state = 'Preference could not be saved' },
    inspect() { return { preferences: { ...this.preferences }, status: { ...this.status } } },
  }
  const f = fixture()
  const menu = desktopUpdateMenu(updates, (action, run) => measureDesktop(f.store, action, {}, 'desktop', run))
  await menu[4].click({ checked: false })
  const result = await measureDesktop(f.store, 'app.preferences', {}, 'native_agent', () =>
    desktopAppAction(updates, 'app.preferences', { key: 'startAtLogin', enabled: false, expected_value: true }, new AbortController().signal))
  assert.equal(result.applied, false)
  assert.equal(updates.preferences.startAtLogin, true)
  assert.deepEqual(f.values.filter(row => row.metric === 'outcomes').map(row => row.bucket), ['failed', 'failed'])
})

test('a missing preference acknowledgement does not imply a successful save', async () => {
  const f = fixture()
  for (const result of [undefined, {}, { applied: 'PRIVATE_UNEXPECTED_RESULT' }]) {
    assert.equal(await measureDesktop(f.store, 'app.preferences', {}, 'native_agent', () => result), result)
  }
  assert.deepEqual(f.values.filter(row => row.metric === 'outcomes').map(row => row.bucket), ['unconfirmed', 'unconfirmed', 'unconfirmed'])
  assert.equal(JSON.stringify(f.values).includes('PRIVATE'), false)
})
