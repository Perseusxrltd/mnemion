import { createReadStream, existsSync, mkdtempSync, readFileSync, rmSync, statSync, writeFileSync } from 'node:fs'
import { basename, join } from 'node:path'
import { tmpdir } from 'node:os'
import { createHash } from 'node:crypto'
import { spawnSync } from 'node:child_process'
import { root, platformArtifacts } from './platform-artifacts.mjs'
import { verifyNativeResources } from './native-resources.mjs'
import { packageFootprint } from './package-footprint.mjs'

const artifacts = platformArtifacts()
const requireSignature = process.env.MNEMION_REQUIRE_CODE_SIGNATURE === '1'
const installerDownloadBudget = 400 * 1024 * 1024

function requireFile(path, minBytes = 1) {
  if (!existsSync(path) || !statSync(path).isFile() || statSync(path).size < minBytes) {
    throw new Error(`Missing or incomplete packaged file: ${path}`)
  }
}

function run(command, args, options = {}) {
  const result = spawnSync(command, args, { cwd: root, encoding: 'utf8', timeout: 120_000, maxBuffer: 32 * 1024 * 1024, ...options })
  if (result.error || !(options.allowedStatus || [0]).includes(result.status)) {
    throw new Error(`${command} failed: ${result.error?.message || result.stderr || result.stdout}`)
  }
  return `${result.stdout || ''}\n${result.stderr || ''}`
}

function payload(listing, paths) {
  const normalized = listing.replaceAll('\\', '/')
  for (const path of paths) {
    if (!normalized.includes(path)) throw new Error(`Installer is missing ${path}`)
  }
}

requireFile(artifacts.app)
requireFile(join(artifacts.resources, 'frontend/dist/index.html'))
for (const file of ['LICENSE', 'NOTICE', 'inventory.json', 'sbom.cdx.json']) {
  requireFile(join(artifacts.resources, 'licenses', file))
}
requireFile(join(artifacts.resources, 'client', process.platform === 'win32' ? 'mnemion-client.exe' : 'mnemion-client'))
const nativeRuntime = verifyNativeResources(artifacts.resources)
for (const installer of artifacts.installers) {
  requireFile(installer, 40 * 1024 * 1024)
  if (statSync(installer).size > installerDownloadBudget) {
    throw new Error(`Installer exceeds the 400 MiB download budget: ${basename(installer)}`)
  }
}

