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
const { sendBrowserTelemetry } = load(new URL('../src/workspace/telemetry-transport.ts', import.meta.url))
const contract = createRequire(entry)('../../../../mnemion/product_telemetry/disclosure.json')
const allowed = { network: 'unmetered', constrained: false }
const measured = () => ({ kind: 'outcome', workflow: 'memory.recall', surface: 'browser', outcome: 'success' })

async function transportFixture(run, mode = 'success', policyMode = 'success') {
  const saved = globalThis.fetch, savedWindow = globalThis.window, calls = [], policyCalls = []
  globalThis.window = { location: new URL('https://workspace.example/privacy') }
  let entered, release, policyEntered, policyRelease, aborts = 0, policyAborts = 0
  const started = new Promise(resolve => { entered = resolve })
  const policyStarted = new Promise(resolve => { policyEntered = resolve })
  globalThis.fetch = (url, options) => {
    if (options.method === 'GET') {
      policyCalls.push({ url, options })
      policyEntered()
      return new Promise((resolve, reject) => {
        const abort = () => { policyAborts++; reject(new DOMException('Cancelled', 'AbortError')) }
        const respond = () => {
          options.signal.removeEventListener('abort', abort)
          let policy = { state: 'unmanaged', enabled: true, metric_groups: ['usage', 'reliability', 'performance', 'resources'] }
          if (policyMode === 'disabled') policy = { state: 'restricted', enabled: false, metric_groups: [] }
          if (policyMode === 'groups') policy = { state: 'restricted', enabled: true, metric_groups: ['reliability'] }
          if (policyMode === 'extra') policy.identifier = 'PRIVATE_POLICY_SENTINEL'
          if (policyMode === 'invalid') policy = { state: 'unmanaged', enabled: 'yes', metric_groups: ['usage'] }
          const body = policyMode === 'huge' ? 'x'.repeat(1025) : policyMode === 'malformed' ? '{broken' : JSON.stringify(policy)
          const response = new Response(body, { status: policyMode === 'bad_status' ? 503 : 200, headers: {
            'Content-Type': policyMode === 'html' ? 'text/html' : 'application/json',
            'Content-Length': policyMode === 'wrong_length' ? String(body.length + 1) : String(Buffer.byteLength(body)),
            'Cache-Control': policyMode === 'cached' ? 'max-age=300' : 'no-store',
            ...(policyMode === 'aged' ? { Age: '1' } : {}),
          } })
          Object.defineProperty(response, 'url', { value: policyMode === 'wrong_url' ? 'https://private.invalid/policy' : url })
          Object.defineProperty(response, 'redirected', { value: policyMode === 'redirected' })
          resolve(response)
        }
        options.signal.addEventListener('abort', abort, { once: true })
        if (options.signal.aborted) abort()
        else if (policyMode === 'hold') policyRelease = respond
        else respond()
      })
    }
    calls.push({ url, options, body: [...options.body] })
    entered()
    return new Promise((resolve, reject) => {
      const abort = () => { aborts++; reject(new DOMException('Cancelled', 'AbortError')) }
      const respond = () => {
        options.signal.removeEventListener('abort', abort)
        resolve({ status: mode === 'bad_status' ? 200 : 204, redirected: mode === 'redirected',
          url: mode === 'wrong_url' ? 'https://private.invalid/' : url,
          headers: new Headers({ 'Content-Length': mode === 'nonempty_length' ? '4' : '0' }),
          body: ['bad_status', 'empty_stream'].includes(mode) ? { getReader() { throw new Error('Response contents must never be read') } } : null })
      }
      options.signal.addEventListener('abort', abort, { once: true })
      if (options.signal.aborted) abort()
      else if (mode === 'hold') release = respond
      else respond()
    })
  }
  try { await run({ calls, policyCalls, started, policyStarted, release: () => release(), policyRelease: () => policyRelease(),
    aborts: () => aborts, policyAborts: () => policyAborts }) }
  finally { globalThis.fetch = saved; if (savedWindow === undefined) delete globalThis.window; else globalThis.window = savedWindow }
}

