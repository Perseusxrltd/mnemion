import assert from 'node:assert/strict'
import { webcrypto } from 'node:crypto'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import ts from 'typescript'
import { MnemionClient } from '../../../packages/client/dist/index.js'

function native(bridge) {
  const code = ts.transpileModule(readFileSync(new URL('../src/workspace/native.ts', import.meta.url), 'utf8'), {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
  }).outputText
  const exported = {}
  new Function('window', 'exports', 'crypto', code)({ mnemion: bridge }, exported, webcrypto)
  return exported.nativeFetch
}

function stalled() {
  let entered, reject, request
  const started = new Promise(resolve => { entered = resolve })
  const cancelled = []
  const bridge = {
    serviceRequest(value) {
      request = value; entered()
      return new Promise((_, fail) => { reject = fail })
    },
    async serviceRequestCancel(id) { cancelled.push(id); reject(new Error('Native request cancelled')) },
  }
  return { bridge, started, cancelled, request: () => request, stop: () => reject?.(new Error('Fixture stopped')) }
}

async function boundedSettlement(pending) {
  let timer
  try {
    return await Promise.race([
      pending.then(value => ({ state: 'resolved', value }), error => ({ state: 'rejected', error })),
      new Promise(resolve => { timer = setTimeout(() => resolve({ state: 'still_waiting' }), 150) }),
    ])
  } finally { clearTimeout(timer) }
}

test('the SDK deadline promptly cancels a stalled native request', async () => {
  const f = stalled()
  const client = new MnemionClient({ baseUrl: 'https://example.invalid', apiKey: 'fixture-key',
    timeoutMs: 25, retries: 0, fetch: native(f.bridge) })
  const pending = client.me()
  try {
    await f.started
    const observed = await boundedSettlement(pending)
    assert.equal(observed.state, 'rejected')
    assert.match(observed.error.message, /timed out/)
    assert.deepEqual(f.cancelled, [f.request().requestId])
    assert.match(f.request().requestId, /^[0-9a-f-]{36}$/)
  } finally { f.stop(); await pending.catch(() => {}) }
})

test('a user abort settles without waiting for the native network reply', async () => {
  const f = stalled(), controller = new AbortController()
  const pending = native(f.bridge)('https://example.invalid/v1/recall', {
    method: 'POST', body: '{"query":"private fixture"}', signal: controller.signal,
  })
  try {
    await f.started
    const reason = new DOMException('User cancelled', 'AbortError')
    controller.abort(reason)
    const observed = await boundedSettlement(pending)
    assert.equal(observed.state, 'rejected')
    assert.equal(observed.error, reason)
    assert.deepEqual(f.cancelled, [f.request().requestId])
  } finally { f.stop(); await pending.catch(() => {}) }
})

test('pre-aborted work never enters the native bridge', async () => {
  const controller = new AbortController(), reason = new Error('Already cancelled')
  controller.abort(reason)
  await assert.rejects(native({ serviceRequest: () => assert.fail('Cancelled work was dispatched') })(
    'https://example.invalid/v1/me', { signal: controller.signal }), error => error === reason)
  assert.equal(native(undefined), undefined, 'ordinary browser fetch remains separate')
})

test('successful responses remove cancellation listeners and preserve request data', async () => {
  const controller = new AbortController(), requests = [], cancellations = []
  const bridge = {
    async serviceRequest(request) { requests.push(request); return { status: 200,
      headers: { 'Content-Type': 'application/json' }, body: new TextEncoder().encode('{"ready":true}') } },
    async serviceRequestCancel(id) { cancellations.push(id); return true },
  }
  const response = await native(bridge)('https://example.invalid/v1/recall', { method: 'POST',
    headers: { Authorization: 'Bearer private-fixture' }, body: '{"query":"private-query"}', signal: controller.signal })
  assert.deepEqual(await response.json(), { ready: true })
  controller.abort()
  assert.deepEqual(cancellations, [])
  assert.equal(requests[0].body, '{"query":"private-query"}')
  assert.equal(requests[0].headers.authorization, 'Bearer private-fixture')
  assert.ok(!JSON.stringify(requests[0].headers).includes(requests[0].requestId))
})

test('a closing cancel channel and late native rejection cannot delay the caller', async () => {
  const f = stalled(), controller = new AbortController(), reason = new Error('Stop')
  f.bridge.serviceRequestCancel = async () => { throw new Error('Bridge closed') }
  const pending = native(f.bridge)('https://example.invalid/v1/me', { signal: controller.signal })
  await f.started
  controller.abort(reason)
  const observed = await boundedSettlement(pending)
  assert.equal(observed.state, 'rejected')
  assert.equal(observed.error, reason)
  f.stop()
  await new Promise(resolve => setImmediate(resolve))
})

test('a timed-out unsafe SDK write is not retried', async () => {
  const f = stalled(), requests = []
  const original = f.bridge.serviceRequest
  f.bridge.serviceRequest = request => { requests.push(request); return original(request) }
  const client = new MnemionClient({ baseUrl: 'https://example.invalid', apiKey: 'fixture-key',
    timeoutMs: 25, retries: 2, fetch: native(f.bridge) })
  const pending = client.request('POST', '/v1/principals', { body: { name: 'private-fixture' } })
  try {
    await assert.rejects(pending, /timed out/)
    assert.equal(requests.length, 1)
    assert.equal(requests[0].headers['idempotency-key'], undefined)
  } finally { f.stop(); await pending.catch(() => {}) }
})
