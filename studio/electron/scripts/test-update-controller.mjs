/** Exercise the actual controller across asynchronous shutdown/install guards. */
import assert from 'node:assert/strict'
import { EventEmitter } from 'node:events'
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { after, mock, test } from 'node:test'

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
after(() => {
  mock.restoreAll()
  if (previousResources === undefined) delete process.resourcesPath
  else process.resourcesPath = previousResources
  rmSync(temporary, { recursive: true, force: true })
})

function fixture(t, { ready = true } = {}) {
  directory = mkdtempSync(join(temporary, 'profile-'))
  mkdirSync(join(directory, '.config'))
  writeFileSync(join(directory, 'desktop-preferences.json'), JSON.stringify({ automaticUpdates: true, startAtLogin: false, background: true }))
  const keys = ['APPIMAGE', 'MNEMION_AUTO_UPDATE', 'MNEMION_START_AT_LOGIN', 'MNEMION_STUDIO_SMOKE_FILE', 'MNEMION_STUDIO_SMOKE_HEADLESS']
  const previous = Object.fromEntries(keys.map(key => [key, process.env[key]]))
  for (const key of keys) delete process.env[key]
  process.env.APPIMAGE = join(directory, 'fixture.AppImage')
  idle = 0; idleState = 'active'; quits = 0
  const state = { safe: true, focused: true, busy: false, drains: 0, cancelled: 0, attempts: 0, installs: 0,
    drain: async () => true, beforeFinalGuard: () => {} }
  const window = { isFocused: () => state.focused, isVisible: () => true, isMinimized: () => false,
    webContents: { executeJavaScript: async () => state.safe } }
  const controller = new DesktopUpdates(() => window, () => state.busy,
    async () => { state.drains++; return await state.drain() }, () => {}, () => { state.cancelled++ })
  // The adapter is a fixture; policy, all controller rechecks and the exact
  // Windows final authorization callback remain the production implementation.
  controller.mac = undefined
  controller.windows = {
    check: async () => {}, cancel: async () => {},
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
  return { state, controller }
}

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
