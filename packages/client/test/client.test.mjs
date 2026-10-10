import { test } from 'node:test'
import assert from 'node:assert/strict'
import { MnemionClient, MnemionError } from '../dist/index.js'

test('uncertain saves retry with the same idempotency key and body', async () => {
  const calls = []
  const client = new MnemionClient({ baseUrl: 'http://example.test', apiKey: 'dummy-key', fetch: async (url, options) => {
    calls.push({ url, ...options })
    if (calls.length === 1) throw new TypeError('Connection closed after commit')
    return Response.json({ memory_id: 'one', state: 'accepted' })
  } })
  const saved = await client.save('space', { content: 'Billing uses Postgres' })
  assert.equal(saved.state, 'accepted')
  assert.equal(calls.length, 2)
  assert.equal(calls[0].headers['Idempotency-Key'], calls[1].headers['Idempotency-Key'])
  assert.equal(calls[0].body, calls[1].body)
  assert.ok(!JSON.stringify(client).includes('dummy-key'))
})

test('authorization failure has a stable error and is not retried', async () => {
  let calls = 0
  const client = new MnemionClient({ baseUrl: 'http://example.test', apiKey: 'invalid', fetch: async () => {
    calls++
    return Response.json({ error: { code: 'unauthorized', message: 'API key revoked' }, request_id: 'request-one' }, { status: 401 })
  } })
  await assert.rejects(client.fetch('memory'), error => error instanceof MnemionError && error.status === 401 && error.requestId === 'request-one')
  assert.equal(calls, 1)
})

test('non-idempotent administrative writes are not silently repeated', async () => {
  let calls = 0
  const client = new MnemionClient({ baseUrl: 'http://example.test', apiKey: 'dummy', fetch: async () => {
    calls++; throw new TypeError('Network lost')
  } })
  await assert.rejects(client.createPrincipal('Billing app'))
  assert.equal(calls, 1)
})

test('browser fetch is invoked with its required global receiver', async () => {
  const client = new MnemionClient({ baseUrl: 'http://example.test', apiKey: 'dummy', fetch: function () {
    assert.equal(this, globalThis, 'Browser fetch rejects a client-instance receiver')
    return Promise.resolve(Response.json({ principal_id: 'browser-client' }))
  } })
  assert.equal((await client.me()).principal_id, 'browser-client')
})

test('busy reads respect Retry-After without replaying administrative writes', async () => {
  let calls = 0
  const fetch = async () => {
    calls++
    return calls === 1
      ? Response.json({ error: { code: 'inference_busy', message: 'Retry shortly' } }, { status: 503, headers: { 'Retry-After': '0.35' } })
      : Response.json({ hits: [] })
  }
  const client = new MnemionClient({ baseUrl: 'http://example.test', apiKey: 'dummy', fetch })
  const started = performance.now()
  await client.search({ query: 'decision', all_accessible: true })
  assert.ok(performance.now() - started >= 300, 'The server admission delay must be respected')
  assert.equal(calls, 2)
  calls = 0
  await assert.rejects(client.createPrincipal('agent'), error =>
    error instanceof MnemionError && error.retryable && error.retryAfterSeconds === 0.35)
  assert.equal(calls, 1)
})

test('retry hints are bounded and non-object proxy errors remain structured', async () => {
  for (const [header, expected] of [['9999999', 30], ['invalid', undefined], [new Date(Date.now() + 600000).toUTCString(), 30]]) {
    const client = new MnemionClient({ baseUrl: 'http://example.test', apiKey: 'dummy', retries: 0,
      fetch: async () => Response.json(null, { status: 503, headers: { 'Retry-After': header } }) })
    await assert.rejects(client.me(), error => error instanceof MnemionError && error.code === 'http_error' && error.retryAfterSeconds === expected)
  }
})

test('cancelling during backoff stops the wait and the next request', async () => {
  let calls = 0
  const abort = new AbortController()
  const client = new MnemionClient({ baseUrl: 'http://example.test', apiKey: 'dummy', fetch: async () => {
    calls++
    return Response.json({}, { status: 503, headers: { 'Retry-After': '30' } })
  } })
  const pending = client.request('GET', '/v1/me', { signal: abort.signal })
  const timer = setTimeout(() => abort.abort(new Error('Cancelled by user')), 20)
  try { await assert.rejects(pending, /Cancelled by user/) } finally { clearTimeout(timer) }
  assert.equal(calls, 1)
})
