import assert from 'node:assert/strict'
import { randomBytes, randomUUID } from 'node:crypto'
import { readFile } from 'node:fs/promises'
import { test } from 'node:test'
import { WorkspaceConnections } from '../dist/workspace-connections.js'
import { WorkspacePasswordAuth } from '../dist/workspace-auth.js'
import { WorkspaceStore } from '../dist/workspace-store.js'
import { DesktopWorkspaceActions } from '../dist/desktop-workspace-actions.js'
import { desktopAction } from '../dist/desktop-actions.js'
import { workspaceFixture, fixtureCredential as credential } from './workspace-fixture.mjs'

const endpoint = 'https://memory.example.test'
const signal = () => new AbortController().signal
const secret = prefix => prefix + randomBytes(32).toString('base64url')

async function setup(t, options = {}) {
  const f = await workspaceFixture(t)
  const observed = { local: true, changes: 0, prepares: 0, requests: 0, offline: false, openCalls: 0 }
  const verify = async (address, value) => {
    observed.requests++
    if (observed.offline) throw new Error('Workspace offline')
    assert.equal(address, endpoint)
    assert.equal(value, options.tokens?.access_token ?? credential)
    return f.identity
  }
  const connections = new WorkspaceConnections(f.store, verify, options.auth)
  const settings = {
    connections, localSelected: () => observed.local,
    deselectLocal: () => { observed.local = false },
    openLocal: async () => {
      observed.openCalls++
      const session = await connections.connect(endpoint, credential, false)
      observed.local = true
      return session
    },
    beforeChange: async () => { observed.prepares++; await options.prepare?.(connections) },
    changed: () => { observed.changes++ },
  }
  const actions = new DesktopWorkspaceActions(settings)
  const call = (action, input = {}, cancellation = signal()) => {
    desktopAction(action, input)
    return actions.execute(action, input, cancellation)
  }
  const connectInput = async extra => ({ endpoint, credential, remember: true,
    expected_revision: (await actions.status()).revision,
    expected_tenant_id: f.identity.tenant_id, expected_principal_id: f.identity.principal_id, ...extra })
  return { ...f, connections, actions, call, observed, settings, verify, connectInput }
}

test('credential verification is read-only and a different intended person never replaces a connection', async t => {
  const f = await setup(t)
  const before = await f.actions.status()
  assert.deepEqual(await f.call('workspace.verify', { endpoint, credential }), { endpoint, me: f.identity })
  assert.deepEqual(await f.actions.status(), before)
  for (const field of ['expected_tenant_id', 'expected_principal_id']) {
    await assert.rejects(f.call('workspace.connect', await f.connectInput({ [field]: randomUUID() })), /different workspace or person/)
    assert.deepEqual(await f.actions.status(), before)
  }
  assert.equal(f.observed.local, true)
  assert.equal(f.observed.changes, 0)
  await assert.rejects(readFile(f.path), { code: 'ENOENT' })
})

test('a remembered connection survives a new manager without exposing secrets or native handles', async t => {
  const f = await setup(t)
  const old = await f.actions.status()
  const connected = await f.call('workspace.connect', await f.connectInput())
  assert.equal(connected.active.me.principal_id, f.identity.principal_id)
  assert.equal(connected.local_selected, false)
  assert.notEqual(connected.revision, old.revision)
  assert.equal(f.observed.changes, 1)
  const native = (await f.connections.status()).active
  for (const value of [credential, native.sessionToken]) {
    assert.ok(!JSON.stringify(connected).includes(value))
    assert.ok(!(await readFile(f.path, 'utf8')).includes(value))
  }
  await assert.rejects(f.call('workspace.disconnect', { expected_revision: old.revision }), /connection changed/)
  f.connections.lock()
  const restarted = new WorkspaceConnections(new WorkspaceStore(f.directory, f.cipher), f.verify)
  const actions = new DesktopWorkspaceActions({ ...f.settings, connections: restarted })
  const reopened = await actions.execute('workspace.restore', {
    expected_revision: (await actions.status()).revision, id: native.bookmarkId,
  }, signal())
  assert.equal(reopened.active.bookmarkId, native.bookmarkId)
  assert.equal(reopened.active.me.principal_id, f.identity.principal_id)
  assert.ok(!JSON.stringify(reopened).includes('mnm_session_'))
  assert.notEqual((await restarted.status()).active.sessionToken, native.sessionToken)
})

test('offline inspection preserves the saved record and failed reconnect does not switch local selection', async t => {
  const f = await setup(t)
  const saved = await f.call('workspace.connect', await f.connectInput())
  await f.call('workspace.disconnect', { expected_revision: saved.revision })
  f.observed.offline = true
  f.observed.local = true
  const before = await f.actions.status(), requests = f.observed.requests
  const inspected = await f.call('workspace.inspect', { id: saved.active.bookmarkId })
  assert.equal(inspected.access.identity.principal_id, f.identity.principal_id)
  assert.equal(f.observed.requests, requests)
  await assert.rejects(f.call('workspace.restore', { id: saved.active.bookmarkId, expected_revision: before.revision }), /offline/)
  assert.deepEqual(await f.actions.status(), before)
})

