import { test } from 'node:test'
import assert from 'node:assert/strict'
import { MnemionClient, MnemionError, supportsJournalFolding, supportsLiveConversations, conversationCapture } from '../dist/index.js'

test('live capture shows only bounded counters from a supported completed checkpoint', () => {
  const checkpoint = { id: 'a'.repeat(32), generation: 'b'.repeat(32), file: 'c'.repeat(32),
    captured: 1000, observed: 1042, read: 1500, reused: 3, rendered: 1 }
  const encode = value => 'jsonl:v1:' + JSON.stringify(value)
  assert.deepEqual(conversationCapture(encode(checkpoint)), {
    captured: 1000, observed: 1042, pending: 42, read: 1500, reused: 3, rendered: 1,
  })
  assert.equal(conversationCapture('jsonl:unfinished-scan'), null)
  assert.equal(conversationCapture('jsonl:v1:{broken'), null)
  assert.equal(conversationCapture(encode({ ...checkpoint, observed: 999 })), null)
  assert.equal(conversationCapture(encode({ ...checkpoint, read: '1500' })), null)
  assert.equal(conversationCapture(encode({ ...checkpoint, reused: -1 })), null)
  assert.equal(conversationCapture(encode({ ...checkpoint, captured: Number.MAX_SAFE_INTEGER + 1 })), null)
  assert.equal(conversationCapture(encode({ ...checkpoint, id: 'arbitrary-source-text' })), null)
  assert.equal(supportsLiveConversations('4.16.99'), false)
  assert.equal(supportsLiveConversations('4.17.0'), true)
  assert.equal(supportsLiveConversations('5.0.0'), true)
  assert.equal(supportsLiveConversations(undefined), false)
})

test('journal filing keeps optimistic versions and does not opt older workspaces in', async () => {
  const calls = []
  const client = new MnemionClient({ baseUrl: 'https://example.invalid', apiKey: 'fixture-key', fetch: async (url, options) => {
    calls.push({ url, method: options.method, body: JSON.parse(options.body) })
    return Response.json({ configured: true, version: 3, fold_enabled: true })
  } })
  await client.organizeJournal('team-space', 2)
  assert.equal(calls[0].url, 'https://example.invalid/v1/spaces/team-space/writeback/organize')
  assert.equal(calls[0].method, 'POST')
  assert.deepEqual(calls[0].body, { expected_version: 2 })
  await client.configureJournal('team-space', { expected_version: 3, destination_id: 'team', publish_to_repository: true, acknowledge_retained_git_history: true })
  assert.ok(!Object.hasOwn(calls[1].body, 'fold_enabled'))
  assert.equal(supportsJournalFolding('4.15.9'), false)
  assert.equal(supportsJournalFolding('4.16.0'), true)
  assert.equal(supportsJournalFolding('5.0.0'), true)
  assert.equal(supportsJournalFolding('unknown'), false)
})

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

test('a safe request catches up with one observed credential rotation', async () => {
  let credential = 'before-rotation'
  const sent = []
  const client = new MnemionClient({ baseUrl: 'https://example.invalid', apiKey: async () => credential,
    fetch: async (_, options) => {
      sent.push(options.headers.Authorization)
      if (sent.length === 1) {
        credential = 'after-rotation'
        return Response.json({ error: { code: 'unauthorized' } }, { status: 401 })
      }
      return Response.json({ principal_id: 'same-person' })
    },
  })
  assert.equal((await client.me()).principal_id, 'same-person')
  assert.deepEqual(sent, ['Bearer before-rotation', 'Bearer after-rotation'])
})

test('rotation recovery never loops, reuses a rejected token or repeats an unsafe write', async () => {
  for (const mode of ['unchanged', 'repeated-rejection', 'write', 'no-retries', 'provider-failure']) {
    let credential = 'first', calls = 0, acquisitions = 0
    const client = new MnemionClient({ baseUrl: 'https://example.invalid', retries: mode === 'no-retries' ? 0 : 5,
      apiKey: async () => {
        acquisitions++
        if (mode === 'provider-failure' && acquisitions > 1) throw new Error('Sign in again')
        return credential
      },
      fetch: async () => {
        calls++
        if (mode !== 'unchanged') credential += '-rotated'
        return Response.json({ error: { code: 'unauthorized' } }, { status: 401 })
      },
    })
    await assert.rejects(mode === 'write' ? client.createPrincipal('person') : client.me())
    assert.equal(calls, mode === 'repeated-rejection' ? 2 : 1, mode)
    assert.ok(acquisitions <= 2, mode)
  }
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
