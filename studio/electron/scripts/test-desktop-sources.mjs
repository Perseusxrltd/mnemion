import assert from 'node:assert/strict'
import { randomUUID } from 'node:crypto'
import { setImmediate } from 'node:timers/promises'
import { test } from 'node:test'
import { DesktopSources } from '../dist/desktop-sources.js'
import { sourceProcess } from '../dist/desktop-source-process.js'
import { desktopAction } from '../dist/desktop-actions.js'
import { readCaptureArchive, readCapturePreview, readCaptureRecoveries, readCaptureRestored } from '../dist/capture-messages.js'
import { workspaceFixture, fixtureCredential as credential } from './workspace-fixture.mjs'

const report = () => ({ completed: true, timestamp: new Date().toISOString(), duration_seconds: 0.1,
  changed: 1, removed: 0, unchanged: 0, conflicts: 0, remote_sync_available: true })
const definition = () => ({ id: randomUUID(), endpoint: 'https://memory.example.invalid', tenant_id: randomUUID(),
  connector_id: randomUUID(), principal_id: randomUUID(), name: 'Folder', provider: 'filesystem', path: '/selected/folder',
  members: ['employee:alice'], publish_to_mapped_members: true, poll_seconds: 300, memory_limit_mib: 256,
  max_files: 10000, enabled: true })

async function fixture(t) {
  const f = await workspaceFixture(t)
  let document = { format: 1, revision: 'not-configured', sources: [] }, now = Date.now()
  const status = new Map()
  const state = { running: 0, maximum: 0, scans: [], stores: 0, failSave: false, loseSave: false, failVerify: false,
    statusCalls: [], failBegin: false, loseBegin: false, failFinish: false, loseFinish: false, corruptStatus: false,
    repairs: 0, loseRepair: false, failRepair: false, captureRetireRequests: [], failCaptureRetire: false }
  const settings = value => { const { enabled, status_epoch, ...other } = value; return JSON.stringify(other) }
  const call = async (request, signal, resources) => {
    if (request.operation === 'load') return structuredClone(document)
    if (request.operation.startsWith('status')) {
      state.statusCalls.push(request.operation)
      const current = document.sources.find(source => source.id === request.id)
      const record = status.get(request.id)
      if (request.operation === 'status') {
        if (state.corruptStatus) return { format: 1, sources: document.sources.map(source => ({ id: source.id,
          activity: { phase: 'attention', durability: 'unavailable', reason_code: 'source_status_invalid', repair_token: 'a'.repeat(64) } })) }
        return { format: 1, sources: document.sources.flatMap(source => {
          const saved = status.get(source.id)
          if (!saved || saved.epoch !== source.status_epoch) return []
          const activity = structuredClone(saved.activity)
          if (activity.phase === 'scanning' && saved.owner !== request.owner) Object.assign(activity, { phase: 'attention', reason_code: 'interrupted' })
          return [{ id: source.id, activity }]
        }) }
      }
      if (request.operation === 'status_repair') {
        assert.equal(request.expected_revision, document.revision)
        assert.ok(current)
        assert.equal(request.confirm, true)
        state.repairs++
        if (state.failRepair) throw new Error('synthetic repair refused')
        if (!state.corruptStatus || request.repair_token !== 'a'.repeat(64)) throw Object.assign(new Error('Changed observation'), { code: 'source_status_changed' })
        state.corruptStatus = false
        for (const source of document.sources) status.set(source.id, { epoch: source.status_epoch, owner: request.owner, run: randomUUID(),
          activity: { phase: 'waiting', durability: 'saved', reason_code: 'history_reset', next_scan_at: new Date(now + source.poll_seconds * 1000).toISOString() } })
        if (state.loseRepair) { state.loseRepair = false; throw new Error('synthetic lost repair return') }
        return { format: 1, repaired: true, history_restored: false, original_preserved: true }
      }
      if (request.operation === 'status_begin') {
        if (state.corruptStatus) throw Object.assign(new Error('private raw contents'), { code: 'source_status_invalid' })
        if (state.failBegin) throw new Error('private status write failure')
        assert.equal(request.expected_revision, document.revision)
        assert.ok(current?.enabled)
        const previous = record?.epoch === current.status_epoch ? record.activity : {}
        const activity = { phase: 'scanning', durability: 'saved', started_at: new Date(now).toISOString(),
          ...(previous.report ? { report: previous.report } : {}),
          ...(previous.last_success_report ? { last_success_report: previous.last_success_report } : {}),
          ...(previous.last_failure ? { last_failure: previous.last_failure } : {}) }
        status.set(current.id, { owner: request.owner, run: request.run, epoch: current.status_epoch, activity })
        if (state.loseBegin) { state.loseBegin = false; throw new Error('private reply lost after start') }
        return structuredClone({ format: 1, id: current.id, activity })
      }
      assert.equal(request.operation, 'status_finish')
      if (state.failFinish) throw new Error('private outcome persistence failure')
      if (!current || !record || record.epoch !== current.status_epoch) return { format: 1, ignored: true }
      assert.equal(record.owner, request.owner); assert.equal(record.run, request.run)
      assert.equal(record.activity.phase, 'scanning')
      const reason_code = request.reason_code ?? (request.report.completed ? undefined : 'partial')
      const activity = { ...record.activity, phase: reason_code ? 'attention' : 'complete',
        finished_at: new Date(now).toISOString(), next_scan_at: new Date(now + current.poll_seconds * 1000).toISOString(),
        ...(request.report ? { report: request.report } : {}), ...(request.report?.completed ? { last_success_report: request.report } : {}),
        ...(reason_code ? { reason_code, last_failure: { observed_at: new Date(now).toISOString(), reason_code } } : {}) }
      record.activity = activity
      if (state.loseFinish) { state.loseFinish = false; throw new Error('private reply lost after finish') }
      return structuredClone({ format: 1, id: current.id, activity })
    }
    if (request.operation === 'verify') {
      assert.equal(request.credential, credential)
      if (state.failVerify) throw new Error('Source identity mismatch')
      return structuredClone(request.source)
    }
    if (request.operation === 'store') {
      state.stores++
      if (state.failSave) throw new Error('Storage unavailable')
      assert.equal(request.expected_revision, document.revision)
      document = { format: 1, revision: randomUUID(), sources: structuredClone(request.sources).map(source => {
        const old = document.sources.find(item => item.id === source.id)
        return { ...source, status_epoch: old && settings(old) === settings(source) ? old.status_epoch : randomUUID() }
      }) }
      if (state.loseSave) { state.loseSave = false; throw new Error('Reply lost after commit') }
      return structuredClone(document)
    }
    if (request.operation === 'capture_retire') {
      state.captureRetireRequests.push(structuredClone(request))
      assert.equal(request.discard_local_inbox, true)
      if (state.failCaptureRetire) throw new Error('Workspace offline; capture revocation unconfirmed')
      return { retired: true, remote_grant_revoked: true, local_inbox_discarded: true }
    }
    assert.equal(request.operation, 'scan'); assert.equal(request.credential, credential)
    state.running++; state.maximum = Math.max(state.maximum, state.running)
    resources?.(42 * 1024 * 1024)
    try {
      return await new Promise((resolve, reject) => {
        signal.addEventListener('abort', () => reject(new Error('Stopped')), { once: true })
        state.scans.push({ id: request.source.id, privateRequest: structuredClone(request), finish: (value = report()) => resolve(value), fail: reject })
      })
    } finally { state.running-- }
  }
  const options = { call, cipher: f.cipher, now: () => now }
  const manager = new DesktopSources(options)
  t.after(() => manager.close())
  const add = async (source = definition()) => manager.configure({ source, credential, expected_revision: (await manager.status()).revision })
  const flush = async () => { await setImmediate(); await setImmediate() }
  return { ...f, manager, options, state, add, flush, document: () => document,
    advance: seconds => { now += seconds * 1000 } }
}

