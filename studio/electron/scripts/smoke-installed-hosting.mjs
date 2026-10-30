/** Install this build into a new disposable location and use the real local UI. */
import { spawn, spawnSync } from 'node:child_process'
import { copyFileSync, existsSync, mkdirSync, readFileSync, readdirSync, realpathSync, rmSync, writeFileSync } from 'node:fs'
import { rm } from 'node:fs/promises'
import { createHash, randomUUID } from 'node:crypto'
import { createServer } from 'node:net'
import { isAbsolute, join } from 'node:path'
import { tmpdir } from 'node:os'
import { platformArtifacts, root } from './platform-artifacts.mjs'
import { verifyNativeResources } from './native-resources.mjs'
import { localDiagnostic } from '../dist/local-diagnostics.js'
import { workspaceOpenFailure } from '../dist/local-hosting-diagnostics.js'
import { modelSetupFailure } from '../dist/native-model-diagnostics.js'
import { backupStateDiagnostic } from '../dist/backup-state-diagnostics.js'
import { sanitizeObservation } from '../telemetry-observation-diagnostic.mjs'
import { finishResourceCleanup, inspectedBodyHex, nsisSilentUninstallArgs, performOwnedInstall, publicOwnedReport, resourceCaseStoreReady, resourceInstallSteps, resourceVerificationRoot, verifyPreparedPackage, waitForOwnedWindowsRemoval, windowsProductReadScript, windowsProductRefusalScript } from './installed-resource-report.mjs'
import { publishResourceCase } from './resource-case-boundary.mjs'

const artifacts = platformArtifacts()
// Production NSIS owns registry entries. Run only on a fresh hosted CI machine,
// and explicitly refuse an existing installation before changing anything.
if (process.platform === 'win32' && (process.env.CI !== 'true' || process.env.RUNNER_OS !== 'Windows')) {
  throw new Error('The production NSIS first-install probe requires a disposable Windows CI runner')
}
// macOS exposes /var through a symlink; the private workspace correctly rejects
// redirected parents, so start with the canonical OS temporary directory.
// Elevated Windows runners give Node-created directories an Administrators
// owner. Create this disposable profile with explicit current-user ownership
// before either the app or its private fixture writer uses it.
const python = process.env.MNEMION_ENGINE_PYTHON
if (!python) throw new Error('The native host fixture needs the pinned build interpreter')
const temporary = join(realpathSync(tmpdir()), 'mnemion-installed-hosting-' + randomUUID())
run(python, ['-c', 'from pathlib import Path; import sys; from mnemion.local_state import directory; directory(Path(sys.argv[1]), exist_ok=False)', temporary], { cwd: root })
const installed = join(temporary, 'Applications Équipe with spaces')
const userData = join(temporary, 'Private profile')
const probeFile = join(temporary, 'hosting-probe.json')
const smokeFile = join(temporary, 'smoke.json')
const quitFile = join(temporary, 'quit-request')
const telemetryDelivery = process.env.MNEMION_TELEMETRY_INSTALLED_DELIVERY === '1'
const telemetryResource = process.env.MNEMION_TELEMETRY_INSTALLED_RESOURCE === '1'
if (telemetryDelivery && telemetryResource) throw new Error('Installed delivery and the resource workload are separate runs')
const evidenceFile = join(root, telemetryResource ? 'build-tmp/telemetry-installed-resources.json' : telemetryDelivery ? 'build-tmp/telemetry-installed-delivery.json' : 'build-tmp/installed-hosting-evidence.json')
const uninstallDirs = []
const resourceCases = []
const resourceInstallations = []
const removedInstallationIds = new Set()
const cleanupFailures = []
let executable
let child
let stdout = '', stderr = ''
let phase = 'installation'
let installationComplete = false
let succeeded = false
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms))
const environment = Object.fromEntries(Object.entries(process.env).filter(([key]) => !key.startsWith('MNEMION_')))

function setupFailure(error) {
  // The ordinary error/log remains private. Revalidate each diagnostic field
  // before placing this small classification in the uploaded artifact.
  if (typeof error !== 'string' || error.length > 512) return undefined
  const match = /^Error: Missing setup field: (\{[^\n]+\})$/.exec(error)
  if (!match) return undefined
  try {
    const value = JSON.parse(match[1])
    const selectors = ['input[autocomplete="organization"]', 'input[autocomplete="name"]', '.ws-memory-limit input', '.ws-setup-advanced input[max="65535"]', '.ws-journal-host input[type="url"]', 'unknown']
    if (!selectors.includes(value.selector) || ![null, 1, 2, 3].includes(value.step) || !['workspace', 'journal', 'help', 'other'].includes(value.route)) return undefined
    return { selector: value.selector, step: value.step, route: value.route }
  } catch { return undefined }
}

function run(command, args, options = {}) {
  const result = spawnSync(command, args, { encoding: 'utf8', timeout: 180000, maxBuffer: 1024 * 1024, ...options })
  if (result.error || result.status !== 0) throw new Error(`Installed-app command failed: ${result.error?.message || result.stderr || result.stdout}`)
  return result.stdout
}

function refuseExistingWindowsProduct() {
  if (process.platform !== 'win32') return
  const env = { ...environment }
  for (const key of Object.keys(env)) if (key.toLowerCase() === 'psmodulepath') delete env[key]
  run('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command', windowsProductRefusalScript()], { env })
}

function readWindowsMnemionProducts() {
  const env = { ...environment }
  for (const key of Object.keys(env)) if (key.toLowerCase() === 'psmodulepath') delete env[key]
  let stdout
  try {
    stdout = run('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command', windowsProductReadScript()], { env })
  } catch { throw new Error('uninstall_failed') }
  try {
    const parsed = JSON.parse(stdout || '[]')
    return Array.isArray(parsed) ? parsed : [parsed]
  } catch { throw new Error('uninstall_failed') }
}

async function installPrepared(destination, installer, refuseExisting) {
  if (process.platform === 'win32') {
    if (refuseExisting) refuseExistingWindowsProduct()
    const env = { ...environment, MNEMION_PROBE_INSTALLER: installer, MNEMION_PROBE_INSTALL_DIRECTORY: destination }
    for (const key of Object.keys(env)) if (key.toLowerCase() === 'psmodulepath') delete env[key]
    run('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command',
      '$ErrorActionPreference="Stop"; $p=Start-Process -FilePath $env:MNEMION_PROBE_INSTALLER -ArgumentList @("/S","/currentuser",("/D="+$env:MNEMION_PROBE_INSTALL_DIRECTORY)) -PassThru -Wait; exit $p.ExitCode'], { env })
    executable = join(destination, 'Mnemion Studio.exe')
  } else if (process.platform === 'darwin') {
    const volume = join(temporary, 'installer-volume-' + createHash('sha256').update(destination).digest('hex').slice(0, 12))
    run('hdiutil', ['attach', '-readonly', '-nobrowse', '-mountpoint', volume, installer])
    try {
      mkdirSync(destination)
      run('ditto', [join(volume, 'Mnemion Studio.app'), join(destination, 'Mnemion Studio.app')])
    } finally { run('hdiutil', ['detach', volume]) }
    executable = join(destination, 'Mnemion Studio.app/Contents/MacOS/Mnemion Studio')
  } else {
    mkdirSync(destination)
    const appImage = join(destination, 'Mnemion Studio.AppImage')
    copyFileSync(installer, appImage)
    run('chmod', ['755', appImage])
    run(appImage, ['--appimage-extract'], { cwd: destination })
    // AppImages support a user-owned portable installation without root/FUSE.
    executable = join(destination, 'squashfs-root/AppRun')
  }
  if (!existsSync(executable)) throw new Error('The native installer omitted the application executable')
}

