import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import { createHash } from 'node:crypto'
import { chmodSync, copyFileSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, relative } from 'node:path'
import test from 'node:test'
import { performOwnedInstall, resourceInstallSteps, verifyPreparedPackage } from './installed-resource-report.mjs'
import { verifyNativeResources } from './native-resources.mjs'
import { packageJson, root } from './platform-artifacts.mjs'

if (!process.env.MNEMION_ENGINE_PYTHON) {
  process.env.MNEMION_ENGINE_PYTHON = process.platform === 'win32' ? 'python' : 'python3'
}

const platform = { linux: 'linux', darwin: 'macos', win32: 'windows' }[process.platform]
const arch = process.arch
const componentArch = platform === 'windows' ? 'x64' : arch

function python(code, args) {
  const result = spawnSync(process.env.MNEMION_ENGINE_PYTHON, ['-c', code, ...args], {
    cwd: root, encoding: 'utf8', maxBuffer: 8 * 1024 * 1024,
  })
  if (result.status !== 0) throw new Error(result.stderr || result.stdout || 'python failed')
  return result.stdout.trim()
}

function sourceDigest(directory) {
  return python(
    'from deploy.native_resources import source_digest; from pathlib import Path; import sys; print(source_digest(Path(sys.argv[1])))',
    [directory],
  )
}

function binary(kind, machine) {
  const header = Buffer.alloc(128)
  if (kind === 'windows') {
    header.write('MZ', 0)
    header.writeUInt32LE(64, 60)
    header.write('PE\0\0', 64, 'latin1')
    header.writeUInt16LE(machine === 'x64' ? 0x8664 : 0xaa64, 68)
  } else if (kind === 'linux') {
    header.write('\u007fELF', 0, 'latin1')
    header[4] = 2
    header[5] = 1
    header.writeUInt16LE(machine === 'x64' ? 62 : 183, 18)
  } else {
    header.writeUInt32LE(0xfeedfacf, 0)
    header.writeUInt32LE(machine === 'x64' ? 0x01000007 : 0x0100000c, 4)
  }
  return header
}

function walk(directory) {
  const files = []
  for (const name of readdirSync(directory)) {
    const path = join(directory, name)
    if (statSync(path).isDirectory()) files.push(...walk(path))
    else files.push(path)
  }
  return files
}

function seal(directory, metadata) {
  const files = {}
  for (const path of walk(directory)) {
    const info = statSync(path)
    files[relative(directory, path).replaceAll('\\', '/')] = {
      size: info.size,
      sha256: createHash('sha256').update(readFileSync(path)).digest('hex'),
      executable: (info.mode & 0o111) !== 0,
    }
  }
  metadata.files = files
  writeFileSync(join(directory, 'mnemion-runtime.json'), JSON.stringify(metadata))
}

function writeComponent(directory, names, executableNames, metadata) {
  mkdirSync(directory, { recursive: true })
  for (const name of names) {
    const path = join(directory, ...name.split('/'))
    mkdirSync(join(path, '..'), { recursive: true })
    const executable = executableNames.includes(name)
    writeFileSync(path, executable ? binary(platform, componentArch) : 'license fixture')
    if (executable && process.platform !== 'win32') chmodSync(path, 0o755)
  }
  seal(directory, metadata)
}

function writeResources(directory, sourceSha, lockSha) {
  const configuration = JSON.parse(readFileSync(join(root, 'deploy/native-postgres.json'), 'utf8'))
  const suffix = platform === 'windows' ? '.exe' : ''
  const engineExec = ['mnemion-engine' + suffix, '_internal/mnemion/product_telemetry/network-state.node']
  const engineLicenses = ['licenses/LICENSE', 'licenses/NOTICE', 'licenses/inventory.json', 'licenses/sbom.cdx.json']
  const databaseExec = ['postgres', 'pg_ctl', 'initdb', 'pg_dump', 'pg_restore', 'psql'].map(name => 'bin/' + name + suffix)
  const databaseLicenses = ['postgresql', 'pgvector', 'openssl', 'zlib'].map(name => 'licenses/' + name + '.txt')
  const common = {
    format: 1, platform, architecture: componentArch, version: packageJson.version,
    model_weights_bundled: false, lock_sha256: lockSha, source_sha256: sourceSha,
  }
  writeComponent(join(directory, 'engine'), [...engineExec, ...engineLicenses], engineExec, { ...common, component: 'service' })
  writeComponent(join(directory, 'postgresql'), [...databaseExec, ...databaseLicenses], databaseExec, {
    ...common,
    component: 'postgresql',
    sources: Object.fromEntries(['postgresql', 'pgvector', 'openssl', 'zlib'].map(name => [name, configuration[name]])),
  })
}

function stampInventory(directory, sourceRoot) {
  const printed = python(
    [
      'import json, sys',
      'from pathlib import Path',
      'from deploy.native_resources import verify',
      'resources, platform, arch, version = sys.argv[1:5]',
      'source = sys.argv[5] if len(sys.argv) > 5 else ""',
      'kwargs = {"source_root": Path(source)} if source else {}',
      'print(json.dumps(verify(Path(resources), platform, arch, version, **kwargs)))',
    ].join('\n'),
    [directory, platform, arch, packageJson.version, sourceRoot || ''],
  )
  writeFileSync(join(directory, 'native-runtime.json'), printed + '\n')
}

