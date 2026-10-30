import test from 'node:test'
import assert from 'node:assert/strict'
import { setTimeout as delay } from 'node:timers/promises'
import { createRequire } from 'node:module'
import { NativeNetworkConditions, networkFlags } from '../dist/telemetry-network.js'
import { DesktopTelemetryConditions } from '../dist/telemetry-conditions.js'
import { readCpuTotals } from '../dist/telemetry-cpu.js'
import { readReviewClock } from '../dist/telemetry-review-clock.js'
import { startReviewLifetime, checkReviewLifetime, REVIEW_LIFETIME_MS } from '../dist/telemetry-review-lifetime.js'

const tick = () => new Promise(resolve => setImmediate(resolve))
const plain = value => { const { observed, ...conditions } = networkFlags(value); return conditions }

test('only the documented fixed OS flags can allow an unmetered path', () => {
  for (const value of [true, false, null, undefined, '9', NaN, 1, 2, 3, 7, 11, 15, 256, -1]) {
    assert.deepEqual(networkFlags(value), { network: 'unknown', constrained: true, observed: false })
  }
  assert.deepEqual(networkFlags(0), { network: 'unknown', constrained: false, observed: false })
  assert.deepEqual(networkFlags(9), { network: 'unmetered', constrained: false, observed: true })
  assert.deepEqual(networkFlags(14), { network: 'metered', constrained: true, observed: true })
})

test('OS probes run only inside an awake attempt, with no idle or closed refresh', async () => {
  let calls = 0, now = 0, code = 9
  const conditions = new NativeNetworkConditions(async () => { calls++; return code }, () => now)
  assert.deepEqual(conditions.read(), { network: 'unknown', constrained: true })
  await tick(); assert.equal(calls, 0)
  assert.equal(await conditions.start(new AbortController().signal), true)
  assert.deepEqual(conditions.read(), plain(9)); assert.equal(calls, 1)
  now = 300; code = 10
  conditions.read(); conditions.read(); await tick()
  assert.equal(calls, 2); assert.deepEqual(conditions.read(), plain(10))
  conditions.close(); now = 10000; conditions.read(); await tick()
  assert.equal(calls, 2)
  assert.deepEqual(conditions.read(), { network: 'unknown', constrained: true })
})

test('missing capabilities and errors cannot erase a previously observed restriction', async () => {
  let code = 10
  const conditions = new NativeNetworkConditions(async () => {
    if (code === -1) throw new Error('OS unavailable')
    return code
  })
  const start = () => conditions.start(new AbortController().signal)
  assert.equal(await start(), true); assert.deepEqual(conditions.read(), plain(10)); conditions.close()
  code = 0; assert.equal(await start(), true); assert.deepEqual(conditions.read(), plain(10)); conditions.close()
  code = -1; assert.equal(await start(), true); assert.deepEqual(conditions.read(), plain(14)); conditions.close()
  code = 9; assert.equal(await start(), true); assert.deepEqual(conditions.read(), plain(9)); conditions.close()
})

test('cancelled native work is ignored and cannot overlap the next attempt', async () => {
  let finish, calls = 0
  const old = new Promise(resolve => { finish = resolve })
  const conditions = new NativeNetworkConditions(() => ++calls === 1 ? old : Promise.resolve(10))
  const stop = new AbortController(), first = conditions.start(stop.signal)
  await tick(); assert.equal(calls, 1)
  stop.abort(); assert.equal(await first, false)
  const second = conditions.start(new AbortController().signal)
  await tick(); assert.equal(calls, 1)
  finish(9); assert.equal(await second, true)
  assert.equal(calls, 2); assert.deepEqual(conditions.read(), plain(10)); conditions.close()
})

test('closing before a queued microtask starts avoids the OS call entirely', async () => {
  let calls = 0
  const conditions = new NativeNetworkConditions(async () => { calls++; return 9 })
  const started = conditions.start(new AbortController().signal)
  conditions.close()
  assert.equal(await started, false)
  assert.equal(calls, 0)
})

test('slow OS replies do not extend freshness beyond one second from query start', async () => {
  let finish, now = 0
  const conditions = new NativeNetworkConditions(() => new Promise(resolve => { finish = resolve }), () => now)
  const started = conditions.start(new AbortController().signal)
  await tick(); now = 600; finish(9); assert.equal(await started, true)
  now = 1001
  assert.equal(conditions.read().constrained, true)
  conditions.close()
  await tick()
})

test('expired samples and a rolled back clock suppress handoff while a probe is pending', async () => {
  let now = 0, calls = 0, finish
  const conditions = new NativeNetworkConditions(() => ++calls === 1 ? Promise.resolve(9)
    : new Promise(resolve => { finish = resolve }), () => now)
  assert.equal(await conditions.start(new AbortController().signal), true)
  now = 1001
  assert.deepEqual(conditions.read(), { network: 'unknown', constrained: true })
  await tick(); conditions.read(); assert.equal(calls, 2)
  finish(9); await tick(); assert.deepEqual(conditions.read(), plain(9))
  now = 900; assert.equal(conditions.read().constrained, true)
  conditions.close()
})

