/** Exercise the actual controller across asynchronous shutdown/install guards. */
import assert from 'node:assert/strict'
import { EventEmitter } from 'node:events'
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { after, mock, test } from 'node:test'
import { setImmediate as immediate } from 'node:timers/promises'
import { TelemetryCatalog } from '../dist/telemetry-catalog.js'
import { UpdateMeasurement } from '../dist/maintenance-measurement.js'

const temporary = mkdtempSync(join(tmpdir(), 'mnemion-update-controller-'))
const previousResources = process.resourcesPath
process.resourcesPath = temporary
let directory = temporary
let idle = 0
let idleState = 'active'
let quits = 0
const app = Object.assign(new EventEmitter(), {
  isPackaged: true,
  getPath: () => directory,
  getVersion: () => '4.0.11',
  setLoginItemSettings: () => {},
  quit: () => { quits++; app.emit('will-quit') },
})
const automatic = Object.assign(new EventEmitter(), {
  setFeedURL: () => {},
  checkForUpdates: async () => ({}),
  quitAndInstall: () => { quits++; app.emit('will-quit') },
})
class PlatformBridge {
  async check() {}
  async cancel() {}
}
mock.module('electron', { namedExports: { app, powerMonitor: { getSystemIdleTime: () => idle, getSystemIdleState: () => idleState },
  net: { request: () => { throw new Error('Unit tests must never start a download') } },
  session: { fromPartition: () => ({}) } } })
mock.module('electron-updater', { defaultExport: { autoUpdater: automatic } })
mock.module('../dist/macos-updates.js', { namedExports: { MacUpdateBridge: PlatformBridge } })
mock.module('../dist/windows-updates.js', { namedExports: { WindowsUpdateBridge: PlatformBridge } })
const { DesktopUpdates } = await import('../dist/updates.js')
const { desktopAppAction } = await import('../dist/desktop-app-actions.js')
const { desktopAction } = await import('../dist/desktop-actions.js')
after(() => {
  mock.restoreAll()
  if (previousResources === undefined) delete process.resourcesPath
  else process.resourcesPath = previousResources
  rmSync(temporary, { recursive: true, force: true })
})

function fixture(t, { ready = true, telemetry, verificationMode = 'stage' } = {}) {
  directory = mkdtempSync(join(temporary, 'profile-'))
  mkdirSync(join(directory, '.config'))
  writeFileSync(join(directory, 'desktop-preferences.json'), JSON.stringify({ automaticUpdates: true, startAtLogin: false, background: true }))
  const keys = ['APPIMAGE', 'MNEMION_AUTO_UPDATE', 'MNEMION_START_AT_LOGIN', 'MNEMION_STUDIO_SMOKE_FILE', 'MNEMION_STUDIO_SMOKE_HEADLESS']
  const previous = Object.fromEntries(keys.map(key => [key, process.env[key]]))
  for (const key of keys) delete process.env[key]
  process.env.APPIMAGE = join(directory, 'fixture.AppImage')
  idle = 0; idleState = 'active'; quits = 0
  const state = { safe: true, focused: true, visible: true, minimized: false, busy: false, drains: 0, cancelled: 0, attempts: 0, installs: 0, checks: 0,
    drain: async () => true, beforeFinalGuard: () => {} }
  const window = { isFocused: () => state.focused, isVisible: () => state.visible, isMinimized: () => state.minimized,
    webContents: { executeJavaScript: async () => state.safe } }
  const controller = new DesktopUpdates(() => window, () => state.busy,
    async () => { state.drains++; return await state.drain() }, () => {}, () => { state.cancelled++ }, telemetry)
  // This fixture drives platform-bridge events even when its runner is Linux.
  if (verificationMode !== 'actual') controller.measurements = new UpdateMeasurement(telemetry, verificationMode)
  // The adapter is a fixture; policy, all controller rechecks and the exact
  // Windows final authorization callback remain the production implementation.
  controller.mac = undefined
  controller.windows = {
    check: async () => { state.checks++ }, cancel: async () => {},
    install: async guard => {
      state.attempts++
      state.beforeFinalGuard()
      if (!await guard()) return false
      state.installs++
      return true
    },
  }
  if (ready) controller.platformEvent({ state: 'ready', version: '4.0.12' })
  t.after(() => {
    app.emit('will-quit'); app.removeAllListeners(); automatic.removeAllListeners()
    for (const key of keys) {
      if (previous[key] === undefined) delete process.env[key]
      else process.env[key] = previous[key]
    }
  })
  return { state, controller, directory }
}