const retainedDefinition = () => ({ ...definition(), provider: 'conversations', capture_mode: 'messages',
  custody: { source_id: randomUUID(), grant_id: randomUUID(), keep_accepted: true, pending_limit_mib: 256 } })

const archiveReport = source => ({ format: 'mnemion-capture-archive-v1', created_at: '2026-10-21T04:00:00Z', name: source.name,
  binding: { tenant_id: source.tenant_id, connector_id: source.connector_id, source_id: source.custody.source_id,
    grant_id: source.custody.grant_id, namespace: 'selected-source', capture_mode: 'messages' },
  database_bytes: 81920, archive_sha256: 'c'.repeat(64), authenticated: true, workspace_credentials_included: false, source_enrolled: false,
  status: { format: 'mnemion-selected-inbox-v1', pending_events: 1, pending_bytes: 1024, database_bytes: 81920,
    stored_events: 0, forgotten_events: 0, unknown_pages: 1, over_limit: false,
    coverage: { format: 'mnemion-capture-coverage-v1', capture_mode: 'messages', catalog: 'unobserved',
      tracked_scopes: 0, checking_scopes: 0, failed_scopes: 0, missing_scopes: 0, uncertain_scopes: 0,
      unknown_prefix_scopes: 0, uncertain_intervals: 0, observed_bytes: 0, examined_prefix_bytes: 0,
      unaccepted_observed_bytes: 0, unresolved_previous_bytes: 0, records: { lines: 0, selected: 0, omitted: 0, unsupported: 0 },
      tracked_from: null, observed_at: null, complete_prefix_at: null, last_contact_at: null, last_acknowledged_at: null,
      queue_nonempty_since: null, history_before_tracking: 'unknown' } } })

test('capture backup unwraps only the inbox key and never replays an uncertain export', async t => {
  const f = await fixture(t), source = retainedDefinition(), calls = [], unsealed = []
  await f.add(source)
  let view = await f.manager.status()
  await f.manager.control('pause', { id: source.id, expected_revision: view.revision, enabled: false })
  const saved = f.document().sources[0]
  let lose = false
  const manager = new DesktopSources({ ...f.options, cipher: {
    available: () => f.cipher.available(), encrypt: value => f.cipher.encrypt(value),
    decrypt: async value => { unsealed.push(value.toString('base64')); assert.equal(value.toString('base64'), saved.sealed_inbox_key); return f.cipher.decrypt(value) },
  }, call: async (request, ...rest) => {
    if (request.operation !== 'capture_export') return f.options.call(request, ...rest)
    calls.push(request)
    if (lose) throw new Error('Export return lost after publication')
    return archiveReport(source)
  } })
  t.after(() => manager.close())
  view = await manager.status()
  const input = { id: source.id, expected_revision: view.revision, file: '/synthetic/backup.mnemion-capture', recovery_key: 'mnm_bk_' + 'x'.repeat(43), confirm: true }
  assert.deepEqual(await manager.backup(input), archiveReport(source))
  assert.equal(calls[0].credential, undefined); assert.equal(unsealed.length, 1)
  assert.equal(calls[0].inbox_key, await f.cipher.decrypt(Buffer.from(saved.sealed_inbox_key, 'base64')))
  lose = true
  await assert.rejects(manager.backup(input), /return lost/)
  assert.equal(calls.length, 2); assert.equal(manager.busy, false)
  assert.equal(desktopAction('source.backup', input).mutation, true)
})

test('capture archive inspection does not load damaged settings or open OS credentials', async t => {
  const source = retainedDefinition(), expected = archiveReport(source), requests = []
  const manager = new DesktopSources({ cipher: { available: () => { throw new Error('No OS key store') } },
    call: async request => { requests.push(request); assert.equal(request.operation, 'capture_inspect'); return expected } })
  t.after(() => manager.close())
  const input = { file: '/synthetic/backup.mnemion-capture', recovery_key: 'mnm_bk_' + 'x'.repeat(43) }
  assert.deepEqual(await manager.inspectBackup(input), expected)
  assert.equal(requests.length, 1)
  assert.equal(desktopAction('source.backup.inspect', input).mutation, false)
  assert.throws(() => readCaptureArchive({ ...expected, inbox_key: 'must not escape the helper' }))
  assert.throws(() => readCaptureArchive({ ...expected, workspace_credentials_included: true }))
})

const recoveryReport = source => ({ format: 'mnemion-capture-restored-v1', id: source.id, archive_sha256: 'c'.repeat(64),
  previous_grant_id: randomUUID(), grant_id: source.custody.grant_id, previous_grant_revoked: true,
  source_enrolled: true, source_enabled: false, status: archiveReport(source).status })

