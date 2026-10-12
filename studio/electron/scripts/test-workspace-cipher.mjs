import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { test } from 'node:test'
import { boundedCredentialCipher } from '../dist/workspace-cipher.js'
import { WorkspaceStore } from '../dist/workspace-store.js'
import { workspaceFixture, fixtureCredential as credential } from './workspace-fixture.mjs'

function deferred() {
  let resolve
  const promise = new Promise(done => { resolve = done })
  return { promise, resolve }
}

test('OS consent waits are bounded and share one outstanding availability request', async () => {
  const consent = deferred()
  let calls = 0, cryptoCalls = 0
  const cipher = boundedCredentialCipher({
    available: () => { calls++; return consent.promise },
    encrypt: async () => { cryptoCalls++; return Buffer.from('opaque') },
    decrypt: async () => { cryptoCalls++; return 'value' },
  }, { checkTimeoutMs: 20, operationTimeoutMs: 20 })
  assert.deepEqual(await Promise.all([cipher.available(), cipher.available(), cipher.available()]), [false, false, false])
  await assert.rejects(cipher.encrypt('synthetic secret'), /secure store/)
  assert.equal(calls, 1)
  assert.equal(cryptoCalls, 0)
  consent.resolve(true)
  assert.equal(await cipher.available(), true)
})

test('denied asynchronous availability never permits a credential write or decryption', async t => {
  const f = await workspaceFixture(t)
  const bookmark = await f.store.save('https://memory.example.com', credential, f.identity)
  const before = await readFile(f.path)
  let encrypted = 0, decrypted = 0
  const store = new WorkspaceStore(f.directory, {
    available: async () => false,
    encrypt: async value => { encrypted++; return f.cipher.encrypt(value) },
    decrypt: async value => { decrypted++; return f.cipher.decrypt(value) },
  })
  await assert.rejects(store.save(bookmark.endpoint, credential + '_changed', f.identity), /password store/)
  await assert.rejects(store.credential(bookmark.id), /password store/)
  assert.equal((await store.inspect(bookmark.id)).accessStatus, 'locked')
  assert.equal(encrypted, 0)
  assert.equal(decrypted, 0)
  assert.deepEqual(await readFile(f.path), before)
})

test('late OS encryption cannot write a connection after the UI operation timed out', async t => {
  const f = await workspaceFixture(t)
  await f.store.save('https://memory.example.com', credential, f.identity)
  const before = await readFile(f.path)
  const consent = deferred()
  const cipher = boundedCredentialCipher({
    available: async () => true,
    encrypt: async value => { await consent.promise; return f.cipher.encrypt(value) },
    decrypt: async value => f.cipher.decrypt(value),
  }, { checkTimeoutMs: 20, operationTimeoutMs: 20 })
  const store = new WorkspaceStore(f.directory, cipher)
  await assert.rejects(store.save('https://another.example.com', credential + '_new', f.identity), /secure store/)
  assert.deepEqual(await readFile(f.path), before)
  consent.resolve()
  await new Promise(resolve => setImmediate(resolve))
  assert.deepEqual(await readFile(f.path), before)
  assert.equal((await store.list()).length, 1)
})

test('a timed-out native crypto request cannot accumulate more plaintext requests', async () => {
  const finish = deferred()
  let calls = 0
  const cipher = boundedCredentialCipher({
    available: async () => true,
    encrypt: async () => { calls++; await finish.promise; return Buffer.from('opaque') },
    decrypt: async () => 'value',
  }, { checkTimeoutMs: 20, operationTimeoutMs: 20 })
  await assert.rejects(cipher.encrypt('first'), /secure store/)
  await assert.rejects(cipher.encrypt('second'), /secure store/)
  assert.equal(calls, 1)
  finish.resolve()
  await new Promise(resolve => setImmediate(resolve))
  assert.deepEqual(await cipher.encrypt('third'), Buffer.from('opaque'))
  assert.equal(calls, 2)
})

test('an asynchronous provider can still read the existing protected record', async t => {
  const f = await workspaceFixture(t)
  const saved = await f.store.save('https://memory.example.com', credential, f.identity)
  const before = await readFile(f.path)
  const cipher = boundedCredentialCipher({
    available: async () => true,
    encrypt: async value => f.cipher.encrypt(value),
    decrypt: async value => f.cipher.decrypt(value),
  })
  const reopened = new WorkspaceStore(f.directory, cipher)
  assert.equal((await reopened.credential(saved.id)).credential, credential)
  assert.equal((await reopened.inspect(saved.id)).accessStatus, 'recorded')
  assert.deepEqual(await readFile(f.path), before)
})

test('provider errors and malformed results cannot expose or persist plaintext', async () => {
  const secret = 'mnm_' + 'private-fixture-'.repeat(4)
  const cipher = boundedCredentialCipher({
    available: async () => true,
    encrypt: async () => { throw new Error(secret) },
    decrypt: async () => ({ result: secret }),
  })
  for (const operation of [() => cipher.encrypt(secret), () => cipher.decrypt(Buffer.from('opaque'))]) {
    await assert.rejects(operation(), error => error.message.includes('secure store') && !error.message.includes(secret))
  }
  const invalid = boundedCredentialCipher({
    available: async () => true,
    encrypt: async () => secret,
    decrypt: async () => 'x'.repeat(16385),
  })
  await assert.rejects(invalid.encrypt(secret), /secure store/)
  await assert.rejects(invalid.decrypt(Buffer.from('opaque')), /secure store/)
})