test('a missing native reply stops preparation after its one-second deadline', async () => {
  const conditions = new NativeNetworkConditions(() => new Promise(() => {}))
  // The application is awake; this test owns the only referenced timer.
  const awake = delay(1150)
  assert.equal(await conditions.start(new AbortController().signal), false)
  assert.equal(conditions.read().constrained, true)
  await awake
})

test('the compiled Node ABI exposes fixed admission and private review controls', async () => {
  const binding = createRequire(import.meta.url)('../dist/telemetry-network.node')
  const names = ['initializeReviewClock', 'readCpuTotals', 'readReviewClock', 'readState']
  if (process.platform === 'win32') names.push('readPrivateStore')
  assert.deepEqual(Object.keys(binding).sort(), names.sort())
  if (process.platform === 'win32') assert.equal(await binding.readPrivateStore(), 0)
  const value = await binding.readState()
  assert.ok([0, 8, 9, 10, 12, 13, 14].includes(value))
  const cpu = binding.readCpuTotals()
  assert.ok(Array.isArray(cpu) && (cpu.length === 0 || cpu.length === 3))
  if (cpu.length) {
    assert.ok(cpu.every(value => Number.isSafeInteger(value) && value >= 0))
    assert.ok(cpu[0] <= cpu[1] && cpu[1] > 0 && cpu[2] > 0 && cpu[2] <= 1048576)
  }
})

test('valid aggregate CPU counters avoid the per-core OS allocation path', () => {
  const result = readCpuTotals(() => [300, 1000, 2], () => { throw new Error('Per-core path must remain unused') })
  assert.deepEqual(result, { idle: 300, total: 1000, count: 2, source: 'native' })
})

test('native review clocks are shared without exposing an epoch in the receipt', () => {
  const first = readReviewClock(true), second = readReviewClock()
  const comparable = first !== null && second !== null && first.epoch === second.epoch && first.elapsed_ms <= second.elapsed_ms
  assert.equal(comparable, true)
  assert.equal(readReviewClock(false, () => null), null)
  assert.equal(readReviewClock(false, () => [123, '0'.repeat(32)]), null)
  assert.equal(readReviewClock(false, () => [2 ** 53, 'a'.repeat(32)]), null)
  assert.equal(readReviewClock('yes', () => { throw new Error('Invalid initialization must not call the OS') }), null)
})

test('review expiry survives restart, input expiry, clock stalls and rollback', () => {
  const clock = { epoch: '1234567890abcdef1234567890abcdef', elapsed_ms: 50000 }, now = 10000000
  const lifetime = startReviewLifetime(now, clock, now + 86400000)
  assert.equal(lifetime.expires_ms, now + REVIEW_LIFETIME_MS)
  const checked = checkReviewLifetime(lifetime, now + 800000, { ...clock, elapsed_ms: 850000 })
  assert.ok(checked)
  assert.equal(checked.expires_ms, lifetime.expires_ms)
  assert.equal(checkReviewLifetime(checked, now + 800000, { ...clock, elapsed_ms: 950000 }), null)
  assert.equal(checkReviewLifetime(checked, now + 799999, { ...clock, elapsed_ms: 850001 }), null)
  assert.equal(checkReviewLifetime(checked, now + 800001, { ...clock, elapsed_ms: 849999 }), null)
  assert.equal(checkReviewLifetime(checked, now + 800001, { ...clock, epoch: 'f'.repeat(32), elapsed_ms: 850001 }), null)
  assert.equal(checkReviewLifetime(checked, now + 800001, null), null)
  const short = startReviewLifetime(now, clock, now + 100)
  assert.equal(checkReviewLifetime(short, now + 100, clock), null)
  assert.equal(checkReviewLifetime(short, now, { ...clock, elapsed_ms: 50100 }), null)
})

test('older, missing or invalid aggregate CPU support retains the current Node fallback', () => {
  const core = { model: 'unused', speed: 0, times: { user: 100, nice: 0, sys: 50, idle: 300, irq: 10 } }
  for (const value of [null, [], [1, 2], [1, 2, 3, 4], [3, 2, 1], [1, 2, 0], [NaN, 2, 1], [0, Infinity, 1], [0, 2 ** 53, 1], [0, 1, 1048577]]) {
    assert.deepEqual(readCpuTotals(() => value, () => [core, core]), { idle: 600, total: 920, count: 2, source: 'node' })
  }
  assert.equal(readCpuTotals(() => { throw new Error('Native unavailable') }, () => []), null)
  assert.equal(readCpuTotals(() => null, () => [{ ...core, times: { ...core.times, idle: NaN } }]), null)
})