function localAction(controller, action, input = {}, signal = new AbortController().signal) {
  desktopAction(action, input)
  return desktopAppAction(controller, action, input, signal)
}

function measurements() {
  const rows = [], choice = { enabled: true, revision: 0, generation: 'a'.repeat(32) }
  const store = { available: true, catalog: new TelemetryCatalog(JSON.parse(readFileSync(new URL('../dist/telemetry-catalog.json', import.meta.url), 'utf8'))),
    snapshot: async () => choice.enabled ? { revision: choice.revision, store_generation: choice.generation } : null,
    recordMany: async (values, stamp) => {
      if (!choice.enabled || stamp.revision !== choice.revision || stamp.store_generation !== choice.generation) return false
      for (const value of values) store.catalog.observation(value)
      rows.push(...structuredClone(values)); return true
    } }
  return { rows, choice, store }
}

test('one download cycle retains distinct validation attempts across a retry', async t => {
  const measured = measurements(), { controller } = fixture(t, { ready: false, telemetry: () => measured.store })
  await controller.check()
  controller.platformEvent({ state: 'current' })
  await immediate()
  assert.deepEqual(measured.rows, [], 'Ordinary current-version polling is not usage')
  controller.platformEvent({ state: 'downloading', version: '4.0.12', percent: 1 })
  controller.platformEvent({ state: 'downloading', version: '4.0.12', percent: 20 })
  controller.platformEvent({ state: 'verifying' })
  controller.platformEvent({ state: 'error', message: 'PRIVATE_URL_OR_ERROR' })
  await controller.check(true)
  controller.platformEvent({ state: 'downloading', version: '4.0.12', percent: 60 })
  controller.platformEvent({ state: 'verifying' })
  controller.platformEvent({ state: 'ready', version: '4.0.12' })
  await immediate()
  assert.equal(measured.rows.filter(row => row.kind === 'submission' && row.workflow === 'update.download').length, 1)
  assert.equal(measured.rows.find(row => row.kind === 'outcome' && row.workflow === 'update.download').outcome, 'success')
  assert.deepEqual(measured.rows.filter(row => row.kind === 'outcome' && row.workflow === 'update.verify').map(row => row.outcome), ['failed', 'success'])
  assert.equal(/PRIVATE|4\.0\.12|percent/.test(JSON.stringify(measured.rows)), false)
})

test('opt-out and quit discard pending update measurement without changing updater behavior', async t => {
  const measured = measurements(), { controller } = fixture(t, { ready: false, telemetry: () => measured.store })
  controller.platformEvent({ state: 'downloading', version: '4.0.12', percent: 1 })
  controller.platformEvent({ state: 'verifying' })
  await immediate()
  measured.choice.enabled = false; measured.choice.revision++
  controller.platformEvent({ state: 'ready', version: '4.0.12' })
  await immediate()
  assert.equal(controller.canRequestRestart, true)
  assert.deepEqual(measured.rows, [])
  measured.choice.enabled = true
  controller.downloaded = false
  controller.platformEvent({ state: 'downloading', version: '4.0.13', percent: 1 })
  app.emit('will-quit')
  await immediate()
  assert.deepEqual(measured.rows, [])
})

test('cached platform validation is observed once without inventing a download', async t => {
  const measured = measurements(), { controller } = fixture(t, { ready: false, telemetry: () => measured.store })
  controller.platformEvent({ state: 'verifying' })
  controller.platformEvent({ state: 'verifying' })
  controller.platformEvent({ state: 'ready', version: '4.0.12' })
  controller.platformEvent({ state: 'ready', version: '4.0.12' })
  await immediate()
  assert.deepEqual(measured.rows.filter(row => row.kind === 'submission'), [{ kind: 'submission', workflow: 'update.verify', surface: 'desktop' }])
  assert.equal(measured.rows.find(row => row.kind === 'outcome').outcome, 'success')
  assert.ok(Object.hasOwn(measured.rows.find(row => row.kind === 'outcome'), 'latency_ms'))
})

