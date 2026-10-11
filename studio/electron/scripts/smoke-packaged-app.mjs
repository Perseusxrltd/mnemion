import { spawn, spawnSync } from 'node:child_process'
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { randomBytes, randomUUID } from 'node:crypto'
import { createServer } from 'node:http'
import { join } from 'node:path'
import { root as repoRoot, platformArtifacts } from './platform-artifacts.mjs'

const appExe = process.env.MNEMION_PACKAGED_APP || platformArtifacts().app
const smokeRoot = join(repoRoot, '.tmp', 'packaged-app-smoke')
const userData = join(smokeRoot, 'user-data')
const smokeFile = join(smokeRoot, 'smoke-status.json')
const workspaceConfig = join(smokeRoot, 'workspace-probe.json')
const logs = {
  stdout: '',
  stderr: '',
}
let child

function fail(message) {
  throw new Error(message)
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms))
}

async function waitForSmokeStatus(timeoutMs = 60_000) {
  const deadline = Date.now() + timeoutMs
  let last = null

  while (Date.now() < deadline) {
    if (child.exitCode !== null) {
      fail(`Packaged app exited before client-ready. exitCode=${child.exitCode}; last=${JSON.stringify(last)}`)
    }
    if (existsSync(smokeFile)) {
      const parsed = JSON.parse(readFileSync(smokeFile, 'utf8'))
      last = parsed
      if (parsed.stage === 'client-ready') return parsed
      if (['backend-timeout', 'backend-exit', 'startup-error', 'uncaught-exception', 'unhandled-rejection'].includes(parsed.stage)) {
        fail(`Packaged app smoke failed at ${parsed.stage}: ${JSON.stringify(parsed)}`)
      }
    }
    await sleep(500)
  }

  fail(`Packaged app did not report client-ready. Last status: ${JSON.stringify(last)}`)
}

function hasShellTrayWarning() {
  return /No displays detected|Unable to create status tray icon|Error setting status tray icon image|Unable to set tooltip for status tray icon/.test(logs.stderr)
}

function stopProcessTree(child) {
  if (!child.pid) return
  if (process.platform === 'win32') {
    spawnSync('taskkill.exe', ['/PID', String(child.pid), '/T', '/F'], { stdio: 'ignore' })
  } else {
    child.kill('SIGTERM')
  }
  child.stdout?.destroy()
  child.stderr?.destroy()
  child.unref()
}

async function stopAndWait() {
  const stopped = child
  stopProcessTree(stopped)
  const deadline = Date.now() + 10000
  while (stopped.exitCode === null && stopped.signalCode === null && Date.now() < deadline) await sleep(100)
  if (stopped.exitCode === null && stopped.signalCode === null) fail('The native app did not exit before the restart check')
}

async function removeSmokeRoot() {
  for (let attempt = 0; attempt < 24; attempt += 1) {
    try {
      rmSync(smokeRoot, { recursive: true, force: true })
      return
    } catch (err) {
      if (attempt === 23) {
        if (process.env.MNEMION_VERBOSE_SMOKE_CLEANUP === '1') {
          console.warn(`Unable to remove smoke temp folder: ${err.message}`)
        }
        return
      }
      await sleep(500)
    }
  }
}

if (!existsSync(appExe)) {
  fail(`Packaged app executable not found: ${appExe}`)
}

rmSync(smokeRoot, { recursive: true, force: true })
mkdirSync(smokeRoot, { recursive: true, mode: 0o700 })

const credential = randomBytes(32).toString('base64url')
const identity = { principal_id: randomUUID(), tenant_id: randomUUID(), name: 'Native test user', tenant_name: 'Native validation', administrator: false }
let authenticatedRequests = 0
let unexpectedRequests = 0
const service = createServer((request, response) => {
  response.setHeader('Content-Type', 'application/json')
  if (request.headers.authorization !== 'Bearer ' + credential) {
    unexpectedRequests++
    response.writeHead(401).end('{}')
    return
  }
  authenticatedRequests++
  if (request.url === '/organization/v1/me') response.end(JSON.stringify(identity))
  else if (request.url === '/organization/v1/spaces') response.end(JSON.stringify({ items: [], next_cursor: null }))
  else { unexpectedRequests++; response.writeHead(404).end('{}') }
})
await new Promise((resolve, reject) => { service.once('error', reject); service.listen(0, '127.0.0.1', resolve) })
const endpoint = `http://127.0.0.1:${service.address().port}/organization`

function launch(phase) {
  rmSync(smokeFile, { force: true })
  writeFileSync(workspaceConfig, JSON.stringify({ endpoint, credential, phase }), { mode: 0o600 })
  const args = process.platform === 'linux' && process.env.MNEMION_NATIVE_KEYRING_REQUIRED === '1' ? ['--password-store=gnome-libsecret'] : []
  child = spawn(appExe, args, {
    env: {
      ...process.env,
      ELECTRON_ENABLE_LOGGING: '1',
      MNEMION_LEGACY_STUDIO: '0',
      MNEMION_STUDIO_USER_DATA: userData,
      MNEMION_STUDIO_SMOKE_FILE: smokeFile,
      MNEMION_STUDIO_SMOKE_HEADLESS: '0',
      MNEMION_STUDIO_WORKSPACE_PROBE: workspaceConfig,
    },
    windowsHide: true,
    stdio: ['ignore', 'pipe', 'pipe'],
  })
  child.stdout?.on('data', chunk => {
    logs.stdout += chunk.toString()
    if (logs.stdout.length > 20_000) logs.stdout = logs.stdout.slice(-20_000)
  })
  child.stderr?.on('data', chunk => {
    logs.stderr += chunk.toString()
    if (logs.stderr.length > 20_000) logs.stderr = logs.stderr.slice(-20_000)
  })
}

