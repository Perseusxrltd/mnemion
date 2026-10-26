import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { test } from 'node:test'
import assert from 'node:assert/strict'
import ts from 'typescript'

const entry = new URL('../src/workspace/telemetry-policy.ts', import.meta.url), modules = new Map()
function load(url) {
  if (modules.has(url.href)) return modules.get(url.href)
  const exported = {}; modules.set(url.href, exported)
  const code = ts.transpileModule(readFileSync(url, 'utf8'), { compilerOptions: {
    target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, esModuleInterop: true,
  } }).outputText
  const local = createRequire(url)
  new Function('require', 'exports', code)(name => name.startsWith('.') && !name.endsWith('.json')
    ? load(new URL(name.replace(/\.js$/, '') + '.ts', url)) : local(name), exported)
  return exported
}
const { BrowserTelemetry } = load(entry)
const { budgetKey, budgetState, choiceKey, queueKey, DAY } = load(new URL('../src/workspace/telemetry-budget.ts', import.meta.url))
const contract = createRequire(entry)('../../../../mnemion/product_telemetry/disclosure.json')
const allowed = { network: 'unmetered', constrained: false }
const observation = { kind: 'submission', workflow: 'memory.recall', surface: 'browser' }

async function scenario(run, available = true) {
  const original = { collection_available: contract.collection_available, destination: contract.destination }, wall = Date.now
  Object.assign(contract, { collection_available: available, destination: available ? 'https://example.invalid/v1/report' : null })
  const time = { wall: wall(), elapsed: 1000, lease: 5 }, values = new Map(), writes = []
  let busy = false, live = false, epoch = '1'.repeat(32), fault = () => false, initializations = 0
  let groups = ['usage', 'reliability', 'performance', 'resources']
  Date.now = () => time.wall
  const locks = { async request(_name, _options, callback) {
    if (busy) return callback(null)
    busy = true
    try { return await callback({}) } finally { busy = false }
  } }
  const storageFor = target => ({ getItem: key => target.get(key) ?? null,
    setItem(key, value) { if (fault(key, value)) throw new Error('PRIVATE_STORAGE_FAILURE'); target.set(key, value); writes.push([key, value]) },
    removeItem(key) { target.delete(key) } })
  const storage = storageFor(values)
  const clock = { read: () => live ? { epoch, elapsed_ms: time.elapsed } : null,
    async ensure(expected = null) {
      initializations++
      if (expected !== null && (!live || epoch !== expected)) return null
      live = true
      return this.read()
    }, close() { live = false } }
  const make = (store = storage) => new BrowserTelemetry(() => store,
    () => ({ state: 'unmanaged', enabled: true, metric_groups: groups }), () => false, () => true,
    { locks: () => locks, now: () => time.wall, monotonic: () => time.lease, events: () => null }, clock)
  const first = make(), second = make()
  const request = (client, extra = {}) => { const value = client.reviewStatus(); return {
    expected_revision: value.status.revision, expected_generation: value.status.store_generation,
    expected_review_token: value.review.token, ...extra } }
  const action = (client, name, extra) => client.reviewAction(name, request(client, extra))
  const choose = (client, enabled) => { const current = client.status(); return client.configure({ enabled,
    expected_revision: current.revision, expected_generation: current.store_generation, disclosure_version: enabled && available ? 1 : 0 }) }
  const record = async (client = first) => locks.request(choiceKey, {}, () => {
    const status = client.status()
    return client.record(observation, { revision: status.revision, store_generation: status.store_generation }, Math.floor(time.wall / DAY))
  })
  const stamp = (client = first) => { const status = client.status(); return { revision: status.revision, store_generation: status.store_generation } }
  try { await run({ first, second, values, storage, storageFor, make, writes, clock, time, action, request, choose, record, stamp,
    initializations: () => initializations, budget: () => budgetState(values.get(budgetKey)),
    fault: callback => { fault = callback }, groups: value => { groups = value }, epoch: value => { epoch = value } }) }
  finally { Date.now = wall; Object.assign(contract, original); clock.close() }
}

test('manual mode can be saved before disclosure without measurements or clock initialization', () => scenario(async f => {
  assert.equal(f.first.reviewStatus().packet, null)
  assert.equal((await f.action(f.first, 'inspect_report')).packet, null)
  assert.equal(f.values.size, 0)
  const paused = await f.action(f.first, 'review_mode', { mode: 'review' })
  assert.equal(paused.review.outcome, 'paused')
  assert.equal(paused.status.disclosure_version, 0)
  assert.equal(paused.status.effective_enabled, false)
  assert.equal((await f.action(f.first, 'inspect_report')).message, 'collection_not_permitted')
  assert.equal(f.values.has(queueKey), false)
  assert.equal(f.initializations(), 0)
}, false))