test('verification completion time is captured before a pending privacy read returns', async t => {
  const measured = measurements()
  let now = 10, release
  t.mock.method(performance, 'now', () => now)
  measured.store.snapshot = () => new Promise(resolve => { release = resolve })
  const observation = new UpdateMeasurement(() => measured.store)
  observation.verifying()
  now = 50
  observation.verified()
  now = 240
  release({ revision: 0, store_generation: measured.choice.generation })
  await immediate()
  const outcome = measured.rows.find(row => row.kind === 'outcome')
  assert.equal(outcome.outcome, 'success')
  assert.equal(outcome.latency_ms, 40)
})

test('Linux completion uses the original policy and omits an unobservable validation duration', async t => {
  const measured = measurements(), { controller } = fixture(t, { ready: false, telemetry: () => measured.store, verificationMode: 'completion' })
  controller.platformEvent({ state: 'downloading', percent: 0 })
  controller.measurements.downloadProgress()
  await immediate()
  measured.store.snapshot = () => { throw new Error('Completion must not acquire new permission') }
  controller.platformEvent({ state: 'ready', version: '4.0.12' })
  await immediate()
  const validation = measured.rows.filter(row => row.workflow === 'update.verify')
  assert.deepEqual(validation, [
    { kind: 'submission', workflow: 'update.verify', surface: 'desktop' },
    { kind: 'outcome', workflow: 'update.verify', surface: 'desktop', outcome: 'success', reason: 'none' },
  ])
  assert.equal(controller.canRequestRestart, true)
})

test('Linux opaque errors and current-version polls cannot claim validation outcomes', async t => {
  const measured = measurements(), { controller } = fixture(t, { ready: false, telemetry: () => measured.store, verificationMode: 'completion' })
  controller.platformEvent({ state: 'downloading', percent: 0 })
  controller.measurements.downloadProgress()
  controller.platformEvent({ state: 'error' })
  await controller.check(true)
  controller.platformEvent({ state: 'current' })
  await immediate()
  assert.equal(measured.rows.some(row => row.workflow === 'update.verify'), false)
})

test('Linux cached completion without a fresh transfer does not backfill verification', async t => {
  const measured = measurements(), { controller } = fixture(t, { ready: false, telemetry: () => measured.store, verificationMode: 'completion' })
  controller.platformEvent({ state: 'downloading', percent: 0 })
  controller.platformEvent({ state: 'ready', version: '4.0.12' })
  await immediate()
  assert.equal(measured.rows.some(row => row.workflow === 'update.verify'), false)
  assert.equal(controller.canRequestRestart, true)
})

test('the Linux updater callbacks connect actual transfer progress to untimed verification', { skip: process.platform !== 'linux' }, async t => {
  const measured = measurements(), { controller } = fixture(t, { ready: false, telemetry: () => measured.store, verificationMode: 'actual' })
  automatic.emit('update-available', { version: '4.0.12' })
  automatic.emit('download-progress', { percent: 100, private: 'PRIVATE_DOWNLOAD_ADDRESS' })
  automatic.emit('update-downloaded', { version: '4.0.12' })
  await immediate()
  const outcome = measured.rows.find(row => row.kind === 'outcome' && row.workflow === 'update.verify')
  assert.equal(outcome.outcome, 'success')
  assert.equal(Object.hasOwn(outcome, 'latency_ms'), false)
  assert.equal(JSON.stringify(measured.rows).includes('PRIVATE'), false)
  assert.equal(controller.canRequestRestart, true)
})

test('validation cancellation and a replaced privacy store preserve updater behavior', async t => {
  const measured = measurements(), { controller } = fixture(t, { ready: false, telemetry: () => measured.store })
  controller.platformEvent({ state: 'verifying' })
  controller.platformEvent({ state: 'cancelled' })
  await immediate()
  assert.deepEqual(measured.rows.filter(row => row.kind === 'outcome').map(row => row.outcome), ['cancelled'])
  measured.rows.length = 0
  controller.platformEvent({ state: 'verifying' })
  await immediate()
  measured.choice.generation = 'b'.repeat(32)
  controller.platformEvent({ state: 'ready', version: '4.0.12' })
  await immediate()
  assert.deepEqual(measured.rows, [])
  assert.equal(controller.canRequestRestart, true)
})

