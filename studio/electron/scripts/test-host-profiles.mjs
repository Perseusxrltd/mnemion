import assert from 'node:assert/strict'
import { test } from 'node:test'
import { mkdtemp, readFile, rm, writeFile, link } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { createCipheriv, createDecipheriv, randomBytes, randomUUID } from 'node:crypto'
import { HostProfiles } from '../dist/host-profiles.js'
import { desktopAction } from '../dist/desktop-actions.js'

// Authenticated fixture cipher tests custody; native OS stores have their own
// installed-app qualification and are not represented by this fixture.
function cipher() {
  const key = randomBytes(32)
  return {
    available: () => true,
    encrypt: value => { const iv = randomBytes(12), aes = createCipheriv('aes-256-gcm', key, iv); return Buffer.concat([iv, aes.update(value), aes.final(), aes.getAuthTag()]) },
    decrypt: value => { const aes = createDecipheriv('aes-256-gcm', key, value.subarray(0, 12)); aes.setAuthTag(value.subarray(-16)); return Buffer.concat([aes.update(value.subarray(12, -16)), aes.final()]).toString() },
  }
}
const keys = { private_key: 'fixture-private-host-key-never-return-to-renderer', public_key: 'ssh-ed25519 ' + Buffer.alloc(51, 1).toString('base64'), fingerprint: 'SHA256:' + 'A'.repeat(43) }
function connection() { return { host_id: randomUUID(), operator_id: randomUUID(), hostname: 'memory.example.test', port: 7893, username: 'mnemion', host_key_algorithm: 'ssh-ed25519', host_key_fingerprint: 'SHA256:' + 'B'.repeat(43), operator_key_fingerprint: keys.fingerprint } }
function request(host, action = 'service.stop') { return { protocol: 1, host_id: host.host_id, request_id: randomUUID(), action, issued_at: new Date().toISOString(), valid_until: new Date(Date.now() + 3600000).toISOString(), approve_service_interruption: true } }
function reply(host, req, result) { return { protocol: 1, host_id: host.host_id, operator_id: host.operator_id, request_id: req.request_id, ok: true, result, error: null } }
function helper(remote = async value => reply(value.connection, value.request, { phase: 'queued' })) {
  return async value => {
    if (value.operation === 'keygen') return keys
    if (value.operation === 'validate') return { connection: value.connection, request: value.request }
    assert.equal(value.private_key, keys.private_key)
    return remote(value)
  }
}

test('host login survives reopen, binds its enrollment and never exposes its private key', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'mnemion-host-profile-')), secure = cipher()
  try {
    const manager = new HostProfiles(directory, secure, helper())
    const created = await manager.create('Company operator')
    assert.equal(JSON.stringify(created).includes(keys.private_key), false)
    const host = connection()
    await assert.rejects(manager.enroll(created.id, host, false), /Confirm/)
    await manager.enroll(created.id, host, true)
    assert.equal((await readFile(join(directory, 'hosts.json'), 'utf8')).includes(keys.private_key), false)
    const reopened = new HostProfiles(directory, secure, helper())
    assert.equal((await reopened.status()).profiles[0].connection.host_id, host.host_id)
    assert.equal(JSON.stringify(await reopened.status()).includes('sealed'), false)
    const saved = JSON.parse(await readFile(join(directory, 'hosts.json'), 'utf8'))
    saved.profiles[0].connection.hostname = 'different.example.test'
    await writeFile(join(directory, 'hosts.json'), JSON.stringify(saved), { mode: 0o600 })
    await assert.rejects(reopened.request(created.id, request(host)), /protected host identity/)
    assert.equal((await readFile(join(directory, 'hosts.json'), 'utf8')).includes('different.example.test'), true)
  } finally { await rm(directory, { recursive: true, force: true }) }
})

test('a lost host reply persists the exact operation and is reconciled after app restart without replay', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'mnemion-host-profile-')), secure = cipher()
  let effects = 0
  try {
    const manager = new HostProfiles(directory, secure, helper(async () => { effects++; throw new Error('Reply lost') }))
    const created = await manager.create('Custodian'), host = connection(), job = request(host)
    await manager.enroll(created.id, host, true)
    await assert.rejects(manager.request(created.id, job), /Reply lost/)
    assert.equal(effects, 1)
    const reopened = new HostProfiles(directory, secure, helper(async value => {
      assert.equal(value.request.action, 'operations.get')
      return reply(host, value.request, { operation_id: job.request_id, phase: 'succeeded', result: { stopped: true } })
    }))
    assert.deepEqual((await reopened.status()).profiles[0].last_operation.request, job)
    await assert.rejects(reopened.remove(created.id, true), /outstanding operation/)
    await assert.rejects(reopened.request(created.id, request(host, 'service.start')), /outstanding host operation/)
    await reopened.request(created.id, { protocol: 1, host_id: host.host_id, request_id: randomUUID(), action: 'operations.get', operation_id: job.request_id })
    assert.equal((await reopened.status()).profiles[0].last_operation.phase, 'succeeded')
    assert.equal(effects, 1)
    await reopened.remove(created.id, true)
    assert.equal((await reopened.status()).profiles.length, 0)
  } finally { await rm(directory, { recursive: true, force: true }) }
})

