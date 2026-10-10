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