function verifyInstalled(destination, manifest = undefined, packageName = undefined) {
  installationComplete = true
  uninstallDirs.push(destination)
  const resources = process.platform === 'darwin' ? join(destination, 'Mnemion Studio.app/Contents/Resources') :
    join(destination, ...(process.platform === 'linux' ? ['squashfs-root', 'resources'] : ['resources']))
  if (manifest === undefined) return verifyNativeResources(resources)
  return verifyPreparedPackage(manifest, packageName, resources)
}

async function install(destination = installed, installer = artifacts.installers[0], refuseExisting = true) {
  await installPrepared(destination, installer, refuseExisting)
  return verifyInstalled(destination)
}

async function freePort() {
  const server = createServer()
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve) })
  const port = server.address().port
  await new Promise(resolve => server.close(resolve))
  return port
}

async function launch(config) {
  phase = config.phase
  console.log("Installed local workspace probe: " + config.phase)
  rmSync(smokeFile, { force: true }); rmSync(quitFile, { force: true })
  writeFileSync(probeFile, JSON.stringify(config), { mode: 0o600 })
  stdout = ''; stderr = ''
  const args = process.platform === 'linux' && process.env.MNEMION_NATIVE_KEYRING_REQUIRED === '1' ? ['--password-store=gnome-libsecret'] : []
  child = spawn(executable, args, { cwd: installed, detached: process.platform !== 'win32', windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'],
    env: { ...environment, MNEMION_STUDIO_USER_DATA: userData, MNEMION_STUDIO_SMOKE_FILE: smokeFile,
      MNEMION_STUDIO_HOSTING_PROBE: probeFile,
      ...(telemetryDelivery ? { MNEMION_TELEMETRY_INSTALLED_DELIVERY: '1' } : {}),
      MNEMION_AUTO_UPDATE: '0', MNEMION_START_AT_LOGIN: '0', ELECTRON_ENABLE_LOGGING: '1' } })
  let spawnError
  child.on('error', error => { spawnError = error })
  child.stdout.on('data', bytes => { stdout = (stdout + bytes).slice(-16000) })
  child.stderr.on('data', bytes => { stderr = (stderr + bytes).slice(-16000) })
  const deadline = Date.now() + 12 * 60 * 1000
  let last
  while (Date.now() < deadline) {
    if (spawnError) throw spawnError
    if (child.exitCode !== null || child.signalCode !== null) throw new Error(`The installed app exited before hosting validation completed: phase=${phase}, exit=${child.exitCode}, signal=${child.signalCode}`)
    if (existsSync(smokeFile)) {
      try { last = JSON.parse(readFileSync(smokeFile, 'utf8')) } catch { await sleep(100); continue }
      if (last.stage === 'hosting-ready') return last.hosting
      if (['startup-error', 'uncaught-exception', 'unhandled-rejection', 'backend-exit'].includes(last.stage)) {
        throw new Error('Installed hosting failed: ' + JSON.stringify(last))
      }
    }
    await sleep(200)
  }
  throw new Error('Installed hosting timed out at ' + last?.stage)
}

async function stop() {
  if (!child) return
  // Exercise the app's real before-quit service/database drain. Do not replace it
  // with a direct database stop that could conceal an unsafe application exit.
  if (child.exitCode === null && child.signalCode === null) writeFileSync(quitFile, 'quit\n', { mode: 0o600 })
  const deadline = Date.now() + 120000
  while (child.exitCode === null && child.signalCode === null && Date.now() < deadline) await sleep(100)
  if (child.exitCode !== 0) throw new Error(`The installed application did not finish a clean shutdown: phase=${phase}, exit=${child.exitCode}, signal=${child.signalCode}`)
  const pidFile = join(userData, 'mnemion-local-workspace/database/postmaster.pid')
  if (existsSync(pidFile)) throw new Error('The installed app left its private PostgreSQL cluster running')
  const recovered = join(userData, 'mnemion-recovered-workspaces')
  if (existsSync(recovered) && readdirSync(recovered).some(id => existsSync(join(recovered, id, 'database/postmaster.pid')))) {
    throw new Error('The installed app left a recovered PostgreSQL cluster running')
  }
}

function loopbackFixture(value) {
  let url
  try { url = new URL(value) } catch { throw new Error('Telemetry delivery fixture refused a non-loopback destination') }
  const port = Number(url.port)
  if (url.protocol !== 'http:' || !['127.0.0.1', 'localhost'].includes(url.hostname) || url.username || url.password ||
      url.search || url.hash || (url.pathname !== '/' && url.pathname !== '') || !Number.isInteger(port) || port < 1 || port > 65535) {
    throw new Error('Telemetry delivery fixture refused a non-loopback destination')
  }
  return url.origin
}

function readDeliveryStore(credential) {
  const result = spawnSync(python, ['-m', 'deploy.probe_telemetry_installed', '--read-store', userData], {
    cwd: root, encoding: 'utf8', input: credential, timeout: 30000, maxBuffer: 1024 * 1024,
  })
  if (result.status !== 0) throw new Error('Installed telemetry store could not be read')
  return JSON.parse(result.stdout)
}

