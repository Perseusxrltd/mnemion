import assert from 'node:assert/strict'
import { randomUUID } from 'node:crypto'
import { lstat } from 'node:fs/promises'
import { test } from 'node:test'
import { WorkspaceConnections } from '../dist/workspace-connections.js'
import { WorkspaceStore } from '../dist/workspace-store.js'
import { workspaceFixture, fixtureCredential as credential, recoveryFixture } from './workspace-fixture.mjs'

const endpoint = 'https://memory.example.com/organization'
const api = new URL(endpoint + '/v1/me')
const header = session => 'Bearer ' + session.sessionToken
const deferred = () => { let resolve; const promise = new Promise(done => { resolve = done }); return { promise, resolve } }

test('recovery directory capture uses the real native credential and offline inspection never connects', async t => {
  const f = await workspaceFixture(t), identity = { ...f.identity, administrator: true }
  const record = recoveryFixture(identity)
  let reads = 0, available = true
  const connections = new WorkspaceConnections(f.store, async () => identity, undefined, undefined, undefined, async (address, key) => {
    reads++; assert.equal(address, endpoint); assert.equal(key, credential)
    return available ? record : undefined
  })
  const session = await connections.connect(endpoint, credential, true)
  assert.equal(reads, 1)
  await connections.disconnect()
  const inspected = await connections.inspect(session.bookmarkId)
  assert.deepEqual(inspected.recovery.record, record)
  assert.ok(!JSON.stringify(inspected).includes(credential))
  assert.equal((await connections.status()).active, null)
  assert.equal(reads, 1)
  available = false
  await connections.restore(session.bookmarkId)
  assert.deepEqual((await connections.inspect(session.bookmarkId)).recovery.record, record)
})

test('recovery refresh preserves observations on outage, discards denied access and rejects late connection changes', async t => {
  const f = await workspaceFixture(t), identity = { ...f.identity, administrator: true }
  const original = recoveryFixture(identity)
  let answer = async () => original
  const connections = new WorkspaceConnections(f.store, async () => identity, undefined, undefined, undefined, () => answer())
  let session = await connections.connect(endpoint, credential, true)
  answer = async () => undefined
  await assert.rejects(connections.refreshRecovery(session.sessionToken), /last saved copy is preserved/)
  assert.deepEqual((await connections.inspect(session.bookmarkId)).recovery.record, original)
  const newer = { ...original, revision: 2 }
  answer = async () => newer
  assert.deepEqual((await connections.refreshRecovery(session.sessionToken)).recovery.record, newer)
  const entered = deferred(), gate = deferred()
  answer = async () => { entered.resolve(); return gate.promise }
  const pending = connections.refreshRecovery(session.sessionToken)
  await entered.promise
  await connections.disconnect()
  gate.resolve({ ...original, revision: 3 })
  await assert.rejects(pending, /active connection changed/)
  assert.deepEqual((await connections.inspect(session.bookmarkId)).recovery.record, newer)
  answer = async () => newer
  session = await connections.restore(session.bookmarkId)
  answer = async () => null
  await assert.rejects(connections.refreshRecovery(session.sessionToken), /no longer has access/)
  assert.equal((await connections.inspect(session.bookmarkId)).recovery, undefined)
})

test('ordinary users and session-only logins do not capture administrator recovery references', async t => {
  const f = await workspaceFixture(t)
  let identity = f.identity, reads = 0
  const connections = new WorkspaceConnections(f.store, async () => identity, undefined, undefined, undefined, async () => { reads++; return recoveryFixture(identity) })
  let session = await connections.connect(endpoint, credential, true)
  await assert.rejects(connections.refreshRecovery(session.sessionToken), /administrator connection/)
  identity = { ...identity, administrator: true }
  session = await connections.connect(endpoint, credential, false)
  await assert.rejects(connections.refreshRecovery(session.sessionToken), /remembered administrator/)
  assert.equal(reads, 0)
})

test('a remembered connection resumes after restart with a fresh renderer handle and rechecked identity', async t => {
  const f = await workspaceFixture(t)
  let checks = 0
  const verify = async (address, key) => {
    assert.equal(address, endpoint)
    assert.equal(key, credential)
    checks++
    return f.identity
  }
  const first = new WorkspaceConnections(f.store, verify)
  const connected = await first.connect(endpoint, credential, true)
  assert.equal(await first.authorization(api, header(connected)), 'Bearer ' + credential)
  assert.ok(!JSON.stringify(connected).includes(credential))
  assert.ok(!JSON.stringify(await first.status()).includes(credential))
  first.lock()
  const restarted = new WorkspaceConnections(new WorkspaceStore(f.directory, f.cipher), verify)
  const [a, b] = await Promise.all([restarted.resume(), restarted.resume()])
  assert.deepEqual(a, b)
  assert.equal(checks, 2)
  assert.notEqual(a.sessionToken, connected.sessionToken)
  assert.equal(await restarted.authorization(api, header(a)), 'Bearer ' + credential)
  await assert.rejects(() => restarted.authorization(api, header(connected)), /Reconnect/)
})

