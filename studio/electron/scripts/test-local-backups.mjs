import assert from 'node:assert/strict'
import { createCipheriv, createDecipheriv, randomBytes, randomUUID } from 'node:crypto'
import fs, { mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { syncBuiltinESMExports } from 'node:module'
import { spawnSync } from 'node:child_process'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { test } from 'node:test'
import { LocalBackups, createRecoveryKey, recoveryKeyId, readBackupDocument } from '../dist/local-backups.js'
import { backupResult } from '../dist/local-backup-protocol.js'
import { replaceFile } from '../dist/atomic-file.js'
import { BackupStateError, backupStateDiagnostic, backupStateMessage } from '../dist/backup-state-diagnostics.js'

test('backup state diagnostics carry only fixed categories, never private filenames or OS error text', () => {
  const secret = 'PRIVATE_CREDENTIAL_SENTINEL'
  const error = new BackupStateError(join(tmpdir(), secret, 'backup-policy.json'), 'open',
    Object.assign(new Error(secret), { code: 'EACCES', path: secret }))
  assert.equal(error.message, backupStateMessage)
  assert.deepEqual(backupStateDiagnostic(error.diagnostic), { document: 'policy', stage: 'open', filesystem: 'denied' })
  assert.ok(!JSON.stringify(error).includes(secret))
  assert.deepEqual(new BackupStateError(secret, 'path', { code: secret }).diagnostic,
    { document: 'other', stage: 'path', filesystem: 'other' })
})

test('uploaded backup diagnostics reject additional fields, malformed values and prototype names', () => {
  const fixture = { document: 'policy', stage: 'metadata_before_read', filesystem: 'none' }
  assert.deepEqual(backupStateDiagnostic(fixture), fixture)
  assert.equal(backupStateDiagnostic(undefined), undefined)
  for (const key of Object.keys(fixture)) {
    for (const value of ['private-secret', { private: true }, ['none'], null, 4, true]) {
      assert.throws(() => backupStateDiagnostic({ ...fixture, [key]: value }), /Invalid backup-state/)
    }
    const missing = { ...fixture }; delete missing[key]
    assert.throws(() => backupStateDiagnostic(missing), /Invalid backup-state/)
  }
  for (const value of [null, [], { ...fixture, path: 'private-secret' },
    JSON.parse('{"document":"policy","stage":"json","toString":"none"}')]) {
    assert.throws(() => backupStateDiagnostic(value), /Invalid backup-state/)
  }
})

async function documentFixture(t) {
  const root = await mkdtemp(join(tmpdir(), 'mnemion-backup-document-'))
  t.after(() => rm(root, { recursive: true, force: true }))
  const path = join(root, 'backup-policy.json'), replacement = join(root, 'replacement.json')
  await writeFile(path, '{"revision":1}\n', { mode: 0o600 })
  await writeFile(replacement, '{"revision":2}\n', { mode: 0o600 })
  return { root, path, replacement }
}

test('native Windows folder protection leaves a concurrent backup status read stable',
  { skip: process.platform !== 'win32', timeout: 30000 }, async t => {
    const base = await mkdtemp(join(tmpdir(), 'mnemion-directory-reader-'))
    t.after(() => rm(base, { recursive: true, force: true }))
    const directory = join(base, 'Private state Équipe'), path = join(directory, 'backup-policy.json')
    const project = resolve(dirname(fileURLToPath(import.meta.url)), '../../..')
    function protect() {
      const result = spawnSync(process.env.MNEMION_TEST_PYTHON || 'python', ['-c',
        'from pathlib import Path; import sys; from mnemion.local_state import directory; directory(Path(sys.argv[1]))', directory],
        { cwd: project, encoding: 'utf8', timeout: 10000 })
      assert.equal(result.status, 0, 'The real private-directory helper must complete')
    }
    protect()
    // Like the desktop settings writer, this child inherits the private DACL.
    await writeFile(path, '{"revision":1}\n', { mode: 0o600 })
    const originalOpen = fs.open
    const mock = t.mock.method(fs, 'open', async (selected, ...args) => {
      if (selected === path) protect()
      return originalOpen(selected, ...args)
    })
    syncBuiltinESMExports()
    try { assert.deepEqual(await readBackupDocument(path), { revision: 1 }) }
    finally { mock.mock.restore(); syncBuiltinESMExports() }
  })

for (const point of ['before-open', 'after-open', 'during-read']) {
  // Windows blocks replacement while the descriptor is open. Its real sharing
  // transition is qualified separately below; these two timings require POSIX.
  test(`backup metadata snapshot follows one atomic replacement ${point}`,
    { skip: process.platform === 'win32' && point !== 'before-open' }, async t => {
    const f = await documentFixture(t), originalOpen = fs.open
    let opens = 0
    const mock = t.mock.method(fs, 'open', async (path, ...args) => {
      if (path !== f.path) return originalOpen(path, ...args)
      const first = ++opens === 1
      if (first && point === 'before-open') await fs.rename(f.replacement, f.path)
      const file = await originalOpen(path, ...args)
      if (first && point === 'after-open') await fs.rename(f.replacement, f.path)
      if (first && point === 'during-read') {
        const read = file.read.bind(file)
        let replaced = false
        file.read = async (...input) => {
          const result = await read(...input)
          if (!replaced) { replaced = true; await fs.rename(f.replacement, f.path) }
          return result
        }
      }
      return file
    })
    syncBuiltinESMExports()
    try {
      assert.deepEqual(await readBackupDocument(f.path), { revision: 2 })
      assert.equal(opens, 2)
    } finally { mock.mock.restore(); syncBuiltinESMExports() }
  })
}

test('Windows backup reader releases its sharing lock before replacement completes',
  { skip: process.platform !== 'win32', timeout: 5000 }, async t => {
    const f = await documentFixture(t), originalOpen = fs.open, originalRename = fs.rename
    let opens = 0, attempts = 0, firstError, replacement
    let firstAttemptDone
    const firstAttempt = new Promise(resolve => { firstAttemptDone = resolve })
    const rename = t.mock.method(fs, 'rename', async (...args) => {
      if (args[1] !== f.path) return originalRename(...args)
      const first = ++attempts === 1
      try { return await originalRename(...args) }
      catch (error) { if (first) firstError = error.code; throw error }
      finally { if (first) firstAttemptDone() }
    })
    const open = t.mock.method(fs, 'open', async (path, ...args) => {
      const file = await originalOpen(path, ...args)
      if (path === f.path && ++opens === 1) {
        replacement = replaceFile(f.replacement, f.path)
        replacement.catch(() => {})
        await firstAttempt
      }
      return file
    })
    syncBuiltinESMExports()
    try {
      assert.deepEqual(await readBackupDocument(f.path), { revision: 1 })
      assert.ok(['EPERM', 'EACCES', 'EBUSY'].includes(firstError))
      await replacement
      assert.ok(attempts >= 2)
      assert.deepEqual(await readBackupDocument(f.path), { revision: 2 })
      assert.equal(opens, 2)
    } finally {
      await replacement?.catch(() => {})
      open.mock.restore(); rename.mock.restore(); syncBuiltinESMExports()
    }
  })

test('backup metadata snapshot bounds repeated atomic replacement without resetting data', async t => {
  const f = await documentFixture(t), originalOpen = fs.open
  const next = join(f.root, 'next.json')
  await writeFile(next, '{"revision":3}\n', { mode: 0o600 })
  let opens = 0
  const mock = t.mock.method(fs, 'open', async (path, ...args) => {
    if (path === f.path) {
      await fs.rename(++opens === 1 ? f.replacement : next, f.path)
    }
    return originalOpen(path, ...args)
  })
  syncBuiltinESMExports()
  try {
    await assert.rejects(readBackupDocument(f.path), /Backup settings could not be read safely/)
    assert.equal(opens, 2)
    assert.equal(await readFile(f.path, 'utf8'), '{"revision":3}\n')
  } finally { mock.mock.restore(); syncBuiltinESMExports() }
})

test('backup metadata snapshot rejects permissions changed after its path check', { skip: process.platform === 'win32' }, async t => {
  const f = await documentFixture(t), originalOpen = fs.open
  let opens = 0
  const mock = t.mock.method(fs, 'open', async (path, ...args) => {
    if (path === f.path) { ++opens; await fs.chmod(path, 0o644) }
    return originalOpen(path, ...args)
  })
  syncBuiltinESMExports()
  try {
    await assert.rejects(readBackupDocument(f.path), /Backup settings could not be read safely/)
    assert.equal(opens, 1)
  } finally { mock.mock.restore(); syncBuiltinESMExports() }
})

test('backup metadata snapshot rejects an in-place rewrite rather than retrying it', async t => {
  const f = await documentFixture(t), originalOpen = fs.open
  let opens = 0
  const mock = t.mock.method(fs, 'open', async (path, ...args) => {
    if (path === f.path) { ++opens; await writeFile(path, '{"revision":123456789}\n') }
    return originalOpen(path, ...args)
  })
  syncBuiltinESMExports()
  try {
    await assert.rejects(readBackupDocument(f.path), error => {
      assert.equal(error.message, backupStateMessage)
      assert.deepEqual(error.diagnostic, { document: 'policy', stage: 'metadata_before_read', filesystem: 'none' })
      return true
    })
    assert.equal(opens, 1)
  } finally { mock.mock.restore(); syncBuiltinESMExports() }
})

test('backup metadata snapshot rejects corrupt JSON without another open', async t => {
  const f = await documentFixture(t), originalOpen = fs.open
  await writeFile(f.path, '{PRIVATE_INVALID_JSON_SENTINEL}\n')
  let opens = 0
  const mock = t.mock.method(fs, 'open', async (path, ...args) => {
    if (path === f.path) ++opens
    return originalOpen(path, ...args)
  })
  syncBuiltinESMExports()
  try {
    await assert.rejects(readBackupDocument(f.path), error => {
      assert.equal(error.message, backupStateMessage)
      assert.deepEqual(error.diagnostic, { document: 'policy', stage: 'json', filesystem: 'none' })
      assert.ok(!JSON.stringify(error).includes('PRIVATE_INVALID_JSON_SENTINEL'))
      return true
    })
    assert.equal(opens, 1)
  } finally { mock.mock.restore(); syncBuiltinESMExports() }
})

test('backup metadata snapshot rejects a replaced symlink without exposing its path', { skip: process.platform === 'win32' }, async t => {
  const f = await documentFixture(t), originalOpen = fs.open
  let opens = 0
  const mock = t.mock.method(fs, 'open', async (path, ...args) => {
    if (path === f.path) { ++opens; await fs.unlink(path); await fs.symlink(f.replacement, path) }
    return originalOpen(path, ...args)
  })
  syncBuiltinESMExports()
  try {
    await assert.rejects(readBackupDocument(f.path), error => {
      assert.equal(error.message, 'Backup settings could not be read safely. Existing recovery files were retained.')
      return true
    })
    assert.equal(opens, 1)
  } finally { mock.mock.restore(); syncBuiltinESMExports() }
})

test('host inspections retain recovery facts and discard private server settings', () => {
  const stamp = new Date().toISOString(), tenant = randomUUID()
  const inspection = { kind: 'host', key_id: 'a'.repeat(24), encrypted_bytes: 4096, sha256: 'b'.repeat(64),
    authenticated: true, archive_verified: true, ledger_at: stamp, snapshot_at: stamp,
    tenant_count: 1, tenant_ids: [tenant], backup_id: randomUUID(), memory_count: 4,
    application_version: '4.29.0', server_version: 180006, embedded_ledger_sha256: 'c'.repeat(64),
    host_package: { package_id: randomUUID(), service_version: '4.29.0', source_connectors: 2,
      private_files: 3, host_configuration_restored: false, provider_secret: 'private-host-sentinel' },
    environment: { secret: 'private-host-sentinel' } }
  const result = backupResult('backup-inspect', inspection)
  assert.equal(result.kind, 'host')
  assert.equal(result.host_package.package_id, inspection.host_package.package_id)
  assert.equal(result.embedded_ledger_sha256, inspection.embedded_ledger_sha256)
  assert.ok(!JSON.stringify(result).includes('private-host-sentinel'))
  for (const change of [{ source_connectors: 65 }, { private_files: 129 }, { host_configuration_restored: true }]) {
    assert.throws(() => backupResult('backup-inspect', { ...inspection, host_package: { ...inspection.host_package, ...change } }), /host package/)
  }
  assert.throws(() => backupResult('backup-inspect', { ...inspection, embedded_ledger_sha256: undefined }), /included access ledger/)
})

test('completed host recovery identifies its access ledger without reviving host settings', () => {
  const stamp = new Date().toISOString()
  const value = { format: 1, state: 'restored', started_at: stamp, restored_at: stamp,
    workspace_id: randomUUID(), source_workspace_id: null, backup_id: randomUUID(), tenant_id: randomUUID(),
    snapshot_sha256: 'a'.repeat(64), ledger_sha256: 'b'.repeat(64), data_directory: join(tmpdir(), 'recovered-host'),
    tenant_count: 1, keys_rotated: true, verified_tables: 70, deletions_reconciled: 1,
    ledger_at: stamp, external_connections_require_review: true,
    host_package: { package_id: randomUUID(), service_version: '4.29.0', source_connectors: 1,
      private_files: 2, host_configuration_restored: false, ledger_source: 'embedded', token: 'private-host-sentinel' } }
  assert.equal(backupResult('backup-restore', value).host_package.ledger_source, 'embedded')
  assert.ok(!JSON.stringify(backupResult('backup-restore', value)).includes('private-host-sentinel'))
  assert.throws(() => backupResult('backup-restore', { ...value, host_package: { ...value.host_package, ledger_source: 'unknown' } }), /ledger selection/)
})

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

for (const cancel of [false, true]) {
  test(`backup retention ${cancel ? 'cancellation' : 'save'} under a Windows sharing lock preserves the protected key`, async t => {
    const f = await fixture(t), configured = await f.manager.configure(f.settings)
    const path = join(f.root, 'backup-policy.json'), before = await readFile(path, 'utf8')
    const descriptor = Object.getOwnPropertyDescriptor(process, 'platform'), rename = fs.rename
    const controller = new AbortController()
    let calls = 0
    const mock = t.mock.method(fs, 'rename', async (temporary, destination) => {
      assert.equal(destination, path)
      assert.equal(await readFile(path, 'utf8'), before)
      assert.equal(f.manager.busy, true)
      if (++calls === 1) {
        if (cancel) setImmediate(() => controller.abort())
        throw Object.assign(new Error('fixture sharing lock'), { code: 'EPERM' })
      }
      return rename(temporary, destination)
    })
    Object.defineProperty(process, 'platform', { ...descriptor, value: 'win32' })
    syncBuiltinESMExports()
    const retention = { mode: 'limited', snapshots: 2, ledgers: 2 }
    try {
      const pending = f.manager.configure({ ...f.settings, recovery_key: undefined,
        expected_revision: configured.configuration.revision, retention }, controller.signal)
      if (cancel) await assert.rejects(pending, { name: 'AbortError' })
      else assert.deepEqual((await pending).configuration.retention, retention)
    } finally {
      mock.mock.restore()
      syncBuiltinESMExports()
      Object.defineProperty(process, 'platform', descriptor)
    }
    const after = await readFile(path, 'utf8')
    assert.equal(calls, cancel ? 1 : 2)
    assert.equal(f.manager.busy, false)
    assert.ok(!after.includes(f.key))
    assert.equal(JSON.parse(after).sealed_key, JSON.parse(before).sealed_key)
    if (cancel) assert.equal(after, before)
    else assert.notEqual(JSON.parse(after).revision, JSON.parse(before).revision)
    assert.equal((await fs.readdir(f.root)).some(name => name.endsWith('.tmp')), false)
    await f.manager.run()
    assert.equal(f.calls[0].input.recovery_key, f.key)
  })
}

test('legacy settings keep every copy, and later schedule edits preserve the chosen retention', async t => {
  const f = await fixture(t)
  await f.manager.configure(f.settings)
  const path = join(f.root, 'backup-policy.json')
  const raw = JSON.parse(await readFile(path, 'utf8'))
  delete raw.retention
  await writeFile(path, JSON.stringify(raw), { mode: 0o600 })
  const legacy = await f.manager.status()
  assert.deepEqual(legacy.configuration.retention, { mode: 'keep_all', snapshots: 7, ledgers: 96 })
  const policy = { mode: 'limited', snapshots: 3, ledgers: 12 }
  const limited = await f.manager.configure({ ...f.settings, expected_revision: legacy.configuration.revision, retention: policy })
  const edited = await f.manager.configure({ ...f.settings, expected_revision: limited.configuration.revision, snapshot_hours: 12 })
  assert.deepEqual(edited.configuration.retention, policy)
  await f.manager.run()
  assert.deepEqual(f.calls[0].input.retention, policy)
})

test('offline inventory works with a locked key store and excludes concurrent configuration', async t => {
  const f = await fixture(t)
  const configured = await f.manager.configure(f.settings)
  f.locked(true); f.host.status.state = 'stopped'
  let release, entered
  const inside = new Promise(resolve => { entered = resolve })
  f.host.runBackup = async (action, input) => {
    assert.equal(action, 'backup-inventory')
    assert.equal(input.key_id, recoveryKeyId(f.key))
    assert.ok(!JSON.stringify(input).includes(f.key))
    entered(); await new Promise(resolve => { release = resolve })
    return { state: 'keep_all' }
  }
  const pending = f.manager.inventory()
  await inside
  await assert.rejects(f.manager.configure({ ...f.settings, expected_revision: configured.configuration.revision }), /Another local operation/)
  release()
  assert.equal((await pending).state, 'keep_all')
  assert.equal(f.manager.busy, false)
})

test('manual cleanup requires a current policy revision, reviewed plan and explicit confirmation', async t => {
  const f = await fixture(t)
  const configured = await f.manager.configure({ ...f.settings, retention: { mode: 'limited', snapshots: 2, ledgers: 2 } })
  const input = { expected_revision: configured.configuration.revision, plan_token: 'a'.repeat(64), confirm: true }
  f.host.runBackup = async (action, request) => { f.calls.push({ action, input: request }); return { state: 'complete', deleted_files: 2 } }
  await assert.rejects(f.manager.prune({ ...input, confirm: false }), /confirm/)
  await assert.rejects(f.manager.prune({ ...input, expected_revision: randomUUID() }), /confirm/)
  await assert.rejects(f.manager.prune({ ...input, plan_token: 'invalid' }), /confirm/)
  assert.equal(f.calls.length, 0)
  f.locked(true); f.host.status.state = 'stopped'
  assert.equal((await f.manager.prune(input)).deleted_files, 2)
  assert.equal(f.calls[0].action, 'backup-prune')
  assert.ok(!JSON.stringify(f.calls[0]).includes(f.key))
  assert.equal(f.calls[0].input.plan_token, input.plan_token)
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
