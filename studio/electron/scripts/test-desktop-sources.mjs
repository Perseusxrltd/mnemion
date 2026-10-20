import assert from 'node:assert/strict'
import { randomUUID } from 'node:crypto'
import { setImmediate } from 'node:timers/promises'
import { test } from 'node:test'
import { DesktopSources } from '../dist/desktop-sources.js'
import { desktopAction } from '../dist/desktop-actions.js'
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
  const state = { running: 0, maximum: 0, scans: [], stores: 0, failSave: false, loseSave: false, failVerify: false }
  const call = async (request, signal, resources) => {
    if (request.operation === 'load') return structuredClone(document)
    if (request.operation === 'verify') {
      assert.equal(request.credential, credential)
      if (state.failVerify) throw new Error('Source identity mismatch')
      return structuredClone(request.source)
    }
    if (request.operation === 'store') {
      state.stores++
      if (state.failSave) throw new Error('Storage unavailable')
      assert.equal(request.expected_revision, document.revision)
      document = { format: 1, revision: randomUUID(), sources: structuredClone(request.sources) }
      if (state.loseSave) { state.loseSave = false; throw new Error('Reply lost after commit') }
      return structuredClone(document)
    }
    assert.equal(request.operation, 'scan'); assert.equal(request.credential, credential)
    state.running++; state.maximum = Math.max(state.maximum, state.running)
    resources?.(42 * 1024 * 1024)
    try {
      return await new Promise((resolve, reject) => {
        signal.addEventListener('abort', () => reject(new Error('Stopped')), { once: true })
        state.scans.push({ id: request.source.id, finish: () => resolve(report()) })
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

test('source configuration persists protected keys, reopens and refuses a stale revision', async t => {
  const f = await fixture(t), initial = await f.manager.status(), source = { ...definition(), provider: 'conversations', capture_mode: 'messages' }
  const configured = await f.add(source)
  assert.equal(configured.sources[0].connector_id, source.connector_id)
  assert.ok(!JSON.stringify(configured).includes(credential))
  assert.ok(!JSON.stringify(configured).includes('sealed_key'))
  assert.ok(!JSON.stringify(f.document()).includes(credential))
  assert.equal(f.cipher.decrypt(Buffer.from(f.document().sources[0].sealed_key, 'base64')), credential)
  const reopened = new DesktopSources(f.options)
  t.after(() => reopened.close())
  assert.deepEqual((await reopened.status()).sources.map(s => s.id), [source.id])
  assert.equal((await reopened.status()).sources[0].capture_mode, 'messages')
  await assert.rejects(f.manager.control('pause', { id: source.id, expected_revision: initial.revision, enabled: false }), /changed/)
  assert.equal((await f.manager.status()).sources[0].enabled, true)
})

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
  const f = await fixture(t), source = definition()
  await f.add(source)
  for (const field of ['path', 'endpoint', 'tenant_id', 'connector_id', 'principal_id', 'provider']) {
    await assert.rejects(f.manager.configure({ expected_revision: (await f.manager.status()).revision,
      source: { ...source, [field]: 'different' } }), /new connection/)
  }
  assert.equal(f.state.stores, 1)
  for (const action of ['source.status', 'source.configure', 'source.pause', 'source.sync', 'source.remove']) {
    assert.equal(desktopAction(action, {}).workspace, false)
    assert.throws(() => desktopAction(action, { arbitrary_shell: 'forbidden' }), /unsupported input/)
  }
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
