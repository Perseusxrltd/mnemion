import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import ts from 'typescript'

const source = readFileSync(new URL('../src/workspace/telemetry-conditions.ts', import.meta.url), 'utf8')
const exported = {}
new Function('exports', ts.transpileModule(source, { compilerOptions: {
  target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS,
} }).outputText)(exported)
const { BrowserConditions } = exported

function fixture(t, delay = null, state = 'nominal') {
  t.mock.timers.enable({ apis: ['setTimeout'] })
  let callback, timer, disconnected = 0, now = 10000
  class Pressure {
    constructor(receive) { callback = receive }
    async observe() { if (delay !== null) timer = setTimeout(() => callback([{ state, time: now }]), delay) }
    disconnect() { disconnected++; clearTimeout(timer) }
  }
  const values = { navigator: { onLine: true }, document: { visibilityState: 'visible' }, PressureObserver: Pressure }
  const saved = Object.fromEntries(Object.keys(values).map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)]))
  const heap = Object.getOwnPropertyDescriptor(performance, 'memory')
  const clock = Object.getOwnPropertyDescriptor(performance, 'now')
  for (const [key, value] of Object.entries(values)) Object.defineProperty(globalThis, key, { configurable: true, value })
  Object.defineProperty(performance, 'memory', { configurable: true, value: { usedJSHeapSize: 1, jsHeapSizeLimit: 100 } })
  Object.defineProperty(performance, 'now', { configurable: true, value: () => now })
  t.after(() => {
    for (const [key, descriptor] of Object.entries(saved)) {
      if (descriptor) Object.defineProperty(globalThis, key, descriptor)
      else delete globalThis[key]
    }
    if (heap) Object.defineProperty(performance, 'memory', heap)
    else delete performance.memory
    if (clock) Object.defineProperty(performance, 'now', clock)
    else delete performance.now
  })
  return { conditions: new BrowserConditions(), stop: new AbortController(),
    disconnected: () => disconnected, late: () => callback([{ state: 'nominal', time: now }]),
    deliver: record => callback([record]), raw: value => callback(value), callback: () => callback,
    listen: receive => { callback = receive },
    clock: value => { now = value } }
}

test('the first valid browser pressure reading may arrive after one second', async t => {
  const f = fixture(t, 1100)
  const pending = f.conditions.start(f.stop.signal)
  t.mock.timers.tick(1100)
  assert.equal(await pending, true)
  assert.deepEqual(f.conditions.read(), { network: 'unknown', constrained: false })
  f.conditions.close()
  assert.equal(f.disconnected(), 1)
})

test('missing pressure remains refused after the bounded three-second startup', async t => {
  const f = fixture(t)
  const pending = f.conditions.start(f.stop.signal)
  let completed = false
  pending.then(() => { completed = true })
  t.mock.timers.tick(2999)
  await Promise.resolve()
  assert.equal(completed, false)
  t.mock.timers.tick(1)
  assert.equal(await pending, false)
  assert.equal(f.disconnected(), 1)
  f.late()
  assert.equal(f.conditions.read().constrained, true)
  delete globalThis.PressureObserver
  assert.equal(await f.conditions.start(new AbortController().signal), true)
  assert.deepEqual(f.conditions.read(), { network: 'unknown', constrained: false })
})

test('opt-out cancellation ends pressure startup and ignores a late nominal callback', async t => {
  const f = fixture(t, 1100)
  const pending = f.conditions.start(f.stop.signal)
  t.mock.timers.tick(500)
  f.stop.abort()
  assert.equal(await pending, false)
  assert.equal(f.disconnected(), 1)
  f.late()
  t.mock.timers.tick(3000)
  assert.equal(f.conditions.read().constrained, true)
})

test('a delayed critical reading cannot qualify browser delivery', async t => {
  const f = fixture(t, 1100, 'critical')
  const pending = f.conditions.start(f.stop.signal)
  t.mock.timers.tick(1100)
  assert.equal(await pending, false)
  assert.equal(f.disconnected(), 1)
  assert.equal(f.conditions.read().constrained, true)
  const Pressure = globalThis.PressureObserver
  delete globalThis.PressureObserver
  assert.equal(await f.conditions.start(new AbortController().signal), false)
  assert.equal(f.conditions.read().constrained, true)
  globalThis.PressureObserver = class {
    constructor(receive) { f.listen(receive) }
    observe() { return Promise.resolve() }
    disconnect() {}
  }
  const cleared = f.conditions.start(new AbortController().signal)
  f.deliver({ state: 'nominal', time: 10000 })
  assert.equal(await cleared, true)
  assert.equal(f.conditions.read().constrained, false)
  globalThis.PressureObserver = Pressure
})