test('device recovery seals independent keys and reloads a committed source after a lost reply without replay', async t => {
  const f = await fixture(t), source = { ...retainedDefinition(), enabled: false }, requests = []
  const handle = 'native_session_administrator_handle'
  const manager = new DesktopSources({ ...f.options, retirementCredential: async (selected, supplied) => {
    assert.equal(supplied, handle); assert.equal(selected.endpoint, source.endpoint)
    assert.equal(selected.custody.grant_id, source.custody.grant_id)
    assert.equal(selected.sealed_key, undefined); assert.equal(selected.sealed_inbox_key, undefined)
    return 'one-use-administrator-token'
  }, call: async (request, ...rest) => {
    if (request.operation !== 'capture_restore') return f.options.call(request, ...rest)
    requests.push(request)
    assert.equal(request.credential, credential)
    assert.equal(request.retirement_credential, 'one-use-administrator-token')
    assert.equal(Buffer.from(request.inbox_key, 'base64').length, 32)
    assert.equal(await f.cipher.decrypt(Buffer.from(request.source.sealed_key, 'base64')), credential)
    assert.equal(await f.cipher.decrypt(Buffer.from(request.source.sealed_inbox_key, 'base64')), request.inbox_key)
    assert.notEqual(request.source.sealed_key, request.source.sealed_inbox_key)
    const document = f.document()
    document.sources = [structuredClone(request.source)]; document.revision = randomUUID()
    throw new Error('Synthetic return lost after source installation')
  } })
  t.after(() => manager.close())
  const input = { source, expected_revision: (await manager.status()).revision, credential,
    retirement_credential: handle, file: '/synthetic/backup.mnemion-capture',
    recovery_key: 'mnm_bk_' + 'x'.repeat(43), archive_sha256: 'c'.repeat(64), preview_hash: 'a'.repeat(64), confirm: true }
  await assert.rejects(manager.restore({ ...input, expected_revision: 'obsolete' }), /settings changed/)
  assert.equal(requests.length, 0)
  await assert.rejects(manager.restore(input), /return lost/)
  const view = await manager.status()
  assert.equal(view.sources.length, 1); assert.equal(view.sources[0].enabled, false)
  assert.equal(view.sources[0].activity.phase, 'paused')
  for (const secret of [credential, input.retirement_credential, 'one-use-administrator-token', requests[0].inbox_key,
    requests[0].source.sealed_key, requests[0].source.sealed_inbox_key]) assert.equal(JSON.stringify(view).includes(secret), false)
  await assert.rejects(manager.restore(input), /settings changed/)
  await assert.rejects(manager.restore({ ...input, expected_revision: view.revision }), /already exists/)
  assert.equal(requests.length, 1); assert.equal(manager.busy, false)
  assert.equal(desktopAction('source.restore', input).mutation, true)
})

test('finishing recovery unwraps protected intent keys; discard never unwraps the inbox or exposes private records', async t => {
  const f = await fixture(t), source = { ...retainedDefinition(), enabled: false }, unsealed = [], requests = []
  const inboxKey = Buffer.alloc(32, 7).toString('base64')
  const saved = { ...source, sealed_key: f.cipher.encrypt(credential).toString('base64'),
    sealed_inbox_key: f.cipher.encrypt(inboxKey).toString('base64') }
  const receipt = recoveryReport(source)
  const manager = new DesktopSources({ ...f.options, cipher: { ...f.cipher,
    decrypt: value => { unsealed.push(value.toString('base64')); return f.cipher.decrypt(value) } },
    call: async (request, ...rest) => {
      requests.push(request)
      if (request.operation === 'capture_restore_load') return { source: saved, archive_sha256: receipt.archive_sha256,
        previous_grant_id: receipt.previous_grant_id }
      if (request.operation === 'capture_restore_finish') {
        assert.equal(request.credential, credential); assert.equal(request.inbox_key, inboxKey)
        const document = f.document(); document.sources = [saved]; document.revision = randomUUID()
        return { document: structuredClone(document), recovery: receipt }
      }
      if (request.operation === 'capture_restore_discard') {
        assert.equal(request.credential, credential); assert.equal(request.inbox_key, undefined)
        return { discarded: true, replacement_grant_revoked: true, archive_modified: false }
      }
      return f.options.call(request, ...rest)
    } })
  t.after(() => manager.close())
  let input = { id: source.id, expected_revision: (await manager.status()).revision, confirm: true }
  const result = await manager.finishRecovery(input)
  assert.deepEqual(result.recovery, receipt); assert.equal(result.view.sources[0].enabled, false)
  assert.deepEqual(unsealed, [saved.sealed_key, saved.sealed_inbox_key])
  assert.equal(JSON.stringify(result).includes(credential), false); assert.equal(JSON.stringify(result).includes(inboxKey), false)
  assert.equal(JSON.stringify(result).includes(saved.sealed_inbox_key), false)
  // The private helper separately verifies that only an unfinished recovery can be discarded.
  input = { ...input, expected_revision: result.view.revision }
  unsealed.length = 0
  assert.deepEqual(await manager.finishRecovery(input, true), { discarded: true, replacement_grant_revoked: true, archive_modified: false })
  assert.deepEqual(unsealed, [saved.sealed_key])
  assert.equal(requests.filter(r => r.operation === 'capture_restore_finish').length, 1)
  assert.equal(desktopAction('source.restore.finish', input).mutation, true)
  assert.equal(desktopAction('source.restore.discard', input).mutation, true)
  assert.throws(() => readCaptureRestored({ ...receipt, credential }))
  assert.throws(() => readCaptureRestored({ ...receipt, previous_grant_id: receipt.grant_id }))
  assert.throws(() => readCaptureRestored({ ...receipt, previous_grant_revoked: false }))
})

test('recovery discovery needs no source settings or unlocked key store and rejects extra private fields', async t => {
  const source = retainedDefinition(), expected = { format: 'mnemion-capture-recoveries-v1', items: [{ id: source.id,
    name: source.name, endpoint: source.endpoint, archive_sha256: 'c'.repeat(64), created_at: '2026-10-21T04:00:00Z', copy_available: false }] }
  let fail = true, calls = 0
  const manager = new DesktopSources({ cipher: { available: () => { throw new Error('No OS key store') } },
    call: request => { calls++; assert.equal(request.operation, 'capture_restore_list')
      if (fail) throw new Error('Synthetic synchronous refusal')
      return Promise.resolve(expected)
    } })
  t.after(() => manager.close())
  await assert.rejects(manager.recoveries(), /synchronous refusal/)
  assert.equal(manager.busy, false)
  fail = false
  assert.deepEqual(await manager.recoveries(), expected); assert.equal(calls, 2)
  assert.equal(desktopAction('source.restore.list', {}).mutation, false)
  assert.throws(() => readCaptureRecoveries({ ...expected, items: [{ ...expected.items[0], sealed_key: 'private' }] }))
  assert.throws(() => readCaptureRecoveries({ ...expected, items: [expected.items[0], expected.items[0]] }))
})

test('background recovery reads coalesce without rejecting a user backup and are drained on close', async t => {
  const f = await fixture(t), source = { ...retainedDefinition(), enabled: false }
  await f.add(source)
  let finishRead, reads = 0, backups = 0
  const manager = new DesktopSources({ ...f.options, call: async (request, ...rest) => {
    if (request.operation === 'capture_restore_list') {
      reads++
      return new Promise(resolve => { finishRead = resolve })
    }
    if (request.operation === 'capture_export') { backups++; return archiveReport(source) }
    return f.options.call(request, ...rest)
  } })
  t.after(() => manager.close())
  const view = await manager.status()
  const first = manager.recoveries(), second = manager.recoveries()
  await f.flush()
  assert.equal(reads, 1); assert.equal(manager.busy, false)
  await manager.backup({ id: source.id, expected_revision: view.revision, file: '/synthetic/backup.mnemion-capture',
    recovery_key: 'mnm_bk_' + 'x'.repeat(43), confirm: true })
  assert.equal(backups, 1)
  let closed = false
  const closing = manager.close().then(() => { closed = true })
  await f.flush(); assert.equal(closed, false)
  finishRead({ format: 'mnemion-capture-recoveries-v1', items: [] })
  assert.deepEqual(await first, await second)
  await closing; assert.equal(closed, true)
  await assert.rejects(manager.recoveries(), /app update/)
})

