import assert from 'node:assert/strict'
import { createCipheriv, createDecipheriv, randomBytes, randomUUID } from 'node:crypto'
import { mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { test } from 'node:test'
import { LocalBackups, createRecoveryKey, recoveryKeyId } from '../dist/local-backups.js'

async function fixture(t) {
  const base = await mkdtemp(join(tmpdir(), 'mnemion-backups-'))
  t.after(() => rm(base, { recursive: true, force: true }))
  const root = join(base, 'host'), destination = join(base, 'Cloud équipe')
  await mkdir(root, { mode: 0o700 }); await mkdir(destination, { mode: 0o700 })
  const workspace_id = randomUUID(), secret = randomBytes(32), calls = []
  let available = true
  const cipher = {
    available: () => available,
    encrypt: value => {
      assert.ok(available)
      const nonce = randomBytes(12), operation = createCipheriv('aes-256-gcm', secret, nonce)
      const encrypted = Buffer.concat([operation.update(value, 'utf8'), operation.final()])
      return Buffer.concat([nonce, operation.getAuthTag(), encrypted])
    },
    decrypt: value => {
      assert.ok(available)
      const operation = createDecipheriv('aes-256-gcm', secret, value.subarray(0, 12))
      operation.setAuthTag(value.subarray(12, 28))
      return Buffer.concat([operation.update(value.subarray(28)), operation.final()]).toString('utf8')
    },
  }
  const host = {
    dataDirectory: root, busy: false,
    status: { state: 'running', info: { settings: { workspace_id } } },
    cancelBackup() {},
    async waitForInspection() {},
    async runBackup(action, input) {
      calls.push({ action, input })
      const stamp = new Date().toISOString(), id = randomUUID().replaceAll('-', '')
      const folder = join(input.destination, 'Mnemion backups', workspace_id)
      const file = kind => ({ file: join(folder, kind + '-' + id + '.mnemion.enc'), bytes: 100, sha256: 'a'.repeat(64), key_id: recoveryKeyId(input.recovery_key), authenticated: true })
      const ledger = { format: 1, operation_id: id, workspace_id, scope: 'complete_local_database', tenant_count: 1,
        ledger_at: stamp, application_version: '4.4.0', verified_at: stamp, ledger: file('ledger') }
      await mkdir(folder, { recursive: true, mode: 0o700 })
      await writeFile(ledger.ledger.file, Buffer.alloc(100))
      await writeFile(join(root, 'last-ledger.json'), JSON.stringify(ledger), { mode: 0o600 })
      if (action === 'backup-ledger') return ledger
      const result = { ...ledger, snapshot: { ...file('snapshot'), backup_id: randomUUID(), snapshot_at: stamp, memory_count: 3 } }
      await writeFile(result.snapshot.file, Buffer.alloc(100))
      await writeFile(join(root, 'last-backup.json'), JSON.stringify(result), { mode: 0o600 })
      return result
    },
  }
  const manager = new LocalBackups(host, cipher)
  t.after(() => manager.close())
  const key = createRecoveryKey()
  const settings = { expected_revision: null, destination, enabled: true, snapshot_hours: 24, ledger_minutes: 15, recovery_key: key, key_saved: true }
  return { root, host, manager, cipher, key, settings, calls, locked: value => { available = !value } }
}

test('scheduled keys remain protected across reopen and never appear in status', async t => {
  const f = await fixture(t)
  const saved = await f.manager.configure(f.settings)
  const document = await readFile(join(f.root, 'backup-policy.json'), 'utf8')
  assert.ok(!document.includes(f.key))
  assert.ok(!JSON.stringify(saved).includes(f.key))
  const reopened = new LocalBackups(f.host, f.cipher)
  t.after(() => reopened.close())
  await reopened.run()
  assert.equal(f.calls.length, 1)
  assert.equal(f.calls[0].input.recovery_key, f.key)
  assert.ok((await reopened.status()).last_snapshot.snapshot.authenticated)
})

test('unavailable secure storage refuses scheduled plaintext fallback but permits a supplied manual key', async t => {
  const f = await fixture(t)
  f.locked(true)
  await assert.rejects(f.manager.configure(f.settings), /secure store/)
  await assert.rejects(readFile(join(f.root, 'backup-policy.json')), { code: 'ENOENT' })
  const view = await f.manager.configure({ ...f.settings, enabled: false })
  assert.equal(view.configuration.protected_key, false)
  assert.ok(!(await readFile(join(f.root, 'backup-policy.json'), 'utf8')).includes(f.key))
  await assert.rejects(f.manager.run(), /Enter the recovery key/)
  await f.manager.run(false, f.key)
  assert.equal(f.calls.length, 1)
})

test('concurrent overdue scheduler observations coalesce into one snapshot and ledger', async t => {
  const f = await fixture(t)
  await f.manager.configure(f.settings)
  await Promise.all([f.manager.tick(), f.manager.tick(), f.manager.tick()])
  assert.deepEqual(f.calls.map(call => call.action), ['backup'])
  await f.manager.tick()
  assert.equal(f.calls.length, 1)
})

test('changing the schedule invalidates a pending scheduler observation', async t => {
  const f = await fixture(t)
  const configured = await f.manager.configure(f.settings)
  const status = await f.manager.status()
  let release
  const waiting = new Promise(resolve => { release = resolve })
  const original = f.manager.status.bind(f.manager)
  let first = true
  f.manager.status = async () => first ? (first = false, await waiting, status) : original()
  const checking = f.manager.tick()
  await f.manager.configure({ ...f.settings, recovery_key: undefined, expected_revision: configured.configuration.revision, enabled: false })
  release()
  await checking
  assert.equal(f.calls.length, 0)
})

test('a cancelled key-unlock operation cannot later start a backup', async t => {
  const f = await fixture(t)
  await f.manager.configure(f.settings)
  const original = f.cipher.decrypt
  let release, entered
  const inside = new Promise(resolve => { entered = resolve })
  f.cipher.decrypt = value => { entered(); return new Promise(resolve => { release = () => resolve(original(value)) }) }
  const pending = f.manager.run()
  const rejected = assert.rejects(pending, /cancelled/)
  await inside
  f.manager.cancel()
  release()
  await rejected
  assert.equal(f.calls.length, 0)
})

test('stale settings and extra private fields cannot overwrite or leak through the policy', async t => {
  const f = await fixture(t)
  await f.manager.configure(f.settings)
  await assert.rejects(f.manager.configure(f.settings), /changed/)
  const path = join(f.root, 'backup-policy.json')
  const record = JSON.parse(await readFile(path, 'utf8'))
  await writeFile(path, JSON.stringify({ ...record, private_key: f.key }), { mode: 0o600 })
  await assert.rejects(f.manager.status(), /safely/)
})

test('failed automatic backups retain their notice and retry deadline across application restart', async t => {
  const f = await fixture(t)
  await f.manager.configure(f.settings)
  const original = f.host.runBackup
  let failedCalls = 0
  f.host.runBackup = async () => { ++failedCalls; throw new Error('The selected drive is unavailable.') }
  await f.manager.tick()
  const reopened = new LocalBackups(f.host, f.cipher)
  t.after(() => reopened.close())
  assert.match((await reopened.status()).last_error, /drive is unavailable/)
  await reopened.tick()
  assert.equal(failedCalls, 1)
  f.host.runBackup = original
  await reopened.run()
  assert.equal((await reopened.status()).last_error, undefined)
})

test('a deleted or resized backup remains visibly unavailable and becomes due again', async t => {
  const f = await fixture(t)
  await f.manager.configure(f.settings)
  const saved = await f.manager.run()
  assert.equal((await f.manager.status()).snapshot_availability, 'present')
  await rm(saved.snapshot.file)
  assert.equal((await f.manager.status()).snapshot_availability, 'missing')
  await f.manager.tick()
  assert.equal(f.calls.length, 2)
  const next = await f.manager.status()
  assert.equal(next.snapshot_availability, 'present')
  await writeFile(next.last_ledger.ledger.file, 'altered bytes')
  assert.equal((await f.manager.status()).ledger_availability, 'changed')
})
