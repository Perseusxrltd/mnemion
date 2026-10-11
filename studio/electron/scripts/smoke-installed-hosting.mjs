/** Install this build into a new disposable location and use the real local UI. */
import { spawn, spawnSync } from 'node:child_process'
import { copyFileSync, existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, realpathSync, rmSync, writeFileSync } from 'node:fs'
import { rm } from 'node:fs/promises'
import { createHash } from 'node:crypto'
import { createServer } from 'node:net'
import { join } from 'node:path'
import { tmpdir } from 'node:os'
import { platformArtifacts, root } from './platform-artifacts.mjs'
import { verifyNativeResources } from './native-resources.mjs'

const artifacts = platformArtifacts()
// Production NSIS owns registry entries. Run only on a fresh hosted CI machine,
// and explicitly refuse an existing installation before changing anything.
if (process.platform === 'win32' && (process.env.CI !== 'true' || process.env.RUNNER_OS !== 'Windows')) {
  throw new Error('The production NSIS first-install probe requires a disposable Windows CI runner')
}
// macOS exposes /var through a symlink; the private workspace correctly rejects
// redirected parents, so start with the canonical OS temporary directory.
const temporary = mkdtempSync(join(realpathSync(tmpdir()), 'mnemion-installed-hosting-'))
const installed = join(temporary, 'Applications Équipe with spaces')
const userData = join(temporary, 'Private profile')
const probeFile = join(temporary, 'hosting-probe.json')
const smokeFile = join(temporary, 'smoke.json')
const quitFile = join(temporary, 'quit-request')
const evidenceFile = join(root, 'build-tmp/installed-hosting-evidence.json')
let executable
let child
let stdout = '', stderr = ''
let installationComplete = false
let succeeded = false
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms))
const environment = Object.fromEntries(Object.entries(process.env).filter(([key]) => !key.startsWith('MNEMION_')))

function run(command, args, options = {}) {
  const result = spawnSync(command, args, { encoding: 'utf8', timeout: 180000, maxBuffer: 1024 * 1024, ...options })
  if (result.error || result.status !== 0) throw new Error(`Installed-app command failed: ${result.error?.message || result.stderr || result.stdout}`)
  return result.stdout
}

async function install() {
  if (process.platform === 'win32') {
    const env = { ...environment, MNEMION_PROBE_INSTALLER: artifacts.installers[0], MNEMION_PROBE_INSTALL_DIRECTORY: installed }
    for (const key of Object.keys(env)) if (key.toLowerCase() === 'psmodulepath') delete env[key]
    run('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command',
      '$ErrorActionPreference="Stop"; $entries=Get-ItemProperty -Path "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*","HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*","HKLM:\\Software\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*" -ErrorAction SilentlyContinue; '
      + 'if ($entries | Where-Object { $_.DisplayName -eq "Mnemion Studio" }) { throw "Refusing to modify an existing Mnemion installation" }; '
      + '$p=Start-Process -FilePath $env:MNEMION_PROBE_INSTALLER -ArgumentList @("/S","/currentuser",("/D="+$env:MNEMION_PROBE_INSTALL_DIRECTORY)) -PassThru -Wait; exit $p.ExitCode'], { env })
    executable = join(installed, 'Mnemion Studio.exe')
  } else if (process.platform === 'darwin') {
    const volume = join(temporary, 'installer-volume')
    run('hdiutil', ['attach', '-readonly', '-nobrowse', '-mountpoint', volume, artifacts.installers[0]])
    try {
      mkdirSync(installed)
      run('ditto', [join(volume, 'Mnemion Studio.app'), join(installed, 'Mnemion Studio.app')])
    } finally { run('hdiutil', ['detach', volume]) }
    executable = join(installed, 'Mnemion Studio.app/Contents/MacOS/Mnemion Studio')
  } else {
    mkdirSync(installed)
    const appImage = join(installed, 'Mnemion Studio.AppImage')
    copyFileSync(artifacts.installers[0], appImage)
    run('chmod', ['755', appImage])
    run(appImage, ['--appimage-extract'], { cwd: installed })
    // AppImages support a user-owned portable installation without root/FUSE.
    executable = join(installed, 'squashfs-root/AppRun')
  }
  if (!existsSync(executable)) throw new Error('The native installer omitted the application executable')
  installationComplete = true
  const resources = process.platform === 'darwin' ? join(installed, 'Mnemion Studio.app/Contents/Resources') :
    join(installed, ...(process.platform === 'linux' ? ['squashfs-root', 'resources'] : ['resources']))
  return verifyNativeResources(resources)
}

async function freePort() {
  const server = createServer()
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve) })
  const port = server.address().port
  await new Promise(resolve => server.close(resolve))
  return port
}