function validate(status) {
  if (!status.trayCreated && process.platform !== 'linux') fail('Packaged app did not create a tray')
  if (status.trayCreated && !status.trayIconLoaded) fail('Packaged app tray icon was empty or missing')
  if (process.platform === 'win32' && !String(status.trayIconSource ?? '').endsWith('icon.ico')) {
    fail(`Packaged app did not prefer the Windows tray .ico asset: ${status.trayIconSource}`)
  }
  if (process.platform === 'darwin' && !String(status.trayIconSource ?? '').endsWith('icon-trayTemplate.png')) {
    fail('Packaged Mac app did not load its menu-bar template icon')
  }
  if (!status.windowCreated) fail('Packaged app did not create its window')
  if (status.legacyEnabled) fail('A default launch unexpectedly enabled the legacy backend')
  if (!status.renderer?.workspace || !status.renderer?.serviceBridge || !status.renderer?.vaultBridge) {
    fail(`Packaged renderer or preload failed: ${JSON.stringify(status.renderer)}`)
  }
  if (!status.renderer.workspaceBridge) fail('The packaged workspace setup bridge is unavailable')
  const secureStorage = status.renderer.secureStorage
  if ((process.platform !== 'linux' || process.env.MNEMION_NATIVE_KEYRING_REQUIRED === '1') && !secureStorage?.available) fail('The native OS credential store is unavailable')
  if (secureStorage?.available) {
    if (!secureStorage.encryptedRoundTrip || !secureStorage.disconnectPersisted || !secureStorage.forgotten) fail('OS-protected workspace storage did not pass its native checks')
  } else if (!secureStorage?.plaintextFallbackRefused) fail('An unavailable keychain must not fall back to plaintext credentials')
  if (status.renderer.nodeAvailable) fail('Node must not be available to the renderer')
  if (!status.renderer.documentation) fail('Packaged versioned documentation must load without a service')
  const guard = status.renderer.updateGuard
  if (!guard?.clean || guard.edited !== false || !guard.removed || !guard.viewChanged) {
    fail('Automatic restarts must preserve unsaved drafts without blocking on read-only view filters')
  }
  if (existsSync(join(userData, 'desktop-preferences.json'))) fail('Smoke tests must not register login startup')
  if (!status.localClient?.capabilities?.includes('obsidian-refresh')) {
    fail('The packaged local client does not support Obsidian refresh')
  }
  if (status.localClient.version !== status.version) fail('The packaged local client and desktop versions must match')
  const protocol = status.renderer.workspaceProtocol
  if (!protocol?.authenticated || !protocol.outsideRejected || !protocol.staleRejected || !protocol.reconnectPaused) {
    fail('The native workspace protocol did not authenticate or constrain the saved connection')
  }
}

let succeeded = false
try {
  launch('save')
  const first = await waitForSmokeStatus()
  validate(first)
  const savedFile = join(userData, 'workspaces', 'connections.json')
  if (first.renderer.secureStorage.available) {
    if (!existsSync(savedFile) || readFileSync(savedFile, 'utf8').includes(credential)) fail('The native bookmark must persist with an encrypted key')
  } else if (existsSync(savedFile)) fail('A session-only connection must not write a credential file')
  await stopAndWait()
  launch('resume')
  const status = await waitForSmokeStatus()
  validate(status)
  const protocol = status.renderer.workspaceProtocol
  if (status.renderer.secureStorage.available) {
    if (!protocol.processRestartRestored || !protocol.uiRestored || !protocol.forgotten) fail('The saved workspace must reopen after app restart and support forgetting')
  } else if (!protocol.sessionOnlyDidNotPersist) fail('The unavailable-keychain session must be absent after app restart')
  if (authenticatedRequests < 4 || unexpectedRequests) fail('The native service fixture received an unexpected or unauthenticated request')
  console.log(JSON.stringify({
    ok: true,
    trayCreated: status.trayCreated,
    trayIconLoaded: status.trayIconLoaded,
    trayIconSource: status.trayIconSource,
    shellTrayWarning: hasShellTrayWarning(),
    windowCreated: status.windowCreated,
    version: status.version,
    localClient: status.localClient,
    renderer: status.renderer,
    firstLaunchProtocol: first.renderer.workspaceProtocol,
    authenticatedRequests,
  }, null, 2))
  succeeded = true
} catch (error) {
  if (logs.stdout.trim()) console.error(logs.stdout.trim())
  if (logs.stderr.trim()) console.error(logs.stderr.trim())
  console.error(error.message)
  process.exitCode = 1
} finally {
  if (child) stopProcessTree(child)
  service.closeAllConnections()
  await new Promise(resolve => service.close(resolve))
  if (process.env.MNEMION_KEEP_SMOKE !== '1') {
    await removeSmokeRoot()
  }
}

if (succeeded) {
  process.exit(0)
}