async function runInstalledTelemetryDelivery(nativeRuntime) {
  const endpoint = loopbackFixture(process.env.MNEMION_TELEMETRY_FIXTURE_ENDPOINT)
  const spaceId = process.env.MNEMION_TELEMETRY_FIXTURE_SPACE
  const credential = process.env.MNEMION_TELEMETRY_FIXTURE_KEY
  if (!/^[a-f0-9-]{36}$/.test(spaceId || '') || typeof credential !== 'string' || credential.length < 16 ||
      credential.length > 256 || /\s/.test(credential)) throw new Error('Telemetry delivery fixture is incomplete')
  const deliveryChecks = ['disclosure_required', 'setup_disclosure_deferred_without_permission', 'manual_choice_before_permission',
    'app_disclosure_acknowledged', 'exact_review_preserved', 'native_optout_invalidates_review', 'reenable_starts_empty',
    'discard_does_not_spend', 'approved_attempt_uses_inspected_body']
  const first = await launch({ phase: 'telemetry-delivery', endpoint, spaceId, credential })
  if (first.packaged !== true || first.runtime?.packaged !== true) throw new Error('The telemetry delivery probe did not run inside a packaged app')
  if (deliveryChecks.some(name => first.checks?.[name] !== true)) throw new Error('Installed telemetry delivery checks did not complete')
  if (!/^[0-9a-f]{50}$/.test(first.approved_body_hex || '')) throw new Error('Installed telemetry delivery did not return the inspected 25-byte body')
  await stop()
  const restarted = await launch({ phase: 'telemetry-restart' })
  if (restarted.packaged !== true || restarted.checks?.optout_and_review_survive_restart !== true) {
    throw new Error('Installed telemetry opt-out did not survive one clean restart')
  }
  await stop()
  const store = readDeliveryStore(credential)
  if (store.attempts?.[0] !== 1 || store.attempts?.[1] !== 65536 || store.lease_cleared !== true || store.queue_cells !== 0) {
    throw new Error('Installed telemetry delivery did not keep one cleared 65536-byte reservation')
  }
  if (store.fixture_content_absent !== true) throw new Error('Installed telemetry store retained fixture content')
  const installer = artifacts.installers[0]
  const observation = sanitizeObservation(first.observation)
  const evidence = {
    qualification: 'installed fixture delivery',
    app_checks_passed: true,
    collector_compared: false,
    production_collection_available: false,
    resource_acceptance: false,
    platform: process.platform,
    architecture: process.arch,
    packaged: true,
    runtime: first.runtime,
    installer_sha256: createHash('sha256').update(readFileSync(installer)).digest('hex'),
    approved_body_hex: first.approved_body_hex,
    review_checks: { ...first.checks, optout_and_review_survive_restart: true },
    app_launches: 2,
    durable: {
      attempts: store.attempts,
      lease_cleared: store.lease_cleared === true,
      queue_cells: store.queue_cells,
      fixture_content_absent: store.fixture_content_absent === true,
    },
    ...(observation ? { observation } : {}),
    nativeRuntime,
    scope: 'Diagnostic packaged app, loopback fixture disclosure baked before packaging, one inspected report and one restart. Production ingress, provider privacy, resources and full V08 remain unqualified.',
  }
  mkdirSync(join(root, 'build-tmp'), { recursive: true })
  writeFileSync(evidenceFile, JSON.stringify(evidence, null, 2) + '\n')
  console.log(JSON.stringify({ qualification: evidence.qualification, app_checks_passed: true, packaged: true }))
}

const RESOURCE_CASES = [
  { label: 'r1-unavailable', condition: 'unavailable', available: false, enabled: false, replicate: 1, package: 'inactive' },
  { label: 'r1-opted_out', condition: 'opted_out', available: true, enabled: false, replicate: 1, package: 'active' },
  { label: 'r1-enabled', condition: 'enabled', available: true, enabled: true, replicate: 1, package: 'active' },
  { label: 'r2-enabled', condition: 'enabled', available: true, enabled: true, replicate: 2, package: 'active' },
  { label: 'r2-opted_out', condition: 'opted_out', available: true, enabled: false, replicate: 2, package: 'active' },
  { label: 'r2-unavailable', condition: 'unavailable', available: false, enabled: false, replicate: 2, package: 'inactive' },
]
const RESOURCE_CHECKPOINTS = ['before_workspace_connect', 'workspace_connected', 'first_memory_cycle_and_delivery', '8_memory_cycles', '16_memory_cycles', '32_memory_cycles', '64_memory_cycles', '96_memory_cycles', '128_memory_cycles']
const installedExecutables = new Map()

function sameResourceCase(row, expected) {
  const keys = Object.keys(row || {}).sort().join()
  return keys === 'available,condition,enabled,label,package,replicate'
    && RESOURCE_CASES[0] && expected.label === row.label && expected.condition === row.condition
    && expected.available === row.available && expected.enabled === row.enabled
    && expected.replicate === row.replicate && expected.package === row.package
}

function loadResourceManifest() {
  const manifestPath = process.env.MNEMION_TELEMETRY_RESOURCE_MANIFEST
  const credential = process.env.MNEMION_TELEMETRY_FIXTURE_KEY
  if (!manifestPath || !existsSync(manifestPath)) throw new Error('Resource package preparation is missing')
  const text = readFileSync(manifestPath, 'utf8')
  if (text.includes('PRIVATE_RENDERER_MEMORY_CANARY') || text.includes(credential || 'api_key') || text.includes('api_key')) {
    throw new Error('Resource manifest contained private fixture material')
  }
  const manifest = JSON.parse(text)
  if (!/^[0-9a-f]{40}$/.test(manifest.source || '') || !Array.isArray(manifest.cases) || manifest.cases.length !== RESOURCE_CASES.length) {
    throw new Error('Resource package preparation is missing')
  }
  for (const condition of ['inactive', 'active']) {
    const item = manifest.packages?.[condition]
    if (!item || typeof item.installer !== 'string' || !/^[0-9a-f]{64}$/.test(item.sha256 || '') || !existsSync(item.installer)) {
      throw new Error('Resource package preparation is missing')
    }
    const actual = createHash('sha256').update(readFileSync(item.installer)).digest('hex')
    if (actual !== item.sha256 || item.condition !== condition) throw new Error('Resource package hash did not match the manifest')
    const sourceRoot = resourceVerificationRoot(manifest, condition)
    const disclosure = join(sourceRoot, 'mnemion/product_telemetry/disclosure.json')
    const route = join(sourceRoot, 'mnemion/product_telemetry/transport-route.json')
    if (!isAbsolute(sourceRoot) || !existsSync(disclosure) || !existsSync(route)) {
      throw new Error('Resource package preparation is missing')
    }
  }
  if (resourceVerificationRoot(manifest, 'inactive') === resourceVerificationRoot(manifest, 'active')) {
    throw new Error('Resource package preparation is missing')
  }
  if (manifest.packages.inactive.installer === manifest.packages.active.installer) throw new Error('Resource package preparation is missing')
  manifest.cases.forEach((row, index) => {
    if (!sameResourceCase(row, RESOURCE_CASES[index])) throw new Error('Resource package preparation is missing')
  })
  return manifest
}

function boundedCleanupCode(error) {
  const code = String(error && error.message || '')
  if (code === 'uninstall_unreadable' || code === 'uninstall_missing' || code === 'uninstall_failed') return code
  return 'uninstall_failed'
}

function uninstallWindowsProduct(directory) {
  let names
  try { names = readdirSync(directory) } catch { throw new Error('uninstall_unreadable') }
  const uninstaller = names.find(name => /^Uninstall .*\.exe$/.test(name))
  if (!uninstaller) throw new Error('uninstall_missing')
  let args
  try { args = nsisSilentUninstallArgs(directory) } catch { throw new Error('uninstall_failed') }
  // _?= keeps NSIS in this directory so the process exit is the real uninstall.
  // The following poll only confirms this run's registration. It deletes nothing.
  try {
    run(join(directory, uninstaller), args, { windowsVerbatimArguments: true })
  } catch { throw new Error('uninstall_failed') }
  waitForOwnedWindowsRemoval(directory, readWindowsMnemionProducts, () => {
    Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 500)
  }, 60)
}

function retireInstallation(item) {
  if (removedInstallationIds.has(item.id)) return
  if (process.platform === 'win32') uninstallWindowsProduct(item.directory)
  else rmSync(item.directory, { recursive: true, force: true })
  removedInstallationIds.add(item.id)
}