const previewReport = () => ({ format: 'mnemion-capture-preview-v1', configuration_hash: 'a'.repeat(64), policy_revision: 'b'.repeat(64),
  observed_at: '2026-10-21T03:00:00+00:00', capture_mode: 'messages', catalog: 'complete', visited_entries: 1, read_bytes: 120,
  files: [{ path: 'selected/session.jsonl', status: 'sampled', file_bytes: 150, read_bytes: 120, prefix_bytes: 100,
    records: { lines: 2, selected: 1, omitted: 1, unsupported: 0 } }], records: { lines: 2, selected: 1, omitted: 1, unsupported: 0 },
  file_limit: 8, byte_limit: 1048576, attachment_binaries: 'not_read', external_links: 'not_followed', hidden_reasoning: 'unavailable',
  field_redaction: 'not_supported', automatic_expiry: 'not_enabled', content_saved: false })

test('capture preview is read-only and passes its reviewed hash to configuration', async t => {
  const f = await fixture(t), requests = []
  const manager = new DesktopSources({ ...f.options, call: async (request, ...rest) => {
    requests.push(request)
    return request.operation === 'preview' ? previewReport() : f.options.call(request, ...rest)
  } })
  t.after(() => manager.close())
  const source = { ...retainedDefinition(), capture_policy: { format: 'mnemion-capture-policy-v1', preset: 'selected',
    capture_mode: 'messages', include: ['selected/*.jsonl'], exclude: [], retention: 'until_deleted', max_file_bytes: 1e9, max_record_bytes: 2e6 } }
  const selection = { path: source.path, capture_mode: source.capture_mode, capture_policy: source.capture_policy,
    keep_accepted: true, memory_limit_mib: 256, max_files: 10000, pending_limit_mib: 256 }
  const result = await manager.preview(selection)
  assert.deepEqual(result, previewReport()); assert.equal(f.state.stores, 0)
  assert.deepEqual(requests.find(request => request.operation === 'preview'), { operation: 'preview', selection })
  await assert.rejects(manager.configure({ expected_revision: (await manager.status()).revision, source, credential }), /Preview the current capture settings/)
  assert.equal(f.state.stores, 0)
  const configured = await manager.configure({ expected_revision: (await manager.status()).revision, source, credential, preview_hash: result.configuration_hash })
  assert.equal(requests.find(request => request.operation === 'verify').preview_hash, result.configuration_hash)
  assert.deepEqual(configured.sources[0].capture_policy, source.capture_policy)
  assert.equal(manager.busy, false)
  assert.equal(desktopAction('source.preview', { selection }).mutation, false)
})

for (const [name, mutate] of [
  ['private content', value => { value.files[0].content = 'never cross the preview boundary' }],
  ['outside path', value => { value.files[0].path = '../outside.jsonl' }],
  ['inconsistent prefix', value => { value.files[0].prefix_bytes = 200 }],
  ['invented supported content', value => { value.hidden_reasoning = 'available' }],
  ['inconsistent aggregate', value => { value.read_bytes += 1 }],
]) test(`capture preview rejects ${name}`, () => {
  const result = previewReport(); mutate(result)
  assert.throws(() => readCapturePreview(result), /preview/)
})

test('a failed capture preview releases the controller for updates and later work', async t => {
  const f = await fixture(t)
  const manager = new DesktopSources({ ...f.options, call: (request, ...rest) => {
    if (request.operation === 'preview') throw new Error('synthetic helper failure')
    return f.options.call(request, ...rest)
  } })
  t.after(() => manager.close())
  await assert.rejects(manager.preview({}), /synthetic helper failure/)
  assert.equal(manager.busy, false)
  assert.equal((await manager.status()).sources.length, 0)
})

const coverage = () => ({ format: 'mnemion-capture-coverage-v1', capture_mode: 'messages', catalog: 'available',
  tracked_scopes: 1, checking_scopes: 0, failed_scopes: 0, missing_scopes: 0,
  uncertain_scopes: 0, unknown_prefix_scopes: 0, uncertain_intervals: 0,
  observed_bytes: 120, examined_prefix_bytes: 100, unaccepted_observed_bytes: 20,
  unresolved_previous_bytes: 0, records: { lines: 3, selected: 1, omitted: 1, unsupported: 1 },
  tracked_from: '2026-10-21T01:00:00+00:00', observed_at: '2026-10-21T01:01:00+00:00',
  complete_prefix_at: '2026-10-21T01:01:00+00:00', last_contact_at: null,
  last_acknowledged_at: null, queue_nonempty_since: '2026-10-21T01:01:00+00:00',
  history_before_tracking: 'unknown' })
const queuedCapture = () => ({ locally_accepted: 1, pending_events: 1, pending_bytes: 1024,
  remote_committed_events: 0, stored_events: 0, forgotten_events: 0, unknown_pages: 0,
  database_bytes: 65536, over_limit: false, capture_complete: true, delivery_complete: false,
  device_pending_bytes: 1024, device_database_bytes: 65536, reason_code: 'capture_delivery_unavailable',
  coverage: coverage() })

const indexProgress = () => ({ status: 'available', last_attempt_at: '2026-10-21T02:00:00+00:00', active: null,
  completed: { generation_id: 'fixture-generation', inference_paused: false,
    started_at: '2026-10-21T01:59:00+00:00', observed_at: '2026-10-21T02:00:00+00:00',
    pages: 1, next_cursor: null, counts: { events: 10, lexical_indexed: 10, vector_indexed: 8,
      waiting: 2, failed: 0, withheld: 0, forgotten: 0, unknown: 0 } } })

test('coverage stays available to native agents after a desktop restart', async t => {
  const f = await fixture(t)
  await f.add(retainedDefinition()); await f.manager.start(); await f.flush()
  const capture = queuedCapture()
  capture.coverage.index = indexProgress()
  f.state.scans[0].finish({ ...report(), completed: false, changed: 0, remote_sync_available: false, capture })
  await f.flush()
  assert.deepEqual((await f.manager.status()).sources[0].activity.report.capture.coverage, capture.coverage)
  await f.manager.close()
  const reopened = new DesktopSources(f.options); t.after(() => reopened.close())
  assert.deepEqual((await reopened.status()).sources[0].activity.report.capture.coverage, capture.coverage)
})

