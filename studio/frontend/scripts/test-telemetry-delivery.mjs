import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import assert from 'node:assert/strict'
import { test } from 'node:test'
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
const { BrowserTelemetry, choiceKey, queueKey } = load(entry)
const { budgetKey, budgetState, DAY, WEEK, COST } = load(new URL('../src/workspace/telemetry-budget.ts', import.meta.url))
const { pendingState } = load(new URL('../src/workspace/telemetry-aggregate.ts', import.meta.url))
const contract = createRequire(entry)('../../../../mnemion/product_telemetry/disclosure.json')
const allowed = { network: 'unmetered', constrained: false }
const measured = () => ({ kind: 'outcome', workflow: 'memory.recall', surface: 'browser', outcome: 'success' })

async function available(run) {
  const saved = { collection_available: contract.collection_available, destination: contract.destination }
  Object.assign(contract, { collection_available: true, destination: 'https://example.invalid/telemetry' })
  try { await run() } finally { Object.assign(contract, saved) }
}

function fixture() {
  const values = new Map(), events = new EventTarget(), listeners = new Map()
  const add = events.addEventListener.bind(events), remove = events.removeEventListener.bind(events)
  events.addEventListener = (name, callback, ...rest) => { listeners.set(callback, name); add(name, callback, ...rest) }
  events.removeEventListener = (name, callback, ...rest) => { listeners.delete(callback); remove(name, callback, ...rest) }
  let now = Date.now(), monotonic = 100, busy = false, restricted = false, privacy = false, fault = () => false
  const storage = { getItem: key => values.get(key) ?? null,
    setItem: (key, value) => { if (fault(key, value)) throw new Error('PRIVATE_SENTINEL'); values.set(key, value) },
    removeItem: key => { values.delete(key) } }
  const locks = { request(name, _options, callback) {
    assert.equal(name, choiceKey)
    if (busy) return Promise.resolve(callback(null))
    busy = true
    try { return Promise.resolve(callback({ name })) } finally { busy = false }
  } }
  const client = () => new BrowserTelemetry(() => storage,
    () => ({ state: restricted ? 'restricted' : 'unmanaged', enabled: !restricted, metric_groups: restricted ? [] : ['usage'] }),
    () => privacy, () => true, { locks: () => locks, now: () => now, monotonic: () => monotonic, events: () => events })
  const first = client(), choice = (target, enabled) => {
    const status = target.status()
    return target.configure({ enabled, expected_revision: status.revision, expected_generation: status.store_generation,
      disclosure_version: enabled ? 1 : 0 })
  }
  const enqueue = (target = first, count = 1) => {
    const stamp = target.status()
    for (let index = 0; index < count; index++) assert.equal(target.record(measured(), stamp, Math.floor(now / DAY)), true)
    return stamp
  }
  return { first, client, choice, enqueue, values, storage, events, listeners,
    budget: () => budgetState(storage.getItem(budgetKey)),
    advance: milliseconds => { now += milliseconds; monotonic += milliseconds },
    rollback: () => { now-- }, stallClock: () => { monotonic += 5000 },
    busy: value => { busy = value }, restrict: value => { restricted = value }, privacy: value => { privacy = value },
    fault: value => { fault = value } }
}

test('the shipped disclosure cannot reserve or initialize a browser delivery', async () => {
  const instance = fixture()
  assert.equal(await instance.first.delivery.reserve({ revision: 0, store_generation: 'a'.repeat(32) }, allowed), null)
  assert.equal(instance.values.size, 0)
})

test('one origin shares spending, consumes cells and keeps the contribution limit', async () => available(async () => {
  const instance = fixture(), client = instance.first
  instance.choice(client, true)
  const stamp = instance.enqueue(client, 6), other = instance.client()
  const [report, second] = await Promise.all([client.delivery.reserve(stamp, allowed), other.delivery.reserve(stamp, allowed)])
  assert.ok(report); assert.equal(second, null)
  assert.equal(report.body().length, 4)
  assert.equal(instance.budget().attempts.length, 1)
  assert.equal(instance.budget().attempts[0].reserved_bytes, COST)
  const pending = pendingState(instance.storage.getItem(queueKey))
  assert.equal(pending.entries.length, 0)
  assert.equal(pending.contributions[0].count, 6)
  assert.equal(client.status().delivery_budget.state, 'in_flight')
  let writes = 0
  assert.equal(await client.delivery.guardedWrite(report, body => { writes++; assert.equal(body.length, 4); return true }), true)
  assert.deepEqual([...report.body()], [0, 0, 0, 0])
  assert.equal(await client.delivery.current(report), true, 'a started handoff remains cancellable')
  assert.equal(await client.delivery.guardedWrite(report, () => { writes++; return true }), false)
  assert.equal(writes, 1)
  await client.delivery.cancel(report)
  assert.equal(instance.budget().lease, null)
  assert.equal(instance.client().status().delivery_budget.attempts_in_rolling_week, 1)
  assert.equal(await instance.client().delivery.reserve(stamp, allowed), null)
}))