function publishResourceCleanup() {
  if (!cleanupFailures.length || !existsSync(evidenceFile)) return
  try {
    const evidence = JSON.parse(readFileSync(evidenceFile, 'utf8'))
    evidence.cleanup_failures = cleanupFailures.slice(0, 8)
    evidence.workload_completed = false
    writeFileSync(evidenceFile, JSON.stringify(evidence, null, 2) + '\n')
  } catch { /* The process exit still reports the cleanup failure. */ }
}

function readResourceStore(profile) {
  const result = spawnSync(python, ['-m', 'deploy.probe_telemetry_installed', '--read-resource-store', profile], {
    cwd: root, encoding: 'utf8', timeout: 30000, maxBuffer: 64 * 1024,
  })
  if (result.status !== 0 || !result.stdout) return { present: false, attempts: null, reserved_bytes: null, fixture_content_absent: false }
  try { return JSON.parse(result.stdout) } catch { return { present: false, attempts: null, reserved_bytes: null, fixture_content_absent: false } }
}

function resourceWorkloadCompleted(app, owned) {
  return Number.isInteger(app?.memory_cycles)
    && app.memory_cycles === owned?.canonical_operations_completed
    && app.memory_results_verified === true
    && Array.isArray(app.checkpoints) && app.checkpoints.join() === RESOURCE_CHECKPOINTS.join()
    && app.model_calls === 0
    && app.resource_acceptance === false
    && owned?.resource_acceptance === false
    && owned?.delivery_diagnostics_enabled !== true
}

function publicHosting(hosting) {
  const runtime = hosting?.runtime && typeof hosting.runtime === 'object' ? {
    electron: hosting.runtime.electron, node: hosting.runtime.node, platform: hosting.runtime.platform,
    arch: hosting.runtime.arch, packaged: hosting.runtime.packaged === true,
  } : undefined
  return {
    memory_cycles: hosting?.memory_cycles,
    memory_results_verified: hosting?.memory_results_verified === true,
    checkpoints: hosting?.checkpoints,
    condition: hosting?.condition,
    replicate: hosting?.replicate,
    label: hosting?.label,
    source: typeof hosting?.source === 'string' && /^[0-9a-f]{40}$/.test(hosting.source) ? hosting.source : null,
    package_condition: hosting?.package_condition,
    package_sha256: typeof hosting?.package_sha256 === 'string' && /^[0-9a-f]{64}$/.test(hosting.package_sha256) ? hosting.package_sha256 : null,
    model_calls: hosting?.model_calls,
    forced_gc: hosting?.forced_gc === true,
    idle_padding: hosting?.idle_padding === true,
    memory_api_operations: hosting?.memory_api_operations,
    inspected_body_hex: inspectedBodyHex(hosting?.approved_body_hex),
    production_collection_available: false,
    resource_acceptance: hosting?.resource_acceptance === false ? false : null,
    qualification: 'installed resource workload',
    packaged: hosting?.packaged === true,
    runtime,
  }
}