for (const [name, damage] of [
  ['counter inconsistency', value => { value.records.selected = 30 }],
  ['unknown content field', value => { value.raw_body = 'Never render this arbitrary field' }],
  ['unknown selection', value => { value.capture_mode = 'all' }],
  ['invalid time', value => { value.last_contact_at = 'not-a-time' }],
  ['unsafe integer', value => { value.observed_bytes = Number.MAX_SAFE_INTEGER + 1 }],
  ['invented history completeness', value => { value.history_before_tracking = 'complete' }],
  ['inconsistent index counts', value => { value.index = indexProgress(); value.index.completed.counts.vector_indexed = 10 }],
  ['incomplete index marked complete', value => { value.index = indexProgress(); value.index.completed.next_cursor = '1'.repeat(64) }],
  ['invalid index observation time', value => { value.index = indexProgress(); value.index.completed.observed_at = 'yesterday' }],
  ['unbounded model identity', value => { value.index = indexProgress(); value.index.completed.generation_id = 'x'.repeat(129) }],
]) test(`invalid coverage is visible as a source error: ${name}`, async t => {
  const f = await fixture(t)
  await f.add(retainedDefinition()); await f.manager.start(); await f.flush()
  const capture = queuedCapture(); damage(capture.coverage)
  f.state.scans[0].finish({ ...report(), completed: false, changed: 0, remote_sync_available: false, capture })
  await f.flush()
  const activity = (await f.manager.status()).sources[0].activity
  assert.equal(activity.phase, 'attention')
  assert.equal(activity.reason_code, 'source_invalid_response')
  assert.equal(activity.report, undefined)
})

test('retained capture keeps an independent protected key and sends it only through the scan pipe', async t => {
  const f = await fixture(t), source = retainedDefinition()
  let view = await f.add(source)
  const sealed = f.document().sources[0].sealed_inbox_key
  const privateKey = await f.cipher.decrypt(Buffer.from(sealed, 'base64'))
  assert.equal(Buffer.from(privateKey, 'base64').length, 32)
  assert.notEqual(privateKey, credential)
  assert.ok(!JSON.stringify(view).includes('sealed_inbox_key'))
  assert.ok(!JSON.stringify(view).includes(privateKey))
  view = await f.manager.configure({ expected_revision: view.revision,
    source: { ...source, custody: { ...source.custody, pending_limit_mib: 128 } } })
  assert.equal(f.document().sources[0].sealed_inbox_key, sealed, 'Changing a limit cannot replace the inbox key')
  await f.manager.start(); await f.flush()
  assert.equal(f.state.scans[0].privateRequest.inbox_key, privateKey)
  assert.ok(!JSON.stringify(f.state.scans[0].privateRequest.source).includes(privateKey))
  const capture = { locally_accepted: 2, pending_events: 2, pending_bytes: 1024, remote_committed_events: 0,
    stored_events: 0, forgotten_events: 0, unknown_pages: 0, database_bytes: 65536, over_limit: false,
    capture_complete: true, delivery_complete: false, device_pending_bytes: 1024, device_database_bytes: 65536,
    reason_code: 'capture_delivery_unavailable' }
  f.state.scans[0].finish({ ...report(), completed: false, changed: 0, remote_sync_available: false, capture })
  await f.flush()
  const activity = (await f.manager.status()).sources[0].activity
  assert.equal(activity.phase, 'attention')
  assert.equal(activity.durability, 'saved')
  assert.deepEqual(activity.report.capture, capture)
})

test('retained source removal requires pause, explicit discard and confirmed native retirement', async t => {
  const f = await fixture(t), source = retainedDefinition()
  let view = await f.add(source)
  const remove = () => ({ expected_revision: view.revision, id: source.id, confirm: true, discard_local_inbox: true })
  await assert.rejects(f.manager.control('remove', remove()), /Pause/)
  assert.equal(f.state.captureRetireRequests.length, 0)
  view = await f.manager.control('pause', { expected_revision: view.revision, id: source.id, enabled: false })
  await assert.rejects(f.manager.control('remove', { ...remove(), discard_local_inbox: undefined }), /Confirm discarding/)
  f.state.failCaptureRetire = true
  await assert.rejects(f.manager.control('remove', remove()), /unconfirmed/)
  assert.equal(f.document().sources.length, 1)
  assert.ok(f.document().sources[0].sealed_inbox_key)
  f.state.failCaptureRetire = false
  view = await f.manager.control('remove', remove())
  assert.equal(view.sources.length, 0)
  assert.equal(f.state.captureRetireRequests[1].credential, credential)
})

test('lost enrollment reply retains the first key and a damaged key stops scans visibly', async t => {
  const f = await fixture(t), source = retainedDefinition()
  f.state.loseSave = true
  await assert.rejects(f.add(source), /lost/)
  const sealed = f.document().sources[0].sealed_inbox_key
  const view = await f.manager.status()
  await f.manager.configure({ expected_revision: view.revision, source })
  assert.equal(f.document().sources[0].sealed_inbox_key, sealed)
  await f.manager.close()
  f.document().sources[0].sealed_inbox_key = Buffer.from('damaged sealed key').toString('base64')
  const reopened = new DesktopSources(f.options)
  t.after(() => reopened.close())
  await reopened.start(); await f.flush()
  assert.equal(f.state.scans.length, 0)
  const activity = (await reopened.status()).sources[0].activity
  assert.equal(activity.reason_code, 'capture_key_unavailable')
  assert.equal(activity.durability, 'saved')
})

test('one-use removal authority can replace a lost device key without changing saved capture keys', async t => {
  const f = await fixture(t), source = { ...retainedDefinition(), enabled: false }
  const view = await f.add(source), original = JSON.stringify(f.document())
  const handle = 'private_native_administrator_handle', replacement = 'private_administrator_fixture_key'
  f.options.cipher = { available: () => false, encrypt: () => { throw new Error('must not save a key') }, decrypt: () => { throw new Error('lost device key') } }
  f.options.retirementCredential = async (bound, supplied) => {
    assert.equal(supplied, handle); assert.equal(bound.endpoint, source.endpoint)
    assert.equal(bound.custody.grant_id, source.custody.grant_id)
    assert.ok(!Object.hasOwn(bound, 'sealed_inbox_key'))
    return replacement
  }
  f.state.failCaptureRetire = true
  const input = { expected_revision: view.revision, id: source.id, confirm: true,
    discard_local_inbox: true, retirement_credential: handle }
  await assert.rejects(f.manager.control('remove', input), /unconfirmed/)
  assert.equal(JSON.stringify(f.document()), original)
  assert.equal(f.state.captureRetireRequests[0].credential, replacement)
  assert.ok(!JSON.stringify(await f.manager.status()).includes(replacement))
  f.state.failCaptureRetire = false
  assert.equal((await f.manager.control('remove', input)).sources.length, 0)
  assert.ok(!JSON.stringify(f.document()).includes(replacement))
})

