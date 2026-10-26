import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { BroadcastChannel } from 'node:worker_threads'
import assert from 'node:assert/strict'
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
const { BrowserReviewClock } = load(new URL('../src/workspace/telemetry-review-clock.ts', import.meta.url))
const { startReviewLifetime, checkReviewLifetime } = load(new URL('../../electron/telemetry-review-lifetime.ts', import.meta.url))
let serial = 0
function fixture() {
  const channelName = `mnemion-review-test-${process.pid}-${++serial}`, pages = [], calls = { channel: 0, nonce: 0 }
  let elapsed = 50, busy = false, nonce = 0
  const locks = { async request(_name, { ifAvailable }, callback) {
    assert.equal(ifAvailable, true)
    if (busy) return callback(null)
    busy = true
    try { return await callback({}) } finally { busy = false }
  } }
  return {
    calls, advance: amount => { elapsed += amount },
    page(origin = 0, overrides = {}) {
      const page = new BrowserReviewClock({ now: () => origin + elapsed, locks: () => locks,
        channel: () => { calls.channel++; return new BroadcastChannel(channelName) },
        nonce: () => { calls.nonce++; return (++nonce).toString(16).padStart(32, '0') }, ...overrides })
      pages.push(page)
      return page
    },
    close: () => pages.forEach(page => page.close()),
  }
}

test('read-only views and unavailable coordination cannot initialize a browser review epoch', async () => {
  const f = fixture()
  try {
    const page = f.page()
    assert.equal(page.read(), null)
    assert.equal(await page.ensure('invalid'), null)
    assert.equal(await f.page(0, { locks: () => null }).ensure(), null)
    assert.equal(await f.page(0, { locks: () => ({ request: async (_name, _options, callback) => callback(null) }) }).ensure(), null)
    assert.deepEqual(f.calls, { channel: 0, nonce: 0 })
  } finally { f.close() }
})

test('live tabs with different clock origins preserve the original report age', async () => {
  const f = fixture()
  try {
    const first = f.page(100_000), second = f.page(27)
    const created = await first.ensure()
    assert.ok(created)
    const lifetime = startReviewLifetime(1_000_000, created, 2_000_000)
    f.advance(100_000)
    const joined = await second.ensure(created.epoch)
    assert.ok(joined)
    assert.equal(joined.epoch, created.epoch)
    assert.ok(joined.elapsed_ms >= 100_000)
    const checked = checkReviewLifetime(lifetime, 1_100_000, joined)
    assert.ok(checked)
    assert.equal(checked.created_ms, lifetime.created_ms)
    assert.equal(checked.expires_ms, lifetime.expires_ms)
    first.close()
    f.advance(800_000)
    assert.equal(checkReviewLifetime(checked, 1_100_000, second.read()), null)
  } finally { f.close() }
})

test('closing every peer prevents a reopened page from reviving an old approval clock', async () => {
  const f = fixture()
  try {
    const oldPage = f.page(), oldClock = await oldPage.ensure()
    assert.ok(oldClock)
    oldPage.close()
    const reopened = f.page(300_000)
    assert.equal(await reopened.ensure(oldClock.epoch), null)
    assert.equal(reopened.read(), null)
    const fresh = await reopened.ensure()
    assert.ok(fresh)
    assert.notEqual(fresh.epoch, oldClock.epoch)
    assert.equal(checkReviewLifetime(startReviewLifetime(0, oldClock, 900_000), 1, fresh), null)
  } finally { f.close() }
})

test('simultaneous tabs do not create competing epochs while discovery owns the origin lock', async () => {
  const f = fixture()
  try {
    const first = f.page(), second = f.page(17_000)
    const starting = first.ensure()
    assert.equal(await second.ensure(), null)
    const created = await starting
    assert.ok(created)
    const joined = await second.ensure()
    assert.ok(joined)
    assert.equal(joined.epoch, created.epoch)
  } finally { f.close() }
})

test('page exit cancels discovery and rollback permanently discards the local clock', async () => {
  const f = fixture()
  try {
    const exiting = f.page(), pending = exiting.ensure()
    exiting.close()
    assert.equal(await pending, null)
    assert.equal(exiting.read(), null)
    const page = f.page(), created = await page.ensure()
    assert.ok(created)
    f.advance(10)
    assert.ok(page.read())
    f.advance(-1)
    assert.equal(page.read(), null)
    f.advance(10)
    assert.equal(page.read(), null)
    assert.equal(await page.ensure(created.epoch), null)
  } finally { f.close() }
})

test('missing channels and invalid random values fail closed without a clock', async () => {
  const f = fixture()
  try {
    const missing = f.page(0, { channel: () => { throw new Error('unavailable') } })
    assert.equal(await missing.ensure(), null)
    assert.equal(missing.read(), null)
    assert.equal(await f.page(0, { nonce: () => '0'.repeat(32) }).ensure(), null)
  } finally { f.close() }
})