test('a failed handoff and repeated opt-out or opt-in never refund the reservation', async () => available(async () => {
  const instance = fixture(), client = instance.first
  instance.choice(client, true)
  const report = await client.delivery.reserve(instance.enqueue(), allowed)
  assert.equal(await client.delivery.guardedWrite(report, () => { throw new Error('PRIVATE_SENTINEL') }), false)
  assert.equal(report.closed, true)
  assert.equal(instance.budget().lease, null)
  instance.choice(client, false); instance.choice(client, false); instance.choice(client, true)
  const stamp = instance.enqueue()
  assert.equal(await client.delivery.reserve(stamp, allowed), null)
  assert.equal(instance.budget().attempts.length, 1)
  assert.ok(!JSON.stringify(client.status()).includes('PRIVATE_SENTINEL'))
}))

test('the final write fence observes another tab opting out and rejects a stale handle', async () => available(async () => {
  const instance = fixture(), client = instance.first
  instance.choice(client, true)
  const report = await client.delivery.reserve(instance.enqueue(), allowed)
  instance.choice(instance.client(), false)
  let writes = 0
  assert.equal(await client.delivery.guardedWrite(report, () => { writes++; return true }), false)
  instance.choice(instance.client(), true)
  assert.equal(await client.delivery.guardedWrite(report, () => { writes++; return true }), false)
  assert.equal(writes, 0)
  assert.deepEqual([...report.body()], [0, 0, 0, 0])
}))

test('an active watch survives handoff, aborts cross-tab opt-out once, and removes listeners', async () => available(async () => {
  const instance = fixture(), client = instance.first
  instance.choice(client, true)
  const report = await client.delivery.reserve(instance.enqueue(), allowed), stop = new AbortController()
  assert.equal(await client.delivery.guardedWrite(report, () => true), true)
  let aborts = 0
  const watching = client.delivery.watch(report, () => { aborts++; throw new Error('PRIVATE_SENTINEL') }, stop.signal)
  instance.choice(instance.client(), false)
  const changed = new Event('storage'); Object.defineProperty(changed, 'key', { value: choiceKey })
  instance.events.dispatchEvent(changed)
  await watching
  assert.equal(aborts, 1)
  assert.equal(instance.listeners.size, 0)
  assert.equal(report.closed, true)
}))

test('same-tab opt-out aborts synchronously and shutdown stops only the owned active watch', async () => available(async () => {
  for (const action of ['choice', 'pagehide', 'finished']) {
    const instance = fixture(), client = instance.first
    instance.choice(client, true)
    const report = await client.delivery.reserve(instance.enqueue(), allowed), stop = new AbortController()
    let aborts = 0
    const watching = client.delivery.watch(report, () => { aborts++ }, stop.signal)
    if (action === 'choice') instance.choice(client, false)
    else if (action === 'pagehide') instance.events.dispatchEvent(new Event('pagehide'))
    else stop.abort()
    assert.equal(aborts, action === 'finished' ? 0 : 1)
    await watching
    assert.equal(instance.listeners.size, 0)
    assert.equal(report.closed, true)
  }
}))

test('unknown network cost, pressure, privacy, company restrictions and lock contention suppress delivery', async () => available(async () => {
  for (const condition of ['unknown', 'metered', 'constrained', 'privacy', 'company', 'busy']) {
    const instance = fixture(), client = instance.first
    instance.choice(client, true)
    const stamp = instance.enqueue()
    if (condition === 'privacy') instance.privacy(true)
    if (condition === 'company') instance.restrict(true)
    if (condition === 'busy') instance.busy(true)
    const network = condition === 'unknown' ? undefined : condition === 'metered' ? { ...allowed, network: 'metered' }
      : condition === 'constrained' ? { ...allowed, constrained: true } : allowed
    assert.equal(await client.delivery.reserve(stamp, network), null, condition)
    assert.equal(instance.budget().attempts.length, 0, condition)
  }
}))

test('policy narrowing and a stalled or reversed wall clock invalidate a prepared report', async () => available(async () => {
  for (const condition of ['privacy', 'company', 'monotonic', 'rollback']) {
    const instance = fixture(), client = instance.first
    instance.choice(client, true)
    const report = await client.delivery.reserve(instance.enqueue(), allowed)
    if (condition === 'privacy') instance.privacy(true)
    if (condition === 'company') instance.restrict(true)
    if (condition === 'monotonic') instance.stallClock()
    if (condition === 'rollback') instance.rollback()
    assert.equal(await client.delivery.current(report), false, condition)
    assert.equal(instance.budget().attempts.length, 1, condition)
    assert.equal(instance.budget().lease, null, condition)
    assert.equal(report.closed, true, condition)
  }
}))