test('late updater events after quit acquire no new observation or privacy read', async t => {
  const measured = measurements(), { controller } = fixture(t, { ready: false, telemetry: () => measured.store })
  controller.platformEvent({ state: 'verifying' })
  app.emit('will-quit')
  let lateReads = 0
  measured.store.snapshot = () => { lateReads++; return null }
  controller.platformEvent({ state: 'downloading', percent: 0 })
  controller.platformEvent({ state: 'verifying' })
  controller.platformEvent({ state: 'ready', version: '4.0.12' })
  await immediate()
  assert.equal(lateReads, 0)
  assert.deepEqual(measured.rows, [])
})

test('installer handoff reports accepted only after the real final safety check', async t => {
  const measured = measurements(), { controller, state } = fixture(t, { telemetry: () => measured.store })
  await controller.restartIfSafe(true)
  await immediate()
  assert.equal(state.installs, 1)
  assert.deepEqual(measured.rows.filter(row => row.kind === 'submission'), [{ kind: 'submission', workflow: 'update.apply', surface: 'desktop' }])
  assert.equal(measured.rows.find(row => row.kind === 'outcome').outcome, 'accepted')
})

test('local agents see independent app update policy and cannot mutate the returned snapshot', t => {
  const { controller } = fixture(t)
  const status = localAction(controller, 'app.status')
  assert.equal(status.version, '4.0.11')
  assert.equal(status.ready_version, '4.0.12')
  assert.equal(status.enabled, true)
  assert.equal(status.regular_check_seconds.minimum, 21600)
  assert.equal(status.computer_idle_seconds, 0)
  assert.equal(status.inactivity_remaining_seconds, 600)
  idle = 427
  assert.equal(localAction(controller, 'app.status').inactivity_remaining_seconds, 173)
  idle = 900
  assert.equal(localAction(controller, 'app.status').inactivity_remaining_seconds, 0)
  idle = NaN
  assert.equal(localAction(controller, 'app.status').computer_idle_seconds, null)
  assert.equal(localAction(controller, 'app.status').inactivity_remaining_seconds, null)
  status.preferences.automaticUpdates = false
  status.status.state = 'Changed by caller'
  assert.equal(controller.preferences.automaticUpdates, true)
  assert.notEqual(controller.status.state, 'Changed by caller')
  assert.throws(() => localAction(controller, 'app.status', { credential: 'not accepted' }), /unsupported/)
})

test('app preference changes reject stale, mistyped and administrator-managed requests', t => {
  const { controller } = fixture(t)
  const action = input => localAction(controller, 'app.preferences', input)
  assert.throws(() => action({ key: 'background', enabled: false, expected_value: false }), /changed/)
  assert.throws(() => action({ key: 'background', enabled: 'false', expected_value: true }), /boolean/)
  assert.equal(action({ key: 'background', enabled: false, expected_value: true }).preferences.background, false)
  assert.throws(() => action({ key: 'background', enabled: true, expected_value: true }), /changed/)
  controller.managed = true
  assert.throws(() => action({ key: 'automaticUpdates', enabled: false, expected_value: true }), /administrator/)
  assert.equal(controller.preferences.automaticUpdates, true)
})

test('an agent can check immediately without waiting for six hours or enabling paused updates', async t => {
  const { state, controller } = fixture(t, { ready: false })
  assert.equal(localAction(controller, 'app.update-check').requested, true)
  await Promise.resolve()
  assert.equal(state.checks, 1)
  assert.equal(state.installs, 0)
  controller.preferences.automaticUpdates = false
  assert.throws(() => localAction(controller, 'app.update-check'), /paused/)
  assert.equal(state.checks, 1)
})

