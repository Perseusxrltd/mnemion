import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { WindowsTelemetryPrivateProbe, privateStoreBindingPath, privateStoreQuery } from '../dist/telemetry-private-store.js'

function deferred() {
  let resolve
  const promise = new Promise(finish => { resolve = finish })
  return { promise, resolve }
}

test('successive reads use the current paths and do not reuse an earlier grant', async () => {
  const seen = []
  const probe = new WindowsTelemetryPrivateProbe((root, database) => {
    seen.push([root, database])
    return seen.length === 1 ? 1 : 0
  })
  assert.equal(await probe.read('root-a', 'file-a'), true)
  assert.equal(await probe.read('root-b', 'file-b'), false)
  assert.deepEqual(seen, [['root-a', 'file-a'], ['root-b', 'file-b']])
})

test('only the integer 1 grants, so a native refusal cannot be coerced into admission', async () => {
  const values = [0, 2, true, '1', null, undefined, { accepted: 1 }, Promise.resolve(true), Promise.resolve('1')]
  let index = 0
  const probe = new WindowsTelemetryPrivateProbe(() => values[index++])
  for (let count = 0; count < values.length; count++) assert.equal(await probe.read('root', 'database'), false)
  assert.equal(index, values.length)
  assert.equal(await new WindowsTelemetryPrivateProbe(() => Promise.resolve(1)).read('root', 'database'), true)
})

test('a missing or malformed native export refuses and does not stick the slot', async () => {
  const bindings = [null, undefined, false, 1, {}, { readPrivateStore: 1 }, { readState() { return 1 } }, { readPrivateStore: 'readPrivateStore' }]
  for (const binding of bindings) {
    const probe = new WindowsTelemetryPrivateProbe(privateStoreQuery(binding))
    assert.equal(await probe.read('root', 'database'), false)
    assert.equal(await probe.read('other-root', 'other-database'), false)
  }
})

test('a busy check, a timeout, and a late success cannot grant or release a successor', async t => {
  const pending = []
  const probe = new WindowsTelemetryPrivateProbe((root, database) => {
    assert.deepEqual([root, database], ['root', 'database'])
    const item = deferred()
    pending.push(item)
    return item.promise
  })
  const awake = setTimeout(() => {}, 3000)
  t.after(() => clearTimeout(awake))
  const first = probe.read('root', 'database')
  assert.equal(await probe.read('other-root', 'other-database'), false)
  for (let index = 0; index < 32; index++) assert.equal(await probe.read('root', 'database'), false)
  assert.equal(pending.length, 1)
  assert.equal(await first, false)
  assert.equal(await probe.read('root', 'database'), false)
  assert.equal(pending.length, 1)
  pending[0].resolve(1)
  await pending[0].promise
  assert.equal(await first, false, 'a late success cannot grant the timed-out check')
  const second = probe.read('root', 'database')
  assert.equal(pending.length, 2)
  pending[1].resolve(0)
  assert.equal(await second, false)
  const third = probe.read('root', 'database')
  pending[2].resolve(1)
  assert.equal(await third, true)
})

test('a rejected or thrown native call refuses without retaining the slot', async () => {
  let calls = 0
  const rejected = new WindowsTelemetryPrivateProbe(() => { calls++; return Promise.reject(new Error('native')) })
  assert.equal(await rejected.read('root', 'database'), false)
  assert.equal(await rejected.read('root', 'database'), false)
  const thrown = new WindowsTelemetryPrivateProbe(() => { calls++; throw new Error('unavailable') })
  assert.equal(await thrown.read('root', 'database'), false)
  assert.equal(await thrown.read('root', 'database'), false)
  assert.equal(calls, 4)
})

test('the shared Windows routine is the only owner, reparse, hardlink and size check', () => {
  const shared = readFileSync(new URL('../../../mnemion/product_telemetry/native/private-store.c', import.meta.url), 'utf8')
  const bridge = readFileSync(new URL('../../../mnemion/product_telemetry/native/network-node.c', import.meta.url), 'utf8')
  const entry = readFileSync(new URL('../native/telemetry-private-store.c', import.meta.url), 'utf8')
  const wrapper = readFileSync(new URL('../telemetry-private-store.ts', import.meta.url), 'utf8')
  const networkBuild = readFileSync(new URL('../../../deploy/build_telemetry_network.ps1', import.meta.url), 'utf8')
  const helperBuild = readFileSync(new URL('./build-telemetry-private-store.ps1', import.meta.url), 'utf8')
  assert.match(shared, /int mnemion_private_store_accessible/)
  for (const token of [
    'FILE_ATTRIBUTE_REPARSE_POINT',
    'nNumberOfLinks != 1',
    'EqualSid(owner, user)',
    'GetSecurityInfo',
    'nFileSizeLow > 98304',
    'ACCESS_ALLOWED_ACE_TYPE',
  ]) assert.equal(shared.split(token).length - 1, 1, token)
  assert.equal(bridge.includes('FILE_ATTRIBUTE_REPARSE_POINT'), false)
  assert.equal(entry.includes('FILE_ATTRIBUTE_REPARSE_POINT'), false)
  assert.match(bridge, /mnemion_private_store_accessible\(item->root, item->database\)/)
  assert.match(bridge, /InterlockedCompareExchange\(&private_busy, 1, 0\)/)
  assert.match(entry, /mnemion_private_store_accessible\(argv\[1\], argv\[2\]\)/)
  assert.equal(wrapper.includes('spawn('), false)
  assert.match(networkBuild, /private-store\.c/)
  assert.match(helperBuild, /private-store\.c/)
  assert.match(networkBuild, /\$Architecture/)
  assert.match(networkBuild, /'x64', 'arm64'/)
  assert.match(helperBuild, /\$Architecture/)
  assert.match(helperBuild, /'x64', 'arm64'/)
})

test('the in-process addon is loaded from outside the ASAR archive', () => {
  const base = process.platform === 'win32' ? 'file:///C:/Mnemion/resources/' : 'file:///tmp/Mnemion/resources/'
  const addon = privateStoreBindingPath(base + 'app.asar/dist/telemetry-private-store.js')
  assert.ok(addon.replaceAll('\\', '/').endsWith('/app.asar.unpacked/dist/telemetry-network.node'))
})