test('session handles cannot send a stored credential outside the selected API', async t => {
  const f = await workspaceFixture(t)
  const broker = new WorkspaceConnections(f.store, async () => f.identity)
  const session = await broker.connect(endpoint, credential, true)
  for (const address of [
    'https://another.example.com/organization/v1/me', 'http://memory.example.com/organization/v1/me',
    'https://memory.example.com:8443/organization/v1/me', endpoint + '/../../v1/me',
    endpoint + '/v1fake/me', endpoint + '/admin', endpoint + '/v1/me#fragment',
    'https://person@memory.example.com/organization/v1/me',
  ]) await assert.rejects(() => broker.authorization(new URL(address), header(session)), /own workspace API/)
  assert.equal(await broker.authorization(new URL(endpoint + '/health/ready'), header(session)), 'Bearer ' + credential)
  assert.equal(await broker.authorization(new URL(endpoint + '/v1/recall?limit=1'), header(session)), 'Bearer ' + credential)
  await assert.rejects(() => broker.authorization(api, header(session) + 'changed'), /Reconnect/)
})

test('disconnect invalidates the handle and prevents auto-resume even when requested concurrently', async t => {
  const f = await workspaceFixture(t)
  const broker = new WorkspaceConnections(f.store, async () => f.identity)
  const session = await broker.connect(endpoint, credential, true)
  const disconnect = broker.disconnect()
  await assert.rejects(() => broker.authorization(api, header(session)), /Reconnect/)
  assert.equal(await broker.resume(), null)
  await disconnect
  const restarted = new WorkspaceConnections(new WorkspaceStore(f.directory, f.cipher), async () => f.identity)
  assert.equal(await restarted.resume(), null)
  assert.equal((await restarted.status()).bookmarks.length, 1)
  assert.equal((await restarted.restore(session.bookmarkId)).me.tenant_id, f.identity.tenant_id)
})

test('session-only connections need no keychain and leave no new credential on disk', async t => {
  const f = await workspaceFixture(t)
  f.cipher.unlocked = false
  const broker = new WorkspaceConnections(f.store, async () => f.identity)
  const session = await broker.connect(endpoint, credential, false)
  assert.equal(session.remembered, false)
  assert.equal(await broker.authorization(api, header(session)), 'Bearer ' + credential)
  await assert.rejects(lstat(f.path), { code: 'ENOENT' })
  await assert.rejects(broker.connect(endpoint, credential, true), /password store/)
  assert.equal(await broker.authorization(api, header(session)), 'Bearer ' + credential)
})

test('switching to session-only pauses the previous remembered workspace on the next launch', async t => {
  const f = await workspaceFixture(t)
  const broker = new WorkspaceConnections(f.store, async () => f.identity)
  await broker.connect(endpoint, credential, true)
  await broker.connect('https://another.example.com', credential + '_other', false)
  broker.lock()
  assert.equal(await broker.resume(), null)
  assert.equal((await broker.status()).bookmarks.length, 1)
})

test('expired and changed-identity keys never activate a saved workspace or overwrite it', async t => {
  const f = await workspaceFixture(t)
  const original = new WorkspaceConnections(f.store, async () => f.identity)
  const session = await original.connect(endpoint, credential, true)
  original.lock()
  for (const changed of [{ ...f.identity, tenant_id: randomUUID() }, { ...f.identity, principal_id: randomUUID() }]) {
    const broker = new WorkspaceConnections(f.store, async () => changed)
    await assert.rejects(broker.resume(), /different workspace or person/)
    assert.equal((await broker.status()).active, null)
    assert.equal((await f.store.credential(session.bookmarkId)).bookmark.tenantId, f.identity.tenant_id)
  }
  const revoked = new WorkspaceConnections(f.store, async () => { throw new Error('Key revoked') })
  await assert.rejects(revoked.resume(), /Key revoked/)
  assert.equal((await revoked.status()).active, null)
})