test('an agent restart requires the ready version and releases its request before shutdown', async t => {
  t.mock.timers.enable({ apis: ['setTimeout'] })
  const { state, controller } = fixture(t)
  const action = input => localAction(controller, 'app.update-restart', input)
  assert.throws(() => action({ expected_version: '4.0.12', confirm: 1 }), /Confirm/)
  assert.throws(() => action({ expected_version: '4.0.13', confirm: true }), /changed/)
  assert.equal(action({ expected_version: '4.0.12', confirm: true }).requested, true)
  action({ expected_version: '4.0.12', confirm: true })
  assert.equal(state.installs, 0)
  t.mock.timers.tick(1)
  for (let n = 0; n < 12; n++) await Promise.resolve()
  assert.equal(state.installs, 1)
  assert.equal(quits, 1)
})

test('agent restart preserves drafts and never leaves an active manual restart request behind', async t => {
  t.mock.timers.enable({ apis: ['setTimeout'] })
  const { state, controller } = fixture(t)
  localAction(controller, 'app.update-restart', { expected_version: '4.0.12', confirm: true })
  state.safe = false
  t.mock.timers.tick(1)
  for (let n = 0; n < 8; n++) await Promise.resolve()
  assert.equal(state.installs, 0)
  assert.equal(state.drains, 0)
  state.safe = true
  await controller.restartIfSafe()
  assert.equal(state.installs, 0, 'Normal focus/inactivity checks apply after the refused request')
})

test('cancelled agent calls and shutdown cannot change preferences or fire queued restart work', async t => {
  t.mock.timers.enable({ apis: ['setTimeout'] })
  const { state, controller } = fixture(t)
  const abort = new AbortController(); abort.abort()
  assert.throws(() => localAction(controller, 'app.preferences',
    { key: 'background', enabled: false, expected_value: true }, abort.signal), /abort/i)
  assert.equal(controller.preferences.background, true)
  localAction(controller, 'app.update-restart', { expected_version: '4.0.12', confirm: true })
  app.emit('will-quit')
  t.mock.timers.tick(1)
  await Promise.resolve()
  assert.equal(state.drains, 0)
  assert.equal(state.installs, 0)
})

test('a deliberate restart works while focused and active, after all work checks', async t => {
  const { state, controller } = fixture(t)
  await controller.restartIfSafe()
  assert.equal(state.drains, 0)
  assert.equal(controller.status.version, '4.0.12')
  assert.match(controller.status.state, /background/)
  assert.equal(controller.canRequestRestart, true)
  await controller.restartIfSafe(true)
  assert.equal(state.drains, 1)
  assert.equal(state.installs, 1)
  assert.equal(quits, 1)
  assert.equal(controller.canRequestRestart, false)
})

test('an idle locked desktop permits a safe automatic restart even with retained app focus', async t => {
  const { state, controller } = fixture(t)
  idle = 600; idleState = 'locked'
  await controller.restartIfSafe()
  assert.equal(state.focused, true)
  assert.equal(state.drains, 1)
  assert.equal(state.installs, 1)
  assert.equal(quits, 1)
})

test('unlocking during shutdown or at the final installer guard cancels an automatic restart', async t => {
  for (const phase of ['shutdown', 'installer']) {
    const { state, controller } = fixture(t)
    idle = 600; idleState = 'locked'
    const unlock = () => { idle = 0; idleState = 'active' }
    if (phase === 'shutdown') state.drain = async () => { unlock(); return true }
    else state.beforeFinalGuard = unlock
    await controller.restartIfSafe()
    assert.equal(state.drains, 1, phase)
    assert.equal(state.installs, 0, phase)
    assert.equal(state.cancelled, 1, phase)
    assert.equal(quits, 0, phase)
  }
})

test('a draft opened during shutdown cancels replacement and does not leave a sticky manual request', async t => {
  const { state, controller } = fixture(t)
  state.drain = async () => { state.safe = false; return true }
  await controller.restartIfSafe(true)
  assert.equal(state.installs, 0)
  assert.equal(state.cancelled, 1)
  assert.match(controller.status.state, /save your work/)
  state.safe = true
  await controller.restartIfSafe()
  assert.equal(state.drains, 1)
  assert.equal(quits, 0)
  assert.match(controller.status.state, /background/)
})

