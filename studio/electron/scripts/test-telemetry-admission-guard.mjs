import test from 'node:test'
import assert from 'node:assert/strict'
import { DesktopTelemetryConditions, copyAdmissionGuard } from '../dist/telemetry-conditions.js'

test('one admission read names the reserve veto without a second gauge read', () => {
  const memory = { bytes: 256 * 1024 * 1024 }
  const originalMemory = process.availableMemory
  process.availableMemory = () => memory.bytes
  const cpuCalls = { n: 0 }, networkCalls = { n: 0 }
  let now = 0, online = true, thermal = 'nominal', boom = ''
  let totals = { idle: 0, total: 100, count: 2, source: 'node' }
  let flags = { network: 'unmetered', constrained: false }
  const conditions = new DesktopTelemetryConditions(
    { online: () => online, thermal: () => { if (boom === 'thermal') throw new Error('sensor'); return thermal } },
    { read() { networkCalls.n++; if (boom === 'network') throw new Error('sensor'); return { ...flags } }, async start() { return true }, close() {} },
    () => { cpuCalls.n++; return { ...totals } },
    () => now)
  conditions.traceAdmission = true
  const read = () => {
    const cpu = cpuCalls.n, net = networkCalls.n
    const value = conditions.read()
    return { value, cpu: cpuCalls.n - cpu, net: networkCalls.n - net, guard: copyAdmissionGuard(conditions.admissionGuard) }
  }
  try {
    let sample = read()
    assert.deepEqual(Object.keys(sample.value).sort(), ['constrained', 'network'])
    assert.deepEqual(sample.value, { network: 'unmetered', constrained: true })
    assert.equal(sample.cpu, 1)
    assert.equal(sample.net, 1)
    assert.deepEqual(sample.guard, { schema_version: 1, network: 'unmetered', constrained: true, reason: 'cpu_unobserved' })
    assert.notEqual(sample.guard, conditions.admissionGuard)

    const reused = read()
    assert.equal(reused.cpu, 0)
    assert.equal(reused.net, 1)
    assert.equal(reused.guard.reason, 'cpu_unobserved')

    now = 250
    totals = { idle: 10, total: 200, count: 2, source: 'node' }
    sample = read()
    assert.equal(sample.cpu, 1)
    assert.equal(sample.guard.reason, 'cpu_busy')
    assert.equal(sample.value.constrained, true)
    assert.equal(read().cpu, 0)
    assert.equal(conditions.admissionGuard.reason, 'cpu_busy')

    now = 500
    totals = { idle: 90, total: 300, count: 2, source: 'node' }
    sample = read()
    assert.deepEqual(sample.value, { network: 'unmetered', constrained: false })
    assert.equal(sample.guard.reason, 'allowed')

    flags = { network: 'metered', constrained: false }
    sample = read()
    assert.equal(sample.cpu, 0)
    assert.equal(sample.value.constrained, false)
    assert.equal(sample.guard.reason, 'network_not_allowed')
    flags = { network: 'metered', constrained: true }
    online = false
    sample = read()
    assert.equal(sample.guard.reason, 'network_not_allowed')
    assert.equal(sample.value.constrained, true)

    flags = { network: 'unmetered', constrained: true }
    sample = read()
    assert.equal(sample.guard.reason, 'network_constrained')
    flags = { network: 'unknown', constrained: false }
    sample = read()
    assert.equal(sample.guard.reason, 'offline')
    assert.equal(sample.value.network, 'unknown')

    online = true
    memory.bytes = 64 * 1024 * 1024
    sample = read()
    assert.equal(sample.guard.reason, 'memory')
    memory.bytes = 256 * 1024 * 1024
    thermal = 'critical'
    sample = read()
    assert.equal(sample.guard.reason, 'thermal')

    thermal = 'nominal'
    now = 100
    const calls = { cpu: cpuCalls.n, net: networkCalls.n }
    sample = read()
    assert.equal(sample.guard.reason, 'clock')
    assert.deepEqual(sample.value, { network: 'unknown', constrained: true })
    assert.equal(cpuCalls.n, calls.cpu)
    assert.equal(networkCalls.n, calls.net)

    now = 1000
    flags = { network: 'unmetered', constrained: false }
    totals = { idle: 0, total: 100, count: 2, source: 'node' }
    assert.equal(read().guard.reason, 'cpu_unobserved')
    now = 1300
    totals = { idle: 80, total: 200, count: 2, source: 'node' }
    assert.equal(read().guard.reason, 'allowed')
    now = 1600
    totals = { idle: 200, total: 400, count: 4, source: 'native' }
    assert.equal(read().guard.reason, 'cpu_unobserved')

    now = 1900
    totals = { idle: 280, total: 500, count: 4, source: 'native' }
    assert.equal(read().guard.reason, 'allowed')
    boom = 'thermal'
    const before = { cpu: cpuCalls.n, net: networkCalls.n }
    sample = read()
    assert.equal(sample.guard.reason, 'read_failed')
    assert.deepEqual(sample.value, { network: 'unknown', constrained: true })
    assert.equal(cpuCalls.n, before.cpu)
    assert.equal(networkCalls.n, before.net)

    assert.equal(copyAdmissionGuard({ schema_version: 1, network: 'unmetered', constrained: false, reason: 'allowed', path: '/secret' }).path, undefined)
    assert.equal(copyAdmissionGuard({ schema_version: 1, network: 'vpn', constrained: false, reason: 'allowed' }), null)
    assert.equal(copyAdmissionGuard(null), null)

    const wrapped = new DesktopTelemetryConditions(
      { online: () => true, thermal: () => 'nominal' },
      { read() { networkCalls.n++; return { network: 'unmetered', constrained: false } }, async start() { return true }, close() {} },
      () => { cpuCalls.n++; return { idle: 0, total: 100, count: 1, source: 'node' } },
      () => 0)
    const original = DesktopTelemetryConditions.prototype.read
    let reserveActive = false, reserveGuard = null
    DesktopTelemetryConditions.prototype.read = function (...args) {
      this.traceAdmission = true
      const value = original.apply(this, args)
      if (reserveActive && reserveGuard === null) reserveGuard = copyAdmissionGuard(this.admissionGuard)
      return value
    }
    try {
      assert.equal(wrapped.traceAdmission, false)
      assert.equal(wrapped.admissionGuard, undefined)
      const beforeWrap = networkCalls.n
      reserveActive = true
      const value = wrapped.read()
      reserveActive = false
      assert.deepEqual(value, { network: 'unmetered', constrained: true })
      assert.equal(networkCalls.n, beforeWrap + 1)
      assert.deepEqual(reserveGuard, { schema_version: 1, network: 'unmetered', constrained: true, reason: 'cpu_unobserved' })
      wrapped.read()
      assert.equal(reserveGuard.reason, 'cpu_unobserved')
    } finally { DesktopTelemetryConditions.prototype.read = original }
  } finally { process.availableMemory = originalMemory }
})