test('source configuration persists protected keys, reopens and refuses a stale revision', async t => {
  const f = await fixture(t), initial = await f.manager.status(), source = { ...definition(), provider: 'conversations', capture_mode: 'messages' }
  const configured = await f.add(source)
  assert.equal(configured.sources[0].connector_id, source.connector_id)
  assert.ok(!JSON.stringify(configured).includes(credential))
  assert.ok(!JSON.stringify(configured).includes('sealed_key'))
  assert.ok(!JSON.stringify(configured).includes('status_epoch'))
  assert.ok(!JSON.stringify(f.document()).includes(credential))
  assert.equal(f.cipher.decrypt(Buffer.from(f.document().sources[0].sealed_key, 'base64')), credential)
  const reopened = new DesktopSources(f.options)
  t.after(() => reopened.close())
  assert.deepEqual((await reopened.status()).sources.map(s => s.id), [source.id])
  assert.equal((await reopened.status()).sources[0].capture_mode, 'messages')
  await assert.rejects(f.manager.control('pause', { id: source.id, expected_revision: initial.revision, enabled: false }), /changed/)
  assert.equal((await f.manager.status()).sources[0].enabled, true)
})

test('successful observations and next due time survive restart without changing settings', async t => {
  const f = await fixture(t), source = definition()
  await f.add(source)
  const revision = (await f.manager.status()).revision
  await f.manager.start(); await f.flush()
  const observed = report()
  f.state.scans[0].finish(observed); await f.flush()
  const before = (await f.manager.status()).sources[0].activity
  assert.equal(before.phase, 'complete'); assert.equal(before.durability, 'saved')
  assert.deepEqual(before.last_success_report, observed)
  assert.equal((await f.manager.status()).revision, revision)
  await f.manager.close()
  const reopened = new DesktopSources(f.options)
  t.after(() => reopened.close())
  assert.deepEqual((await reopened.status()).sources[0].activity, before)
  await reopened.start(); await f.flush()
  assert.equal(f.state.scans.length, 1, 'A restart retains the next due time')
  f.advance(301)
  const work = reopened.tick(); await f.flush()
  assert.equal(f.state.scans.length, 2)
  f.state.scans[1].finish(); await work
  assert.equal(f.state.stores, 1)
})

test('failed and partial scans retain the last good report without recording raw errors', async t => {
  const f = await fixture(t), source = definition()
  await f.add(source); await f.manager.start(); await f.flush()
  const good = report()
  f.state.scans[0].finish(good); await f.flush()
  f.advance(301)
  const failure = f.manager.tick(); await f.flush()
  f.state.scans[1].fail(Object.assign(new Error('SECRET raw provider response'), { code: 'provider_rate_limited' }))
  await failure
  let activity = (await f.manager.status()).sources[0].activity
  assert.equal(activity.phase, 'attention'); assert.equal(activity.reason_code, 'provider_rate_limited')
  assert.equal(activity.durability, 'saved'); assert.deepEqual(activity.last_success_report, good)
  assert.ok(!JSON.stringify(activity).includes('SECRET'))
  assert.match(activity.message, /rate limit/)
  const reopened = new DesktopSources(f.options)
  t.after(() => reopened.close())
  assert.deepEqual((await reopened.status()).sources[0].activity, activity)
  f.advance(301)
  const partial = f.manager.tick(); await f.flush()
  f.state.scans[2].finish({ ...report(), completed: false, changed: 2 }); await partial
  activity = (await f.manager.status()).sources[0].activity
  assert.equal(activity.reason_code, 'partial'); assert.equal(activity.report.changed, 2)
  assert.deepEqual(activity.last_success_report, good)
  f.advance(301)
  const complete = f.manager.tick(); await f.flush()
  f.state.scans[3].finish(); await complete
  const recovered = (await f.manager.status()).sources[0].activity
  assert.equal(recovered.phase, 'complete'); assert.equal(recovered.last_failure.reason_code, 'partial')
})

test('unfinished scans appear interrupted to a fresh controller, never successful', async t => {
  const f = await fixture(t), source = definition()
  await f.add(source); await f.manager.start(); await f.flush()
  const reopened = new DesktopSources(f.options)
  t.after(() => reopened.close())
  const activity = (await reopened.status()).sources[0].activity
  assert.equal(activity.phase, 'attention'); assert.equal(activity.reason_code, 'interrupted')
  assert.equal(activity.durability, 'saved'); assert.ok(activity.started_at)
  assert.equal(activity.finished_at, undefined); assert.equal(activity.last_success_report, undefined)
  assert.match(activity.message, /unknown/)
})

for (const loss of ['failBegin', 'loseBegin']) test('unconfirmed start performs no scan and no automatic replay: ' + loss, async t => {
  const f = await fixture(t), source = definition()
  await f.add(source); f.state[loss] = true
  await f.manager.start(); await f.flush()
  const activity = (await f.manager.status()).sources[0].activity
  assert.equal(f.state.scans.length, 0)
  assert.equal(activity.phase, 'attention'); assert.equal(activity.durability, 'unavailable')
  assert.equal(activity.reason_code, 'source_status_unavailable')
  assert.ok(!JSON.stringify(activity).includes('private'))
  await f.manager.tick()
  assert.equal(f.state.statusCalls.filter(call => call === 'status_begin').length, 1)
  const reopened = new DesktopSources(f.options)
  t.after(() => reopened.close())
  assert.equal((await reopened.status()).sources[0].activity.reason_code, loss === 'loseBegin' ? 'interrupted' : undefined)
})

for (const loss of ['failFinish', 'loseFinish']) test('unconfirmed outcome remains attention and finish is never replayed: ' + loss, async t => {
  const f = await fixture(t), source = definition()
  await f.add(source); await f.manager.start(); await f.flush()
  f.state[loss] = true
  f.state.scans[0].finish(); await f.flush()
  const activity = (await f.manager.status()).sources[0].activity
  assert.equal(activity.phase, 'attention'); assert.equal(activity.durability, 'unavailable')
  assert.equal(activity.reason_code, 'source_status_unavailable')
  assert.equal(f.state.statusCalls.filter(call => call === 'status_finish').length, 1)
  assert.equal(f.state.scans.length, 1)
  const reopened = new DesktopSources(f.options)
  t.after(() => reopened.close())
  const recovered = (await reopened.status()).sources[0].activity
  assert.equal(recovered.phase, loss === 'loseFinish' ? 'complete' : 'attention')
  assert.equal(recovered.reason_code, loss === 'loseFinish' ? undefined : 'interrupted')
})

