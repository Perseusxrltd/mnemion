import { spawn, spawnSync } from 'node:child_process'
import { existsSync, mkdirSync, readFileSync, rmSync } from 'node:fs'
import { join } from 'node:path'
import { root as repoRoot, platformArtifacts } from './platform-artifacts.mjs'

const appExe = process.env.MNEMION_PACKAGED_APP || platformArtifacts().app
const smokeRoot = join(repoRoot, '.tmp', 'packaged-app-smoke')
const userData = join(smokeRoot, 'user-data')
const smokeFile = join(smokeRoot, 'smoke-status.json')
const logs = {
  stdout: '',
  stderr: '',
}

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
mkdirSync(smokeRoot, { recursive: true })

const child = spawn(appExe, [], {
  env: {
    ...process.env,
    ELECTRON_ENABLE_LOGGING: '1',
    MNEMION_LEGACY_STUDIO: '0',
    MNEMION_STUDIO_USER_DATA: userData,
    MNEMION_STUDIO_SMOKE_FILE: smokeFile,
    MNEMION_STUDIO_SMOKE_HEADLESS: '0',
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

let succeeded = false

try {
  const status = await waitForSmokeStatus()
  if (!status.trayCreated && process.platform !== 'linux') fail('Packaged app did not create a tray')
  if (status.trayCreated && !status.trayIconLoaded) fail('Packaged app tray icon was empty or missing')
  if (process.platform === 'win32' && !String(status.trayIconSource ?? '').endsWith('icon.ico')) {
    fail(`Packaged app did not prefer the Windows tray .ico asset: ${status.trayIconSource}`)
  }
  if (!status.windowCreated) fail('Packaged app did not create its window')
  if (status.legacyEnabled) fail('A default launch unexpectedly enabled the legacy backend')
  if (!status.renderer?.workspace || !status.renderer?.serviceBridge || !status.renderer?.vaultBridge) {
    fail(`Packaged renderer or preload failed: ${JSON.stringify(status.renderer)}`)
  }
  if (status.renderer.nodeAvailable) fail('Node must not be available to the renderer')
  if (!status.localClient?.capabilities?.includes('obsidian-refresh')) {
    fail('The packaged local client does not support Obsidian refresh')
  }
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
  }, null, 2))
  succeeded = true
} catch (error) {
  if (logs.stdout.trim()) console.error(logs.stdout.trim())
  if (logs.stderr.trim()) console.error(logs.stderr.trim())
  console.error(error.message)
  process.exitCode = 1
} finally {
  stopProcessTree(child)
  if (process.env.MNEMION_KEEP_SMOKE !== '1') {
    await removeSmokeRoot()
  }
}

if (succeeded) {
  process.exit(0)
}