async function runInstalledTelemetryResources() {
  const observer = process.env.MNEMION_OWNED_LAUNCH_PYTHON
  if (!observer) throw new Error('Resource accounting requires MNEMION_OWNED_LAUNCH_PYTHON')
  if (process.env.MNEMION_TELEMETRY_INSTALLED_DELIVERY === '1') throw new Error('Resource launches cannot inherit installed delivery diagnostics')
  const endpoint = loopbackFixture(process.env.MNEMION_TELEMETRY_FIXTURE_ENDPOINT)
  const spaceId = process.env.MNEMION_TELEMETRY_FIXTURE_SPACE
  const credential = process.env.MNEMION_TELEMETRY_FIXTURE_KEY
  if (!/^[a-f0-9-]{36}$/.test(spaceId || '') || typeof credential !== 'string' || credential.length < 16 ||
      credential.length > 256 || /\s/.test(credential)) throw new Error('Resource package preparation is missing')
  const manifest = loadResourceManifest()
  const destinations = {
    inactive: join(temporary, 'inactive-package'),
    active: join(temporary, 'active-package'),
  }
  const buildTmp = join(root, 'build-tmp')
  mkdirSync(buildTmp, { recursive: true })
  const steps = resourceInstallSteps(manifest.cases)
  for (const step of steps) {
    if (step.action === 'refuse-preexisting') {
      if (process.platform === 'win32') refuseExistingWindowsProduct()
      continue
    }
    if (step.action === 'install') {
      const destination = destinations[step.package]
      const installer = manifest.packages[step.package].installer
      await performOwnedInstall(resourceInstallations, { id: step.id, directory: destination, package: step.package }, {
        refusePreexisting: async () => {
          if (process.platform === 'win32') refuseExistingWindowsProduct()
        },
        installProduct: async () => installPrepared(destination, installer, true),
        verify: async () => verifyInstalled(destination, manifest, step.package),
      })
      installedExecutables.set(destination, executable)
      continue
    }
    if (step.action === 'uninstall') {
      const item = resourceInstallations.find(entry => entry.id === step.id)
      if (!item) throw new Error('Resource package preparation is missing')
      try { retireInstallation(item) }
      catch (error) {
        cleanupFailures.push(boundedCleanupCode(error))
        throw new Error('uninstall_failed')
      }
      continue
    }
    const row = manifest.cases.find(entry => entry.label === step.label)
    if (!row) throw new Error('Resource package preparation is missing')
    const destination = destinations[step.package]
    const exe = installedExecutables.get(destination)
    if (!exe || !existsSync(exe)) throw new Error('Resource package preparation is missing')
    const profile = join(temporary, row.label)
    run(python, ['-c', 'from pathlib import Path; import sys; from mnemion.local_state import directory; directory(Path(sys.argv[1]), exist_ok=False)', profile], { cwd: root })
    run(python, ['-m', 'deploy.telemetry_installed_fixture', '--prepare-profile', profile, '--available', row.available ? '1' : '0', '--enabled', row.enabled ? '1' : '0'], { cwd: root })
    const probePath = join(temporary, `${row.label}-hosting-probe.json`)
    const caseSmoke = join(temporary, `${row.label}-smoke.json`)
    const caseQuit = join(temporary, 'quit-request')
    rmSync(caseSmoke, { force: true })
    rmSync(caseQuit, { force: true })
    const probeConfig = {
      condition: row.condition, credential, endpoint, label: row.label, package_condition: row.package,
      package_sha256: manifest.packages[row.package].sha256, phase: 'telemetry-resource',
      probe_entry: './assets/packaged-memory-probe.js', replicate: row.replicate, source: manifest.source, spaceId,
    }
    const probeText = JSON.stringify(probeConfig)
    if (Buffer.byteLength(probeText) > 4096) throw new Error('Resource probe configuration is too large')
    writeFileSync(probePath, probeText, { mode: 0o600 })
    const childEnv = {
      ...environment,
      MNEMION_STUDIO_USER_DATA: profile,
      MNEMION_STUDIO_SMOKE_FILE: caseSmoke,
      MNEMION_STUDIO_HOSTING_PROBE: probePath,
      MNEMION_AUTO_UPDATE: '0',
      MNEMION_START_AT_LOGIN: '0',
      ELECTRON_ENABLE_LOGGING: '1',
    }
    if (childEnv.MNEMION_TELEMETRY_INSTALLED_DELIVERY || childEnv.MNEMION_TELEMETRY_INSTALLED_RESOURCE || childEnv.MNEMION_TELEMETRY_FIXTURE_KEY) {
      throw new Error('Resource launches cannot inherit installed delivery diagnostics')
    }
    const args = process.platform === 'linux' && process.env.MNEMION_NATIVE_KEYRING_REQUIRED === '1' ? ['--password-store=gnome-libsecret'] : []
    const specPath = join(temporary, `${row.label}-owned-spec.json`)
    const reportPath = join(temporary, `${row.label}-owned-launch.json`)
    writeFileSync(specPath, JSON.stringify({
      argv: [exe, ...args], cwd: destination, env: childEnv, profile, quit_file: caseQuit, smoke_file: caseSmoke, report: reportPath,
    }), { mode: 0o600 })
    const result = spawnSync(observer, ['-m', 'deploy.owned_installed_launch', '--spec', specPath], {
      cwd: root, encoding: 'utf8', timeout: 16 * 60 * 1000, maxBuffer: 1024 * 1024,
    })
    let owned = {}
    if (existsSync(reportPath)) {
      const text = readFileSync(reportPath, 'utf8')
      if (text.includes(credential) || text.includes('PRIVATE_RENDERER_MEMORY_CANARY')) throw new Error('Owned launch report contained private fixture material')
      owned = publicOwnedReport(JSON.parse(text))
      writeFileSync(join(buildTmp, `${row.label}-owned-launch.json`), JSON.stringify(owned, null, 2) + '\n')
    }
    let hosting = {}
    if (existsSync(caseSmoke)) {
      const smokeText = readFileSync(caseSmoke, 'utf8')
      if (smokeText.includes(credential) || smokeText.includes('PRIVATE_RENDERER_MEMORY_CANARY')) throw new Error('Resource evidence contained private fixture material')
      const smoke = JSON.parse(smokeText)
      hosting = publicHosting(smoke.hosting)
    }
    const pidFile = join(profile, 'mnemion-local-workspace/database/postmaster.pid')
    const postgresLeft = existsSync(pidFile)
    const store = readResourceStore(profile)
    const telemetryReady = resourceCaseStoreReady(row, store)
    const summary = {
      label: row.label, condition: row.condition, replicate: row.replicate, package_condition: row.package,
      package_sha256: manifest.packages[row.package].sha256, source: manifest.source,
      memory_cycles: Number.isInteger(hosting.memory_cycles) ? hosting.memory_cycles : null,
      memory_results_verified: hosting.memory_results_verified === true,
      memory_api_operations: Number.isInteger(hosting.memory_api_operations) ? hosting.memory_api_operations : null,
      checkpoints: hosting.checkpoints, model_calls: hosting.model_calls,
      canonical_operations_completed: owned.canonical_operations_completed ?? null,
      canonical_operations_known: owned.canonical_operations_known === true ? true : owned.canonical_operations_known === false ? false : null,
      telemetry_attempts: Number.isInteger(store.attempts) ? store.attempts : null,
      telemetry_reserved_bytes: Number.isInteger(store.reserved_bytes) ? store.reserved_bytes : null,
      telemetry_present: store.present === true,
      inspected_body_hex: hosting.inspected_body_hex || null,
      resource_acceptance: hosting.resource_acceptance === false ? false : null,
      hosting_ready: typeof owned.hosting_ready === 'boolean' ? owned.hosting_ready : null,
      root_exit_code: owned.root_exit_code ?? null, failure_stage: owned.failure_stage ?? null,
      delivery_diagnostics_enabled: owned.delivery_diagnostics_enabled === true,
      workload_completed: resourceWorkloadCompleted(hosting, owned) && telemetryReady && result.status === 0 && !postgresLeft,
    }
    resourceCases.push(summary)
    await publishResourceCase(summary)
    if (postgresLeft) throw new Error('The installed app left its private PostgreSQL cluster running')
    if (result.error || result.status !== 0 || summary.workload_completed !== true) {
      throw new Error('Owned resource launch failed: ' + row.label)
    }
  }
  const evidence = {
    qualification: 'installed resource workload',
    resource_acceptance: false,
    production_collection_available: false,
    delivery_compared: false,
    workload_completed: resourceCases.length === RESOURCE_CASES.length && resourceCases.every(row => row.workload_completed === true),
    cleanup_failures: cleanupFailures.slice(0, 8),
    platform: process.platform,
    architecture: process.arch,
    source: manifest.source,
    cases: resourceCases,
  }
  writeFileSync(evidenceFile, JSON.stringify(evidence, null, 2) + '\n')
  console.log(JSON.stringify({ qualification: evidence.qualification, workload_completed: evidence.workload_completed, resource_acceptance: false }))
}

function credentialsHash() {
  return createHash('sha256').update(readFileSync(join(userData, 'mnemion-local-workspace/credentials.json'))).digest('hex')
}