test('unknown exception codes and malformed reports never expose private data', async t => {
  const f = await fixture(t), source = definition()
  await f.add(source); await f.manager.start(); await f.flush()
  f.state.scans[0].fail(Object.assign(new Error('SECRET message'), { code: 'SECRET arbitrary code' })); await f.flush()
  let activity = (await f.manager.status()).sources[0].activity
  assert.equal(activity.reason_code, 'source_unavailable')
  assert.ok(!JSON.stringify(activity).includes('SECRET'))
  f.advance(301)
  const malformed = f.manager.tick(); await f.flush()
  f.state.scans[1].finish({ ...report(), raw_events: ['SECRET transcript'] }); await malformed
  activity = (await f.manager.status()).sources[0].activity
  assert.equal(activity.reason_code, 'source_invalid_response')
  assert.equal(activity.phase, 'attention'); assert.equal(activity.report, undefined)
  assert.ok(!JSON.stringify(activity).includes('SECRET'))
})

test('damaged observations preserve offline pause/removal and configuration changes clear old reports', async t => {
  const f = await fixture(t), source = definition()
  await f.add(source); await f.manager.start(); await f.flush()
  f.state.scans[0].finish(); await f.flush()
  const paused = await f.manager.control('pause', { expected_revision: (await f.manager.status()).revision, id: source.id, enabled: false })
  assert.ok(paused.sources[0].activity.last_success_report)
  const changed = await f.manager.configure({ expected_revision: paused.revision, source: { ...source, enabled: false, max_files: 25 } })
  assert.equal(changed.sources[0].activity.last_success_report, undefined)
  f.state.corruptStatus = true
  const reopened = new DesktopSources(f.options)
  t.after(() => reopened.close())
  const status = await reopened.status()
  assert.equal(status.sources[0].activity.reason_code, 'source_status_invalid')
  assert.equal(status.sources[0].activity.phase, 'paused')
  assert.ok(!JSON.stringify(status).includes('private raw contents'))
  await reopened.control('pause', { expected_revision: status.revision, id: source.id, enabled: false })
  assert.deepEqual((await reopened.control('remove', { expected_revision: (await reopened.status()).revision,
    id: source.id, confirm: true })).sources, [])
})

test('explicit app/agent repair resets device history honestly without settings changes or immediate scans', async t => {
  const f = await fixture(t), first = definition(), second = { ...definition(), enabled: false }
  await f.add(first); await f.add(second)
  const original = structuredClone(f.document())
  f.state.corruptStatus = true
  const manager = new DesktopSources(f.options)
  t.after(() => manager.close())
  let view = await manager.status()
  const token = view.sources[0].activity.repair_token
  assert.equal(token, 'a'.repeat(64))
  const input = { expected_revision: view.revision, id: first.id, repair_token: token, confirm: true }
  assert.match(desktopAction('source.repair', input).description, /every source/)
  await assert.rejects(manager.control('repair', { ...input, confirm: false }), /confirm repair/)
  assert.equal(f.state.repairs, 0)
  await manager.start(); await f.flush()
  assert.equal(f.state.scans.length, 0)
  view = await manager.control('repair', input)
  assert.equal(f.state.repairs, 1); assert.equal(f.state.scans.length, 0)
  assert.deepEqual(f.document(), original)
  assert.equal(view.revision, original.revision)
  for (const source of view.sources) {
    assert.equal(source.activity.reason_code, 'history_reset')
    assert.equal(source.activity.last_success_report, undefined)
    assert.equal(source.activity.repair_token, undefined)
    assert.equal(source.activity.durability, 'saved')
  }
  assert.equal(view.sources.find(source => source.id === second.id).activity.phase, 'paused')
  await manager.tick(); await f.flush()
  assert.equal(f.state.scans.length, 0, 'Repair must not cause a scan')
  const reopened = new DesktopSources(f.options)
  t.after(() => reopened.close())
  assert.deepEqual((await reopened.status()).sources, view.sources)
  f.advance(301)
  const work = manager.tick(); await f.flush()
  assert.equal(f.state.scans.length, 1, 'Normal enabled scheduling resumes at its next interval')
  f.state.scans[0].finish(); await work
})

test('a lost repair reply is read back, never replayed and never mislabeled restored history', async t => {
  const f = await fixture(t), source = definition()
  await f.add(source); f.state.corruptStatus = true
  const manager = new DesktopSources(f.options)
  t.after(() => manager.close())
  const before = await manager.status()
  f.state.loseRepair = true
  await assert.rejects(manager.control('repair', { expected_revision: before.revision, id: source.id,
    repair_token: before.sources[0].activity.repair_token, confirm: true }), /lost repair/)
  const after = await manager.status()
  assert.equal(after.sources[0].activity.reason_code, 'history_reset')
  assert.equal(after.sources[0].activity.last_success_report, undefined)
  assert.equal(f.state.repairs, 1); assert.equal(f.state.scans.length, 0)
  await manager.start(); await f.flush()
  assert.equal(f.state.repairs, 1); assert.equal(f.state.scans.length, 0)
})

test('repair cannot race an active source scan', async t => {
  const f = await fixture(t), source = definition()
  await f.add(source); await f.manager.start(); await f.flush()
  await assert.rejects(f.manager.control('repair', { expected_revision: (await f.manager.status()).revision,
    id: source.id, repair_token: 'a'.repeat(64), confirm: true }), /active source scan/)
  assert.equal(f.state.repairs, 0); assert.equal(f.state.running, 1)
})

for (const [code, expected] of [['source_memory_limit', 'source_memory_limit'],
  ['source_status_invalid', 'source_status_invalid'], ['SECRET raw diagnostic', 'source_unavailable']]) {
  test('native helper forwards only known error codes: ' + expected + '/' + (code === expected), async () => {
    const script = `process.stdin.resume(); process.stdin.on('end', () => { process.stdout.write(JSON.stringify({ event: 'result', ok: false, error: ${JSON.stringify(code)} }) + '\\n'); process.exitCode = 2; });`
    const call = sourceProcess({ executable: process.execPath, prefix: ['-e', script, '--'],
      command: 'synthetic-source', root: 'unused-private-fixture', privateRoots: [], environment: {}, deadlineMs: 5000 })
    await assert.rejects(call({ operation: 'status' }), error => {
      assert.equal(error.code, expected)
      assert.ok(!error.message.includes('SECRET'))
      return true
    })
  })
}

test('unavailable OS storage and a wrong identity do not persist a source', async t => {
  const f = await fixture(t)
  f.cipher.unlocked = false
  await assert.rejects(f.add(), /Unlock OS/)
  assert.equal(f.state.stores, 0)
  f.cipher.unlocked = true; f.state.failVerify = true
  await assert.rejects(f.add(), /identity mismatch/)
  assert.equal(f.state.stores, 0)
  assert.deepEqual((await f.manager.status()).sources, [])
})

