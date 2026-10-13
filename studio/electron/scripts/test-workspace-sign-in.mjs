import assert from 'node:assert/strict'
import { randomBytes, randomUUID } from 'node:crypto'
import { readFile } from 'node:fs/promises'
import { test } from 'node:test'
import { WorkspacePasswordAuth } from '../dist/workspace-auth.js'
import { WorkspaceConnections } from '../dist/workspace-connections.js'
import { WorkspaceStore } from '../dist/workspace-store.js'
import { workspaceFixture } from './workspace-fixture.mjs'

const endpoint = 'https://memory.example.test'
const api = new URL(endpoint + '/v1/me')
const secret = prefix => prefix + randomBytes(32).toString('base64url')
const deferred = () => { let resolve; const promise = new Promise(done => { resolve = done }); return { promise, resolve } }

async function setup(t) {
  const fixture = await workspaceFixture(t)
  const id = randomUUID()
  const expires = new Date(Date.now() + 30 * 86400_000).toISOString()
  const server = { current: null, spent: new Set(), refreshes: 0, signouts: 0, revoked: false, loseResponse: false, responseOverride: null, gate: null }
  function issue(seconds) {
    return { session_id: id, tenant_id: fixture.identity.tenant_id, principal_id: fixture.identity.principal_id,
      access_token: secret('mnm_s_'), refresh_token: secret('mnm_r_'), csrf_token: null,
      access_expires_at: new Date(Date.now() + seconds * 1000).toISOString(), expires_at: expires, persistence: 'native' }
  }
  const request = async (address, operation, input) => {
    assert.equal(address, endpoint)
    if (operation === 'login') {
      assert.equal(input.transport, 'native')
      server.current = issue(30)
      return server.current
    }
    if (operation === 'logout') {
      server.signouts++
      assert.equal(input.session_id, id)
      if (input.refresh_token === server.current?.refresh_token || server.spent.has(input.refresh_token)) server.revoked = true
      return { signed_out: true }
    }
    assert.equal(operation, 'refresh')
    server.refreshes++
    assert.equal(input.workspace_id, fixture.identity.tenant_id)
    assert.equal(input.session_id, id)
    assert.equal(input.refresh_token, server.current.refresh_token, 'The native client must not replay a consumed refresh')
    if (server.revoked) throw new Error('Sign in again')
    if (server.gate) { server.gate.started.resolve(); await server.gate.finished.promise }
    server.spent.add(server.current.refresh_token)
    server.current = issue(900)
    if (server.loseResponse) throw new Error('The server response was lost')
    return server.responseOverride ? { ...server.current, ...server.responseOverride } : server.current
  }
  const auth = new WorkspacePasswordAuth(request)
  const verify = async (address, credential) => {
    assert.equal(address, endpoint)
    if (server.revoked || credential !== server.current.access_token) throw new Error('Session revoked')
    return fixture.identity
  }
  const broker = new WorkspaceConnections(fixture.store, verify, auth)
  const input = { workspace_id: fixture.identity.tenant_id, username: 'person',
    password: 'harbour comet mitten glacier tapestry', device_name: 'Test device' }
  const open = remember => broker.signIn(endpoint, input, remember)
  return { ...fixture, server, auth, verify, broker, input, open }
}

test('native password sign-in keeps both credentials out of the renderer and plaintext state', async t => {
  const f = await setup(t)
  const session = await f.open(true)
  const visible = JSON.stringify([session, await f.broker.status(), await f.broker.inspect(session.bookmarkId)])
  const stored = await readFile(f.path, 'utf8')
  for (const value of [f.input.password, f.server.current.access_token, f.server.current.refresh_token]) {
    assert.ok(!visible.includes(value))
    assert.ok(!stored.includes(value))
  }
  assert.equal(session.authentication, 'password')
  const privateCredential = await f.store.credential(session.bookmarkId)
  assert.equal(privateCredential.credential, f.server.current.refresh_token)
  assert.equal(privateCredential.session.refreshPending, false)
})

test('concurrent API requests rotate once and keep the renderer handle; restart refreshes the saved account', async t => {
  const f = await setup(t)
  const session = await f.open(true)
  const header = 'Bearer ' + session.sessionToken
  const old = f.server.current.refresh_token
  const values = await Promise.all(Array.from({ length: 20 }, () => f.broker.authorization(api, header)))
  assert.equal(f.server.refreshes, 1)
  assert.ok(values.every(value => value === 'Bearer ' + f.server.current.access_token))
  assert.equal((await f.broker.status()).active.sessionToken, session.sessionToken)
  const saved = await f.store.credential(session.bookmarkId)
  assert.notEqual(saved.credential, old)
  assert.equal(saved.credential, f.server.current.refresh_token)
  assert.equal(saved.session.refreshPending, false)
  f.broker.lock()
  const reopened = new WorkspaceConnections(new WorkspaceStore(f.directory, f.cipher), f.verify, f.auth)
  const [a, b] = await Promise.all([reopened.resume(), reopened.resume()])
  assert.deepEqual(a, b)
  assert.equal(f.server.refreshes, 2)
  assert.notEqual(a.sessionToken, session.sessionToken)
  assert.equal(a.me.principal_id, f.identity.principal_id)
  await assert.rejects(reopened.authorization(api, header), /Reconnect/)
})