test('inspection freezes one exact packet without spending and repeat views do not consume later data', () => scenario(async f => {
  f.choose(f.first, true)
  await f.action(f.first, 'review_mode', { mode: 'review' })
  assert.equal(await f.record(), true)
  const first = await f.action(f.first, 'inspect_report')
  assert.equal(first.packet.body_bytes, 4)
  assert.equal(first.packet.report_selection, 'reviewed')
  assert.equal(first.packet.aggregation, 'coarse_global_volume_only')
  assert.equal(first.packet.per_report_privacy_loss, null)
  assert.equal(f.budget().attempts.length, 0)
  assert.equal(await f.first.delivery.eligible(f.stamp()), false)
  assert.equal(await f.first.delivery.reserve(f.stamp(), allowed), null)
  assert.equal(await f.record(), true)
  const pending = f.values.get(queueKey)
  const repeated = await f.action(f.second, 'inspect_report')
  assert.deepEqual(repeated.packet, first.packet)
  assert.equal(repeated.review.expires_ms, first.review.expires_ms)
  assert.equal(f.values.get(queueKey), pending)
  assert.equal(f.second.reviewStatus().packet, null)
}))

test('competing tabs claim approved bytes only once and preserve post-inspection observations', () => scenario(async f => {
  f.choose(f.first, true); await f.action(f.first, 'review_mode', { mode: 'review' }); await f.record()
  const preview = await f.action(f.first, 'inspect_report')
  await f.record()
  const pending = f.values.get(queueKey)
  await f.action(f.second, 'approve_report')
  const reports = await Promise.all([f.first.delivery.reserve(f.stamp(), allowed), f.second.delivery.reserve(f.stamp(), allowed)])
  assert.equal(reports.filter(Boolean).length, 1)
  const owner = reports[0] ? f.first : f.second, report = reports.find(Boolean)
  const bodies = []
  assert.equal(await owner.delivery.guardedWrite(report, body => { bodies.push(Buffer.from(body).toString('base64')); return true }), true)
  assert.deepEqual(bodies, [preview.packet.body_base64])
  assert.equal(f.budget().attempts.length, 1)
  assert.equal(f.budget().review.outcome, 'consumed')
  assert.equal(f.budget().review.report, null)
  assert.equal(f.values.get(queueKey), pending)
  await owner.delivery.cancel(report)
  assert.equal(f.budget().attempts.length, 1)
}))

for (const damage of ['legacy_wire', 'automatic_flag', 'noncanonical_view']) test('browser review rejects ' + damage + ' before approval or spending', () => scenario(async f => {
  f.choose(f.first, true); await f.action(f.first, 'review_mode', { mode: 'review' }); await f.record()
  await f.action(f.first, 'inspect_report')
  const budget = f.budget()
  if (damage === 'legacy_wire') budget.review.report.packet[0] = 1
  else if (damage === 'noncanonical_view') budget.review.report.packet[1] = 1
  else budget.review.report.packet[3] &= 1
  f.storage.setItem(budgetKey, JSON.stringify(budget))
  assert.equal((await f.action(f.second, 'approve_report')).review.outcome, 'invalidated')
  assert.equal(f.budget().review.report, null)
  assert.equal(f.budget().attempts.length, 0)
  assert.equal(await f.first.delivery.reserve(f.stamp(), allowed), null)
}))

test('stalled wall time and a lost epoch cannot renew approval or resume automatic delivery', () => scenario(async f => {
  f.choose(f.first, true); await f.action(f.first, 'review_mode', { mode: 'review' }); await f.record()
  await f.action(f.first, 'inspect_report')
  f.time.elapsed += 900000
  assert.equal((await f.action(f.second, 'approve_report')).review.outcome, 'expired')
  assert.equal(f.budget().review.mode, 'review')
  assert.equal(f.budget().review.report, null)
  assert.equal(f.budget().attempts.length, 0)
  await f.record(); await f.action(f.first, 'inspect_report')
  f.clock.close()
  assert.equal((await f.action(f.second, 'approve_report')).review.outcome, 'expired')
  assert.equal(f.budget().attempts.length, 0)
}))

test('the original review expiry remains a fence after the paid lease is created', () => scenario(async f => {
  f.choose(f.first, true); await f.action(f.first, 'review_mode', { mode: 'review' }); await f.record()
  await f.action(f.first, 'inspect_report'); await f.action(f.first, 'approve_report')
  f.time.elapsed += 899999
  const report = await f.first.delivery.reserve(f.stamp(), allowed)
  assert.ok(report)
  f.time.elapsed++
  assert.equal(await f.first.delivery.guardedWrite(report, () => assert.fail('Expired review reached transport')), false)
  assert.equal(f.budget().attempts.length, 1)
}))