test('one active scan and one queued request survive pause and update preparation', async t => {
  const f = await fixture(t), first = definition(), second = definition()
  await f.add(first); await f.add(second); await f.manager.start(); await f.flush()
  assert.equal(f.state.scans.length, 1); assert.equal(f.manager.memoryBytes, 42 * 1024 * 1024)
  assert.equal(f.manager.pauseForUpdate(), false)
  const revision = (await f.manager.status()).revision
  await f.manager.control('sync', { id: first.id, expected_revision: revision })
  await f.manager.control('sync', { id: first.id, expected_revision: revision })
  f.state.scans[0].finish(); await f.flush()
  const queued = f.manager.tick(); await f.flush()
  assert.equal(f.state.scans.length, 2); assert.equal(f.state.scans[1].id, second.id, 'Repeated requests cannot starve another due source')
  f.state.scans[1].finish(); await queued
  assert.equal(f.manager.memoryBytes, 0); assert.equal(f.state.maximum, 1)
  assert.equal(f.manager.pauseForUpdate(), true)
  await f.manager.tick(); assert.equal(f.state.scans.length, 2)
  f.manager.resumeAfterUpdate(); await f.flush()
  assert.equal(f.state.scans[2].id, first.id)
  const paused = await f.manager.control('pause', { id: first.id, expected_revision: revision, enabled: false })
  assert.equal(paused.sources.find(s => s.id === first.id).activity.phase, 'paused')
  assert.equal(f.state.running, 0)
  assert.equal(f.manager.memoryBytes, 0)
  f.advance(3600)
  const work = f.manager.tick(); await f.flush()
  assert.equal(f.state.scans.at(-1).id, second.id)
  f.state.scans.at(-1).finish(); await work
})

test('a failed pause retains enabled settings; successful removal drains its scan', async t => {
  const f = await fixture(t), source = definition()
  await f.add(source); await f.manager.start(); await f.flush()
  const revision = (await f.manager.status()).revision
  f.state.failSave = true
  await assert.rejects(f.manager.control('pause', { id: source.id, expected_revision: revision, enabled: false }), /Storage unavailable/)
  assert.equal((await f.manager.status()).sources[0].enabled, true)
  assert.equal(f.state.running, 1)
  f.state.failSave = false
  await assert.rejects(f.manager.control('remove', { id: source.id, expected_revision: revision }), /Confirm removal/)
  const removed = await f.manager.control('remove', { id: source.id, expected_revision: revision, confirm: true })
  assert.deepEqual(removed.sources, []); assert.equal(f.state.running, 0)
})

test('a committed write with a lost reply is reloaded rather than replayed', async t => {
  const f = await fixture(t), source = definition()
  f.state.loseSave = true
  await assert.rejects(f.add(source), /Reply lost/)
  const recovered = await f.manager.status()
  assert.equal(recovered.sources[0].id, source.id)
  assert.equal(f.state.stores, 1)
  await f.manager.control('pause', { id: source.id, expected_revision: recovered.revision, enabled: false })
  assert.equal(f.state.stores, 2)
})

test('an existing source cannot silently switch to a different folder or workspace', async t => {
  const f = await fixture(t), source = { ...definition(), scope_id: 'established-office' }
  await f.add(source)
  assert.equal((await f.manager.status()).sources[0].scope_id, 'established-office')
  for (const field of ['path', 'endpoint', 'tenant_id', 'connector_id', 'principal_id', 'provider']) {
    await assert.rejects(f.manager.configure({ expected_revision: (await f.manager.status()).revision,
      source: { ...source, [field]: 'different' } }), /new connection/)
  }
  await assert.rejects(f.manager.configure({ expected_revision: (await f.manager.status()).revision,
    source: { ...source, scope_id: 'another-folder' } }), /folder identity changed/)
  assert.equal(f.state.stores, 1)
  for (const action of ['source.status', 'source.configure', 'source.pause', 'source.sync', 'source.remove', 'source.repair']) {
    assert.equal(desktopAction(action, {}).workspace, false)
    assert.throws(() => desktopAction(action, { arbitrary_shell: 'forbidden' }), /unsupported input/)
  }
})

test('an existing default conversation identity cannot silently change', async t => {
  const f = await fixture(t), source = { ...definition(), provider: 'conversations' }
  await f.add(source)
  await assert.rejects(f.manager.configure({ expected_revision: (await f.manager.status()).revision,
    source: { ...source, scope_id: 'different-conversation' } }), /folder identity changed/)
  assert.equal(f.state.stores, 1)
  assert.equal((await f.manager.status()).sources[0].scope_id, undefined)
})

for (const provider of ['slack', 'gdrive']) test('cloud credentials remain separate and protected across restart and scan: ' + provider, async t => {
  const f = await fixture(t), originalCall = f.options.call, privateCalls = []
  f.options.call = async (...args) => {
    if (['verify', 'scan'].includes(args[0].operation)) privateCalls.push(structuredClone(args[0]))
    return originalCall(...args)
  }
  const { path: _path, ...common } = definition()
  const source = { ...common, provider, ...(provider === 'slack'
    ? { slack: { team_id: 'T123', channels: ['C123'], include_threads: false } }
    : { gdrive: { folder_ids: ['selected-folder'], file_ids: [], recursive: true } }) }
  const secret = provider === 'slack' ? 'private-slack-provider-fixture' : '{"private_key":"synthetic-google-key-fixture"}'
  const first = await f.manager.configure({ expected_revision: (await f.manager.status()).revision,
    source, credential, provider_credential: secret })
  assert.ok(!JSON.stringify(first).includes(secret))
  assert.ok(!JSON.stringify(first).includes('sealed_provider'))
  assert.ok(!JSON.stringify(f.document()).includes(secret))
  assert.equal(f.cipher.decrypt(Buffer.from(f.document().sources[0].sealed_provider, 'base64')), secret)
  assert.equal(f.cipher.decrypt(Buffer.from(f.document().sources[0].sealed_key, 'base64')), credential)
  const reopened = new DesktopSources(f.options)
  t.after(() => reopened.close())
  assert.deepEqual((await reopened.status()).sources.map(s => s.id), [source.id])
  await f.manager.configure({ expected_revision: first.revision, source })
  assert.equal(privateCalls.at(-1).provider_credential, secret, 'blank replacement retains the private provider key')
  if (provider === 'slack') await assert.rejects(f.manager.configure({
    expected_revision: (await f.manager.status()).revision,
    source: { ...source, slack: { ...source.slack, team_id: 'T456' } },
    provider_credential: 'new-private-slack-fixture',
  }), /new connection/)
  await f.manager.start(); await f.flush()
  assert.equal(privateCalls.at(-1).operation, 'scan')
  assert.equal(privateCalls.at(-1).provider_credential, secret)
  assert.equal(privateCalls.at(-1).credential, credential)
  assert.ok(!Object.hasOwn(privateCalls.at(-1).source, 'sealed_provider'))
  const removed = await f.manager.control('remove', { expected_revision: (await f.manager.status()).revision,
    id: source.id, confirm: true })
  assert.deepEqual(removed.sources, [])
  assert.deepEqual(f.document().sources, [])
  assert.equal(f.state.running, 0)
})
