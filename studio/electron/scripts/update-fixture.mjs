// Test entry point only; normal packages do not include this file.
import { app, BrowserWindow, powerMonitor } from 'electron'
import { readFileSync, appendFileSync } from 'node:fs'
import { join } from 'node:path'
import { DesktopUpdates } from './dist/updates.js'

const fixture = JSON.parse(readFileSync(join(process.resourcesPath, 'update-fixture.json'), 'utf8'))
app.setPath('userData', fixture.userData)
let updates
let busy = false
let idleSeconds = 0
let restarts = 0
let quitting = false
const sleep = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds))
function record(event, detail = {}) {
  appendFileSync(fixture.receipt, JSON.stringify({ event, version: app.getVersion(), pid: process.pid, ...detail }) + '\n')
}
function assert(condition, message) {
  if (!condition) throw new Error(message)
}
process.on('uncaughtException', error => { record('error', { message: error.message }); app.exit(1) })
process.on('unhandledRejection', error => { record('error', { message: String(error) }); app.exit(1) })

app.on('before-quit', event => {
  if (updates?.quitNeedsUpdateCleanup) {
    event.preventDefault()
    if (quitting) return
    quitting = true
    void updates.prepareQuit().then(stopped => { quitting = false; if (stopped) app.quit() })
  }
})

await app.whenReady()
record('launched')
if (app.getVersion() === fixture.expectedVersion) {
  // The new process must stay alive long enough for the native installer to finish.
  record('relaunched')
} else {
  const window = new BrowserWindow({
    width: 500, height: 300, show: false,
    webPreferences: { contextIsolation: true, sandbox: true, nodeIntegration: false },
  })
  await window.loadURL('data:text/html;charset=utf-8,' + encodeURIComponent(
    '<textarea></textarea><script>window.mnemion={updateSafety:()=>document.querySelector("textarea").value===""}</script>',
  ))
  // Only system inactivity is simulated; Sparkle and Electron run natively.
  powerMonitor.getSystemIdleTime = () => idleSeconds
  updates = new DesktopUpdates(() => window, () => busy, () => {
    restarts += 1
    record('install-authorized')
  }, () => {})
  await updates.check()
  assert(updates.status.version === fixture.expectedVersion, 'The signed update did not become ready')
  assert(updates.status.state.includes('Update ready'), 'The desktop updater is not waiting safely')

  idleSeconds = 599
  await updates.restartIfSafe()
  assert(restarts === 0, 'A restart occurred before the idle threshold')
  idleSeconds = 600
  busy = true
  await updates.restartIfSafe()
  assert(restarts === 0, 'A restart interrupted an active transfer')
  busy = false
  await window.webContents.executeJavaScript('document.querySelector("textarea").value="unfinished draft"')
  await updates.restartIfSafe()
  assert(restarts === 0, 'A restart discarded a renderer draft')
  await window.webContents.executeJavaScript('document.querySelector("textarea").value=""')
  window.show()
  app.focus({ steal: true })
  window.focus()
  const focusDeadline = Date.now() + 5000
  while (!window.isFocused() && Date.now() < focusDeadline) await sleep(100)
  assert(window.isFocused(), 'The native test window could not be focused')
  await updates.restartIfSafe()
  assert(restarts === 0, 'A restart interrupted a focused window')
  record('guards-passed', { idle: true, transfer: true, draft: true, focus: true })
  window.hide()
  await sleep(100)
  await updates.restartIfSafe()
  assert(restarts === 1, 'An idle, unfocused, clean session did not authorize installation')
}