test('a lost refresh response cannot be replayed by the running app or a restarted process', async t => {
  const f = await setup(t)
  const session = await f.open(true)
  f.server.loseResponse = true
  await assert.rejects(f.broker.authorization(api, 'Bearer ' + session.sessionToken), /response was lost/)
  assert.equal((await f.broker.status()).active, null)
  assert.equal((await f.store.credential(session.bookmarkId)).session.refreshPending, true)
  const reopened = new WorkspaceConnections(new WorkspaceStore(f.directory, f.cipher), f.verify, f.auth)
  await assert.rejects(reopened.resume(), /interrupted/)
  assert.equal(f.server.refreshes, 1)
})

test('a managed host must be ready before a saved refresh token is consumed', async t => {
  const f = await setup(t)
  const session = await f.open(true)
  f.broker.lock()
  const ready = deferred()
  const entered = deferred()
  const reopened = new WorkspaceConnections(f.store, f.verify, f.auth, async bookmark => {
    assert.equal(bookmark.tenantId, f.identity.tenant_id)
    entered.resolve(); await ready.promise
  })
  const resumed = reopened.resume()
  await entered.promise
  assert.equal(f.server.refreshes, 0)
  assert.equal((await f.store.credential(session.bookmarkId)).session.refreshPending, false)
  ready.resolve()
  assert.equal((await resumed).me.principal_id, f.identity.principal_id)
  assert.equal(f.server.refreshes, 1)
})

test('failed host startup leaves the saved credential available for a later resume', async t => {
  const f = await setup(t)
  const session = await f.open(true)
  f.broker.lock()
  const reopened = new WorkspaceConnections(f.store, f.verify, f.auth, async () => { throw new Error('Local workspace is paused') })
  await assert.rejects(reopened.resume(), /paused/)
  assert.equal(f.server.refreshes, 0)
  assert.equal((await f.store.credential(session.bookmarkId)).session.refreshPending, false)
  const afterRecovery = new WorkspaceConnections(f.store, f.verify, f.auth)
  assert.equal((await afterRecovery.resume()).me.principal_id, f.identity.principal_id)
})

test('refresh persistence failure clears the live connection and revokes the newly issued session', async t => {
  const f = await setup(t)
  const session = await f.open(true)
  const encrypt = f.cipher.encrypt.bind(f.cipher)
  let writes = 0
  f.cipher.encrypt = value => {
    if (++writes === 2) throw new Error('Protected store write failed')
    return encrypt(value)
  }
  await assert.rejects(f.broker.authorization(api, 'Bearer ' + session.sessionToken), /write failed/)
  assert.equal(f.server.refreshes, 1)
  assert.equal(f.server.signouts, 1)
  assert.equal(f.server.revoked, true)
  assert.equal((await f.broker.status()).active, null)
  assert.equal((await f.store.credential(session.bookmarkId)).session.refreshPending, true)
})

test('locked storage prevents sending the refresh credential and allows later recovery after unlock', async t => {
  const f = await setup(t)
  const session = await f.open(true)
  f.cipher.unlocked = false
  await assert.rejects(f.broker.authorization(api, 'Bearer ' + session.sessionToken), /Unlock/)
  assert.equal(f.server.refreshes, 0)
  f.cipher.unlocked = true
  assert.equal((await f.store.credential(session.bookmarkId)).session.refreshPending, false)
  const reopened = new WorkspaceConnections(new WorkspaceStore(f.directory, f.cipher), f.verify, f.auth)
  assert.equal((await reopened.resume()).me.principal_id, f.identity.principal_id)
})

test('an outside URL cannot trigger refresh or receive a saved credential', async t => {
  const f = await setup(t)
  const session = await f.open(true)
  await assert.rejects(f.broker.authorization(new URL('https://other.example.test/v1/me'), 'Bearer ' + session.sessionToken), /own workspace/)
  assert.equal(f.server.refreshes, 0)
})

test('a changed identity or absolute deadline is never persisted after refresh', async t => {
  for (const responseOverride of [{ principal_id: randomUUID() }, { session_id: randomUUID() },
    { expires_at: new Date(Date.now() + 25 * 86400_000).toISOString() }]) {
    const f = await setup(t)
    const session = await f.open(true)
    f.server.responseOverride = responseOverride
    await assert.rejects(f.broker.authorization(api, 'Bearer ' + session.sessionToken), /saved account/)
    assert.equal((await f.broker.status()).active, null)
    assert.equal((await f.store.credential(session.bookmarkId)).session.refreshPending, true)
  }
})

test('disconnect during refresh cannot reconnect or persist the late reply', async t => {
  const f = await setup(t)
  const session = await f.open(true)
  const gate = { started: deferred(), finished: deferred() }
  f.server.gate = gate
  const request = f.broker.authorization(api, 'Bearer ' + session.sessionToken)
  const denied = assert.rejects(request)
  await gate.started.promise
  await f.broker.disconnect()
  gate.finished.resolve()
  await denied
  assert.equal((await f.broker.status()).active, null)
  assert.equal((await f.broker.status()).activeId, null)
  assert.equal((await f.broker.status()).bookmarks.length, 0)
  assert.equal(f.server.revoked, true)
})

test('temporary logins use no protected store and sign out without keeping a refresh credential', async t => {
  const f = await setup(t)
  f.cipher.unlocked = false
  const session = await f.open(false)
  await f.broker.authorization(api, 'Bearer ' + session.sessionToken)
  assert.equal(f.server.refreshes, 1)
  assert.deepEqual(await f.store.list(), [])
  await f.broker.disconnect()
  assert.equal(f.server.revoked, true)
  assert.equal(await f.broker.resume(), null)
})