test('unsaved work and changes during review prevent the requested mutation', async t => {
  let refuse = true, drift = false
  const f = await setup(t, { prepare: async connections => {
    if (refuse) throw new Error('Save or discard edits first')
    if (drift) await connections.connect(endpoint, credential, false)
  } })
  await assert.rejects(f.call('workspace.connect', await f.connectInput()), /Save or discard/)
  assert.equal(f.observed.requests, 0)
  assert.equal((await f.actions.status()).active, null)
  refuse = false; drift = true
  await assert.rejects(f.call('workspace.connect', await f.connectInput()), /changed during review/)
  assert.equal(f.observed.requests, 1)
  assert.equal((await f.actions.status()).active.remembered, false)
  assert.equal(f.observed.changes, 1, 'The app must refresh even when a competing change caused refusal')
  assert.equal(f.observed.local, true)
})

test('unavailable OS protection refuses remembering without losing the active or local connection', async t => {
  const f = await setup(t)
  await f.call('workspace.connect', await f.connectInput({ remember: false }))
  f.observed.local = true
  const before = await f.actions.status()
  f.cipher.unlocked = false
  await assert.rejects(f.call('workspace.connect', await f.connectInput()), /password store/)
  const after = await f.actions.status()
  assert.deepEqual(after.active, before.active)
  assert.equal(after.local_selected, true)
  assert.equal(after.bookmarks.length, 0)
  await assert.rejects(readFile(f.path), { code: 'ENOENT' })
})

test('password login retains refresh protection and a failed remote logout still clears local access', async t => {
  const f = await workspaceFixture(t)
  const tokens = { session_id: randomUUID(), tenant_id: f.identity.tenant_id, principal_id: f.identity.principal_id,
    access_token: secret('mnm_s_'), refresh_token: secret('mnm_r_'), csrf_token: null, persistence: 'native',
    access_expires_at: new Date(Date.now() + 900_000).toISOString(), expires_at: new Date(Date.now() + 86400_000).toISOString() }
  let local = true, changed = 0, logout = 0
  const auth = new WorkspacePasswordAuth(async (address, operation, input) => {
    assert.equal(address, endpoint)
    if (operation === 'logout') { logout++; throw new Error('Workspace offline') }
    assert.equal(operation, 'login'); assert.equal(input.transport, 'native')
    return tokens
  })
  const connections = new WorkspaceConnections(f.store, async (_endpoint, token) => {
    assert.equal(token, tokens.access_token); return f.identity
  }, auth)
  const actions = new DesktopWorkspaceActions({ connections, localSelected: () => local,
    deselectLocal: () => { local = false }, openLocal: async () => { throw new Error('unused') },
    beforeChange: async () => {}, changed: () => { changed++ } })
  const credentials = { workspace_id: f.identity.tenant_id, username: 'person',
    password: 'harbour comet mitten glacier tapestry', device_name: 'Local agent setup' }
  const signed = await actions.execute('workspace.sign-in', { endpoint, credentials, remember: true,
    expected_revision: (await actions.status()).revision }, signal())
  assert.equal(signed.active.authentication, 'password')
  for (const value of [credentials.password, tokens.access_token, tokens.refresh_token]) {
    assert.ok(!JSON.stringify(signed).includes(value))
    assert.ok(!(await readFile(f.path, 'utf8')).includes(value))
  }
  assert.equal((await f.store.credential(signed.active.bookmarkId)).credential, tokens.refresh_token)
  await assert.rejects(actions.execute('workspace.disconnect', { expected_revision: signed.revision }, signal()), /Signed out on this device/)
  const after = await actions.status()
  assert.equal(after.active, null); assert.equal(after.bookmarks.length, 0)
  assert.equal(local, false); assert.equal(logout, 1); assert.equal(changed, 2)
})

test('forgetting an inactive bookmark keeps the current connection and local open is observation-bound', async t => {
  const f = await setup(t)
  const saved = await f.call('workspace.connect', await f.connectInput())
  const prior = await f.actions.status()
  const local = await f.call('local.open', { expected_revision: prior.revision })
  assert.equal(local.local_selected, true)
  assert.equal(local.active.remembered, false)
  const forget = await f.call('workspace.forget', { expected_revision: local.revision, id: saved.active.bookmarkId })
  assert.equal(forget.local_selected, true)
  assert.deepEqual(forget.active, local.active)
  assert.equal(forget.bookmarks.length, 0)
  await assert.rejects(f.call('local.open', { expected_revision: prior.revision }), /connection changed/)
  assert.equal(f.observed.openCalls, 1)
  const controller = new AbortController(); controller.abort()
  await assert.rejects(f.call('workspace.disconnect', { expected_revision: forget.revision }, controller.signal), /abort/i)
  assert.deepEqual((await f.actions.status()).active, local.active)
})
