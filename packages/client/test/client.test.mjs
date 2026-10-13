import { test } from 'node:test'
import assert from 'node:assert/strict'
import { MnemionClient, MnemionError } from '../dist/index.js'

test('an offline tunnel has actionable diagnostics without repeating private proxy content', async () => {
  let calls = 0
  const client = new MnemionClient({ baseUrl: 'https://example.invalid', apiKey: 'private-test-token', fetch: async () => {
    calls++
    return new Response('private-test-token and private host details', { status: 404, headers: { 'ngrok-error-code': 'ERR_NGROK_3200', 'X-Request-ID': 'private-test-token' } })
  } })
  await assert.rejects(client.me(), error => error instanceof MnemionError && error.code === 'tunnel_offline' &&
    !JSON.stringify(error).includes('private-test-token') && !error.message.includes('private-test-token'))
  assert.equal(calls, 1)
})

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

test('credential providers refresh their result for a retried idempotent request', async () => {
  let acquisitions = 0
  const calls = []
  const client = new MnemionClient({ baseUrl: 'https://example.invalid', apiKey: async () => 'fixture-' + (++acquisitions), fetch: async (url, options) => {
    calls.push(options)
    if (calls.length === 1) throw new TypeError('Lost response after acceptance')
    return Response.json({ state: 'accepted' })
  } })
  await client.save('space', { content: 'One idempotent memory' })
  assert.equal(acquisitions, 2)
  assert.equal(calls[0].headers.Authorization, 'Bearer fixture-1')
  assert.equal(calls[1].headers.Authorization, 'Bearer fixture-2')
  assert.equal(calls[0].headers['Idempotency-Key'], calls[1].headers['Idempotency-Key'])
  assert.equal(calls[0].body, calls[1].body)
  assert.ok(!JSON.stringify(client).includes('fixture-'))
})

test('credential acquisition failures are not retried even for reads', async () => {
  let acquisitions = 0, requests = 0
  const client = new MnemionClient({ baseUrl: 'https://example.invalid', retries: 5, apiKey: async () => {
    acquisitions++; throw new Error('Protected store is locked')
  }, fetch: async () => { requests++; return Response.json({}) } })
  await assert.rejects(client.me(), /Protected store is locked/)
  assert.equal(acquisitions, 1)
  assert.equal(requests, 0)
})

test('a stalled credential provider is bounded by the request deadline', async () => {
  let acquisitions = 0, requests = 0
  const client = new MnemionClient({ baseUrl: 'https://example.invalid', timeoutMs: 20, retries: 5,
    apiKey: () => { acquisitions++; return new Promise(() => {}) },
    fetch: async () => { requests++; return Response.json({}) },
  })
  await assert.rejects(client.me(), /timed out/)
  assert.equal(acquisitions, 1)
  assert.equal(requests, 0)
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

test('administrator creation is explicit and never inherited by the next identity', async () => {
  const calls = []
  const client = new MnemionClient({ baseUrl: 'https://example.invalid', apiKey: 'fixture', fetch: async (url, options) => {
    const body = JSON.parse(options.body)
    calls.push({ url, body })
    return Response.json({ id: 'fixture', ...body })
  } })
  assert.equal((await client.createPrincipal('Second administrator', 'human', { administrator: true })).administrator, true)
  assert.equal((await client.createPrincipal('Assistant')).administrator, false)
  assert.deepEqual(calls.map(call => call.body), [
    { name: 'Second administrator', kind: 'human', administrator: true },
    { name: 'Assistant', kind: 'application', administrator: false },
  ])
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
  calls = 0
  await assert.rejects(client.disablePrincipal('retired-agent'), error =>
    error instanceof MnemionError && error.retryable && error.retryAfterSeconds === 0.35)
  assert.equal(calls, 1, 'Disabling an identity must not be replayed automatically')
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