for (const [label, time] of [['stale', 7500], ['future', 10001], ['missing', undefined], ['nonfinite', NaN]]) {
  test('a ' + label + ' sampled pressure timestamp cannot become fresh on callback', async t => {
    const f = fixture(t)
    const pending = f.conditions.start(f.stop.signal)
    f.deliver({ state: 'nominal', time })
    assert.equal(await pending, false)
    assert.equal(f.conditions.read().constrained, true)
    assert.equal(f.disconnected(), 1)
    delete globalThis.PressureObserver
    assert.equal(await f.conditions.start(new AbortController().signal), true)
    assert.equal(f.conditions.read().constrained, false)
  })
}

test('sample freshness expires from the OS reading time and refuses a reversed clock', async t => {
  const f = fixture(t)
  const pending = f.conditions.start(f.stop.signal)
  f.deliver({ state: 'nominal', time: 9500 })
  assert.equal(await pending, true)
  assert.equal(f.conditions.read().constrained, false)
  f.clock(11501)
  assert.equal(f.conditions.read().constrained, true)
  f.clock(9400)
  assert.equal(f.conditions.read().constrained, true)
  f.conditions.close()
})

async function quiet(t) {
  const f = fixture(t)
  delete globalThis.PressureObserver
  assert.equal(await f.conditions.start(f.stop.signal), true)
  assert.deepEqual(f.conditions.read(), { network: 'unknown', constrained: false })
  return f
}

function named(name, message = name) {
  const error = new Error(message)
  error.name = name
  return error
}

test('absent pressure and heap sensors do not invent a reading or an unmetered network', async t => {
  const saved = {
    navigator: Object.getOwnPropertyDescriptor(globalThis, 'navigator'),
    document: Object.getOwnPropertyDescriptor(globalThis, 'document'),
    PressureObserver: Object.getOwnPropertyDescriptor(globalThis, 'PressureObserver'),
  }
  const heap = Object.getOwnPropertyDescriptor(performance, 'memory')
  Object.defineProperty(globalThis, 'navigator', { configurable: true, value: { onLine: true } })
  Object.defineProperty(globalThis, 'document', { configurable: true, value: { visibilityState: 'visible' } })
  delete globalThis.PressureObserver
  delete performance.memory
  t.after(() => {
    for (const [key, descriptor] of Object.entries(saved)) {
      if (descriptor) Object.defineProperty(globalThis, key, descriptor)
      else delete globalThis[key]
    }
    if (heap) Object.defineProperty(performance, 'memory', heap)
    else delete performance.memory
  })
  const conditions = new BrowserConditions()
  assert.equal(await conditions.start(new AbortController().signal), true)
  const reading = conditions.read()
  assert.deepEqual(reading, { network: 'unknown', constrained: false })
  assert.deepEqual(Object.keys(reading).sort(), ['constrained', 'network'])
  conditions.close()
  assert.deepEqual(conditions.read(), { network: 'unknown', constrained: false })
})

test('only the pressure error name can count as a missing capability', async t => {
  for (const name of ['NotSupportedError', 'NotAllowedError']) {
    const f = await quiet(t)
    globalThis.PressureObserver = class {
      observe() { return Promise.reject(named(name, 'ordinary text')) }
      disconnect() {}
    }
    assert.equal(await f.conditions.start(new AbortController().signal), true, name)
    assert.equal(f.conditions.read().constrained, false, name)
    globalThis.PressureObserver = class {
      constructor() { throw named(name) }
      disconnect() {}
    }
    assert.equal(await f.conditions.start(new AbortController().signal), true, name)
    assert.equal(f.conditions.read().constrained, false, name)
  }
  for (const error of [new Error('NotSupportedError'), new TypeError('NotAllowedError')]) {
    const f = await quiet(t)
    globalThis.PressureObserver = class {
      observe() { return Promise.reject(error) }
      disconnect() {}
    }
    assert.equal(await f.conditions.start(f.stop.signal), false, error.name)
    assert.equal(f.conditions.read().constrained, true, error.name)
  }
  const f = await quiet(t)
  globalThis.PressureObserver = 1
  assert.equal(await f.conditions.start(f.stop.signal), false)
  assert.equal(f.conditions.read().constrained, true)
})

for (const state of ['fair', 'serious']) {
  test('a supported ' + state + ' pressure reading stays restricted after the sensor disappears', async t => {
    const f = fixture(t)
    const pending = f.conditions.start(f.stop.signal)
    f.deliver({ state, time: 10000 })
    assert.equal(await pending, false)
    assert.equal(f.conditions.read().constrained, true)
    f.raw(null)
    assert.equal(f.conditions.read().constrained, true)
    f.conditions.close()
    delete globalThis.PressureObserver
    assert.equal(await f.conditions.start(new AbortController().signal), false)
    assert.equal(f.conditions.read().constrained, true)
  })
}