try {
  if (telemetryResource) {
    await runInstalledTelemetryResources()
    succeeded = true
  } else {
  const nativeRuntime = await install()
  if (telemetryDelivery) {
    await runInstalledTelemetryDelivery(nativeRuntime)
    succeeded = true
  } else {
  const port = await freePort()
  const preview = await launch({ phase: 'capture-preview', port })
  if (!preview.nativeEmptyCapturePreview) throw new Error('The installed empty capture preview did not complete')
  if (!['nativeTelemetryDisclosurePreview', 'nativeTelemetryAppAgentChoice', 'nativeTelemetryPreviewClearedOnRefresh',
    'nativeTelemetryNoAttemptDuringInspection', 'nativeTelemetryReviewBeforePermission',
    'nativeTelemetryReviewAppAgentChoice'].every(field => preview[field] === true)) throw new Error('Installed privacy controls did not complete')
  if (!['nativeServiceCancelBeforeHeaders', 'nativeServiceCancelDuringBody', 'nativeServiceCancelTokenPrivate']
    .every(field => preview[field] === true)) throw new Error('Installed service-request cancellation did not complete')
  await stop()
  const first = await launch({ phase: 'create', port, emulated: nativeRuntime.engine_emulation === true })
  if (!first.nativeTelemetryOptOutSurvivesRestart) throw new Error('Installed telemetry opt-out did not survive restart')
  if (!first.nativeTelemetryReviewModeSurvivesRestart) throw new Error('Installed report-review mode did not survive restart')
  if (!first.actualSetupControls || !first.realModelInference) throw new Error('The installed UI did not exercise real setup and inference')
  if (!first.nativeNgrokSdkLoaded) throw new Error('The installed engine did not load its remote connection runtime')
  if (!first.journalRegistrationControls) throw new Error('The installed UI did not verify host journal registration and separate publication approval')
  const hostedPage = await fetch(first.endpoint + '/oauth/consent', { signal: AbortSignal.timeout(10000) })
  const hostedHtml = await hostedPage.text()
  const hostedAsset = hostedHtml.match(/src="(\/assets\/[^"<>]+\.js)"/)
  if (hostedPage.status !== 200 || !hostedAsset) throw new Error('The installed service omitted its browser/consent interface')
  const script = await fetch(first.endpoint + hostedAsset[1], { signal: AbortSignal.timeout(10000) })
  if (script.status !== 200 || !(await script.text()).length) throw new Error('The installed hosted interface cannot load its scripts')
  if (!first.navigationPreservesUpdateReadiness || !first.unsavedDraftBlocksUpdate || !first.closedEditorRestoresUpdateReadiness) {
    throw new Error('Installed navigation and unsaved-work update guards did not pass')
  }
  const anonymous = await fetch(first.endpoint + '/v1/spaces', { signal: AbortSignal.timeout(10000) })
  if (anonymous.status !== 401) throw new Error('The installed local service permits unauthenticated data access')
  await stop()
  const credentials = credentialsHash()
  const second = await launch({ phase: 'resume', port, memoryId: first.memoryId, spaceId: first.spaceId })
  if (!second.automaticReopen || !second.savedMemoryPresent || first.tenantId !== second.tenantId || first.endpoint !== second.endpoint) {
    throw new Error('The installed app did not automatically reopen the same saved local workspace')
  }
  await stop()
  if (credentialsHash() !== credentials) throw new Error('Application restart replaced the private workspace credentials')
  for (const [phase, required] of [
    ['backup-capture', ['nativeEncryptedSnapshot', 'laterDeletionLedger', 'protectedKeySaved', 'backupFormRestoresUpdateReadiness', 'nativeVaultConfiguredThroughApp', 'vaultDeletionRecordedAfterSnapshot', 'nativeOperatorPipe', 'operatorScheduleAndUiAgree', 'operatorRetryDoesNotRepeat', 'operatorStaleIdentityRefused', 'operatorRefreshesLedger', 'operatorInspectsEncryptedFiles', 'operatorRestoresIndependentCopy']],
    ['backup-recover', ['protectedKeyReopened', 'realRecoveryControls', 'separateRecoveryCopy', 'originalOrganizationRetained', 'retainedMemoryReadable', 'postSnapshotDeletionPreserved', 'freshAdministratorConnected', 'vaultKeyRestoredThroughApp', 'vaultGrantsRequireFreshReview', 'vaultDeletionPreserved', 'vaultExcludedFromMemory', 'nativeOperatorPipe', 'hostPackageInspected', 'hostLedgerChoiceReviewed', 'hostDatabaseRecovered']],
    ['backup-resume', ['recoveredCopyReopened', 'deletionPreservedAfterReopen', 'originalWorkspaceReopened', 'restoredVaultSurvivesRestart', 'originalVaultRemainsIndependent', 'nativeOperatorPipe', 'operatorRecoverySelection', 'operatorOriginalSelection', 'operatorPreservesUnsavedDraft', 'nativeBackupRetention', 'retentionKeepsVerifiedPairs', 'retentionControlsAndAgentAgree', 'nativeWorkspaceOperator', 'operatorAccountIdentityBound', 'operatorConnectionDraftPreserved', 'operatorWorkspaceSelectionAndUiAgree', 'operatorSelectedReaderRestricted', 'operatorSavedConnectionRestored', 'operatorPrivateCredentialsRetained', 'operatorLocalOwnerReopened',
      'nativeModelPrivateSetup', 'nativeModelRestartAndChoices', 'nativeModelAppAndAgentControls', 'nativeModelEnrollmentWithoutInference']],
  ]) {
    const backup = await launch({ phase, port, memoryId: first.memoryId, spaceId: first.spaceId })
    if (required.some(field => backup[field] !== true)) throw new Error('Installed backup/recovery acceptance failed: ' + phase)
    await stop()
    if (credentialsHash() !== credentials) throw new Error('Recovery modified the original workspace credentials')
    if (phase === 'backup-capture') {
      run(python, ['-m', 'deploy.native_host_backup_fixture', '--fixture', join(temporary, 'native-backup-fixture.json'),
        '--output', join(temporary, 'Server backup Équipe.mnemion-host')], { cwd: root, env: environment })
    }
  }
  for (const [phase, required] of [
    ['capture-enroll', ['nativeCaptureConsentControls', 'nativeCaptureIndependentOsKey', 'nativeCaptureBeforeDelivery', 'nativeCaptureOfflineRemovalPreservesInbox', 'nativeCaptureSelectedPayloadEncrypted', 'nativeCapturePausedBeforeRestart', 'nativeCaptureBackupThroughApp', 'nativeCaptureBackupEncrypted', 'nativeCaptureBackupAppAndAgentAgree', 'nativeCaptureBackupNarrowLayout', 'nativeCaptureFieldExclusionsReviewed', 'nativeCaptureFieldPolicyArchived']],
    ['capture-resume', ['nativeCaptureQueueSurvivesAppRestart', 'nativeCaptureKeyReopenedByOs', 'nativeCaptureDeliversAfterProducerRemoval', 'nativeCaptureVisibleAppCounts', 'nativeCaptureAdministratorRemovalAfterKeyRevocation', 'nativeCaptureRemovalRetainsServerMemory', 'nativeCaptureBackupSurvivesAppRestart', 'nativeCaptureBackupInspectAfterSourceRemoval', 'nativeCaptureRestoreThroughApp', 'nativeCaptureRestoreAppAndAgentAgree', 'nativeCaptureRestorePausedWithNewKeys', 'nativeCaptureRestoreNarrowLayout', 'nativeCaptureFieldExclusionsDelivered']],
    ['capture-restored-resume', ['nativeCaptureRestoredKeyReopenedByOs', 'nativeCaptureRestoredPausedAfterRestart', 'nativeCaptureRestoredQueueReconcilesWithoutDuplicates', 'nativeCaptureRestoredNewMemoriesCaptured', 'nativeCaptureFixtureCleanup', 'nativeCaptureFieldExclusionsSurviveRecovery']],
    ['capture-policy', ['nativeCapturePolicyPausedDrainThroughApp', 'nativeCapturePolicyDrainDoesNotRead', 'nativeCapturePolicyAdministratorReview', 'nativeCapturePolicyBackupAndMigrationThroughApp', 'nativeCapturePolicyRetainsResourceLimits', 'nativeCapturePolicyNewOsKeysAndOldGrantRetired', 'nativeCapturePolicyOldArchiveAndInboxUnmodified', 'nativeCapturePolicyNewCoverageUnobserved', 'nativeCapturePolicyForgetSurvivesReselection', 'nativeCapturePolicyResumedSelectionDelivered', 'nativeCapturePolicyAppAndAgentAgree', 'nativeCapturePolicyNarrowLayout', 'nativeCapturePolicyFixtureCleanup', 'nativeCapturePolicyExpiryReviewedAndPreserved', 'nativeCapturePolicyExpiryScheduledAndVisible', 'nativeCapturePolicyV3FieldExclusionsPreserved', 'nativeCapturePolicyLostRetirementReply', 'nativeCapturePolicyPendingRetirementVisible', 'nativeCapturePolicyRetirementReconciledWithoutReplay']],
    ['capture-boundaries-enroll', ['nativeCaptureAgentEnrollment', 'nativeCaptureIncompleteUnicode', 'nativeCaptureQuotaAppAndAgentAgree', 'nativeCaptureCompletedUnicode', 'nativeCaptureRotationKeepsAcceptedAndGap', 'nativeCaptureExactEventProvenance', 'nativeCaptureLostRealCommitReply', 'nativeCaptureReaderRevokedWhileQueued', 'nativeCaptureBoundaryPrivateState', 'nativeCaptureKeyLossPausePreservesDisk']],
    ['capture-boundaries-resume', ['nativeCaptureUnknownReceiptSurvivesRestart', 'nativeCaptureReceiptReconciledWithoutWrite', 'nativeCaptureMemoryIdsAndVersionsRetained', 'nativeCaptureIndexObservedSeparately', 'nativeCaptureRevokedReaderStaysRevoked', 'nativeCaptureReplayRespectsForget', 'nativeCaptureLocalDeletionHistory', 'nativeCaptureReviewedPolicyStopsOldGrant', 'nativeCapturePendingRetiredThroughApp', 'nativeCaptureBoundaryCleanup', 'nativeCaptureMissingEnrollmentStillPauses', 'nativeCaptureDamagedEnrollmentStillPauses', 'nativeCaptureMissingDatabasePreservesEvidence', 'nativeCaptureDamagedDatabasePreservesEvidence', 'nativeCaptureMatchingFilesReopenAcceptedQueue', 'nativeCaptureKeyLossControlsAfterRestart', 'nativeCaptureLostKeysRefuseResume', 'nativeCaptureOriginalKeysRestoreAcceptedEvidence', 'nativeCaptureLostKeysRetiredThroughApp']],
    ['capture-headless', ['nativeHeadlessEngineEntry', 'nativeHeadlessConsentAndKeyGeneration', 'nativeHeadlessOfflineWatchRestart', 'nativeHeadlessPauseWithoutConnection', 'nativeHeadlessEncryptedBackupAndInspection', 'nativeHeadlessChangedKeyPreservesInbox', 'nativeHeadlessMissingInboxRefusesReset', 'nativeHeadlessDeliveryAfterProducerRemoval', 'nativeHeadlessNewDeviceRecovery', 'nativeHeadlessRecoveryHonorsLaterForgetting', 'nativeHeadlessPausedDrainWithoutIntake', 'nativeHeadlessReviewedPolicyMigration', 'nativeHeadlessPolicyDeletionHistory', 'nativeHeadlessPolicyResume', 'nativeHeadlessFutureCaptureAndRetirement', 'nativeHeadlessIndependentOfDesktopSources', 'nativeHeadlessFixtureCleanup']],
  ]) {
    const capture = await launch({ phase, port, memoryId: first.memoryId, spaceId: first.spaceId })
    if (required.some(field => capture[field] !== true)) throw new Error('Installed retained capture acceptance failed: ' + phase)
    await stop()
    if (credentialsHash() !== credentials) throw new Error('Retained capture modified the original workspace credentials')
  }
  // An unrelated listener must lead to an actual recovery screen, never a new
  // workspace or silent connection to the other program.
  const occupied = createServer(socket => socket.end())
  await new Promise((resolve, reject) => { occupied.once('error', reject); occupied.listen(port, '127.0.0.1', resolve) })
  let recovered
  try {
    recovered = await launch({ phase: 'recover-port', port, memoryId: first.memoryId, spaceId: first.spaceId })
    if (!recovered.recoveredPortConflict || !recovered.savedMemoryPresent || recovered.tenantId !== first.tenantId || recovered.endpoint === first.endpoint) {
      throw new Error('The installed address recovery did not preserve and reconnect the original workspace')
    }
    await stop()
    if (credentialsHash() !== credentials) throw new Error('Address recovery replaced the private workspace credentials')
  } finally { await new Promise(resolve => occupied.close(resolve)) }
  const currentPort = Number(new URL(recovered.endpoint).port)
  const personal = await launch({ phase: 'sign-in', port: currentPort, memoryId: first.memoryId, spaceId: first.spaceId })
  if (!personal.uiInvitationAccepted || !personal.passwordSession || !personal.remembered || !personal.memberMemoryAccess || !personal.administratorAccessDenied) {
    throw new Error('The installed app did not complete a scoped invitation with the actual OS credential store')
  }
  const savedConnections = join(userData, 'workspaces/connections.json')
  if (!existsSync(savedConnections) || /mnm_[rsi]_|harbour comet mitten glacier tapestry/.test(readFileSync(savedConnections, 'utf8'))) {
    throw new Error('A remembered password session must exist without plaintext credentials')
  }
  await stop()
  const reopened = await launch({ phase: 'sign-in-resume', port: currentPort, memoryId: first.memoryId, spaceId: first.spaceId,
    tenantId: personal.tenantId, principalId: personal.principalId, sessionId: personal.sessionId })
  if (!reopened.sameDeviceSessionRestored || !reopened.administratorAccessDenied || !reopened.memberMemoryAccess ||
      !reopened.uiSessionRevoked || !reopened.staleNativeHandleRejected || !reopened.independentOwnerKeyPreserved) {
    throw new Error('The installed app did not preserve and revoke the correct individual device session')
  }
  await stop()
  if (credentialsHash() !== credentials) throw new Error('Individual sign-in or revocation replaced the independent workspace credentials')
  const evidence = { passed: true, platform: process.platform, architecture: process.arch, nativeRuntime,
    installer: process.platform === 'win32' ? 'NSIS per-user' : process.platform === 'darwin' ? 'DMG copied application' : 'AppImage portable user installation',
    installationPathWithSpacesAndUnicode: true, nativeEmptyCapturePreview: true, actualSetupControls: true, authenticatedApi: true,
    nativeTelemetryDisclosurePreview: true, nativeTelemetryAppAgentChoice: true,
    nativeTelemetryPreviewClearedOnRefresh: true, nativeTelemetryNoAttemptDuringInspection: true,
    nativeTelemetryOptOutSurvivesRestart: true,
    nativeTelemetryReviewBeforePermission: true, nativeTelemetryReviewAppAgentChoice: true,
    nativeTelemetryReviewModeSurvivesRestart: true,
    nativeNgrokSdkLoaded: true, hostedBrowserAndConsentAssets: true,
    nativeJournalRegistrationAndSeparateApproval: true,
    nativeEncryptedSnapshotAndLedger: true, backupKeyProtectedAndReopenedByOsStore: true,
    recoveryThroughActualAppControls: true, recoveredCopyReopenedAfterRestart: true,
    postSnapshotDeletionPreservedByRecovery: true, originalWorkspacePreservedAndReopened: true,
    nativeVaultSetupAndIndependentKeyRecovery: true, recoveredVaultRequiresFreshGrants: true,
    vaultDeletionPreservedAndValuesExcludedFromMemory: true, originalAndRecoveredVaultsSurviveRestart: true,
    anonymousAccessRefused: true, realSemanticSaveAndRecall: true, automaticWorkspaceReopen: true,
    restartPreservesWorkspaceAndCredentials: true, savedMemorySurvivesRestart: true,
    configuredRamBudgetPersists: true, cleanDatabaseShutdownOnAppExit: true,
    navigationPreservesUpdateReadiness: true, unsavedDraftBlocksUpdate: true, closedEditorRestoresUpdateReadiness: true,
    occupiedApiPortRecoveredThroughApp: true, addressRecoveryPreservesWorkspaceAndCredentials: true,
    scopedInvitationAcceptedThroughApp: true, passwordSessionProtectedByNativeCredentialStore: true,
    sameIndividualSessionRestoredAfterRestart: true, contributorCannotAdministerOrganization: true,
    ownHostReadyBeforeSavedLoginRefresh: true, currentSessionRevokedThroughApp: true,
    revokedHandleRejected: true, independentOwnerKeyPreserved: true,
    retainedCaptureConsentThroughApp: true, captureKeyProtectedAndReopenedByOs: true,
    selectedCaptureWhileWorkspaceOffline: true, pendingQueueSurvivesAppRestart: true,
    offlineRemovalRefusesUnconfirmedDiscard: true, captureDeliveryAfterProducerRemoval: true,
    captureAppCountsAndAgentControls: true, captureAdministratorRemovalAfterDeviceKeyRevocation: true,
    captureIncompleteUnicodeAndRotation: true, captureExactEventProvenance: true,
    captureLostCommitReplyReconciledAfterRestart: true, captureHistoryQuotasThroughAppAndAgent: true,
    captureReaderRevocationAndDeletionFences: true, captureReviewedPolicyStopsOldDeviceDelivery: true,
    independentPackagedHeadlessCapture: true, headlessWatchRestartAndRecovery: true,
    headlessKeyAndInboxFailuresPreserveEvidence: true, headlessRecoveryPreservesLaterForgetting: true,
    desktopDamagedEnrollmentPauseThroughAppAndAgent: true, desktopMissingAndDamagedInboxPreserved: true,
    desktopCaptureFieldExclusionConsentAndRecovery: true,
    scope: 'Locally built installer, new private profile and real model download. Public download acceptance and update migration are separate gates.' }
  mkdirSync(join(root, 'build-tmp'), { recursive: true })
  writeFileSync(evidenceFile, JSON.stringify(evidence, null, 2) + '\n')
  for (const phase of ['create', 'resume', 'backup-capture', 'backup-recover', 'backup-resume', 'capture-enroll', 'capture-resume', 'capture-restored-resume', 'capture-policy', 'capture-boundaries-enroll', 'capture-boundaries-resume', 'capture-headless', 'recover-port', 'sign-in', 'sign-in-resume']) copyFileSync(join(temporary, phase + '-workspace.png'), join(root, 'build-tmp/installed-hosting-' + phase + '.png'))
  console.log(JSON.stringify(evidence, null, 2))
  succeeded = true
  }
  }
} catch (error) {
  mkdirSync(join(root, 'build-tmp'), { recursive: true })
  // Keep private diagnostic details out of uploaded evidence; even future
  // service logs may contain a generated workspace credential.
  writeFileSync(join(temporary, 'failure.log'), String(error) + '\n' + stdout + '\n' + stderr, { mode: 0o600 })
  let state = {}
  try { state = JSON.parse(readFileSync(smokeFile, 'utf8')) } catch { /* No private contents are copied into the report. */ }
  const shutdown = Object.fromEntries(['localActive', 'localBusy'].filter(key => typeof state?.[key] === 'boolean').map(key => [key, state[key]]))
  const lastStage = typeof state?.stage === 'string' && /^[a-z-]{1,64}$/.test(state.stage) ? state.stage : null
  const setup = setupFailure(state?.error)
  const workspaceOpen = workspaceOpenFailure(state?.error)
  const modelSetup = modelSetupFailure(state?.error)
  let engineDiagnostic
  let invalidEngineDiagnostic = false
  try { engineDiagnostic = localDiagnostic(state?.localDiagnostic) } catch { invalidEngineDiagnostic = true }
  let backupDiagnostic
  let invalidBackupDiagnostic = false
  try { backupDiagnostic = localDiagnostic(state?.backupDiagnostic) } catch { invalidBackupDiagnostic = true }
  let backupState
  let invalidBackupStateDiagnostic = false
  try { backupState = backupStateDiagnostic(state?.backupStateDiagnostic) } catch { invalidBackupStateDiagnostic = true }
  const observation = sanitizeObservation(state?.observation)
  writeFileSync(evidenceFile, JSON.stringify({ passed: false, qualification: telemetryResource ? 'installed resource workload' : telemetryDelivery ? 'installed fixture delivery' : undefined, platform: process.platform, architecture: process.arch,
    ...(telemetryResource ? { resource_acceptance: false, delivery_compared: false, production_collection_available: false, workload_completed: false, cases: resourceCases } : {}),
    phase, childExitCode: child?.exitCode ?? null, childSignal: child?.signalCode ?? null, lastStage, ...shutdown,
    ...(setup ? { setup } : {}),
    ...(workspaceOpen ? { workspaceOpen } : {}),
    ...(modelSetup ? { modelSetup } : {}),
    ...(engineDiagnostic ? { engineDiagnostic } : {}), ...(invalidEngineDiagnostic ? { invalidEngineDiagnostic: true } : {}),
    ...(backupDiagnostic ? { backupDiagnostic } : {}), ...(invalidBackupDiagnostic ? { invalidBackupDiagnostic: true } : {}),
    ...(backupState ? { backupStateDiagnostic: backupState } : {}), ...(invalidBackupStateDiagnostic ? { invalidBackupStateDiagnostic: true } : {}),
    ...(observation ? { observation } : {}),
    stage: installationComplete ? 'installed-local-hosting' : 'installation', privateDiagnostics: 'retained only in the disposable runner temporary directory' }, null, 2) + '\n')
  throw error
} finally {
  if (!telemetryResource && child && child.exitCode === null) {
    try { await stop() } catch {
      if (process.platform === 'win32') spawnSync('taskkill.exe', ['/PID', String(child.pid), '/T', '/F'], { stdio: 'ignore' })
      else { try { process.kill(-child.pid, 'SIGKILL') } catch {} }
    }
  }
  if (process.platform === 'win32' && installationComplete && !telemetryResource) {
    for (const directory of uninstallDirs) {
      let names = []
      try { names = readdirSync(directory) } catch { continue }
      const uninstaller = names.find(name => /^Uninstall .*\.exe$/.test(name))
      if (uninstaller) run(join(directory, uninstaller), ['/S'])
    }
  }
  if (telemetryResource) {
    cleanupFailures.push(...finishResourceCleanup(resourceInstallations, removedInstallationIds, retireInstallation))
    publishResourceCleanup()
    if (succeeded && cleanupFailures.length) throw new Error('uninstall_failed')
  }
  // NSIS can return while its temporary self-deletion helper still holds the
  // installation directory. Retry transient Windows locks with a finite budget;
  // persistent locks still fail the gate rather than silently skipping cleanup.
  if (succeeded) await rm(temporary, { recursive: true, force: true, maxRetries: 12, retryDelay: 250 })
}