let signature = 'not required on this platform'
if (process.platform === 'win32') {
  const { extractFile, listPackage } = await import('@electron/asar')
  const archive = join(artifacts.resources, 'app.asar')
  const embedded = JSON.parse(extractFile(archive, 'dist/windows-updates.json').toString())
  const expected = JSON.parse(readFileSync(join(root, 'studio/electron/native/windows-updates.json'), 'utf8'))
  if (JSON.stringify(embedded) !== JSON.stringify(expected)
    || !extractFile(archive, 'dist/windows-update-security.js').toString().includes('https://github.com/Perseusxrltd/mnemion/releases')
    || listPackage(archive).some(name => /(?:windows-update-fixture|update-fixture)\.mjs$/.test(name))) {
    throw new Error('The Windows package must embed the production update trust configuration')
  }
  const installer = artifacts.installers[0]
  requireFile(`${installer}.blockmap`, 1024)
  const { getPath7za } = await import('app-builder-lib/out/toolsets/7zip.js')
  const listing = run(await getPath7za(), ['l', installer], { allowedStatus: [0, 1] })
  // NSIS self-extractors can return 1 for the data after their 7z payload.
  payload(listing, ['Mnemion Studio.exe', 'resources/client/mnemion-client.exe',
    'resources/engine/mnemion-engine.exe', 'resources/postgresql/bin/postgres.exe', 'resources/native-runtime.json',
    'resources/frontend/dist/index.html', 'resources/frontend/dist/icon.ico'])
  // A PowerShell 7 build shell exports its module path. Windows PowerShell 5
  // must resolve its own security module instead of trying to load that runtime.
  const signatureEnv = { ...process.env }
  for (const key of Object.keys(signatureEnv)) {
    if (key.toLowerCase() === 'psmodulepath') delete signatureEnv[key]
  }
  signature = run('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command',
    `Get-AuthenticodeSignature -LiteralPath '${installer.replaceAll("'", "''")}' | Select-Object -ExpandProperty Status`], { env: signatureEnv }).trim()
  if (requireSignature && signature !== 'Valid') throw new Error(`Authenticode verification failed: ${signature}`)
} else if (process.platform === 'darwin') {
  run('hdiutil', ['verify', artifacts.installers[0]])
  payload(run('unzip', ['-Z1', artifacts.installers[1]]), [
    'Mnemion Studio.app/Contents/MacOS/Mnemion Studio',
    'Mnemion Studio.app/Contents/Resources/client/mnemion-client',
    'Mnemion Studio.app/Contents/Resources/engine/mnemion-engine',
    'Mnemion Studio.app/Contents/Resources/postgresql/bin/postgres',
    'Mnemion Studio.app/Contents/Resources/native-runtime.json',
    'Mnemion Studio.app/Contents/Resources/frontend/dist/index.html',
    'Mnemion Studio.app/Contents/MacOS/MnemionUpdater',
    'Mnemion Studio.app/Contents/Frameworks/Sparkle.framework/',
  ])
  const check = spawnSync('codesign', ['-dv', '--verbose=4', artifacts.bundle], { encoding: 'utf8' })
  signature = /Signature=adhoc/.test(check.stderr || '') ? 'ad hoc; independent Ed25519 updates' : 'unexpected signature'
  if (signature === 'unexpected signature') throw new Error('The free macOS build requires an intact ad-hoc signature')
  run('codesign', ['--verify', '--deep', '--strict', artifacts.bundle])
  const config = JSON.parse(readFileSync(join(root, 'studio/electron/native/sparkle.json'), 'utf8'))
  const build = JSON.parse(readFileSync(join(artifacts.resources, 'macos-updater-build.json'), 'utf8'))
  if (build.fixture !== false || build.public_key !== config.publicKey || build.sparkle_distribution_sha256 !== config.sha256) {
    throw new Error('The macOS updater is not the verified production configuration')
  }
  const plist = join(artifacts.bundle, 'Contents/Info.plist')
  if (run('/usr/libexec/PlistBuddy', ['-c', 'Print :SUPublicEDKey', plist]).trim() !== config.publicKey
    || run('/usr/libexec/PlistBuddy', ['-c', 'Print :SUVerifyUpdateBeforeExtraction', plist]).trim() !== 'true') {
    throw new Error('The installed update verifier is misconfigured')
  }
  const inventory = JSON.parse(readFileSync(join(artifacts.resources, 'licenses/inventory.json'), 'utf8'))
  if (!inventory.components.some(item => item.name === 'Sparkle' && item.version === config.version)) {
    throw new Error('The packaged updater is missing its third-party license inventory')
  }
} else {
  const directory = mkdtempSync(join(tmpdir(), 'mnemion-package-'))
  try {
    run(artifacts.installers[0], ['--appimage-extract'], { cwd: directory })
    const extracted = join(directory, 'squashfs-root')
    for (const path of ['AppRun', 'mnemion-studio', 'resources/client/mnemion-client', 'resources/frontend/dist/index.html']) {
      requireFile(join(extracted, path))
    }
    verifyNativeResources(join(extracted, 'resources'))
    payload(run('dpkg-deb', ['--contents', artifacts.installers[1]]), [
      'resources/client/mnemion-client', 'resources/frontend/dist/index.html', 'mnemion-studio',
      'resources/engine/mnemion-engine', 'resources/postgresql/bin/postgres', 'resources/native-runtime.json',
    ])
  } finally { rmSync(directory, { recursive: true, force: true }) }
}

const checksums = []
for (const path of artifacts.installers) {
  const digest = createHash('sha256')
  for await (const chunk of createReadStream(path)) digest.update(chunk)
  checksums.push(`${digest.digest('hex')}  ${basename(path)}`)
}
writeFileSync(join(artifacts.output, `SHA256SUMS-${process.platform}-${process.arch}.txt`), checksums.join('\n') + '\n')
console.log(JSON.stringify({ ok: true, platform: process.platform, architecture: process.arch, signature, nativeRuntime,
  installer_download_budget_bytes: installerDownloadBudget,
  unpacked: packageFootprint(artifacts.bundle, artifacts.resources),
  installers: artifacts.installers.map(path => ({ file: basename(path), bytes: statSync(path).size })) }, null, 2))