test('ordinary reads keep sensor order and allocate no admission guard', () => {
  const memory = process.availableMemory
  const order = []
  let network = { network: 'unmetered', constrained: false }
  let metering = () => { order.push('metering'); return 'unmetered' }
  let online = () => { order.push('online'); return true }
  process.availableMemory = () => { order.push('memory'); return 256 * 1024 * 1024 }
  const conditions = new DesktopTelemetryConditions(
    {
      online: () => online(),
      thermal: () => { order.push('thermal'); return 'nominal' },
      metering: () => metering(),
    },
    { read() { order.push('network'); return { ...network } }, async start() { return true }, close() {} },
    () => ({ idle: 90, total: 100, count: 1, source: 'node' }),
    () => 0)
  try {
    const value = conditions.read()
    assert.deepEqual(order, ['memory', 'thermal', 'network', 'metering', 'online'])
    // First CPU sample has no pair, so the bit stays constrained. The order is the claim.
    assert.deepEqual(value, { network: 'unmetered', constrained: true })
    assert.deepEqual(Object.keys(value).sort(), ['constrained', 'network'])
    assert.equal(conditions.traceAdmission, false)
    assert.equal(conditions.admissionGuard, undefined)
    assert.equal(copyAdmissionGuard(conditions.admissionGuard), null)

    order.length = 0
    network = { network: 'unmetered', constrained: true }
    online = () => { order.push('online'); throw new Error('online must stay skipped') }
    const constrained = conditions.read()
    assert.deepEqual(order, ['memory', 'thermal', 'network', 'metering'])
    assert.deepEqual(constrained, { network: 'unmetered', constrained: true })
    assert.equal(conditions.admissionGuard, undefined)

    order.length = 0
    network = { network: 'metered', constrained: false }
    metering = () => { order.push('metering'); throw new Error('metering must stay skipped') }
    online = () => { order.push('online'); return false }
    const metered = conditions.read()
    assert.deepEqual(order, ['memory', 'thermal', 'network', 'online'])
    assert.deepEqual(metered, { network: 'metered', constrained: true })
    assert.equal(conditions.admissionGuard, undefined)

    order.length = 0
    network = { network: 'unmetered', constrained: false }
    metering = () => { order.push('metering'); throw new Error('meter') }
    online = () => { order.push('online'); return true }
    const failed = conditions.read()
    assert.deepEqual(order, ['memory', 'thermal', 'network', 'metering'])
    assert.deepEqual(failed, { network: 'unknown', constrained: true })
    assert.equal(conditions.admissionGuard, undefined)
  } finally { process.availableMemory = memory }
})

