// Private rehearsal entry point. It is never included by the production build.
import { app, BrowserWindow, net, powerMonitor, session } from 'electron'
import { appendFileSync, readFileSync, readdirSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { DesktopUpdates } from './dist/updates.js'
import { createWindowsUpdateFetch } from './dist/windows-update-network.js'

const fixture = JSON.parse(readFileSync(join(process.resourcesPath, 'update-fixture.json'), 'utf8'))
app.setPath('userData', fixture.userData)
let updates, window
let busy = false, idleSeconds = 0, shutdowns = 0, quitting = false, quitRequests = 0, cancelled = 0
let shutdownAllowed = true
const sleep = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds))
function record(event, detail = {}) {
  appendFileSync(fixture.receipt, JSON.stringify({ event, timestamp: new Date().toISOString(), version: app.getVersion(), pid: process.pid, ...detail }) + '\n')
}
function assert(condition, message) { if (!condition) throw new Error(message) }
function windowState() {
  return { focused: window.isFocused(), visible: window.isVisible(), minimized: window.isMinimized() }
}
async function mode(value) {
  const response = await fetch(fixture.control + '/' + value)
  assert(response.ok, 'Could not select the isolated fixture case')
}
async function until(predicate, message, timeout = 30_000) {
  const deadline = Date.now() + timeout
  while (!predicate() && Date.now() < deadline) await sleep(50)
  assert(predicate(), message)
}
process.on('uncaughtException', error => { record('error', { message: error.message }); app.exit(1) })
process.on('unhandledRejection', error => { record('error', { message: String(error) }); app.exit(1) })
app.on('will-quit', () => record('will-quit'))
process.on('exit', code => record('process-exit', { code }))
app.on('before-quit', event => {
  quitRequests++
  if (!updates?.quitNeedsUpdateCleanup) return
  event.preventDefault()
  if (quitting) return
  quitting = true
  void updates.prepareQuit().then(stopped => { quitting = false; if (stopped) app.quit() })
})
record('bootstrapped')
app.whenReady().then(async () => {
  record('launched')
  if (app.getVersion() === fixture.expectedVersion) { record('relaunched'); return }
  const network = session.fromPartition('mnemion-redirect-probe', { cache: false })
  const transport = createWindowsUpdateFetch(url => net.request({ url, session: network, redirect: 'manual', credentials: 'omit' }))
  const redirect = await transport(fixture.control + '/redirect-probe', { signal: AbortSignal.timeout(5000) })
  assert(redirect.status === 302 && redirect.headers.get('location') === fixture.control + '/redirect-target',
    'Electron manual redirects did not reach the update URL validator')
  record('native-redirect-verified')
  window = new BrowserWindow({ width: 500, height: 300, show: false,
    webPreferences: { contextIsolation: true, sandbox: true, nodeIntegration: false } })
  await window.loadURL('data:text/html;charset=utf-8,' + encodeURIComponent(
    '<textarea></textarea><script>window.mnemion={updateSafety:()=>document.querySelector("textarea").value===""}</script>',
  ))
  powerMonitor.getSystemIdleTime = () => idleSeconds
  updates = new DesktopUpdates(() => window, () => busy, async () => {
    shutdowns++
    await sleep(25)
    record('workspace-stop', { allowed: shutdownAllowed, window: windowState() })
    return shutdownAllowed
  }, () => {}, () => { cancelled++; record('restart-cancelled') })
  for (const name of ['bad-signature', 'wrong-architecture', 'oversized', 'interrupted']) {
    await mode(name)
    await updates.check()
    assert(updates.status.state.includes('unavailable'), `${name} was not rejected`)
    assert(shutdowns === 0 && quitRequests === 0, `${name} began installation`)
    record('rejected', { case: name })
  }
  await mode('older')
  await updates.check()
  assert(updates.status.state === 'Up to date', 'An older signed version was considered an update')
  record('rejected', { case: 'older' })

  await mode('stalled')
  const transfer = updates.check()
  await until(() => updates.status.state === 'Downloading update', 'The stalled transfer never started')
  updates.setPreference('automaticUpdates', false)
  await transfer
  await until(() => !updates.quitNeedsUpdateCleanup, 'Paused update did not finish cleanup')
  assert(shutdowns === 0 && quitRequests === 0 && !updates.enabled, 'Pausing the transfer failed')
  record('cancelled-transfer')

  await mode('valid')
  updates.setPreference('automaticUpdates', true)
  await until(() => updates.status.state.includes('Update ready'), 'A valid update did not become ready', 90_000)
  idleSeconds = 600
  const cache = join(fixture.userData, 'updates-windows')
  const installer = readdirSync(cache).find(name => name.endsWith('.exe'))
  assert(installer, 'The authenticated installer was not cached')
  writeFileSync(join(cache, installer), 'tampered after ready')
  await updates.restartIfSafe()
  assert(quitRequests === 0 && updates.status.state.includes('unavailable'), 'A modified cached installer was launched')
  assert(shutdowns === 1 && cancelled > 0, 'A rejected installer did not restore the stopped workspace')
  record('rejected', { case: 'cached-tamper' })
  idleSeconds = 0
  await updates.check()
  assert(updates.status.state.includes('Update ready'), 'A valid update did not recover after cached tampering')

  idleSeconds = 599
  await updates.restartIfSafe()
  assert(shutdowns === 1 && quitRequests === 0, 'A restart occurred before the idle threshold')
  idleSeconds = 600
  busy = true
  await updates.restartIfSafe()
  assert(shutdowns === 1 && quitRequests === 0, 'A restart interrupted an active transfer')
  busy = false
  await window.webContents.executeJavaScript('document.querySelector("textarea").value="unfinished draft"')
  await updates.restartIfSafe()
  assert(shutdowns === 1 && quitRequests === 0, 'A restart discarded a renderer draft')
  await window.webContents.executeJavaScript('document.querySelector("textarea").value=""')
  window.restore()
  window.show()
  window.focus()
  try {
    await until(() => window.isFocused() && window.isVisible() && !window.isMinimized(),
      'The native test window could not become visible, restored and focused', 5000)
  } finally { record('focus-window-state', windowState()) }
  await updates.restartIfSafe()
  record('focus-guard-result', { ...windowState(), shutdowns, quitRequests, status: updates.status.state })
  assert(shutdowns === 1 && quitRequests === 0, 'A restart interrupted a focused window')
  window.hide()
  await sleep(100)
  shutdownAllowed = false
  const beforeCancellation = cancelled
  await updates.restartIfSafe()
  assert(shutdowns === 2 && quitRequests === 0 && cancelled === beforeCancellation + 1,
    'A failed workspace stop did not cancel installation')
  record('guards-passed', { idle: true, transfer: true, draft: true, focus: true, shutdown: true })
  shutdownAllowed = true
  await updates.restartIfSafe()
  assert(shutdowns === 3 && quitRequests === 1, 'An idle clean session did not launch the verified installer')
})
