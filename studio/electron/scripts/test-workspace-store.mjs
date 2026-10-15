import assert from 'node:assert/strict'
import { randomUUID } from 'node:crypto'
import { chmod, lstat, mkdir, readFile, rm, symlink, writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { test } from 'node:test'
import { WorkspaceStore, workspaceEndpoint } from '../dist/workspace-store.js'
import { workspaceFixture as fixture, fixtureCredential as credential, recoveryFixture } from './workspace-fixture.mjs'

test('administrator recovery references survive restart only inside OS-protected storage', async t => {
  const f = await fixture(t), identity = { ...f.identity, administrator: true }
  const record = recoveryFixture(identity)
  const saved = await f.store.save('https://memory.example.com', credential, identity, undefined, record)
  const raw = await readFile(f.path, 'utf8')
  assert.ok(!raw.includes(record.directory.instructions))
  assert.ok(!JSON.stringify(await f.store.status()).includes('recovery'))
  const restarted = new WorkspaceStore(f.directory, f.cipher)
  assert.deepEqual((await restarted.inspect(saved.id)).recovery.record, record)
  assert.equal((await restarted.credential(saved.id)).credential, credential)
  f.cipher.unlocked = false
  assert.equal((await restarted.inspect(saved.id)).accessStatus, 'locked')
  assert.equal((await restarted.inspect(saved.id)).recovery, undefined)
  f.cipher.unlocked = true
  await restarted.save(saved.endpoint, credential, { ...identity, administrator: false })
  assert.equal((await restarted.inspect(saved.id)).recovery, undefined)
  assert.equal((await restarted.credential(saved.id)).credential, credential)
})

test('recovery cache rejects another tenant, changed destination and credential reflection without changing saved access', async t => {
  const f = await fixture(t), identity = { ...f.identity, administrator: true }
  const record = recoveryFixture(identity)
  const saved = await f.store.save('https://memory.example.com', credential, identity, undefined, record)
  const before = await readFile(f.path, 'utf8')
  await assert.rejects(f.store.cacheRecovery(saved.id, identity, saved.endpoint, { ...record, tenant_id: randomUUID() }))
  await assert.rejects(f.store.cacheRecovery(saved.id, identity, 'https://different.example.org', record))
  const reflected = structuredClone(record); reflected.directory.instructions = credential
  await assert.rejects(f.store.cacheRecovery(saved.id, identity, saved.endpoint, reflected))
  assert.equal(await readFile(f.path, 'utf8'), before)
  const document = JSON.parse(before)
  const payload = JSON.parse(f.cipher.decrypt(Buffer.from(document.connections[0].sealed, 'base64')))
  payload.recovery.record.tenant_id = randomUUID()
  document.connections[0].sealed = f.cipher.encrypt(JSON.stringify(payload)).toString('base64')
  await writeFile(f.path, JSON.stringify(document))
  const inspected = await f.store.inspect(saved.id)
  assert.equal(inspected.accessStatus, 'recorded')
  assert.equal(inspected.recoveryStatus, 'unavailable')
  assert.equal((await f.store.credential(saved.id)).credential, credential)
})

test('large optional recovery references do not break an otherwise valid protected connection', async t => {
  const f = await fixture(t)
  const identity = { ...f.identity, administrator: true, name: '🧠'.repeat(128), tenant_name: '🧠'.repeat(128) }
  const record = recoveryFixture(identity); record.directory.instructions = '🧠'.repeat(1100)
  const saved = await f.store.save('https://memory.example.com/' + 'a'.repeat(3900), 'a'.repeat(1024), identity, undefined, record)
  const restarted = new WorkspaceStore(f.directory, f.cipher)
  assert.equal((await restarted.credential(saved.id)).credential.length, 1024)
  assert.equal((await restarted.inspect(saved.id)).accessStatus, 'recorded')
  assert.equal((await restarted.inspect(saved.id)).recovery, undefined)
})

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

test('asynchronous OS protection must finish before a connection is saved', async t => {
  const f = await fixture(t)
  let release
  const gate = new Promise(resolve => { release = resolve })
  const store = new WorkspaceStore(f.directory, {
    available: () => true,
    encrypt: async value => { await gate; return f.cipher.encrypt(value) },
    decrypt: async value => f.cipher.decrypt(value),
  })
  const pending = store.save('https://memory.example.com', credential, f.identity)
  await new Promise(resolve => setTimeout(resolve, 20))
  await assert.rejects(lstat(f.path), { code: 'ENOENT' })
  release()
  const saved = await pending
  assert.equal((await store.credential(saved.id)).credential, credential)
  const failed = new WorkspaceStore(f.directory, {
    available: () => true, encrypt: async () => { throw new Error('OS store unavailable') },
    decrypt: async value => f.cipher.decrypt(value),
  })
  const before = await readFile(f.path, 'utf8')
  await assert.rejects(failed.save(saved.endpoint, credential + '_rotated', f.identity), /OS store unavailable/)
  assert.equal(await readFile(f.path, 'utf8'), before)
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

test('offline inspection returns a dated encrypted identity without a credential or a storage write', async t => {
  const f = await fixture(t)
  const identity = { ...f.identity, administrator: true }
  const saved = await f.store.save('https://memory.example.com', credential, identity)
  await f.store.select(null)
  const before = await readFile(f.path, 'utf8')
  const inspection = await new WorkspaceStore(f.directory, f.cipher).inspect(saved.id)
  assert.deepEqual(inspection, { bookmark: saved, access: { identity, verifiedAt: saved.updatedAt }, accessStatus: 'recorded' })
  assert.ok(!before.includes('administrator'))
  assert.ok(!JSON.stringify(inspection).includes(credential))
  assert.ok(!JSON.stringify(inspection).includes('sealed'))
  assert.equal(await readFile(f.path, 'utf8'), before)
  assert.equal((await f.store.status()).activeId, null)
})

test('older saved connections remain usable and cannot be mistaken for a recorded administrator', async t => {
  const f = await fixture(t)
  const saved = await f.store.save('https://memory.example.com', credential, f.identity)
  const document = JSON.parse(await readFile(f.path, 'utf8'))
  const payload = JSON.parse(f.cipher.decrypt(Buffer.from(document.connections[0].sealed, 'base64')))
  delete payload.identity
  delete payload.verifiedAt
  document.connections[0].sealed = f.cipher.encrypt(JSON.stringify(payload)).toString('base64')
  await writeFile(f.path, JSON.stringify(document))
  const before = await readFile(f.path, 'utf8')
  assert.deepEqual(await f.store.inspect(saved.id), { bookmark: saved, access: null, accessStatus: 'not-recorded' })
  assert.equal((await f.store.credential(saved.id)).credential, credential)
  assert.equal(await readFile(f.path, 'utf8'), before)
})

test('locked secure storage retains offline context without decrypting or assigning a role', async t => {
  const f = await fixture(t)
  const saved = await f.store.save('https://memory.example.com', credential, f.identity)
  f.cipher.unlocked = false
  f.cipher.decrypt = () => { throw new Error('Must not decrypt while locked') }
  assert.deepEqual(await f.store.inspect(saved.id), { bookmark: saved, access: null, accessStatus: 'locked' })
})

test('tampered metadata cannot change the date, identity, or destination of a verified access observation', async t => {
  const f = await fixture(t)
  const saved = await f.store.save('https://memory.example.com', credential, { ...f.identity, administrator: true })
  const original = JSON.parse(await readFile(f.path, 'utf8'))
  for (const mutation of [
    row => { row.updatedAt = '2099-01-01T00:00:00.000Z' },
    row => { row.principalName = 'A different administrator' },
    row => { row.label = 'Another organization' },
    row => { row.endpoint = 'https://another.example.com' },
    row => { row.tenantId = randomUUID() },
    row => { row.principalId = randomUUID() },
  ]) {
    const document = structuredClone(original)
    mutation(document.connections[0])
    await writeFile(f.path, JSON.stringify(document))
    const before = await readFile(f.path, 'utf8')
    const result = await f.store.inspect(saved.id)
    assert.equal(result.access, null)
    assert.equal(result.accessStatus, 'unavailable')
    assert.ok(!JSON.stringify(result).includes(credential))
    assert.equal(await readFile(f.path, 'utf8'), before)
  }
})

test('malformed or secret-bearing access observations never reach the recovery view', async t => {
  const f = await fixture(t)
  const saved = await f.store.save('https://memory.example.com', credential, f.identity)
  const original = JSON.parse(await readFile(f.path, 'utf8'))
  const originalPayload = JSON.parse(f.cipher.decrypt(Buffer.from(original.connections[0].sealed, 'base64')))
  for (const mutation of [
    value => { value.identity.administrator = 'true' },
    value => { delete value.verifiedAt },
    value => { value.identity.tenant_id = randomUUID() },
    value => { value.identity.name = credential },
  ]) {
    const document = structuredClone(original)
    const payload = structuredClone(originalPayload)
    mutation(payload)
    document.connections[0].sealed = f.cipher.encrypt(JSON.stringify(payload)).toString('base64')
    await writeFile(f.path, JSON.stringify(document))
    const result = await f.store.inspect(saved.id)
    assert.equal(result.access, null)
    assert.equal(result.accessStatus, 'unavailable')
    assert.ok(!JSON.stringify(result).includes(credential))
  }
})