test('pausing updates during shutdown is respected before replacement', async t => {
  const { state, controller } = fixture(t)
  state.drain = async () => { controller.setPreference('automaticUpdates', false); return true }
  await controller.restartIfSafe(true)
  assert.equal(state.attempts, 0)
  assert.equal(state.cancelled, 1)
  assert.equal(controller.canRequestRestart, false)
  assert.equal(quits, 0)
})

test('work starting at the final installer guard prevents replacement', async t => {
  const { state, controller } = fixture(t)
  state.beforeFinalGuard = () => { state.busy = true }
  await controller.restartIfSafe(true)
  assert.equal(state.attempts, 1)
  assert.equal(state.installs, 0)
  assert.equal(state.cancelled, 1)
  assert.equal(quits, 0)
})

test('overlapping restart requests perform only one drain and installation', async t => {
  const { state, controller } = fixture(t)
  let release
  state.drain = () => new Promise(resolve => { release = resolve })
  const first = controller.restartIfSafe(true)
  const second = controller.restartIfSafe(true)
  await new Promise(resolve => setImmediate(resolve))
  assert.equal(state.drains, 1)
  release(true)
  await Promise.all([first, second])
  assert.equal(state.installs, 1)
  assert.equal(quits, 1)
})

for (const platform of ['Windows', 'Mac', 'Linux']) {
  for (const mode of ['automatic', 'requested', 'requested-minimized', 'requested-hidden', 'background-disabled']) {
    test(`${platform} handoff preserves ${mode} presentation through one relaunch`,
      { skip: platform === 'Linux' && process.platform !== 'linux' }, async t => {
      const { state, controller, directory } = fixture(t)
      if (platform !== 'Windows') controller.windows = undefined
      if (platform === 'Mac') controller.mac = { install: () => { state.installs++; return true } }
      state.focused = false; idle = 600
      state.minimized = mode === 'requested-minimized'
      state.visible = mode !== 'requested-hidden'
      controller.preferences.background = mode !== 'background-disabled'
      await controller.restartIfSafe(mode.startsWith('requested'))
      const path = join(directory, 'desktop-update-relaunch.json')
      assert.equal(existsSync(path), true, 'Only a successful installer handoff leaves a relaunch hint')
      // The new process reads its installed version, not the updater's old one.
      t.mock.method(app, 'getVersion', () => '4.0.12')
      assert.equal(controller.consumeBackgroundRelaunch(),
        ['automatic', 'requested-minimized', 'requested-hidden'].includes(mode))
      assert.equal(controller.consumeBackgroundRelaunch(), null, 'Later deliberate launches use normal startup')
      assert.equal(existsSync(path), false)
    })
  }
}

test('Windows presentation follows the final guard after asynchronous installer validation', async t => {
  const { state, controller } = fixture(t)
  state.beforeFinalGuard = () => { state.minimized = true }
  await controller.restartIfSafe(true)
  t.mock.method(app, 'getVersion', () => '4.0.12')
  assert.equal(controller.consumeBackgroundRelaunch(), true)
})

test('work starting at the final guard cannot leave a background relaunch hint', async t => {
  const { state, controller, directory } = fixture(t)
  state.beforeFinalGuard = () => { state.safe = false }
  await controller.restartIfSafe(true)
  assert.equal(state.installs, 0)
  assert.equal(existsSync(join(directory, 'desktop-update-relaunch.json')), false)
})

for (const failure of ['refused', 'throw', 'late-error', 'cancelled']) {
  test(`${failure} installation removes its one-use relaunch state`, async t => {
    const { controller, directory } = fixture(t)
    controller.windows.install = async guard => {
      assert.equal(await guard(), true)
      if (failure === 'throw') throw new Error('Disposable installer refusal')
      return failure !== 'refused'
    }
    await controller.restartIfSafe(true)
    if (failure === 'late-error' || failure === 'cancelled') {
      controller.platformEvent({ state: failure === 'late-error' ? 'error' : 'cancelled' })
    }
    assert.equal(existsSync(join(directory, 'desktop-update-relaunch.json')), false)
  })
}

