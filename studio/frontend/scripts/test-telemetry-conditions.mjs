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
    deliver: record => callback([record]), clock: value => { now = value } }
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
})

for (const [label, time] of [['stale', 7500], ['future', 10001], ['missing', undefined], ['nonfinite', NaN]]) {
  test('a ' + label + ' sampled pressure timestamp cannot become fresh on callback', async t => {
    const f = fixture(t)
    const pending = f.conditions.start(f.stop.signal)
    f.deliver({ state: 'nominal', time })
    assert.equal(await pending, false)
    assert.equal(f.conditions.read().constrained, true)
    assert.equal(f.disconnected(), 1)
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
