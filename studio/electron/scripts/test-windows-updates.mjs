import assert from 'node:assert/strict'
import { test } from 'node:test'
import { generateKeyPairSync, createHash, sign } from 'node:crypto'
import { mkdtemp, readFile, readdir, rm, symlink, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { verifyWindowsManifest, verifyWindowsInstaller, compareWindowsVersions, allowedWindowsRedirect,
  windowsManifestURL, WINDOWS_INSTALLER_MINIMUM, WINDOWS_READY_LIFETIME } from '../dist/windows-update-security.js'
import { transferWindowsUpdate } from '../dist/windows-update-transfer.js'
import { WindowsUpdateBridge, windowsInstallerEnvironment } from '../dist/windows-updates.js'
import { createWindowsUpdateFetch } from '../dist/windows-update-network.js'
import { EventEmitter } from 'node:events'
import { Readable } from 'node:stream'

const pair = generateKeyPairSync('ed25519')
const publicKey = pair.publicKey.export({ type: 'spki', format: 'der' }).subarray(-32).toString('base64')
const trust = { schema: 1, algorithm: 'ed25519', publicKey, publisherNames: [] }
const bytes = Buffer.alloc(WINDOWS_INSTALLER_MINIMUM, 0x39)
const digest = createHash('sha512').update(bytes).digest('base64')
function data(changes = {}) {
  const version = changes.version || '4.0.2'
  const architecture = changes.architecture || 'x64'
  const filename = `Mnemion-Studio-${version}-windows-${architecture}.exe`
  return { schema: 1, application: 'com.perseusxr.mnemion-studio', platform: 'windows', architecture,
    version, filename, url: `https://github.com/Perseusxrltd/mnemion/releases/download/v${version}/${filename}`,
    size: bytes.length, sha512: digest, ...changes }
}
function envelope(payload = data(), key = pair.privateKey) {
  const raw = Buffer.from(JSON.stringify(payload))
  return Buffer.from(JSON.stringify({ schema: 1, payload: raw.toString('base64'), signature: sign(null, raw, key).toString('base64') }))
}
async function directory(t) {
  const path = await mkdtemp(join(tmpdir(), 'mnemion-windows-update-'))
  t.after(() => rm(path, { recursive: true, force: true }))
  return path
}
function fixture(cacheDirectory, { manifest = () => envelope(), download, launch = async () => {} } = {}) {
  const events = [], requests = []
  const fetcher = async (url, options) => {
    requests.push({ url, options })
    if (url === windowsManifestURL('x64')) return new Response(manifest())
    if (download) return download(url, options)
    return new Response(bytes, { headers: { 'content-length': String(bytes.length) } })
  }
  const bridge = new WindowsUpdateBridge({ version: '4.0.1', architecture: 'x64', cacheDirectory,
    applicationPath: join(cacheDirectory, 'installed', 'Mnemion Studio.exe'), resourcesPath: join(cacheDirectory, 'resources'), trust },
  fetcher, event => events.push(event), launch)
  return { bridge, requests, events }
}

test('only exact publisher-signed application and architecture metadata is accepted', () => {
  const verified = verifyWindowsManifest(envelope(), publicKey, 'x64')
  assert.deepEqual(verified, data())
  assert.equal(Object.isFrozen(verified), true)
  for (const change of [
    { schema: 2 }, { application: 'another.app' }, { platform: 'linux' }, { architecture: 'arm64' },
    { version: '4.0.3-beta' }, { version: '04.0.3' }, { version: '3.9.9' }, { version: '999999999.1.1' },
    { filename: '../update.exe' }, { url: 'https://example.com/update.exe' },
    { url: data().url + '?changed=1' }, { url: data().url.replace('v4.0.2', 'latest') },
    { size: -1 }, { size: bytes.length - 1 }, { size: 1024 ** 3 + 1 }, { size: '40000000' },
    { sha512: 'bad' }, { sha512: digest + '\n' }, { package: 'unverified-web-installer.7z' },
  ]) assert.throws(() => verifyWindowsManifest(envelope(data(change)), publicKey, 'x64'))
  assert.throws(() => verifyWindowsManifest(envelope(), publicKey, 'ia32'))
})

test('metadata tampering, wrong keys, oversized envelopes and unknown formats fail closed', () => {
  const altered = JSON.parse(envelope())
  altered.payload = Buffer.from(JSON.stringify(data({ version: '4.9.0' }))).toString('base64')
  assert.throws(() => verifyWindowsManifest(Buffer.from(JSON.stringify(altered)), publicKey, 'x64'))
  const other = generateKeyPairSync('ed25519')
  assert.throws(() => verifyWindowsManifest(envelope(data(), other.privateKey), publicKey, 'x64'))
  assert.throws(() => verifyWindowsManifest(Buffer.alloc(16 * 1024 + 1), publicKey, 'x64'))
  assert.throws(() => verifyWindowsManifest(Buffer.from([0xff, 0xfe]), publicKey, 'x64'))
  assert.throws(() => verifyWindowsManifest(Buffer.from(JSON.stringify({ ...JSON.parse(envelope()), schema: 2 })), publicKey, 'x64'))
  assert.throws(() => verifyWindowsManifest(Buffer.from(JSON.stringify({ ...JSON.parse(envelope()), extra: true })), publicKey, 'x64'))
  assert.throws(() => verifyWindowsManifest(envelope(), 'invalid key', 'x64'))
})

test('stable comparison blocks downgrade and handles multi-digit versions numerically', () => {
  assert.equal(compareWindowsVersions('4.0.2', '4.0.1'), 1)
  assert.equal(compareWindowsVersions('4.0.1', '4.0.1'), 0)
  assert.equal(compareWindowsVersions('4.9.1', '4.10.0'), -1)
  assert.equal(compareWindowsVersions('4.0.100', '4.0.99'), 1)
})

test('redirects stay within the official immutable release and GitHub asset CDN', () => {
  const initial = windowsManifestURL('x64')
  const immutable = initial.replace('latest/download', 'download/v4.0.2')
  const cdn = 'https://release-assets.githubusercontent.com/github-production-release-asset/test?token=example'
  assert.equal(allowedWindowsRedirect(initial, immutable, initial), true)
  assert.equal(allowedWindowsRedirect(immutable, cdn, initial), true)
  assert.equal(allowedWindowsRedirect(data().url, cdn, data().url), true)
  for (const next of ['http://github.com/update', 'file:///tmp/update', 'https://127.0.0.1/update',
    'https://github.com.attacker.example/update', immutable.replace('mnemion/', 'other/'),
    immutable.replace('x64', 'arm64'), immutable.replace('v4.0.2', 'v4.0.2-beta'),
    immutable + '?x=1', 'https://user:pass@release-assets.githubusercontent.com/file',
    'https://release-assets.githubusercontent.com:444/file', cdn + '#fragment']) {
    assert.equal(allowedWindowsRedirect(initial, next, initial), false)
  }
  assert.equal(allowedWindowsRedirect(cdn, 'https://example.com', initial), false)
  assert.equal(allowedWindowsRedirect(data().url, data().url.replace('4.0.2', '4.0.3'), data().url), false)
})

test('cached installers are verified for size, content and symlinks every time', async t => {
  const root = await directory(t), path = join(root, data().filename)
  await writeFile(path, bytes)
  verifyWindowsInstaller(path, data())
  await writeFile(path, Buffer.from('truncated'))
  assert.throws(() => verifyWindowsInstaller(path, data()))
  await writeFile(path, bytes)
  const { open } = await import('node:fs/promises')
  const file = await open(path, 'r+')
  await file.write(Buffer.from([0]), 0, 1, 40)
  await file.close()
  assert.throws(() => verifyWindowsInstaller(path, data()))
  // Windows CI may disallow creating symlinks; Linux/macOS enforce this case.
  if (process.platform !== 'win32') {
    const link = join(root, 'linked.exe')
    await symlink(path, link)
    assert.throws(() => verifyWindowsInstaller(link, data()))
  }
})

test('transport rejects unsafe redirects, oversized streams, length mismatches and truncated transfers', async () => {
  const run = (response, changes = {}) => transferWindowsUpdate(async () => response, data().url, {
    signal: new AbortController().signal, limit: 5, timeout: 1000, consume: async () => {}, ...changes,
  })
  await assert.rejects(run(new Response('oversized')))
  await assert.rejects(run(new Response('ok', { headers: { 'content-length': '6' } })))
  await assert.rejects(run(new Response('ok', { headers: { 'content-length': 'invalid' } })))
  await assert.rejects(run(new Response('ok'), { expectedSize: 4 }))
  await assert.rejects(run(new Response('', { status: 302, headers: { location: 'https://example.com/update' } })))
  await assert.rejects(run(new Response('', { status: 403 })))
  const result = await run(new Response('hello'), { expectedSize: 5 })
  assert.equal(result, 5)
})

test('transport cancels stalled requests at its deadline and honours an already paused caller', async () => {
  const stalled = async (_url, options) => new Promise((_resolve, reject) => {
    options.signal.addEventListener('abort', () => reject(new Error('aborted')), { once: true })
  })
  await assert.rejects(transferWindowsUpdate(stalled, data().url, {
    signal: new AbortController().signal, limit: 5, timeout: 15, consume: async () => {},
  }))
  const controller = new AbortController()
  controller.abort()
  let requested = false
  await assert.rejects(transferWindowsUpdate(async () => { requested = true; return new Response('') }, data().url, {
    signal: controller.signal, limit: 5, timeout: 50, consume: async () => {},
  }))
  assert.equal(requested, false)
})

test('Electron redirect events are returned for validation without following or forwarding credentials', async () => {
  let aborted = false, followed = false
  const request = new EventEmitter()
  request.setHeader = () => {}
  request.abort = () => { aborted = true; request.emit('error', new Error('cancelled redirect')) }
  request.followRedirect = () => { followed = true }
  request.end = () => queueMicrotask(() => request.emit('redirect', 302, 'GET', 'https://release-assets.githubusercontent.com/file'))
  const fetcher = createWindowsUpdateFetch(() => request)
  const response = await fetcher(data().url, { signal: new AbortController().signal })
  assert.equal(response.status, 302)
  assert.equal(response.headers.get('location'), 'https://release-assets.githubusercontent.com/file')
  assert.equal(aborted, true)
  assert.equal(followed, false)
})

test('Electron response bodies stream through the adapter and aborts stop an active body', async () => {
  const make = (stall = false) => {
    const request = new EventEmitter()
    const incoming = new Readable({ read() {} })
    incoming.statusCode = 200
    incoming.headers = { 'content-type': 'application/octet-stream' }
    request.setHeader = () => {}
    request.abort = () => { incoming.destroy(new Error('aborted')) }
    request.end = () => queueMicrotask(() => {
      request.emit('response', incoming)
      incoming.push(Buffer.from('hello'))
      if (!stall) incoming.push(null)
    })
    return request
  }
  const fetcher = createWindowsUpdateFetch(() => make())
  assert.equal(await (await fetcher(data().url, {})).text(), 'hello')
  const controller = new AbortController()
  const stalled = await createWindowsUpdateFetch(() => make(true))(data().url, { signal: controller.signal })
  controller.abort()
  await assert.rejects(stalled.text())
})

test('a valid update waits for guards, pauses safely, and never installs during ordinary cleanup', async t => {
  const root = await directory(t)
  let launches = 0
  const { bridge, events, requests } = fixture(root, { launch: async () => { launches++ } })
  t.after(() => bridge.cancel())
  await bridge.check()
  assert.equal(events.at(-1).state, 'ready')
  assert.equal(bridge.active, true)
  assert.equal(await bridge.install(async () => false), false)
  assert.equal(launches, 0)
  assert.equal(await bridge.cancel(), true)
  assert.equal(bridge.active, false)
  assert.equal(events.at(-1).state, 'cancelled')
  assert.equal(await bridge.install(async () => true), false)
  assert.deepEqual(await readdir(root), [])
  assert.equal(requests.length, 2)
  assert.equal(requests[0].options.credentials, 'omit')
  assert.equal(requests[0].options.redirect, 'manual')
})

test('same-session cache tampering prevents installation and a subsequent valid update recovers', async t => {
  const root = await directory(t)
  let launches = 0
  const { bridge, events } = fixture(root, { launch: async () => { launches++ } })
  t.after(() => bridge.cancel())
  await bridge.check()
  await writeFile(join(root, data().filename), 'tampered after ready')
  assert.equal(await bridge.install(async () => true), false)
  assert.equal(events.at(-1).state, 'error')
  assert.equal(launches, 0)
  await bridge.check()
  assert.equal(events.at(-1).state, 'ready')
  assert.equal(await bridge.install(async () => true), true)
  assert.equal(launches, 1)
  assert.equal(bridge.installing, true)
  assert.equal(await bridge.install(async () => true), false)
})

test('pre-existing valid cache avoids re-downloading, while launch failure preserves a retryable app', async t => {
  const root = await directory(t)
  await writeFile(join(root, data().filename), bytes)
  let calls = 0
  const { bridge, events, requests } = fixture(root, { launch: async () => {
    if (++calls === 1) throw new Error('Operating system refused execution')
  } })
  t.after(() => bridge.cancel())
  await bridge.check()
  assert.equal(requests.length, 1)
  assert.equal(events.at(-1).state, 'ready')
  assert.equal(await bridge.install(async () => true), false)
  assert.equal(bridge.installing, false)
  assert.equal(events.at(-1).state, 'error')
  await bridge.check()
  assert.equal(await bridge.install(async () => true), true)
  assert.equal(calls, 2)
})

test('bad signatures and signed current/older versions never download an installer', async t => {
  const root = await directory(t)
  for (const manifest of [() => Buffer.from('invalid'), () => envelope(data({ version: '4.0.0' })),
    () => envelope(data({ version: '4.0.1' }))]) {
    const { bridge, requests, events } = fixture(root, { manifest })
    await bridge.check()
    assert.equal(requests.length, 1)
    assert.equal(['current', 'error'].includes(events.at(-1).state), true)
    assert.equal(await bridge.install(async () => true), false)
    await bridge.cancel()
  }
})

test('expired ready updates cannot run', async t => {
  const root = await directory(t)
  const { bridge, events } = fixture(root)
  t.after(() => bridge.cancel())
  await bridge.check()
  const future = Date.now() + WINDOWS_READY_LIFETIME + 1000
  const clock = t.mock.method(Date, 'now', () => future)
  assert.equal(await bridge.install(async () => true), false)
  clock.mock.restore()
  assert.equal(events.at(-1).state, 'error')
})

test('interrupted payload is removed and the next check downloads successfully', async t => {
  const root = await directory(t)
  let broken = true
  const { bridge, events } = fixture(root, { download: async () => broken ? new Response('partial') : new Response(bytes) })
  t.after(() => bridge.cancel())
  await bridge.check()
  assert.equal(events.at(-1).state, 'error')
  assert.deepEqual(await readdir(root), [])
  broken = false
  await bridge.check()
  assert.equal(events.at(-1).state, 'ready')
  assert.equal((await readFile(join(root, data().filename))).length, bytes.length)
})

test('installer environment excludes service secrets, loader overrides and inherited command paths', () => {
  const environment = windowsInstallerEnvironment({ SystemRoot: 'C:\\Windows', USERPROFILE: 'C:\\Users\\Example',
    PATH: 'malicious;paths', NODE_OPTIONS: '--require=anything', MNEMION_API_KEY: 'private',
    GH_TOKEN: 'private', PSModulePath: 'untrusted', MNEMION_AUTO_UPDATE: '0', MNEMION_START_AT_LOGIN: '0' })
  assert.equal(environment.USERPROFILE, 'C:\\Users\\Example')
  assert.equal(environment.MNEMION_AUTO_UPDATE, '0')
  assert.equal(environment.MNEMION_START_AT_LOGIN, '0')
  for (const name of ['NODE_OPTIONS', 'MNEMION_API_KEY', 'GH_TOKEN', 'PSModulePath']) assert.equal(environment[name], undefined)
  assert.equal(environment.PATH.includes('malicious'), false)
})