test('stale tokens and changed groups cannot approve a replaced or differently scoped packet', () => scenario(async f => {
  f.choose(f.first, true); await f.action(f.first, 'review_mode', { mode: 'review' }); await f.record()
  const stale = f.request(f.first)
  await f.action(f.first, 'inspect_report')
  await assert.rejects(f.second.reviewAction('approve_report', stale), /telemetry_review_changed/)
  f.groups(['usage'])
  assert.equal((await f.action(f.second, 'approve_report')).review.outcome, 'invalidated')
  assert.equal(f.budget().review.report, null)
  assert.equal(f.budget().attempts.length, 0)
}))

test('opt-out and re-enable erase reports while preserving the selected manual mode', () => scenario(async f => {
  f.choose(f.first, true); await f.action(f.first, 'review_mode', { mode: 'review' }); await f.record()
  await f.action(f.first, 'inspect_report')
  f.choose(f.second, false)
  assert.equal(f.budget().review.report, null)
  assert.equal(f.budget().review.mode, 'review')
  f.choose(f.second, true)
  await f.record()
  assert.equal(await f.first.delivery.reserve(f.stamp(), allowed), null)
  assert.equal(f.budget().attempts.length, 0)
}))

test('discard loses the staged snapshot and explicit automatic mode only uses later observations', () => scenario(async f => {
  f.choose(f.first, true); await f.action(f.first, 'review_mode', { mode: 'review' }); await f.record()
  await f.action(f.first, 'inspect_report')
  const contributions = JSON.parse(f.values.get(queueKey)).contributions
  await f.action(f.first, 'discard_report')
  assert.deepEqual(JSON.parse(f.values.get(queueKey)).entries, [])
  assert.deepEqual(JSON.parse(f.values.get(queueKey)).contributions, contributions)
  await f.record()
  await f.action(f.first, 'review_mode', { mode: 'automatic' })
  const report = await f.first.delivery.reserve(f.stamp(), allowed)
  assert.ok(report)
  await f.first.delivery.cancel(report)
}))

test('each crash prefix of staging reconciles consumed input before admitting new observations', () => scenario(async f => {
  f.choose(f.first, true); await f.action(f.first, 'review_mode', { mode: 'review' }); await f.record()
  const initial = new Map(f.values)
  f.writes.length = 0
  const preview = await f.action(f.first, 'inspect_report')
  const writes = [...f.writes]
  assert.equal(writes.length, 3)
  for (const prefix of [1, 2]) {
    const values = new Map(initial)
    for (const [key, value] of writes.slice(0, prefix)) values.set(key, value)
    const recovered = f.make(f.storageFor(values))
    assert.equal(recovered.status().effective_enabled, false)
    assert.equal(await f.record(recovered), true)
    const budget = budgetState(values.get(budgetKey)), pending = JSON.parse(values.get(queueKey))
    assert.equal(budget.clear, 'none')
    assert.equal(budget.review.outcome, 'held')
    assert.equal(Buffer.from(budget.review.report.packet).toString('base64'), preview.packet.body_base64)
    assert.equal(pending.entries.length, 1)
    assert.equal(pending.entries[0].count, 1)
    assert.equal(budget.attempts.length, 0)
  }
}))

test('quota failures suppress other tabs without losing the separate spending ledger', () => scenario(async f => {
  f.choose(f.first, true); await f.action(f.first, 'review_mode', { mode: 'review' }); await f.record()
  f.fault(key => key === queueKey)
  await assert.rejects(f.action(f.first, 'inspect_report'), /telemetry_review_unavailable/)
  assert.equal(f.values.has(choiceKey), false)
  assert.equal(f.second.status().effective_enabled, false)
  assert.equal(f.budget().attempts.length, 0)
  assert.equal(await f.second.delivery.reserve(f.stamp(f.second), allowed), null)
}))

test('legacy browser budgets migrate only through explicit controls and preserve spending', () => scenario(async f => {
  f.choose(f.first, true); await f.record()
  const report = await f.first.delivery.reserve(f.stamp(), allowed)
  assert.ok(report); await f.first.delivery.cancel(report)
  const spent = f.budget().attempts
  const { review: _review, ...old } = f.budget()
  f.storage.setItem(budgetKey, JSON.stringify({ ...old, version: 1 }))
  f.storage.setItem(choiceKey, JSON.stringify({ ...JSON.parse(f.values.get(choiceKey)), schema_version: 4 }))
  assert.equal(f.second.status().effective_enabled, false)
  await f.action(f.second, 'review_mode', { mode: 'review' })
  assert.equal(JSON.parse(f.values.get(choiceKey)).schema_version, 5)
  assert.equal(f.budget().version, 2)
  assert.deepEqual(f.budget().attempts, spent)
  assert.equal(f.budget().review.mode, 'review')
}))
