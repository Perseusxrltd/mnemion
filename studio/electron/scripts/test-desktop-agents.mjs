import assert from 'node:assert/strict'
import { setImmediate } from 'node:timers/promises'
import { test } from 'node:test'
import { DesktopAgents } from '../dist/desktop-agents.js'
import { desktopAction } from '../dist/desktop-actions.js'

test('agent installation serializes settings work and drains cancellation before closing', async () => {
  let active = 0, closed = false
  const manager = new DesktopAgents(async (request, signal) => {
    if (request.operation === 'status') return { profiles: [], installations: [], credential_storage: 'private_os_account_file', max_installations: 64 }
    active++
    try { return await new Promise((resolve, reject) => signal.addEventListener('abort', () => setImmediate().then(() => { closed = true; reject(new Error('Cancelled')) }), { once: true })) }
    finally { active-- }
  })
  const installation = manager.install({ setup: {}, configuration_hash: null, credential: 'private-fixture', confirm: true, replace_existing: false })
  const rejected = assert.rejects(installation, /Cancelled/)
  assert.equal(manager.busy, true)
  assert.equal(manager.pauseForUpdate(), false)
  await assert.rejects(manager.remove({ id: 'fixture', configuration_hash: null, confirm: true }), /current agent/)
  await manager.close(); await rejected
  assert.equal(closed, true); assert.equal(active, 0); assert.equal(manager.busy, false)
  await assert.rejects(manager.preview({}), /updating or closing/)
})

test('update suspension blocks new previews and mutations until cancellation resumes the app', async () => {
  let calls = 0
  const manager = new DesktopAgents(async request => { calls++; return request.operation === 'status' ? { profiles: [], installations: [] } : { setup: {} } })
  assert.equal(manager.pauseForUpdate(), true)
  await assert.rejects(manager.preview({}), /updating or closing/)
  await assert.rejects(manager.install({ setup: {}, configuration_hash: null, credential: 'fixture', confirm: true, replace_existing: false }), /updating or closing/)
  assert.equal(calls, 0)
  manager.resumeAfterUpdate()
  await manager.preview({}); assert.equal(calls, 1)
  await manager.close()
  for (const action of ['agent.status', 'agent.preview', 'agent.install', 'agent.remove']) {
    assert.equal(desktopAction(action, {}).workspace, false)
    assert.throws(() => desktopAction(action, { shell_command: 'unreviewed' }), /unsupported input/)
  }
})

test('status overlapping maintenance receives a fresh complete projection', async () => {
  let release
  const gate = new Promise(resolve => { release = resolve })
  const operations = []
  const full = {
    profiles: [{ client: 'codex', config_path: '/fixture.toml', exists: true, custom_path_required: false }],
    installations: [{ id: 'fixture', state: 'installed', configuration_hash: 'abc', private_key_file_exists: true, agent_restart_required: true }],
    credential_storage: 'private_os_account_file', max_installations: 64, runtime_version: '9.9.9', runtime_attention: null,
  }
  const manager = new DesktopAgents(async request => {
    operations.push(request.operation)
    if (request.operation === 'maintain') { await gate; return { runtime_attention: 'partial' } }
    return full
  })
  try {
    manager.start()
    const pending = manager.status()
    release()
    assert.deepEqual(await pending, full)
    assert.deepEqual(operations, ['maintain', 'status'])
  } finally { await manager.close() }
})

test('active maintenance blocks updates and drains before any later call', async () => {
  let active = 0, closed = false, calls = 0
  const manager = new DesktopAgents(async (request, signal) => {
    calls++
    assert.equal(request.operation, 'maintain')
    active++
    try {
      return await new Promise((resolve, reject) => signal.addEventListener('abort', () => setImmediate().then(() => { closed = true; reject(new Error('Cancelled')) }), { once: true }))
    } finally { active-- }
  })
  manager.start()
  assert.equal(manager.busy, true)
  assert.equal(manager.pauseForUpdate(), false)
  const pendingStatus = manager.status()
  const removal = manager.remove({ id: 'fixture', configuration_hash: null, confirm: true })
  const statusRejected = assert.rejects(pendingStatus, /updating or closing/)
  const removalRejected = assert.rejects(removal, /updating or closing/)
  await manager.close()
  await statusRejected
  await removalRejected
  assert.equal(closed, true)
  assert.equal(active, 0)
  assert.equal(manager.busy, false)
  assert.equal(calls, 1)
})