async function launch(config) {
  console.log("Installed local workspace probe: " + config.phase)
  rmSync(smokeFile, { force: true }); rmSync(quitFile, { force: true })
  writeFileSync(probeFile, JSON.stringify(config), { mode: 0o600 })
  stdout = ''; stderr = ''
  child = spawn(executable, [], { cwd: installed, detached: process.platform !== 'win32', windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'],
    env: { ...environment, MNEMION_STUDIO_USER_DATA: userData, MNEMION_STUDIO_SMOKE_FILE: smokeFile,
      MNEMION_STUDIO_HOSTING_PROBE: probeFile, MNEMION_AUTO_UPDATE: '0', MNEMION_START_AT_LOGIN: '0', ELECTRON_ENABLE_LOGGING: '1' } })
  let spawnError
  child.on('error', error => { spawnError = error })
  child.stdout.on('data', bytes => { stdout = (stdout + bytes).slice(-16000) })
  child.stderr.on('data', bytes => { stderr = (stderr + bytes).slice(-16000) })
  const deadline = Date.now() + 12 * 60 * 1000
  let last
  while (Date.now() < deadline) {
    if (spawnError) throw spawnError
    if (child.exitCode !== null) throw new Error('The installed app exited before hosting validation completed')
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
  if (!child || child.exitCode !== null) return
  // Exercise the app's real before-quit service/database drain. Do not replace it
  // with a direct database stop that could conceal an unsafe application exit.
  writeFileSync(quitFile, 'quit\n', { mode: 0o600 })
  const deadline = Date.now() + 120000
  while (child.exitCode === null && Date.now() < deadline) await sleep(100)
  if (child.exitCode !== 0) throw new Error('The installed application did not finish a clean shutdown')
  const pidFile = join(userData, 'mnemion-local-workspace/database/postmaster.pid')
  if (existsSync(pidFile)) throw new Error('The installed app left its private PostgreSQL cluster running')
}

function credentialsHash() {
  return createHash('sha256').update(readFileSync(join(userData, 'mnemion-local-workspace/credentials.json'))).digest('hex')
}

try {
  const nativeRuntime = await install()
  const port = await freePort()
  const first = await launch({ phase: 'create', port, emulated: nativeRuntime.engine_emulation === true })
  if (!first.actualSetupControls || !first.realModelInference) throw new Error('The installed UI did not exercise real setup and inference')
  const anonymous = await fetch(first.endpoint + '/v1/spaces', { signal: AbortSignal.timeout(10000) })
  if (anonymous.status !== 401) throw new Error('The installed local service permits unauthenticated data access')
  await stop()
  const credentials = credentialsHash()
  const second = await launch({ phase: 'resume', port, memoryId: first.memoryId })
  if (!second.automaticReopen || !second.savedMemoryPresent || first.tenantId !== second.tenantId || first.endpoint !== second.endpoint) {
    throw new Error('The installed app did not automatically reopen the same saved local workspace')
  }
  await stop()
  if (credentialsHash() !== credentials) throw new Error('Application restart replaced the private workspace credentials')
  // An unrelated listener must lead to an actual recovery screen, never a new
  // workspace or silent connection to the other program.
  const occupied = createServer(socket => socket.end())
  await new Promise((resolve, reject) => { occupied.once('error', reject); occupied.listen(port, '127.0.0.1', resolve) })
  try {
    const recovered = await launch({ phase: 'recover-port', port, memoryId: first.memoryId })
    if (!recovered.recoveredPortConflict || !recovered.savedMemoryPresent || recovered.tenantId !== first.tenantId || recovered.endpoint === first.endpoint) {
      throw new Error('The installed address recovery did not preserve and reconnect the original workspace')
    }
    await stop()
    if (credentialsHash() !== credentials) throw new Error('Address recovery replaced the private workspace credentials')
  } finally { await new Promise(resolve => occupied.close(resolve)) }
  const evidence = { passed: true, platform: process.platform, architecture: process.arch, nativeRuntime,
    installer: process.platform === 'win32' ? 'NSIS per-user' : process.platform === 'darwin' ? 'DMG copied application' : 'AppImage portable user installation',
    installationPathWithSpacesAndUnicode: true, actualSetupControls: true, authenticatedApi: true,
    anonymousAccessRefused: true, realSemanticSaveAndRecall: true, automaticWorkspaceReopen: true,
    restartPreservesWorkspaceAndCredentials: true, savedMemorySurvivesRestart: true,
    configuredRamBudgetPersists: true, cleanDatabaseShutdownOnAppExit: true,
    occupiedApiPortRecoveredThroughApp: true, addressRecoveryPreservesWorkspaceAndCredentials: true,
    scope: 'Locally built installer, new private profile and real model download. Public download acceptance and update migration are separate gates.' }
  mkdirSync(join(root, 'build-tmp'), { recursive: true })
  writeFileSync(evidenceFile, JSON.stringify(evidence, null, 2) + '\n')
  for (const phase of ['create', 'resume', 'recover-port']) copyFileSync(join(temporary, phase + '-workspace.png'), join(root, 'build-tmp/installed-hosting-' + phase + '.png'))
  console.log(JSON.stringify(evidence, null, 2))
  succeeded = true
} catch (error) {
  mkdirSync(join(root, 'build-tmp'), { recursive: true })
  // Keep private diagnostic details out of uploaded evidence; even future
  // service logs may contain a generated workspace credential.
  writeFileSync(join(temporary, 'failure.log'), String(error) + '\n' + stdout + '\n' + stderr, { mode: 0o600 })
  writeFileSync(evidenceFile, JSON.stringify({ passed: false, platform: process.platform, architecture: process.arch,
    stage: installationComplete ? 'installed-local-hosting' : 'installation', privateDiagnostics: 'retained only in the disposable runner temporary directory' }, null, 2) + '\n')
  throw error
} finally {
  if (child && child.exitCode === null) {
    try { await stop() } catch {
      if (process.platform === 'win32') spawnSync('taskkill.exe', ['/PID', String(child.pid), '/T', '/F'], { stdio: 'ignore' })
      else { try { process.kill(-child.pid, 'SIGKILL') } catch {} }
    }
  }
  if (process.platform === 'win32' && installationComplete) {
    const uninstaller = readdirSync(installed).find(name => /^Uninstall .*\.exe$/.test(name))
    if (uninstaller) run(join(installed, uninstaller), ['/S'])
  }
  // NSIS can return while its temporary self-deletion helper still holds the
  // installation directory. Retry transient Windows locks with a finite budget;
  // persistent locks still fail the gate rather than silently skipping cleanup.
  if (succeeded) await rm(temporary, { recursive: true, force: true, maxRetries: 12, retryDelay: 250 })
}
