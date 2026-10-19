/** Real NSIS first-install/upgrade/relaunch using disposable instrumented packages. */
import { appendFileSync, createReadStream, createWriteStream, existsSync, readFileSync, writeFileSync } from 'node:fs'
import { cp, mkdir, readdir, rename, rm } from 'node:fs/promises'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createRequire } from 'node:module'
import { createServer } from 'node:http'
import { createHash, generateKeyPairSync, randomUUID, sign } from 'node:crypto'
import { spawn, spawnSync } from 'node:child_process'
import { extractAll, extractFile, createPackageWithOptions, getRawHeader } from '@electron/asar'
import { NtExecutable, NtExecutableResource, Resource } from 'resedit'
import { root, platformArtifacts, packageJson } from './platform-artifacts.mjs'
import { InstallerProgressWindow } from './installer-progress.mjs'

if (process.platform !== 'win32') throw new Error('Run this rehearsal on native Windows')
// The disposable packages use the production archive policy as well.
createRequire(import.meta.url)('../builder.config.cjs')
const outputIndex = process.argv.indexOf('--output')
if (outputIndex === -1 || !process.argv[outputIndex + 1]) throw new Error('Pass a fresh --output directory')
const output = resolve(process.argv[outputIndex + 1])
if (existsSync(output)) throw new Error('Use a new, isolated rehearsal directory')
await mkdir(output, { recursive: true })
const scripts = dirname(fileURLToPath(import.meta.url))
const source = platformArtifacts()
const sourceHash = createHash('sha256').update(readFileSync(join(source.resources, 'app.asar'))).digest('hex')
const version = packageJson.version
const parts = version.split('.').map(Number)
const target = `${parts[0]}.${parts[1]}.${parts[2] + 1}`
const id = randomUUID().replaceAll('-', '').slice(0, 12)
const productName = `Mnemion Update Probe ${id}`
const applicationId = `com.perseusxr.mnemion.update-probe.${id}`
const installed = join(output, 'installed with spaces')
const receipt = join(output, 'events.jsonl')
const userData = join(output, 'user-data')
await mkdir(userData)
const nsisLog = join(output, 'nsis-stages.log')
if (/["$\r\n]/.test(nsisLog)) throw new Error('The private NSIS diagnostic path contains unsupported characters')
const nsisInclude = join(output, 'probe-diagnostics.nsh')
writeFileSync(nsisInclude, `!include "${join(root, 'studio/electron/native/windows-installer.nsh')}"\n`
  + ['customInit', 'customInstall', 'customUnInit', 'customUnInstall'].map(stage => [
  `!macro ${stage}`,
  '  Push $R9',
  `  FileOpen $R9 "${nsisLog}" a`,
  '  FileSeek $R9 0 END',
  `  FileWrite $R9 "${stage} ` + '${VERSION} instdir=$INSTDIR executable=$EXEPATH command=$CMDLINE$\\r$\\n"',
  '  FileClose $R9',
  '  Pop $R9',
  '!macroend',
].join('\n')).join('\n'))
writeFileSync(join(userData, 'desktop-preferences.json'), JSON.stringify({ automaticUpdates: true, startAtLogin: false, background: true }))
const pair = generateKeyPairSync('ed25519')
const publicKey = pair.publicKey.export({ type: 'spki', format: 'der' }).subarray(-32).toString('base64')
let mode = 'bad-signature', installerPath, installerSize, installerHash
let downloads = 0
const requests = []
const sockets = new Set()

const server = createServer((request, response) => {
  const path = new URL(request.url, 'http://127.0.0.1').pathname
  if (path === '/control/redirect-probe') {
    response.writeHead(302, { Location: origin + '/control/redirect-target' }).end()
    return
  }
  if (path === '/control/redirect-target') { response.writeHead(500).end('The redirect must not be followed automatically'); return }
  if (path.startsWith('/control/')) {
    mode = path.slice('/control/'.length)
    response.end('ok')
    return
  }
  requests.push({ path, mode })
  if (path.endsWith(`latest-${process.arch}-windows.json`)) {
    const advertised = mode === 'older' ? version : target
    const architecture = mode === 'wrong-architecture' ? (process.arch === 'x64' ? 'arm64' : 'x64') : process.arch
    const filename = `Mnemion-Studio-${advertised}-windows-${architecture}.exe`
    const data = { schema: 1, application: 'com.perseusxr.mnemion-studio', platform: 'windows', architecture,
      version: advertised, filename, url: `${origin}/Perseusxrltd/mnemion/releases/download/v${advertised}/${filename}`,
      size: mode === 'oversized' ? 1024 ** 3 + 1 : installerSize, sha512: installerHash }
    const payload = Buffer.from(JSON.stringify(data))
    const signature = sign(null, payload, pair.privateKey)
    if (mode === 'bad-signature') signature[0] ^= 1
    response.setHeader('Content-Type', 'application/json')
    response.end(JSON.stringify({ schema: 1, payload: payload.toString('base64'), signature: signature.toString('base64') }))
    return
  }
  if (path.endsWith('.exe') && installerPath) {
    downloads++
    response.setHeader('Content-Length', String(installerSize))
    if (mode === 'stalled') { response.write(Buffer.alloc(1024)); return }
    const stream = createReadStream(installerPath, mode === 'interrupted' ? { end: 4095 } : {})
    stream.on('error', () => response.destroy())
    response.on('close', () => stream.destroy())
    if (mode === 'interrupted') { stream.pipe(response, { end: false }); stream.on('end', () => response.destroy()) }
    else stream.pipe(response)
    return
  }
  response.writeHead(404).end()
})
server.on('connection', socket => { sockets.add(socket); socket.on('close', () => sockets.delete(socket)) })
await new Promise(resolve_ => server.listen(0, '127.0.0.1', resolve_))
const origin = `http://127.0.0.1:${server.address().port}`
const env = { ...process.env, CSC_IDENTITY_AUTO_DISCOVERY: 'false' }
for (const name of ['CSC_LINK', 'CSC_KEY_PASSWORD', 'MNEMION_MAC_UPDATE_PRIVATE_KEY', 'MNEMION_WINDOWS_UPDATE_PRIVATE_KEY']) delete env[name]
for (const name of Object.keys(env)) if (name.toLowerCase() === 'psmodulepath') delete env[name]
const log = createWriteStream(join(output, 'build.log'))
const sleep = milliseconds => new Promise(resolve_ => setTimeout(resolve_, milliseconds))
let child
const installationProgress = []

function installerObservation(progressOnly = false, timeout = 20_000) {
  const result = spawnSync('powershell.exe', ['-NoProfile', '-NonInteractive', '-File',
    join(scripts, 'windows-installer-observation.ps1'), ...(progressOnly ? ['-ProgressOnly'] : [])],
  { env: { ...env, MNEMION_PROBE_OUTPUT_DIRECTORY: output }, encoding: 'utf8',
    timeout, windowsHide: true, maxBuffer: 65_536 })
  if (result.status !== 0) return { processInspectionFailed: true }
  try { return JSON.parse(result.stdout) } catch { return { processInspectionFailed: true } }
}

async function run(command, args, timeout = 180_000) {
  await new Promise((resolve_, reject) => {
    const process_ = spawn(command, args, { cwd: join(root, 'studio/electron'), env, stdio: ['ignore', 'pipe', 'pipe'], windowsHide: true })
    process_.stdout.pipe(log, { end: false }); process_.stderr.pipe(log, { end: false })
    const timer = setTimeout(() => { process_.kill(); reject(new Error('Native installer operation timed out')) }, timeout)
    process_.on('error', error => { clearTimeout(timer); reject(error) })
    process_.on('exit', code => { clearTimeout(timer); code === 0 ? resolve_() : reject(new Error(`Native installer operation failed (${code}); inspect build.log`)) })
  })
}

async function prepare(buildVersion) {
  const directory = join(output, 'packages', buildVersion)
  await cp(source.bundle, directory, { recursive: true })
  const resources = join(directory, 'resources')
  const unpacked = join(output, `asar-${buildVersion}`)
  extractAll(join(resources, 'app.asar'), unpacked)
  const manifestPath = join(unpacked, 'package.json')
  const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'))
  manifest.main = 'windows-update-fixture.mjs'
  manifest.name = 'mnemion-update-probe-' + id
  manifest.productName = productName
  manifest.version = buildVersion
  writeFileSync(manifestPath, JSON.stringify(manifest))
  await cp(join(scripts, 'windows-update-fixture.mjs'), join(unpacked, 'windows-update-fixture.mjs'))
  const securityPath = join(unpacked, 'dist/windows-update-security.js')
  const security = readFileSync(securityPath, 'utf8')
  const endpoint = 'https://github.com/Perseusxrltd/mnemion/releases'
  if (!security.includes(endpoint)) throw new Error('The production update policy endpoint was not found')
  writeFileSync(securityPath, security.replace(endpoint, `${origin}/Perseusxrltd/mnemion/releases`))
  writeFileSync(join(unpacked, 'dist/windows-updates.json'), JSON.stringify({ schema: 1, algorithm: 'ed25519', publicKey, publisherNames: [] }))
  await createPackageWithOptions(unpacked, join(resources, 'app.asar'), {})
  const headerHash = createHash('sha256').update(getRawHeader(join(resources, 'app.asar')).headerString).digest('hex')
  const application = join(directory, `${productName}.exe`)
  await rename(join(directory, `${packageJson.build.productName}.exe`), application)
  // Preserve ASAR validation in the instrumented copy by updating its PE resource.
  const executable = NtExecutable.from(readFileSync(application))
  const resource = NtExecutableResource.from(executable)
  const language = Resource.VersionInfo.fromEntries(resource.entries)[0].getAllLanguagesForStringValues()[0]
  resource.entries = resource.entries.filter(entry => entry.type !== 'INTEGRITY' || entry.id !== 'ELECTRONASAR')
  resource.entries.push({ type: 'INTEGRITY', id: 'ELECTRONASAR', lang: language.lang, codepage: language.codepage,
    bin: Buffer.from(JSON.stringify([{ file: 'resources\\app.asar', alg: 'SHA256', value: headerHash }])) })
  resource.outputResource(executable)
  writeFileSync(application, Buffer.from(executable.generate()))
  writeFileSync(join(resources, 'update-fixture.json'), JSON.stringify({ userData, receipt, expectedVersion: target, control: origin + '/control' }))
  const destination = join(output, `installer-${buildVersion}`)
  const configuration = {
    extends: null, appId: applicationId, productName, extraMetadata: { version: buildVersion, name: manifest.name },
    directories: { output: destination }, compression: 'store',
    win: { target: ['nsis'], artifactName: `Mnemion-Studio-${buildVersion}-windows-${process.arch}.exe` },
    nsis: { oneClick: false, allowToChangeInstallationDirectory: true, createDesktopShortcut: false,
      createStartMenuShortcut: false, runAfterFinish: false, include: nsisInclude },
  }
  const configPath = join(output, `builder-${buildVersion}.json`)
  writeFileSync(configPath, JSON.stringify(configuration))
  await run(process.execPath, [join(root, 'studio/electron/node_modules/electron-builder/out/cli/cli.js'),
    '--win', 'nsis', `--${process.arch}`, '--prepackaged', directory, '--config', configPath, '--publish', 'never'], 300_000)
  return join(destination, `Mnemion-Studio-${buildVersion}-windows-${process.arch}.exe`)
}

async function verifyInstalledBinaries(expected, actual) {
  let count = 0
  for (const entry of await readdir(expected, { withFileTypes: true })) {
    const sourcePath = join(expected, entry.name), installedPath = join(actual, entry.name)
    if (entry.isDirectory()) { count += await verifyInstalledBinaries(sourcePath, installedPath); continue }
    if (!/\.(?:exe|dll|node|pyd)$/i.test(entry.name)) continue
    if (!existsSync(installedPath)) throw new Error(`NSIS did not extract a required binary: ${entry.name}`)
    const hashes = []
    for (const path of [sourcePath, installedPath]) {
      const hash = createHash('sha256')
      for await (const bytes of createReadStream(path)) hash.update(bytes)
      hashes.push(hash.digest('hex'))
    }
    if (hashes[0] !== hashes[1]) throw new Error(`NSIS changed an installed binary: ${entry.name}`)
    count++
  }
  return count
}

try {
  const initial = await prepare(version)
  installerPath = await prepare(target)
  const { stat } = await import('node:fs/promises')
  installerSize = (await stat(installerPath)).size
  const hash = createHash('sha512')
  for await (const bytes of createReadStream(installerPath)) hash.update(bytes)
  installerHash = hash.digest('base64')
  // A Windows ARM bootstrap can hand work to an emulated child process.
  // Start-Process -Wait tracks that tree; a successful stub exit is not installation proof.
  env.MNEMION_PROBE_INITIAL_INSTALLER = initial
  env.MNEMION_PROBE_INSTALL_DIRECTORY = installed
  await run('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command',
    '$ErrorActionPreference="Stop"; $p=Start-Process -FilePath $env:MNEMION_PROBE_INITIAL_INSTALLER '
    + '-ArgumentList @("/S","/currentuser",("/D="+$env:MNEMION_PROBE_INSTALL_DIRECTORY)) -PassThru -Wait; exit $p.ExitCode'])
  delete env.MNEMION_PROBE_INITIAL_INSTALLER
  delete env.MNEMION_PROBE_INSTALL_DIRECTORY
  const executable = join(installed, `${productName}.exe`)
  const installationDeadline = Date.now() + 30_000
  while (!existsSync(executable) && Date.now() < installationDeadline) await sleep(250)
  if (!existsSync(executable)) {
    writeFileSync(join(output, 'first-install.json'), JSON.stringify({ architecture: process.arch, installed,
      files: existsSync(installed) ? (await readdir(installed)).slice(0, 40) : [],
      packageFiles: (await readdir(join(output, 'packages', version))).slice(0, 40) }, null, 2))
    throw new Error('NSIS first installation did not create the application')
  }
  const installedBinaries = await verifyInstalledBinaries(join(output, 'packages', version), installed)
  const electronLog = createWriteStream(join(output, 'electron.log'))
  // This fixture tests a real foreground GUI. Hiding its initial native window
  // can leave isFocused() true without a visible window, which is background
  // state under the production update policy. Installers stay silent above.
  child = spawn(executable, [], { stdio: ['ignore', 'pipe', 'pipe'], windowsHide: false, env })
  child.stdout.pipe(electronLog, { end: false }); child.stderr.pipe(electronLog, { end: false })
  child.once('close', () => electronLog.end())
  child.on('error', error => { writeFileSync(join(output, 'spawn-error.txt'), error.message) })
  const started = performance.now()
  const progressWindow = new InstallerProgressWindow(started)
  // The usual fast path does not invoke CIM. Slow copies get observed CPU/IO
  // progress, not an unconditional retry or an unbounded timeout extension.
  let nextObservation = started + 120_000
  let events = [], relaunched, relaunchedAt
  while (true) {
    if (existsSync(receipt)) {
      events = readFileSync(receipt, 'utf8').trim().split('\n').filter(Boolean).map(line => JSON.parse(line))
      const error = events.find(event => event.event === 'error')
      if (error) throw new Error(`The Windows fixture failed: ${error.message}`)
      relaunched = events.find(event => event.event === 'relaunched')
      if (relaunched) { relaunchedAt = performance.now(); break }
    }
    if (child.exitCode !== null && child.exitCode !== 0) throw new Error('The initial application exited unexpectedly')
    const remaining = progressWindow.maximum - (performance.now() - started)
    if (remaining <= 0) throw new Error('NSIS did not replace and relaunch the target application: maximum_duration')
    if (performance.now() >= nextObservation) {
      const observation = installerObservation(true, Math.max(1, Math.min(20_000, Math.floor(remaining))))
      const now = performance.now()
      progressWindow.observe(now, observation.processes)
      const sample = { elapsedSeconds: Math.round((now - started) / 1000), ...observation }
      installationProgress.push(sample)
      appendFileSync(join(output, 'installer-progress.jsonl'), JSON.stringify(sample) + '\n')
      console.log('NSIS progress ' + JSON.stringify(sample))
      nextObservation = now + 30_000
    }
    const expired = progressWindow.expired(performance.now())
    if (expired) throw new Error(`NSIS did not replace and relaunch the target application: ${expired}`)
    await sleep(200)
  }
  if (!relaunched || relaunched.version !== target || relaunched.pid === child.pid) throw new Error('NSIS did not replace and relaunch the target application')
  process.kill(relaunched.pid, 0)
  const updatedBinaries = await verifyInstalledBinaries(join(output, 'packages', target), installed)
  if (events.filter(event => event.event === 'workspace-stop' && event.allowed).length !== 2
    || events.filter(event => event.event === 'workspace-stop' && !event.allowed).length !== 1
    || !events.some(event => event.event === 'restart-cancelled')
    || !events.some(event => event.event === 'guards-passed') || !events.some(event => event.event === 'cancelled-transfer')
    || !events.some(event => event.event === 'native-redirect-verified')) throw new Error('Native Windows guards and recovery checks were incomplete')
  for (const rejected of ['bad-signature', 'wrong-architecture', 'oversized', 'interrupted', 'older', 'cached-tamper']) {
    if (!events.some(event => event.event === 'rejected' && event.case === rejected)) throw new Error('A native rejection case was not measured')
  }
  if (requests.some(request => request.path.endsWith('.exe') && ['bad-signature', 'wrong-architecture', 'oversized', 'older'].includes(request.mode))) throw new Error('Rejected metadata triggered a payload download')
  if (createHash('sha256').update(readFileSync(join(source.resources, 'app.asar'))).digest('hex') !== sourceHash) throw new Error('The production package was changed by the fixture')
  const result = { architecture: process.arch, originalVersion: version, updatedVersion: target, downloads,
    installedBinaries, updatedBinaries, binaryHashesPreserved: true, installationPathWithSpaces: true,
    updateRelaunchSeconds: Math.round((relaunchedAt - started) / 1000),
    installerProgressSamples: installationProgress.length,
    nativeNsisFirstInstallation: true, nativeReplacementAndRelaunch: true, packagedDesktopController: true,
    signedMetadataAndCachedInstallerVerified: true, focusTransferDraftIdleGuards: true,
    nativeManualRedirects: true,
    interruptionPauseTamperingAndRecovery: true, productionPackageUnchanged: true,
    fixtureScope: 'Private copies, ephemeral publisher key and local HTTP; synthetic idle/transfer/draft state; real native windows and NSIS installation' }
  writeFileSync(join(output, 'result.json'), JSON.stringify(result, null, 2))
  console.log(JSON.stringify(result, null, 2))
} catch (error) {
  const diagnostic = { architecture: process.arch, initialPid: child?.pid,
    initialExitCode: child?.exitCode, initialSignal: child?.signalCode,
    files: existsSync(installed) ? (await readdir(installed)).slice(0, 60) : [] }
  try {
    diagnostic.installedVersion = JSON.parse(extractFile(join(installed, 'resources/app.asar'), 'package.json').toString('utf8')).version
    diagnostic.updatedBinaries = await verifyInstalledBinaries(join(output, 'packages', target), installed)
  } catch (failure) { diagnostic.binaryVerification = failure.message }
  diagnostic.processes = installerObservation()
  diagnostic.installationProgress = installationProgress
  writeFileSync(join(output, 'upgrade-failure.json'), JSON.stringify(diagnostic, null, 2))
  throw error
} finally {
  for (const socket of sockets) socket.destroy()
  await new Promise(resolve_ => server.close(resolve_))
  const observed = existsSync(receipt) ? readFileSync(receipt, 'utf8').trim().split('\n').filter(Boolean).map(line => {
    try { return JSON.parse(line).pid } catch { return undefined }
  }) : []
  for (const pid of new Set([child?.pid, ...observed].filter(Boolean))) spawnSync('taskkill.exe', ['/PID', String(pid), '/T', '/F'], { stdio: 'ignore' })
  // Remove this isolated installation and its unique registry entries only.
  if (existsSync(installed)) {
    const uninstaller = (await readdir(installed)).find(name => name.startsWith('Uninstall ') && name.endsWith('.exe'))
    if (uninstaller) await run(join(installed, uninstaller), ['/S']).catch(() => {})
  }
  log.end()
}