test('a later connection wins over a slower earlier verification', async t => {
  const f = await workspaceFixture(t)
  const slow = deferred()
  const broker = new WorkspaceConnections(f.store, async address => address === endpoint ? slow.promise : f.identity)
  const earlier = broker.connect(endpoint, credential, true)
  const rejected = assert.rejects(earlier, /newer connection/)
  const newer = await broker.connect('https://another.example.com', credential + '_new', true)
  slow.resolve(f.identity)
  await rejected
  assert.equal((await broker.status()).active.sessionToken, newer.sessionToken)
  assert.equal((await broker.status()).bookmarks.length, 1)
})

test('disconnect cancels an outstanding identity check without saving it', async t => {
  const f = await workspaceFixture(t)
  const slow = deferred()
  const broker = new WorkspaceConnections(f.store, async () => slow.promise)
  const pending = broker.connect(endpoint, credential, true)
  const rejected = assert.rejects(pending, /newer connection/)
  await broker.disconnect()
  slow.resolve(f.identity)
  await rejected
  assert.equal((await broker.status()).active, null)
  assert.deepEqual(await f.store.list(), [])
})

test('forgetting removes only the selected device bookmark and invalidates its handle', async t => {
  const f = await workspaceFixture(t)
  const broker = new WorkspaceConnections(f.store, async () => f.identity)
  const first = await broker.connect('https://another.example.com', credential, true)
  const second = await broker.connect(endpoint, credential, true)
  await broker.forget(first.bookmarkId)
  assert.equal(await broker.authorization(api, header(second)), 'Bearer ' + credential)
  await broker.forget(second.bookmarkId)
  await assert.rejects(() => broker.authorization(api, header(second)), /Reconnect/)
  assert.equal(await broker.resume(), null)
  assert.deepEqual((await broker.status()).bookmarks, [])
})

test('malformed identities are rejected even for a session-only connection', async t => {
  const f = await workspaceFixture(t)
  for (const bad of [null, {}, { ...f.identity, administrator: 'true' }, { ...f.identity, tenant_id: 'bad' }, { ...f.identity, name: 'x'.repeat(257) }]) {
    const broker = new WorkspaceConnections(f.store, async () => bad)
    await assert.rejects(broker.connect(endpoint, credential, false), /workspace identity/)
    assert.equal((await broker.status()).active, null)
  }
})

test('a service cannot put its echoed key into plaintext identity metadata', async t => {
  const f = await workspaceFixture(t)
  const identity = { ...f.identity, name: credential }
  const broker = new WorkspaceConnections(f.store, async () => identity)
  await assert.rejects(broker.connect(endpoint, credential, false), /invalid identity/)
  await assert.rejects(f.store.save(endpoint, credential, identity), /credential or identity/)
  await assert.rejects(lstat(f.path), { code: 'ENOENT' })
})

test('offline recovery inspection never contacts the server, resumes a session, or grants cached admin access', async t => {
  const f = await workspaceFixture(t)
  const original = new WorkspaceConnections(f.store, async () => ({ ...f.identity, administrator: true }))
  const session = await original.connect(endpoint, credential, true)
  await original.disconnect()
  let checks = 0
  const offline = new WorkspaceConnections(new WorkspaceStore(f.directory, f.cipher), async () => {
    checks++
    throw new Error('The old host is offline')
  })
  const result = await offline.inspect(session.bookmarkId)
  assert.equal(result.access.identity.administrator, true)
  assert.equal(checks, 0)
  assert.equal((await offline.status()).activeId, null)
  assert.equal((await offline.status()).active, null)
  await assert.rejects(() => offline.authorization(api, header(session)), /Reconnect/)
  await assert.rejects(offline.restore(session.bookmarkId), /offline/)
  assert.equal(checks, 1)
  assert.equal((await offline.status()).active, null)
  assert.equal((await offline.inspect(session.bookmarkId)).access.identity.administrator, true)
  assert.equal(checks, 1)
})

test('inspection cannot revive a forgotten connection or interrupt another active workspace', async t => {
  const f = await workspaceFixture(t)
  const broker = new WorkspaceConnections(f.store, async () => f.identity)
  const first = await broker.connect(endpoint, credential, true)
  const next = await broker.connect('https://another.example.com', credential + '_new', true)
  await broker.inspect(first.bookmarkId)
  assert.equal((await broker.status()).active.sessionToken, next.sessionToken)
  assert.equal((await broker.status()).activeId, next.bookmarkId)
  await broker.forget(first.bookmarkId)
  await assert.rejects(broker.inspect(first.bookmarkId), /no longer available/)
  assert.equal((await broker.status()).active.sessionToken, next.sessionToken)
})