test('a malformed pressure callback after a nominal reading invalidates that reading only', async t => {
  const f = fixture(t)
  const pending = f.conditions.start(f.stop.signal)
  f.deliver({ state: 'nominal', time: 10000 })
  assert.equal(await pending, true)
  assert.equal(f.conditions.read().constrained, false)
  const stale = f.callback()
  const again = f.conditions.start(new AbortController().signal)
  f.deliver({ state: 'nominal', time: 10000 })
  assert.equal(await again, true)
  stale(null)
  assert.equal(f.conditions.read().constrained, false)
  f.raw({ state: 'nominal' })
  assert.equal(f.conditions.read().constrained, true)
  const restored = f.conditions.start(new AbortController().signal)
  f.deliver({ state: 'nominal', time: 10000 })
  assert.equal(await restored, true)
  f.raw(null)
  assert.equal(f.conditions.read().constrained, true)
  f.conditions.close()
  assert.equal(f.conditions.read().constrained, true)
})

test('an observed critical restriction survives a malformed callback and capability loss', async t => {
  const f = fixture(t)
  const pending = f.conditions.start(f.stop.signal)
  f.deliver({ state: 'critical', time: 10000 })
  assert.equal(await pending, false)
  f.raw(null)
  f.conditions.close()
  delete globalThis.PressureObserver
  assert.equal(await f.conditions.start(new AbortController().signal), false)
  assert.equal(f.conditions.read().constrained, true)
  globalThis.PressureObserver = class {
    constructor(receive) { f.listen(receive) }
    observe() { return Promise.reject(named('NotSupportedError')) }
    disconnect() {}
  }
  assert.equal(await f.conditions.start(new AbortController().signal), false)
  assert.equal(f.conditions.read().constrained, true)
})

test('saveData and cellular restrictions survive a partial or missing connection', async t => {
  const f = await quiet(t)
  navigator.connection = { saveData: true, type: 'wifi', effectiveType: '4g' }
  assert.deepEqual(f.conditions.read(), { network: 'metered', constrained: true })
  delete navigator.connection
  f.conditions.close()
  assert.deepEqual(f.conditions.read(), { network: 'metered', constrained: true })
  navigator.connection = { type: 'wifi', effectiveType: '4g' }
  assert.equal(f.conditions.read().network, 'metered')
  navigator.connection = { saveData: false, type: 'wifi', effectiveType: '4g' }
  assert.deepEqual(f.conditions.read(), { network: 'unknown', constrained: false })
  navigator.connection = { saveData: false, type: 'cellular', effectiveType: '4g' }
  assert.equal(f.conditions.read().network, 'metered')
  navigator.connection = { saveData: false, effectiveType: '4g' }
  assert.equal(f.conditions.read().network, 'metered')
  navigator.connection = { saveData: false, type: 'wifi', effectiveType: '4g' }
  assert.deepEqual(f.conditions.read(), { network: 'unknown', constrained: false })
  assert.notEqual(f.conditions.read().network, 'unmetered')
})

test('a slow link stays restricted until 3g or 4g is actually reported', async t => {
  const f = await quiet(t)
  for (const kind of ['2g', 'slow-2g']) {
    navigator.connection = { saveData: false, type: 'wifi', effectiveType: kind }
    assert.deepEqual(f.conditions.read(), { network: 'unknown', constrained: true }, kind)
    navigator.connection = { saveData: false, type: 'wifi' }
    assert.equal(f.conditions.read().constrained, true, kind)
    navigator.connection = { saveData: false, type: 'wifi', effectiveType: '' }
    assert.equal(f.conditions.read().constrained, true, kind)
    navigator.connection = { saveData: false, type: 'wifi', effectiveType: '5g' }
    assert.equal(f.conditions.read().constrained, true, kind)
    navigator.connection = { saveData: false, type: 'wifi', effectiveType: kind === '2g' ? '4g' : '3g' }
    assert.deepEqual(f.conditions.read(), { network: 'unknown', constrained: false }, kind)
  }
  navigator.connection = { saveData: false, type: 'wifi', effectiveType: '' }
  assert.equal(f.conditions.read().constrained, false)
  navigator.connection = { saveData: false, type: 'ethernet', effectiveType: 'wifi' }
  assert.deepEqual(f.conditions.read(), { network: 'unknown', constrained: false })
})