test('prepare takes one fresh CPU sample when the 250 ms wait returns early', async () => {
  // The production wait is unref'd. A referenced timer keeps this test alive, then goes away.
  const keepalive = setTimeout(() => {}, 5000)
  const originalMemory = process.availableMemory
  process.availableMemory = () => 256 * 1024 * 1024
  const original = DesktopTelemetryConditions.prototype.read
  const seen = []
  DesktopTelemetryConditions.prototype.read = function (...args) {
    seen.push(args[0])
    this.traceAdmission = true
    return original.apply(this, args)
  }
  const attempt = async frames => {
    let calls = 0
    const started = seen.length
    let tick = 0
    const conditions = new DesktopTelemetryConditions(
      { online: () => true, thermal: () => 'nominal' },
      { read() { return { network: 'unmetered', constrained: false } }, async start() { return true }, close() {} },
      () => { const frame = frames[Math.min(calls, frames.length - 1)]; calls += 1; return { ...frame } },
      () => { const times = [0, 249.659]; const value = times[Math.min(tick, times.length - 1)]; tick += 1; return value })
    const prepared = await conditions.prepare(new AbortController().signal)
    const during = calls
    const value = conditions.read()
    return { prepared, during, after: calls, value, guard: copyAdmissionGuard(conditions.admissionGuard), forwarded: seen.slice(started) }
  }
  try {
    const pair = [
      { idle: 0, total: 100, count: 2, source: 'node' },
      { idle: 40, total: 200, count: 2, source: 'node' },
    ]
    const allowed = await attempt(pair)
    assert.equal(allowed.prepared, true)
    assert.equal(allowed.during, 2)
    assert.equal(allowed.after, 2)
    assert.deepEqual(allowed.forwarded, [undefined, true, undefined])
    assert.deepEqual(allowed.value, { network: 'unmetered', constrained: false })
    assert.deepEqual(allowed.guard, { schema_version: 1, network: 'unmetered', constrained: false, reason: 'allowed' })

    const unchanged = await attempt([
      { idle: 10, total: 100, count: 2, source: 'node' },
      { idle: 10, total: 100, count: 2, source: 'node' },
    ])
    assert.equal(unchanged.during, 2)
    assert.equal(unchanged.after, 2)
    assert.deepEqual(unchanged.guard, { schema_version: 1, network: 'unmetered', constrained: true, reason: 'cpu_unobserved' })

    const invalid = await attempt([
      { idle: 30, total: 100, count: 2, source: 'node' },
      { idle: 10, total: 180, count: 2, source: 'node' },
    ])
    assert.equal(invalid.during, 2)
    assert.equal(invalid.after, 2)
    assert.equal(invalid.value.constrained, true)
    assert.equal(invalid.guard.reason, 'cpu_unobserved')
  } finally {
    DesktopTelemetryConditions.prototype.read = original
    process.availableMemory = originalMemory
    clearTimeout(keepalive)
  }
})
