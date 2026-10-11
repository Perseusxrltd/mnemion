import assert from 'node:assert/strict'
import { randomUUID } from 'node:crypto'
import { chmod, lstat, mkdir, readFile, rm, symlink, writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { test } from 'node:test'
import { WorkspaceStore, workspaceEndpoint } from '../dist/workspace-store.js'
import { workspaceFixture as fixture, fixtureCredential as credential } from './workspace-fixture.mjs'

test('private encrypted storage survives restart without exposing a token in bookmarks', async t => {
  const f = await fixture(t)
  const saved = await f.store.save('https://memory.example.com/', credential, f.identity)
  const file = await readFile(f.path, 'utf8')
  assert.ok(!file.includes(credential))
  assert.ok(!JSON.stringify(await f.store.list()).includes('sealed'))
  if (process.platform !== 'win32') assert.equal((await lstat(f.path)).mode & 0o777, 0o600)
  const restarted = new WorkspaceStore(f.directory, f.cipher)
  assert.deepEqual(await restarted.credential(saved.id), { bookmark: saved, credential })
  assert.equal((await restarted.status()).activeId, saved.id)
})

test('concurrent connection saves preserve both identities and rotate a key in place', async t => {
  const f = await fixture(t)
  const other = { ...f.identity, principal_id: randomUUID() }
  const [first, second] = await Promise.all([
    f.store.save('https://memory.example.com', credential, f.identity),
    f.store.save('https://memory.example.com', credential + '_other', other),
  ])
  const updated = await f.store.save(first.endpoint, credential + '_rotated', f.identity)
  assert.equal(updated.id, first.id)
  assert.equal((await f.store.list()).length, 2)
  assert.equal((await f.store.credential(second.id)).credential, credential + '_other')
  assert.equal((await f.store.credential(first.id)).credential, credential + '_rotated')
})

test('editing a destination or swapping identity cannot redirect a saved credential', async t => {
  const f = await fixture(t)
  const saved = await f.store.save('https://memory.example.com', credential, f.identity)
  const original = JSON.parse(await readFile(f.path, 'utf8'))
  for (const mutation of [
    row => { row.endpoint = 'https://another.example.com' },
    row => { row.tenantId = randomUUID() },
    row => { row.principalId = randomUUID() },
  ]) {
    const document = structuredClone(original)
    mutation(document.connections[0])
    await writeFile(f.path, JSON.stringify(document))
    await assert.rejects(f.store.credential(saved.id), /does not match/)
  }
})

test('locked or unavailable encryption has no plaintext fallback and still allows forgetting', async t => {
  const f = await fixture(t)
  f.cipher.unlocked = false
  await assert.rejects(f.store.save('https://memory.example.com', credential, f.identity), /password store/)
  await assert.rejects(lstat(f.path), { code: 'ENOENT' })
  f.cipher.unlocked = true
  const saved = await f.store.save('https://memory.example.com', credential, f.identity)
  f.cipher.unlocked = false
  await assert.rejects(f.store.credential(saved.id), /password store/)
  await f.store.remove(saved.id)
  assert.deepEqual(await f.store.list(), [])
  assert.equal((await f.store.status()).activeId, null)
})

test('disconnect selection survives restart while retaining the encrypted bookmark', async t => {
  const f = await fixture(t)
  const saved = await f.store.save('https://memory.example.com', credential, f.identity)
  await f.store.select(null)
  const restarted = new WorkspaceStore(f.directory, f.cipher)
  assert.equal((await restarted.status()).activeId, null)
  assert.equal((await restarted.list())[0].id, saved.id)
  await assert.rejects(restarted.select(randomUUID()), /no longer available/)
  assert.equal((await restarted.status()).activeId, null)
})

test('corrupt metadata fails closed without replacing the existing file', async t => {
  const f = await fixture(t)
  await f.store.save('https://memory.example.com', credential, f.identity)
  const bad = '{"format":1000,"connections":[]}'
  await writeFile(f.path, bad)
  await assert.rejects(f.store.save('https://memory.example.com', credential, f.identity), /Invalid saved/)
  assert.equal(await readFile(f.path, 'utf8'), bad)
})

test('an explicit reset recovers corrupt device settings without needing the old keychain', async t => {
  const f = await fixture(t)
  const saved = await f.store.save('https://memory.example.com', credential, f.identity)
  await writeFile(f.path, '{broken')
  f.cipher.unlocked = false
  await assert.rejects(f.store.list())
  await f.store.reset()
  assert.deepEqual(await f.store.status(), { activeId: null, bookmarks: [] })
  f.cipher.unlocked = true
  await assert.rejects(f.store.credential(saved.id), /no longer available/)
  await f.store.save('https://memory.example.com', credential, f.identity)
  assert.equal((await f.store.list()).length, 1)
})

test('reset repairs owned file permissions while refusing linked files', { skip: process.platform === 'win32' }, async t => {
  const f = await fixture(t)
  await f.store.save('https://memory.example.com', credential, f.identity)
  await chmod(f.path, 0o644)
  await chmod(f.directory, 0o755)
  await f.store.reset()
  assert.equal((await lstat(f.path)).mode & 0o777, 0o600)
  assert.equal((await lstat(f.directory)).mode & 0o777, 0o700)
  await rm(f.path)
  const external = join(f.root, 'unrelated.txt')
  await writeFile(external, 'Keep this file', { mode: 0o600 })
  await symlink(external, f.path)
  await assert.rejects(f.store.reset(), /linked elsewhere/)
  assert.equal(await readFile(external, 'utf8'), 'Keep this file')
})

test('oversized and duplicate records cannot be consumed as valid saved workspaces', async t => {
  const f = await fixture(t)
  await f.store.save('https://memory.example.com', credential, f.identity)
  const original = JSON.parse(await readFile(f.path, 'utf8'))
  original.connections.push(original.connections[0])
  await writeFile(f.path, JSON.stringify(original))
  await assert.rejects(f.store.list(), /Invalid saved/)
  await writeFile(f.path, 'x'.repeat(256 * 1024 + 1))
  await assert.rejects(f.store.list(), /size limit/)
})

test('linked or world-readable storage is rejected', { skip: process.platform === 'win32' }, async t => {
  const f = await fixture(t)
  await mkdir(f.directory, { mode: 0o700 })
  const target = join(f.root, 'unrelated.json')
  await writeFile(target, '{"format":1,"connections":[]}', { mode: 0o600 })
  await symlink(target, f.path)
  await assert.rejects(f.store.list(), /not private/)
  assert.equal(await readFile(target, 'utf8'), '{"format":1,"connections":[]}')
  await rm(f.path)
  await f.store.save('https://memory.example.com', credential, f.identity)
  await chmod(f.path, 0o644)
  await assert.rejects(f.store.list(), /not private/)
})

test('workspace addresses cannot smuggle credentials or send a token over remote plaintext HTTP', () => {
  for (const address of ['http://example.com', 'https://name:password@example.com', 'https://example.com/?token=x', 'https://example.com/#secret', 'file:///tmp/workspace']) {
    assert.throws(() => workspaceEndpoint(address))
  }
  assert.equal(workspaceEndpoint('http://127.0.0.1:7892/'), 'http://127.0.0.1:7892')
  assert.equal(workspaceEndpoint('https://memory.example.com/'), 'https://memory.example.com')
})