async function available(run) {
  const saved = { collection_available: contract.collection_available, destination: contract.destination }
  Object.assign(contract, { collection_available: true, destination: 'https://example.invalid/v1/report' })
  try { await run() } finally { Object.assign(contract, saved) }
}

function fixture(asyncLocks = false, releaseLater = false) {
  const values = new Map(), events = new EventTarget(), listeners = new Map()
  const add = events.addEventListener.bind(events), remove = events.removeEventListener.bind(events)
  events.addEventListener = (name, callback, ...rest) => { listeners.set(callback, name); add(name, callback, ...rest) }
  events.removeEventListener = (name, callback, ...rest) => { listeners.delete(callback); remove(name, callback, ...rest) }
  let now = Date.now(), monotonic = performance.now(), busy = false, restricted = false, privacy = false, fault = () => false
  const storage = { getItem: key => values.get(key) ?? null,
    setItem: (key, value) => { if (fault(key, value)) throw new Error('PRIVATE_SENTINEL'); values.set(key, value) },
    removeItem: key => { values.delete(key) } }
  const locks = { request(name, _options, callback) {
    assert.equal(name, choiceKey)
    const run = () => {
      if (busy) return callback(null)
      busy = true
      try {
        const result = callback({ name })
        if (releaseLater) return Promise.resolve(result).finally(() => { busy = false })
        busy = false
        return result
      } catch (error) { busy = false; throw error }
    }
    return asyncLocks ? Promise.resolve().then(run) : Promise.resolve(run())
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

test('a browser v3 upgrade retains spent budget and connection settings still obey restrictions', async () => available(async () => {
  const instance = fixture(), client = instance.first
  let stamp = instance.choice(client, true)
  stamp = client.configure({ enabled: true, expected_revision: stamp.revision, expected_generation: stamp.store_generation,
    disclosure_version: 1, connection_mode: 'unmetered' })
  instance.enqueue()
  assert.equal(await client.delivery.reserve(stamp, { network: 'metered', constrained: false }), null)
  assert.equal(await client.delivery.reserve(stamp, { network: 'unknown', constrained: true }), null)
  assert.equal(instance.budget().attempts.length, 0)
  const report = await client.delivery.reserve(stamp, { network: 'unknown', constrained: false })
  assert.ok(report)
  const spent = instance.budget().attempts
  const old = JSON.parse(instance.storage.getItem(choiceKey))
  old.schema_version = 3; delete old.connection_mode
  instance.storage.setItem(choiceKey, JSON.stringify(old))
  const restarted = instance.client(), before = restarted.status()
  assert.equal(before.connection_mode, 'auto')
  const after = restarted.configure({ enabled: true, expected_revision: before.revision, expected_generation: before.store_generation,
    disclosure_version: 1, connection_mode: 'metered' })
  assert.equal(after.connection_mode, 'metered')
  assert.equal(after.store_generation, stamp.store_generation)
  assert.deepEqual(instance.budget().attempts, spent)
  assert.equal(await client.delivery.current(report), false)
  instance.advance(DAY + 3600000)
  assert.equal(await restarted.delivery.reserve(instance.enqueue(restarted), allowed), null)
}))

test('queued final handoffs send once and do not cancel the winning in-flight request', async () => available(async () => {
  const instance = fixture(true), client = instance.first
  instance.choice(client, true)
  const report = await client.delivery.reserve(instance.enqueue(), allowed)
  let writes = 0
  const outcomes = await Promise.all([0, 1].map(() => client.delivery.guardedWrite(report, () => { writes++; return true })))
  assert.deepEqual(outcomes.sort(), [false, true])
  assert.equal(writes, 1)
  assert.equal(await client.delivery.current(report), true)
  await client.delivery.cancel(report)
  assert.equal(instance.budget().lease, null)
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
  assert.equal(JSON.parse(instance.storage.getItem(choiceKey)).schema_version, 4)
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

test('browser transport uses the disclosed destination and isolated request options', async () => available(() => transportFixture(async transport => {
  const instance = fixture(), client = instance.first
  instance.choice(client, true)
  const report = await client.delivery.reserve(instance.enqueue(), allowed), original = [...report.body()]
  assert.deepEqual(await sendBrowserTelemetry(client, report), { outcome: 'delivered' })
  assert.equal(transport.calls.length, 1)
  assert.equal(transport.policyCalls.length, 1)
  const policy = transport.policyCalls[0]
  assert.equal(policy.url, 'https://workspace.example/studio/telemetry-policy')
  assert.deepEqual(Object.keys(policy.options).sort(), ['cache', 'credentials', 'keepalive', 'method', 'mode', 'redirect', 'referrerPolicy', 'signal'].sort())
  assert.deepEqual([policy.options.method, policy.options.cache, policy.options.credentials, policy.options.mode,
    policy.options.redirect, policy.options.referrerPolicy, policy.options.keepalive],
    ['GET', 'no-store', 'omit', 'same-origin', 'error', 'no-referrer', false])
  const { url, options, body } = transport.calls[0]
  assert.equal(url, contract.destination); assert.deepEqual(body, original)
  assert.deepEqual(Object.keys(options).sort(), ['body', 'cache', 'credentials', 'headers', 'keepalive', 'method', 'mode', 'redirect', 'referrerPolicy', 'signal'].sort())
  assert.deepEqual(options.headers, { 'Content-Type': 'application/octet-stream' })
  assert.deepEqual([options.method, options.cache, options.credentials, options.mode, options.redirect, options.referrerPolicy, options.keepalive],
    ['POST', 'no-store', 'omit', 'cors', 'error', 'no-referrer', false])
  assert.equal(options.signal.aborted, true)
  assert.deepEqual([...report.body()], [0, 0, 0, 0]); assert.equal(report.closed, true)
  assert.equal(instance.budget().lease, null); assert.equal(instance.budget().attempts.length, 1)
})))

test('duplicate browser sends cannot cancel a successful pending request', async () => available(() => transportFixture(async transport => {
  const instance = fixture(true), client = instance.first
  instance.choice(client, true)
  const report = await client.delivery.reserve(instance.enqueue(), allowed)
  const first = sendBrowserTelemetry(client, report)
  assert.deepEqual(await sendBrowserTelemetry(client, report), { outcome: 'suppressed' })
  await transport.started
  assert.deepEqual(await sendBrowserTelemetry(client, report), { outcome: 'suppressed' })
  assert.equal(transport.calls.length, 1); assert.equal(transport.aborts(), 0)
  transport.release()
  assert.deepEqual(await first, { outcome: 'delivered' })
  assert.equal(instance.budget().attempts.length, 1); assert.equal(instance.budget().lease, null)
}, 'hold')))

test('asynchronously released Web Locks do not let the watcher suppress its own sender', async () => available(() => transportFixture(async transport => {
  const instance = fixture(true, true), client = instance.first
  instance.choice(client, true)
  const report = await client.delivery.reserve(instance.enqueue(), allowed)
  assert.deepEqual(await sendBrowserTelemetry(client, report), { outcome: 'delivered' })
  assert.equal(transport.calls.length, 1)
  assert.equal(report.closed, true); assert.equal(instance.budget().lease, null)
})))

for (const control of ['same_tab_off', 'other_tab_off', 'privacy', 'company', 'pagehide'])
  test(`browser ${control} cancels a pending fetch without another request`, async () => available(() => transportFixture(async transport => {
    const instance = fixture(), client = instance.first
    instance.choice(client, true)
    const report = await client.delivery.reserve(instance.enqueue(), allowed)
    const pending = sendBrowserTelemetry(client, report)
    await transport.started
    if (control === 'same_tab_off') instance.choice(client, false)
    else if (control === 'other_tab_off') instance.choice(instance.client(), false)
    else if (control === 'privacy') instance.privacy(true)
    else if (control === 'company') instance.restrict(true)
    else instance.events.dispatchEvent(new Event('pagehide'))
    assert.deepEqual(await pending, { outcome: 'suppressed' })
    assert.equal(transport.calls.length, 1); assert.equal(transport.aborts(), 1)
    assert.equal(instance.budget().attempts.length, 1); assert.equal(instance.budget().lease, null)
    assert.equal(report.closed, true); assert.equal(instance.listeners.size, 0)
  }, 'hold')))

for (const mode of ['redirected', 'wrong_url', 'bad_status', 'nonempty_length'])
  test(`browser ${mode} response is rejected without reading content or retrying`, async () => available(() => transportFixture(async transport => {
    const instance = fixture(), client = instance.first
    instance.choice(client, true)
    const report = await client.delivery.reserve(instance.enqueue(), allowed)
    assert.deepEqual(await sendBrowserTelemetry(client, report), { outcome: 'failed' })
    assert.equal(transport.calls.length, 1); assert.equal(transport.calls[0].options.signal.aborted, true)
    assert.equal(report.closed, true); assert.equal(instance.budget().lease, null)
  }, mode)))

test('a Chromium-style empty 204 stream is accepted without reading it', async () => available(() => transportFixture(async transport => {
  const instance = fixture(), client = instance.first
  instance.choice(client, true)
  const report = await client.delivery.reserve(instance.enqueue(), allowed)
  assert.deepEqual(await sendBrowserTelemetry(client, report), { outcome: 'delivered' })
  assert.equal(transport.calls.length, 1); assert.equal(report.closed, true)
  assert.equal(instance.budget().lease, null)
}, 'empty_stream')))

for (const destination of [null, 'http://example.invalid/v1/report', 'https://secret@example.invalid/v1/report',
  'https://example.invalid/v1/report?account=private', 'https://example.invalid/other'])
  test(`invalid browser collector ${destination === null ? 'null' : new URL(destination).protocol + '/' + new URL(destination).pathname} causes no request`,
    async () => available(() => transportFixture(async transport => {
      const instance = fixture(), client = instance.first
      instance.choice(client, true)
      const report = await client.delivery.reserve(instance.enqueue(), allowed)
      contract.destination = destination
      assert.deepEqual(await sendBrowserTelemetry(client, report), { outcome: 'suppressed' })
      assert.equal(transport.calls.length, 0); assert.equal(report.closed, true)
      assert.equal(instance.budget().attempts.length, 1); assert.equal(instance.budget().lease, null)
    })))

test('an already stopped browser owner cannot start the reserved request', async () => available(() => transportFixture(async transport => {
  const instance = fixture(), client = instance.first, owner = new AbortController()
  instance.choice(client, true)
  const report = await client.delivery.reserve(instance.enqueue(), allowed)
  owner.abort()
  assert.deepEqual(await sendBrowserTelemetry(client, report, owner.signal), { outcome: 'suppressed' })
  assert.equal(transport.calls.length, 0); assert.equal(report.closed, true)
  assert.equal(instance.budget().attempts.length, 1)
})))

test('the browser sender stops a silent request at its actual five-second deadline', async () => available(() => transportFixture(async transport => {
  const instance = fixture(), client = instance.first
  instance.choice(client, true)
  const report = await client.delivery.reserve(instance.enqueue(), allowed), started = performance.now()
  assert.deepEqual(await sendBrowserTelemetry(client, report), { outcome: 'deadline' })
  assert.ok(performance.now() - started >= 4500 && performance.now() - started < 5700)
  assert.equal(transport.calls.length, 1); assert.equal(transport.aborts(), 1)
  assert.equal(instance.budget().attempts.length, 1); assert.equal(instance.budget().lease, null)
}, 'hold')))

for (const mode of ['disabled', 'groups', 'extra', 'invalid', 'huge', 'malformed', 'bad_status', 'html',
  'wrong_length', 'cached', 'aged', 'wrong_url', 'redirected'])
  test(`fresh company ${mode} policy suppresses the report without refund or fallback`, async () => available(() => transportFixture(async transport => {
    const instance = fixture(), client = instance.first
    instance.choice(client, true)
    const report = await client.delivery.reserve(instance.enqueue(), allowed)
    assert.deepEqual(await sendBrowserTelemetry(client, report), { outcome: 'suppressed' })
    assert.equal(transport.policyCalls.length, 1)
    assert.equal(transport.calls.length, 0)
    assert.equal(instance.budget().attempts.length, 1)
    assert.equal(instance.budget().lease, null)
    assert.equal(report.closed, true)
    assert.equal(instance.listeners.size, 0)
    assert.ok(!JSON.stringify(client.status()).includes('PRIVATE_POLICY_SENTINEL'))
  }, 'success', mode)))

for (const control of ['same_tab_off', 'other_tab_off', 'privacy', 'company', 'pagehide', 'owner'])
  test(`${control} interrupts the pending policy read before collector contact`, async () => available(() => transportFixture(async transport => {
    const instance = fixture(true, true), client = instance.first, owner = new AbortController()
    instance.choice(client, true)
    const report = await client.delivery.reserve(instance.enqueue(), allowed)
    const pending = sendBrowserTelemetry(client, report, owner.signal)
    await transport.policyStarted
    assert.equal(instance.budget().attempts.length, 1, 'reserve before any policy traffic')
    if (control === 'same_tab_off') instance.choice(client, false)
    else if (control === 'other_tab_off') instance.choice(instance.client(), false)
    else if (control === 'privacy') instance.privacy(true)
    else if (control === 'company') instance.restrict(true)
    else if (control === 'owner') owner.abort()
    else instance.events.dispatchEvent(new Event('pagehide'))
    assert.deepEqual(await pending, { outcome: 'suppressed' })
    assert.equal(transport.policyAborts(), 1)
    assert.equal(transport.policyCalls.length, 1)
    assert.equal(transport.calls.length, 0)
    assert.equal(instance.budget().attempts.length, 1)
    assert.equal(instance.budget().lease, null)
    assert.equal(instance.listeners.size, 0)
    assert.notEqual(client.status().company_policy.state, 'unreadable', 'local cancellation does not fabricate a company restriction')
  }, 'success', 'hold')))

test('a delayed policy response cannot masquerade as a fresh permission', async () => available(() => transportFixture(async transport => {
  const instance = fixture(), client = instance.first
  instance.choice(client, true)
  const report = await client.delivery.reserve(instance.enqueue(), allowed)
  const pending = sendBrowserTelemetry(client, report)
  await transport.policyStarted
  await new Promise(resolve => setTimeout(resolve, 1050))
  transport.policyRelease()
  assert.deepEqual(await pending, { outcome: 'suppressed' })
  assert.equal(transport.policyCalls.length, 1); assert.equal(transport.calls.length, 0)
  assert.equal(instance.budget().attempts.length, 1); assert.equal(instance.budget().lease, null)
}, 'success', 'hold')))

test('observed company restrictions never widen through refresh, choice changes or caller mutation', async () => available(async () => {
  const instance = fixture(), client = instance.first
  instance.choice(client, true)
  const policy = { state: 'restricted', enabled: true, metric_groups: ['reliability'] }
  client.restrictCompany(policy)
  policy.metric_groups.push('usage'); policy.enabled = false
  assert.deepEqual(client.status().company_policy, { state: 'restricted', enabled: true, metric_groups: [] })
  client.restrictCompany({ state: 'unmanaged', enabled: true, metric_groups: ['usage'] })
  instance.choice(client, false); instance.choice(client, true)
  assert.equal(client.status().effective_enabled, false)
  assert.equal(client.status().reason, 'company_policy')
  const freshPage = instance.client()
  assert.equal(freshPage.status().effective_enabled, true, 'reloading can read a genuinely relaxed policy')
}))

test('the one policy handoff shares current choices and cannot be replayed or use async callbacks', async () => available(async () => {
  for (const mode of ['replay', 'off', 'async']) {
    const instance = fixture(), client = instance.first
    instance.choice(client, true)
    const report = await client.delivery.reserve(instance.enqueue(), allowed)
    let calls = 0
    if (mode === 'off') instance.choice(instance.client(), false)
    const start = mode === 'async' ? async () => { calls++; return true } : () => { calls++; return true }
    assert.equal(await client.delivery.guardedPolicyRead(report, start), mode === 'replay')
    assert.equal(await client.delivery.guardedPolicyRead(report, start), false)
    assert.equal(calls, mode === 'replay' ? 1 : 0)
    await client.delivery.cancel(report)
    assert.equal(instance.budget().attempts.length, 1)
  }
}))