test('a throwing or malformed connection field refuses one read and does not invent a restriction', async t => {
  const f = await quiet(t)
  navigator.connection = { saveData: 1, type: 'wifi', effectiveType: '4g' }
  assert.deepEqual(f.conditions.read(), { network: 'unknown', constrained: true })
  navigator.connection = { saveData: false, type: 1, effectiveType: '4g' }
  assert.deepEqual(f.conditions.read(), { network: 'unknown', constrained: true })
  navigator.connection = { saveData: false, type: 'wifi', effectiveType: 2 }
  assert.deepEqual(f.conditions.read(), { network: 'unknown', constrained: true })
  delete navigator.connection
  assert.deepEqual(f.conditions.read(), { network: 'unknown', constrained: false })
  navigator.connection = { saveData: true, type: 'wifi', effectiveType: '4g' }
  assert.equal(f.conditions.read().network, 'metered')
  const broken = { type: 'wifi', effectiveType: '4g' }
  Object.defineProperty(broken, 'saveData', { get() { throw new Error('saveData') } })
  navigator.connection = broken
  assert.deepEqual(f.conditions.read(), { network: 'metered', constrained: true })
  navigator.connection = { type: 'wifi', effectiveType: '4g' }
  assert.equal(f.conditions.read().network, 'metered')
  let link = { saveData: false, type: 'cellular', effectiveType: '4g' }
  Object.defineProperty(navigator, 'connection', { configurable: true, get() {
    if (link === 'throw') throw new Error('connection')
    return link
  } })
  assert.equal(f.conditions.read().network, 'metered')
  link = 'throw'
  assert.deepEqual(f.conditions.read(), { network: 'metered', constrained: true })
  link = { saveData: false, type: 'wifi', effectiveType: '2g' }
  assert.equal(f.conditions.read().constrained, true)
  const slow = { saveData: false, type: 'wifi' }
  Object.defineProperty(slow, 'effectiveType', { get() { throw new Error('effectiveType') } })
  link = slow
  assert.equal(f.conditions.read().constrained, true)
  assert.equal(f.conditions.read().network, 'unknown')
  link = { saveData: false, type: 'wifi', effectiveType: '4g' }
  assert.deepEqual(f.conditions.read(), { network: 'unknown', constrained: false })
  Object.defineProperty(document, 'visibilityState', { configurable: true, get() { throw new Error('visibility') } })
  link = { saveData: true, type: 'wifi', effectiveType: '4g' }
  f.conditions.read()
  assert.deepEqual(f.conditions.read(), { network: 'metered', constrained: true })
})

test('heap pressure sticks across a missing memory API and close, and a bad sample does not', async t => {
  const f = await quiet(t)
  performance.memory = { usedJSHeapSize: 80, jsHeapSizeLimit: 100 }
  assert.equal(f.conditions.read().constrained, true)
  delete performance.memory
  f.conditions.close()
  assert.equal(f.conditions.read().constrained, true)
  performance.memory = { usedJSHeapSize: 79, jsHeapSizeLimit: 100 }
  assert.equal(f.conditions.read().constrained, false)
  performance.memory = { usedJSHeapSize: NaN, jsHeapSizeLimit: 100 }
  assert.equal(f.conditions.read().constrained, true)
  delete performance.memory
  assert.equal(f.conditions.read().constrained, false)
  Object.defineProperty(performance, 'memory', { configurable: true, get() { throw new Error('memory') } })
  assert.equal(f.conditions.read().constrained, true)
  delete performance.memory
  assert.deepEqual(f.conditions.read(), { network: 'unknown', constrained: false })
})

test('offline, hidden, data saving, cellular and slow links still veto a visible attempt', async t => {
  const f = await quiet(t)
  delete performance.memory
  navigator.connection = { saveData: false, type: 'wifi', effectiveType: '4g' }
  assert.deepEqual(f.conditions.read(), { network: 'unknown', constrained: false })
  navigator.onLine = false
  assert.equal(f.conditions.read().constrained, true)
  navigator.onLine = true
  document.visibilityState = 'hidden'
  assert.equal(f.conditions.read().constrained, true)
  document.visibilityState = 'visible'
  for (const connection of [
    { saveData: true, type: 'wifi', effectiveType: '4g' },
    { saveData: false, type: 'cellular', effectiveType: '4g' },
    { saveData: false, type: 'wifi', effectiveType: '2g' },
    { saveData: false, type: 'wifi', effectiveType: 'slow-2g' },
  ]) {
    navigator.connection = connection
    assert.equal(f.conditions.read().constrained, true, JSON.stringify(connection))
  }
})
