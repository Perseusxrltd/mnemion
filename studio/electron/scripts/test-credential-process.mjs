import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { once } from 'node:events'
import { mkdtemp, readFile, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { randomUUID } from 'node:crypto'
import { fileURLToPath } from 'node:url'
import { test } from 'node:test'
import { CredentialProcess } from '../dist/credential-process.js'
import { boundedCredentialCipher } from '../dist/workspace-cipher.js'
import { WorkspaceStore } from '../dist/workspace-store.js'
import { workspaceFixture, fixtureCredential } from './workspace-fixture.mjs'

const fixture = fileURLToPath(new URL('./credential-process-fixture.mjs', import.meta.url))
function transport(t, mode = 'normal') {
  const children = []
  const storage = new CredentialProcess(() => {
    const child = spawn(process.execPath, [fixture, typeof mode === 'function' ? mode(children.length) : mode], { stdio: ['pipe', 'pipe', 'pipe'] })
    children.push(child)
    return child
  })
  t.after(() => storage.close())
  return { storage, children }
}

test('one private helper round-trips multiple requests and is reaped on final close', { timeout: 5000 }, async t => {
  const { storage, children } = transport(t)
  assert.equal(storage.memoryBytes, 0)
  assert.equal(await storage.available(), true)
  const secret = 'synthetic-secret-☄'
  const sealed = await storage.encrypt(secret)
  assert.equal(await storage.decrypt(sealed), secret)
  assert.equal(children.length, 1)
  assert.ok(storage.memoryBytes >= 96 * 1024 * 1024)
  const exited = once(children[0], 'close')
  storage.close()
  assert.deepEqual(await exited, [null, 'SIGKILL'])
  assert.equal(storage.memoryBytes, 0)
  await assert.rejects(storage.available(), /secure store/)
  assert.equal(children.length, 1)
})

test('sealing and opening multiple saved connections reuses one helper', { timeout: 5000 }, async t => {
  const { storage, children } = transport(t)
  const root = await mkdtemp(join(tmpdir(), 'mnemion-keychain-connections-'))
  t.after(() => rm(root, { recursive: true, force: true }))
  const store = new WorkspaceStore(join(root, 'workspaces'), boundedCredentialCipher(storage))
  const identity = { principal_id: randomUUID(), tenant_id: randomUUID(), name: 'Test user', tenant_name: 'Test team', administrator: false }
  const first = await store.save('https://memory.example.com', fixtureCredential, identity)
  const secondIdentity = { ...identity, principal_id: randomUUID(), name: 'Second user' }
  const second = await store.save('https://other.example.com', fixtureCredential, secondIdentity)
  assert.equal((await store.credential(first.id)).credential, fixtureCredential)
  assert.equal((await store.credential(second.id)).credential, fixtureCredential)
  assert.equal(children.length, 1)
})

test('unanswered native consent cannot pin shutdown or accumulate helper processes', { timeout: 5000 }, async t => {
  const { storage, children } = transport(t, 'hang')
  const cipher = boundedCredentialCipher(storage, { checkTimeoutMs: 100, operationTimeoutMs: 100 })
  assert.deepEqual(await Promise.all([cipher.available(), cipher.available()]), [false, false])
  assert.equal(await cipher.available(), false)
  assert.equal(children.length, 1)
  const exited = once(children[0], 'close')
  const start = Date.now()
  storage.close()
  assert.deepEqual(await exited, [null, 'SIGKILL'])
  assert.ok(Date.now() - start < 1500)
})

test('transport refuses concurrent plaintext operations while a request waits', { timeout: 5000 }, async t => {
  const { storage, children } = transport(t, 'slow')
  await storage.available()
  const first = storage.encrypt('first synthetic secret')
  await assert.rejects(storage.encrypt('second synthetic secret'), /secure store/)
  assert.equal(await storage.decrypt(await first), 'first synthetic secret')
  assert.equal(children.length, 1)
})

for (const mode of ['malformed', 'oversized', 'exit', 'wrong-id']) {
  test(`${mode} helper response fails closed and a later attempt uses a fresh process`, { timeout: 5000 }, async t => {
    const { storage, children } = transport(t, count => count === 0 ? mode : 'normal')
    await assert.rejects(storage.available(), /secure store/)
    assert.equal(await storage.available(), true)
    assert.equal(children.length, 2)
    assert.ok(children[0].exitCode !== null || children[0].signalCode !== null)
  })
}

test('OS denial and provider errors never return a plaintext fallback or raw error', { timeout: 5000 }, async t => {
  const denied = transport(t, 'denied').storage
  const locked = boundedCredentialCipher(denied)
  assert.equal(await locked.available(), false)
  await assert.rejects(locked.encrypt('synthetic secret'), /secure store/)
  const failed = transport(t, 'error').storage
  await assert.rejects(failed.encrypt('synthetic-private-provider-error'), error =>
    error.message.includes('secure store') && !error.message.includes('synthetic-private'))
})

test('a denied provider is discarded so retry can see a newly unlocked OS', { timeout: 5000 }, async t => {
  const { storage, children } = transport(t, count => count === 0 ? 'denied' : 'normal')
  assert.equal(await storage.available(), false)
  assert.equal(storage.memoryBytes, 0)
  assert.equal(await storage.available(), true)
  assert.equal(children.length, 2)
})

test('bounded pipe backpressure still allows a valid large protected payload', { timeout: 5000 }, async t => {
  const { storage } = transport(t)
  const secret = 'x'.repeat(15000)
  assert.equal(await storage.decrypt(await storage.encrypt(secret)), secret)
  await assert.rejects(storage.encrypt('x'.repeat(16385)), /secure store/)
})

test('late helper encryption cannot change a saved workspace after its timeout', { timeout: 5000 }, async t => {
  const f = await workspaceFixture(t)
  await f.store.save('https://memory.example.com', fixtureCredential, f.identity)
  const before = await readFile(f.path)
  const { storage } = transport(t, 'slow')
  const store = new WorkspaceStore(f.directory, boundedCredentialCipher(storage, { checkTimeoutMs: 1500, operationTimeoutMs: 20 }))
  await assert.rejects(store.save('https://another.example.com', fixtureCredential, f.identity), /secure store/)
  await new Promise(resolve => setTimeout(resolve, 150))
  assert.deepEqual(await readFile(f.path), before)
})

test('helper terminates on a lost parent pipe and rejects unexpected operations', { timeout: 5000 }, async () => {
  for (const request of [null, '{"id":1,"operation":"shell","value":"unused"}\n', 'x'.repeat(32769)]) {
    const child = spawn(process.execPath, [fixture, 'normal'], { stdio: ['pipe', 'pipe', 'pipe'] })
    child.stdout.resume(); child.stderr.resume()
    const exited = once(child, 'close')
    if (request === null) child.stdin.end()
    else child.stdin.write(request)
    assert.deepEqual(await exited, [3, null])
  }
})