test('CPU admission requires comparable providers and two fresh samples after missing data', async () => {
  let now = 0, value = { idle: 0, total: 100, count: 2, source: 'native' }
  const network = new NativeNetworkConditions(async () => 9, () => now)
  const conditions = new DesktopTelemetryConditions({ online: () => true, thermal: () => 'nominal' }, network, () => value, () => now)
  try {
    assert.equal(await network.start(new AbortController().signal), true)
    assert.equal(conditions.read().constrained, true)
    now = 250; value = { ...value, idle: 60, total: 200 }
    assert.equal(conditions.read().constrained, false)
    await tick()
    now = 500; value = { idle: 700, total: 1000, count: 2, source: 'node' }
    assert.equal(conditions.read().constrained, true)
    await tick()
    now = 750; value = { ...value, idle: 750, total: 1100 }
    assert.equal(conditions.read().constrained, false)
    await tick()
    now = 1000; value = null
    assert.equal(conditions.read().constrained, true)
    await tick()
    now = 1250; value = { idle: 800, total: 1200, count: 2, source: 'node' }
    assert.equal(conditions.read().constrained, true)
    await tick()
    now = 1500; value = { ...value, idle: 830, total: 1300 }
    assert.equal(conditions.read().constrained, false)
    now = 1750; value = { ...value, idle: 860, total: 1400, count: 4 }
    assert.equal(conditions.read().constrained, true)
    now = 2000; value = { ...value, idle: 900, total: 1500 }
    await network.start(new AbortController().signal)
    assert.equal(conditions.read().constrained, false)
  } finally { conditions.close() }
})

test('a CPU read error or a long idle gap requires two fresh readings', async () => {
  let now = 0, broken = false, value = { idle: 100, total: 200, count: 2, source: 'native' }
  const network = new NativeNetworkConditions(async () => 9, () => now)
  const conditions = new DesktopTelemetryConditions({ online: () => true, thermal: () => 'nominal' }, network,
    () => { if (broken) throw new Error('OS read unavailable'); return value }, () => now)
  try {
    await network.start(new AbortController().signal)
    conditions.read()
    now = 250; value = { ...value, idle: 200, total: 300 }
    assert.equal(conditions.read().constrained, false)
    await tick()
    now = 500; broken = true
    assert.equal(conditions.read().constrained, true)
    now = 750; broken = false; value = { ...value, idle: 300, total: 400 }
    assert.equal(conditions.read().constrained, true)
    await tick()
    now = 1000; value = { ...value, idle: 400, total: 500 }
    assert.equal(conditions.read().constrained, false)
    await tick()
    now = 122000; value = { ...value, idle: 1000, total: 1500 }
    await network.start(new AbortController().signal)
    assert.equal(conditions.read().constrained, true)
    now = 122250; value = { ...value, idle: 1100, total: 1600 }
    assert.equal(conditions.read().constrained, false)
  } finally { conditions.close() }
})

test('busy, reset, inconsistent and rolled-back CPU readings cannot allow delivery', async () => {
  let now = 0, value = { idle: 100, total: 200, count: 2, source: 'native' }
  const network = new NativeNetworkConditions(async () => 9, () => now)
  const conditions = new DesktopTelemetryConditions({ online: () => true, thermal: () => 'nominal' }, network, () => value, () => now)
  try {
    await network.start(new AbortController().signal)
    conditions.read()
    now = 250; value = { ...value, idle: 110, total: 300 }
    assert.equal(conditions.read().constrained, true)
    now = 500; value = { ...value, idle: 50, total: 100 }
    assert.equal(conditions.read().constrained, true)
    now = 750; value = { ...value, idle: 90, total: 110 }
    assert.equal(conditions.read().constrained, true)
    now = 1000; value = { ...value, idle: 100, total: 160 }
    await network.start(new AbortController().signal)
    assert.equal(conditions.read().constrained, false)
    now = 999
    assert.equal(conditions.read().constrained, true)
    now = 1250; value = { ...value, idle: 150, total: 210 }
    assert.equal(conditions.read().constrained, true)
    now = 1500; value = { ...value, idle: 190, total: 310 }
    assert.equal(conditions.read().constrained, false)
  } finally { conditions.close() }
})

test('an additional detector cannot erase the actual OS metered veto', async () => {
  const network = new NativeNetworkConditions(async () => 10)
  const conditions = new DesktopTelemetryConditions({
    online: () => true, thermal: () => 'unknown', metering: () => 'unmetered',
  }, network)
  try {
    assert.equal(await network.start(new AbortController().signal), true)
    assert.equal(conditions.read().network, 'metered')
  } finally { conditions.close() }
})

test('real CPU deltas keep the existing thermal/offline vetoes and close the network gauge', async t => {
  // The desktop already owns an app lifetime; the gauge must not keep Node up.
  const appLifetime = setTimeout(() => {}, 2000)
  t.after(() => clearTimeout(appLifetime))
  let online = true, thermal = 'unknown'
  const network = new NativeNetworkConditions(async () => 9)
  const conditions = new DesktopTelemetryConditions({ online: () => online, thermal: () => thermal }, network)
  try {
    assert.equal(await conditions.prepare(new AbortController().signal), true)
    assert.equal(conditions.read().network, 'unmetered')
    thermal = 'critical'; assert.equal(conditions.read().constrained, true)
    thermal = 'nominal'; online = false; assert.equal(conditions.read().constrained, true)
  } finally { conditions.close() }
  assert.equal(network.read().constrained, true)
})