test('a newer background preference overrides the consumed hint', async t => {
  const { state, controller } = fixture(t)
  state.focused = false; idle = 600
  await controller.restartIfSafe()
  controller.preferences.background = false
  t.mock.method(app, 'getVersion', () => '4.0.12')
  assert.equal(controller.consumeBackgroundRelaunch(), false)
})

async function advance(t, milliseconds) {
  t.mock.timers.tick(milliseconds)
  await new Promise(resolve => setImmediate(resolve))
}

test('failed checks retry promptly, bound outage traffic and allow a fresh manual attempt', async t => {
  t.mock.timers.enable({ apis: ['setTimeout', 'setInterval'] })
  t.mock.method(Math, 'random', () => 0)
  const { controller } = fixture(t, { ready: false })
  let checks = 0
  controller.windows.check = async () => {
    checks++
    // A provider event and a rejected download must not schedule two retries.
    controller.platformEvent({ state: 'error' })
    throw new Error('Disposable unavailable provider')
  }
  await advance(t, 60_000)
  assert.equal(checks, 1)
  await advance(t, 59_999)
  assert.equal(checks, 1)
  await advance(t, 1)
  assert.equal(checks, 2)
  await advance(t, 5 * 60_000)
  assert.equal(checks, 3)
  await advance(t, 15 * 60_000)
  assert.equal(checks, 4)
  assert.match(controller.status.state, /next scheduled check/)
  await advance(t, 30 * 60_000)
  assert.equal(checks, 4)
  await controller.check()
  assert.equal(checks, 5)
  await advance(t, 60_000)
  assert.equal(checks, 6)
})

test('a successful retry clears its timer and retains real restart safeguards', async t => {
  t.mock.timers.enable({ apis: ['setTimeout', 'setInterval'] })
  t.mock.method(Math, 'random', () => 0)
  const { controller, state } = fixture(t, { ready: false })
  let checks = 0
  controller.windows.check = async () => {
    checks++
    controller.platformEvent(checks === 1 ? { state: 'error' } : { state: 'ready', version: '4.0.12' })
  }
  await advance(t, 60_000)
  await advance(t, 60_000)
  assert.equal(checks, 2)
  assert.equal(controller.canRequestRestart, true)
  await advance(t, 20 * 60_000)
  assert.equal(checks, 2)
  assert.equal(state.drains, 0)
  assert.equal(state.installs, 0)
  assert.match(controller.status.state, /background/)
})

test('pausing or quitting cancels retry timers, including late failure events', async t => {
  t.mock.timers.enable({ apis: ['setTimeout', 'setInterval'] })
  t.mock.method(Math, 'random', () => 0)
  const { controller } = fixture(t, { ready: false })
  let checks = 0
  controller.windows.check = async () => { checks++; controller.platformEvent({ state: 'error' }) }
  await advance(t, 60_000)
  assert.equal(checks, 1)
  controller.setPreference('automaticUpdates', false)
  await advance(t, 10 * 60_000)
  await controller.check()
  assert.equal(checks, 1)
  controller.setPreference('automaticUpdates', true)
  await advance(t, 0)
  assert.equal(checks, 2)
  app.emit('will-quit')
  controller.platformEvent({ state: 'error' })
  await controller.check()
  await advance(t, 60 * 60_000)
  assert.equal(checks, 2)
})

test('a pending provider check never overlaps with a retry or queued manual check', async t => {
  t.mock.timers.enable({ apis: ['setTimeout', 'setInterval'] })
  t.mock.method(Math, 'random', () => 0)
  const { controller } = fixture(t, { ready: false })
  let checks = 0
  let release
  controller.windows.check = async () => {
    checks++
    if (checks === 1) {
      await new Promise(resolve => { release = resolve })
      controller.platformEvent({ state: 'error' })
    } else controller.platformEvent({ state: 'current' })
  }
  await advance(t, 60_000)
  await controller.check()
  await advance(t, 5 * 60_000)
  assert.equal(checks, 1)
  release()
  await advance(t, 0)
  assert.equal(checks, 2)
  assert.equal(controller.status.state, 'Up to date')
  await advance(t, 20 * 60_000)
  assert.equal(checks, 2)
})