function writeSource(directory, disclosure, route) {
  mkdirSync(join(directory, 'mnemion/product_telemetry'), { recursive: true })
  mkdirSync(join(directory, 'studio/engine'), { recursive: true })
  mkdirSync(join(directory, 'deploy'), { recursive: true })
  writeFileSync(join(directory, 'mnemion/product_telemetry/disclosure.json'), disclosure)
  writeFileSync(join(directory, 'mnemion/product_telemetry/transport-route.json'), route)
  writeFileSync(join(directory, 'studio/engine/main.py'), '# fixture\n')
  writeFileSync(join(directory, 'pyproject.toml'), '[project]\nname = "fixture"\n')
  copyFileSync(join(root, 'uv.lock'), join(directory, 'uv.lock'))
  writeFileSync(join(directory, 'deploy/build_telemetry_network.py'), '# fixture\n')
  writeFileSync(join(directory, 'deploy/build_telemetry_network.ps1'), '# fixture\n')
  copyFileSync(join(root, 'deploy/native-postgres.json'), join(directory, 'deploy/native-postgres.json'))
}

test('each installed package verifies only against its prepared source', { timeout: 180000 }, async () => {
  assert.ok(platform)
  assert.ok(arch === 'x64' || arch === 'arm64')
  const temp = mkdtempSync(join(tmpdir(), 'mnemion-source-binding-'))
  try {
    const inactiveRoot = join(temp, 'inactive-source')
    const activeRoot = join(temp, 'active-source')
    writeSource(inactiveRoot, '{"collection_available": false}\n', '{"version":2,"address":null,"certificate_authorities":[]}\n')
    writeSource(activeRoot, '{"collection_available": true}\n', '{"version":2,"address":"127.0.0.1","certificate_authorities":[]}\n')
    const inactiveDigest = sourceDigest(inactiveRoot)
    const activeDigest = sourceDigest(activeRoot)
    assert.notEqual(inactiveDigest, activeDigest)
    const lockSha = createHash('sha256').update(readFileSync(join(root, 'uv.lock'))).digest('hex')
    const resources = {
      inactive: join(temp, 'inactive-resources'),
      active: join(temp, 'active-resources'),
      ordinary: join(temp, 'ordinary-resources'),
    }
    writeResources(resources.inactive, inactiveDigest, lockSha)
    writeResources(resources.active, activeDigest, lockSha)
    writeResources(resources.ordinary, sourceDigest(root), lockSha)
    stampInventory(resources.inactive, inactiveRoot)
    stampInventory(resources.active, activeRoot)
    stampInventory(resources.ordinary, '')
    const inactiveInstaller = join(temp, 'inactive.exe')
    const activeInstaller = join(temp, 'active.exe')
    writeFileSync(inactiveInstaller, 'inactive-package')
    writeFileSync(activeInstaller, 'active-package')
    const manifest = JSON.parse(python(
      [
        'import json, sys',
        'from pathlib import Path',
        'from deploy.probe_telemetry_installed import bind_resource_packages',
        'manifest = bind_resource_packages(',
        '    source=sys.argv[1], inactive=Path(sys.argv[2]), active=Path(sys.argv[3]),',
        '    inactive_root=Path(sys.argv[4]), active_root=Path(sys.argv[5]))',
        'print(json.dumps(manifest))',
      ].join('\n'),
      ['a'.repeat(40), inactiveInstaller, activeInstaller, inactiveRoot, activeRoot],
    ))
    assert.equal(manifest.source, 'a'.repeat(40))
    assert.equal(manifest.cases[0].package, 'inactive')
    assert.equal(manifest.cases.at(-1).package, 'inactive')
    assert.equal(JSON.stringify(manifest).includes('source_sha256'), false)
    assert.notEqual(manifest.packages.inactive.source_root, manifest.packages.active.source_root)
    assert.notEqual(manifest.packages.inactive.source_root, root)
    const steps = resourceInstallSteps(manifest.cases)
    const firstInstall = steps.find(step => step.action === 'install')
    assert.equal(firstInstall.package, 'inactive')
    const installations = []
    const verified = await performOwnedInstall(installations, {
      id: firstInstall.id, directory: join(temp, 'installed-inactive'), package: firstInstall.package,
    }, {
      refusePreexisting: async () => {},
      installProduct: async () => {},
      verify: async owned => verifyPreparedPackage(manifest, owned.package, resources[owned.package]),
    })
    assert.equal(installations[0].state, 'verified')
    assert.equal(installations[0].package, 'inactive')
    assert.equal(verified.version, packageJson.version)
    const active = await verifyPreparedPackage(manifest, 'active', resources.active)
    assert.equal(active.version, packageJson.version)
    await assert.rejects(async () => verifyNativeResources(resources.inactive), /different source files/)
    await assert.rejects(
      async () => verifyPreparedPackage(manifest, 'inactive', resources.active),
      /different source files/,
    )
    const claimed = structuredClone(manifest)
    claimed.packages.inactive.source_sha256 = inactiveDigest
    claimed.packages.inactive.source_root = manifest.packages.active.source_root
    await assert.rejects(
      async () => verifyPreparedPackage(claimed, 'inactive', resources.inactive),
      /different source files/,
    )
    await assert.rejects(
      async () => verifyPreparedPackage({ packages: { inactive: { source_sha256: inactiveDigest } } }, 'inactive', resources.inactive),
      /Resource package preparation is missing/,
    )
    await assert.rejects(async () => verifyNativeResources(resources.inactive, ''), /requires the prepared source/)
    const ordinary = await verifyNativeResources(resources.ordinary)
    assert.equal(ordinary.version, packageJson.version)
    await assert.rejects(
      async () => verifyNativeResources(resources.ordinary, manifest.packages.inactive.source_root),
      /different source files/,
    )
    writeFileSync(join(inactiveRoot, 'mnemion/product_telemetry/disclosure.json'), '{"collection_available": false, "tampered": true}\n')
    await assert.rejects(
      async () => verifyPreparedPackage(manifest, 'inactive', resources.inactive),
      /different source files/,
    )
  } finally {
    rmSync(temp, { recursive: true, force: true })
  }
})
