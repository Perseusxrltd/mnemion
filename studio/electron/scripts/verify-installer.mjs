import { createReadStream, existsSync, mkdtempSync, rmSync, statSync, writeFileSync } from 'node:fs'
import { basename, join } from 'node:path'
import { tmpdir } from 'node:os'
import { createHash } from 'node:crypto'
import { spawnSync } from 'node:child_process'
import { root, platformArtifacts } from './platform-artifacts.mjs'

const artifacts = platformArtifacts()
const requireSignature = process.env.MNEMION_REQUIRE_CODE_SIGNATURE === '1'

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
for (const installer of artifacts.installers) requireFile(installer, 40 * 1024 * 1024)

let signature = 'not required on this platform'
if (process.platform === 'win32') {
  const installer = artifacts.installers[0]
  requireFile(`${installer}.blockmap`, 1024)
  const { getPath7za } = await import('app-builder-lib/out/toolsets/7zip.js')
  const listing = run(await getPath7za(), ['l', installer], { allowedStatus: [0, 1] })
  // NSIS self-extractors can return 1 for the data after their 7z payload.
  payload(listing, ['Mnemion Studio.exe', 'resources/client/mnemion-client.exe',
    'resources/frontend/dist/index.html', 'resources/frontend/dist/icon.ico'])
  signature = run('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command',
    `Get-AuthenticodeSignature -LiteralPath '${installer.replaceAll("'", "''")}' | Select-Object -ExpandProperty Status`]).trim()
  if (requireSignature && signature !== 'Valid') throw new Error(`Authenticode verification failed: ${signature}`)
} else if (process.platform === 'darwin') {
  run('hdiutil', ['verify', artifacts.installers[0]])
  payload(run('unzip', ['-Z1', artifacts.installers[1]]), [
    'Mnemion Studio.app/Contents/MacOS/Mnemion Studio',
    'Mnemion Studio.app/Contents/Resources/client/mnemion-client',
    'Mnemion Studio.app/Contents/Resources/frontend/dist/index.html',
  ])
  const check = spawnSync('codesign', ['-dv', '--verbose=4', artifacts.bundle], { encoding: 'utf8' })
  signature = /Authority=Developer ID Application:/.test(check.stderr || '') ? 'Developer ID' : 'unsigned or ad hoc'
  if (requireSignature) {
    if (signature !== 'Developer ID') throw new Error('A Developer ID application signature is required')
    run('codesign', ['--verify', '--deep', '--strict', artifacts.bundle])
    run('spctl', ['--assess', '--type', 'execute', '--verbose=2', artifacts.bundle])
    run('xcrun', ['stapler', 'validate', artifacts.bundle])
  }
} else {
  const directory = mkdtempSync(join(tmpdir(), 'mnemion-package-'))
  try {
    run(artifacts.installers[0], ['--appimage-extract'], { cwd: directory })
    const extracted = join(directory, 'squashfs-root')
    for (const path of ['AppRun', 'mnemion-studio', 'resources/client/mnemion-client', 'resources/frontend/dist/index.html']) {
      requireFile(join(extracted, path))
    }
    payload(run('dpkg-deb', ['--contents', artifacts.installers[1]]), [
      'resources/client/mnemion-client', 'resources/frontend/dist/index.html', 'mnemion-studio',
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
console.log(JSON.stringify({ ok: true, platform: process.platform, architecture: process.arch, signature,
  installers: artifacts.installers.map(path => ({ file: basename(path), bytes: statSync(path).size })) }, null, 2))