test('crashing after spending persists a clear intent; a reload cannot replay old cells or recover allowance', async () => available(async () => {
  const instance = fixture(), client = instance.first
  instance.choice(client, true)
  const stamp = instance.enqueue(client, 6)
  instance.fault(key => key === queueKey)
  assert.equal(await client.delivery.reserve(stamp, allowed), null)
  assert.equal(instance.budget().clear, 'entries')
  assert.equal(instance.budget().attempts.length, 1)
  instance.fault(() => false)
  const reloaded = instance.client(), beforeRead = JSON.stringify([...instance.values])
  assert.equal(reloaded.status().reason, 'coordination_unavailable')
  assert.equal(JSON.stringify([...instance.values]), beforeRead, 'status does not rewrite interrupted storage')
  assert.equal(reloaded.record(measured(), stamp), true)
  const pending = pendingState(instance.storage.getItem(queueKey))
  assert.equal(pending.entries.length, 1)
  assert.equal(pending.entries[0].count, 1)
  assert.equal(pending.contributions[0].count, 7)
  assert.equal(instance.budget().clear, 'none')
  assert.equal(await reloaded.delivery.reserve(stamp, allowed), null)
}))

test('a failed explicit opt-out removes acknowledgement across reloads while retaining spent budget', async () => available(async () => {
  const instance = fixture(), client = instance.first
  instance.choice(client, true)
  const report = await client.delivery.reserve(instance.enqueue(), allowed), generation = client.status().store_generation
  instance.fault(key => key === budgetKey)
  assert.throws(() => instance.choice(client, false), /Product telemetry stays off/)
  assert.equal(instance.storage.getItem(choiceKey), null)
  instance.fault(() => false)
  const reloaded = instance.client()
  assert.equal(reloaded.status().effective_enabled, false)
  assert.equal(await client.delivery.guardedWrite(report, () => true), false)
  instance.choice(reloaded, true)
  assert.notEqual(reloaded.status().store_generation, generation)
  assert.equal(instance.budget().attempts.length, 1)
  assert.equal(instance.storage.getItem(queueKey), null)
  assert.equal(await reloaded.delivery.reserve(instance.enqueue(reloaded), allowed), null)
}))

test('missing or malformed required budget cannot silently recreate an allowance', async () => available(async () => {
  for (const damage of ['missing', 'clock', 'cost', 'generation', 'extra']) {
    const instance = fixture(), client = instance.first
    instance.choice(client, true)
    const report = await client.delivery.reserve(instance.enqueue(), allowed), value = instance.budget()
    if (damage === 'missing') instance.storage.removeItem(budgetKey)
    else {
      if (damage === 'clock') value.next_ms = value.clock_ms
      if (damage === 'cost') value.attempts[0].reserved_bytes = 0
      if (damage === 'generation') value.generation = 'a'.repeat(32)
      if (damage === 'extra') value.identifier = 'PRIVATE_SENTINEL'
      instance.storage.setItem(budgetKey, JSON.stringify(value))
    }
    const reloaded = instance.client()
    assert.equal(reloaded.status().reason, 'storage_unavailable', damage)
    assert.equal(await client.delivery.current(report), false, damage)
    assert.throws(() => instance.choice(reloaded, true), /storage is unavailable/i, damage)
    assert.ok(!JSON.stringify(reloaded.status()).includes('PRIVATE_SENTINEL'))
  }
}))

test('schema two preserves opt-out and migrates only during an explicit choice', async () => available(async () => {
  const instance = fixture(), client = instance.first, generation = 'b'.repeat(32)
  instance.storage.setItem(choiceKey, JSON.stringify({ schema_version: 2, revision: 9, enabled: false,
    disclosure_version: 0, store_generation: generation }))
  assert.equal(client.status().reason, 'user_disabled')
  assert.equal(client.status().delivery_budget.state, 'upgrade_required')
  assert.equal(instance.storage.getItem(budgetKey), null)
  instance.choice(client, false)
  assert.equal(JSON.parse(instance.storage.getItem(choiceKey)).schema_version, 3)
  assert.equal(instance.budget().generation, generation)
  assert.equal(instance.budget().attempts.length, 0)
  assert.equal(client.status().reason, 'user_disabled')
}))

test('spending is bounded to seven rolling-week rows and abandoned handles do not remain usable', async () => available(async () => {
  const instance = fixture(), client = instance.first, reports = []
  instance.choice(client, true)
  for (let index = 0; index < 10; index++) {
    if (index) instance.advance(DAY + 3600001)
    const report = await client.delivery.reserve(instance.enqueue(), allowed)
    assert.ok(report)
    reports.push(report)
    assert.ok(instance.budget().attempts.length <= 7)
    assert.ok(instance.budget().attempts.every(row => row.at_ms > instance.budget().clock_ms - WEEK))
    if (index) assert.equal(reports[index - 1].closed, true)
  }
  assert.equal(instance.budget().attempts.length, 7)
  await client.delivery.cancel(reports.at(-1))
}))

test('async handoffs are rejected before invocation and leave no replayable report', async () => available(async () => {
  const instance = fixture(), client = instance.first
  instance.choice(client, true)
  const report = await client.delivery.reserve(instance.enqueue(), allowed)
  let calls = 0
  assert.equal(await client.delivery.guardedWrite(report, async () => { calls++; return true }), false)
  assert.equal(calls, 0)
  assert.equal(report.closed, true)
  assert.equal(instance.budget().attempts.length, 1)
  assert.equal(instance.budget().lease, null)
}))