test('locked secure storage and multiply linked host files never produce plaintext fallback or new credentials', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'mnemion-host-profile-'))
  try {
    const locked = new HostProfiles(directory, { ...cipher(), available: () => false }, async () => { throw new Error('Must not generate a key') })
    await assert.rejects(locked.create('Locked'), /Unlock/)
    const outside = join(directory, 'preserve.json')
    await writeFile(outside, 'Keep original', { mode: 0o600 })
    await link(outside, join(directory, 'hosts.json'))
    await assert.rejects(locked.status(), /private app storage/)
    assert.equal(await readFile(outside, 'utf8'), 'Keep original')
  } finally { await rm(directory, { recursive: true, force: true }) }
})

test('revoked or unreachable login removal first preserves its exact public recovery record', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'mnemion-host-profile-')), secure = cipher()
  try {
    const manager = new HostProfiles(directory, secure, helper(async () => { throw new Error('Offline') }))
    const created = await manager.create('Revoked device'), host = connection(), job = request(host)
    await manager.enroll(created.id, host, true)
    await assert.rejects(manager.request(created.id, job), /Offline/)
    await assert.rejects(manager.remove(created.id, true), /outstanding/)
    await manager.remove(created.id, true, true)
    assert.equal((await manager.status()).profiles.length, 0)
    const records = (await manager.recoveries()).records
    assert.equal(records.length, 1)
    const archived = await manager.recovery(records[0].id)
    assert.deepEqual(archived.profile.last_operation.request, job)
    assert.equal(archived.original_outcome, 'unconfirmed')
    assert.equal(JSON.stringify(archived).includes(keys.private_key), false)
    assert.equal(JSON.stringify(archived).includes('sealed'), false)
    await assert.rejects(manager.recovery('../hosts.json'), /Choose a recorded/)
  } finally { await rm(directory, { recursive: true, force: true }) }
})

test('a refused replay preserves the original outcome and an explicit archive keeps the host key usable', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'mnemion-host-profile-')), secure = cipher()
  let response = 'lost'
  try {
    const manager = new HostProfiles(directory, secure, helper(async value => {
      if (response === 'lost') throw new Error('Reply lost')
      if (response === 'refused') return { ...reply(value.connection, value.request, null), ok: false,
        error: { code: 'operator_revoked', message: 'Private host diagnostic must not reach the renderer' } }
      return reply(value.connection, value.request, { phase: 'succeeded', stopped: true })
    }))
    const created = await manager.create('Recoverable device'), host = connection(), original = request(host)
    await manager.enroll(created.id, host, true)
    await assert.rejects(manager.request(created.id, original), /Reply lost/)
    response = 'refused'
    const refusal = await manager.request(created.id, original)
    assert.equal(refusal.ok, false)
    assert.equal(JSON.stringify(refusal).includes('Private host diagnostic'), false)
    assert.equal((await manager.status()).profiles[0].last_operation.phase, 'submitted')
    await assert.rejects(manager.archiveRequest(created.id, false), /Confirm/)
    await manager.archiveRequest(created.id, true)
    const retained = (await manager.status()).profiles[0]
    assert.equal(retained.id, created.id)
    assert.equal(retained.last_operation, null)
    const archive = (await manager.recoveries()).records[0]
    assert.deepEqual((await manager.recovery(archive.id)).profile.last_operation.request, original)
    response = 'succeeded'
    const next = request(host, 'service.start')
    await manager.request(created.id, next)
    response = 'refused'
    await manager.request(created.id, next)
    assert.equal((await manager.status()).profiles[0].last_operation.phase, 'succeeded')
    assert.equal((await manager.recoveries()).records.length, 1)
  } finally { await rm(directory, { recursive: true, force: true }) }
})

test('host controls are available without selecting a memory workspace and reject unrelated fields', async () => {
  for (const action of ['host.profiles', 'host.schema', 'host.inspect', 'host.create', 'host.enroll', 'host.forget', 'host.request', 'host.recoveries', 'host.recovery', 'host.request.archive']) {
    assert.equal(desktopAction(action, {}).workspace, false)
    assert.throws(() => desktopAction(action, { command: 'arbitrary shell' }), /unsupported input/)
  }
})
