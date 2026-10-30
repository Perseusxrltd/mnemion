import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { test } from 'node:test'
import ts from 'typescript'

const modules = new Map()
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
const { BrowserTelemetryActivity } = load(new URL('../src/workspace/telemetry-activity.ts', import.meta.url))

function deferred() {
  let resolve
  const promise = new Promise(done => { resolve = done })
  return { promise, resolve }
}

function fixture(t, mode = 'unmetered') {
  const page = new EventTarget(), document = Object.assign(new EventTarget(), { visibilityState: 'visible' })
  const navigator = { onLine: true }
  const values = { window: page, document, navigator }
  const saved = Object.fromEntries(Object.keys(values).map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)]))
  for (const [key, value] of Object.entries(values)) Object.defineProperty(globalThis, key, { configurable: true, value })
  t.after(() => {
    for (const [key, descriptor] of Object.entries(saved)) {
      if (descriptor) Object.defineProperty(globalThis, key, descriptor)
      else delete globalThis[key]
    }
  })
  const entered = deferred(), eligible = deferred()
  let enabled = true, pressureStarts = 0, reservations = 0, seen
  const client = {
    status: () => ({ effective_enabled: enabled, connection_mode: mode, delivery_budget: { state: 'ready' } }),
    delivery: {
      eligible: () => { entered.resolve(); return eligible.promise },
      reserve: async (_stamp, _network, cohorts) => { seen = cohorts; reservations++; return null },
      cancel: async () => {},
    },
    reviewClock: { close() {} },
  }
  const activity = new BrowserTelemetryActivity(client)
  // Observe whether the real owner reaches the resource gate. No sensor result
  // is supplied: these are cancellation tests, not browser sensor acceptance.
  t.mock.method(activity.conditions, 'start', async () => { pressureStarts++; return false })
  const stamp = { revision: 1, store_generation: 'a'.repeat(32) }
  return { activity, page, entered: entered.promise, eligible, pressureStarts: () => pressureStarts,
    reservations: () => reservations, cohorts: () => seen, disable: () => { enabled = false },
    offer: () => activity.offer(stamp), settle: () => activity.activity.settled() }
}

for (const reason of ['privacy change', 'page exit']) {
  test('late eligibility cannot start a browser sensor after ' + reason, async t => {
    const f = fixture(t)
    f.offer()
    await f.entered
    if (reason === 'privacy change') { f.disable(); f.activity.invalidate() }
    else f.page.dispatchEvent(new Event('pagehide'))
    f.eligible.resolve(true)
    await f.settle()
    assert.equal(f.pressureStarts(), 0, 'Cancelled eligibility must not open a sensor')
    assert.equal(f.reservations(), 0)
  })
}

test('eligible awake work still reaches the browser resource gate once', async t => {
  const f = fixture(t)
  f.offer()
  await f.entered
  f.eligible.resolve(true)
  await f.settle()
  assert.equal(f.pressureStarts(), 1)
  assert.equal(f.reservations(), 0, 'A refused resource gate must not spend an attempt')
})

test('eligible browser activity passes one reviewed cohort record', async t => {
  const f = fixture(t)
  t.mock.method(f.activity.conditions, 'start', async () => true)
  f.offer()
  await f.entered
  f.eligible.resolve(true)
  await f.settle()
  assert.equal(f.reservations(), 1)
  assert.equal(f.cohorts().release_family, '4')
  assert.equal(f.cohorts().platform, undefined)
  assert.equal(f.cohorts().architecture, undefined)
})

test('ineligible work never starts a browser sensor', async t => {
  const f = fixture(t)
  f.offer()
  await f.entered
  f.eligible.resolve(false)
  await f.settle()
  assert.equal(f.pressureStarts(), 0)
  assert.equal(f.reservations(), 0)
})

test('owner cancellation reaches a browser sensor that is already starting', async t => {
  const f = fixture(t), entered = deferred(), reading = deferred()
  let signal
  t.mock.method(f.activity.conditions, 'start', async stop => {
    signal = stop; entered.resolve(); return reading.promise
  })
  f.offer()
  await f.entered
  f.eligible.resolve(true)
  await entered.promise
  f.activity.activity.pause('lifecycle')
  const cancelled = signal.aborted
  reading.resolve(false)
  await f.settle()
  assert.equal(cancelled, true, 'The sensor lifetime must follow its existing owner')
  assert.equal(f.reservations(), 0)
})

test('automatic mode still reaches the browser resource gate when network cost is unknown', async t => {
  const f = fixture(t, 'auto')
  f.offer()
  await f.entered
  f.eligible.resolve(true)
  await f.settle()
  assert.equal(f.pressureStarts(), 1)
  assert.equal(f.reservations(), 0, 'A refused resource gate must not spend an attempt')
})

test('an observed metered network does not start a browser sensor in automatic mode', async t => {
  const f = fixture(t, 'auto')
  navigator.connection = { saveData: true }
  f.offer()
  await f.settle()
  assert.equal(f.pressureStarts(), 0)
  assert.equal(f.reservations(), 0)
})

test('saved metered mode does not open a browser sensor', async t => {
  const f = fixture(t, 'metered')
  f.offer()
  await f.settle()
  assert.equal(f.pressureStarts(), 0)
  assert.equal(f.reservations(), 0)
})
