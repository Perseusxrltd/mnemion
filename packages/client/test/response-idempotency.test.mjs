import { test } from 'node:test'
import assert from 'node:assert/strict'
import { MnemionClient, MnemionError } from '../dist/index.js'

test('fresh/replayed metadata belongs to the exact response, without changing its body', async () => {
  let index = 0
  const headers = ['new', 'replayed', 'PRIVATE_SENTINEL', null]
  const client = new MnemionClient({ baseUrl: 'https://example.invalid', apiKey: 'fixture', fetch: async () => {
    const disposition = headers[index++]
    return Response.json({ idempotency: 'PRIVATE_SENTINEL', content: 'private response' }, {
      headers: disposition ? { 'X-Mnemion-Idempotency': disposition } : {},
    })
  } })
  const responses = await Promise.all(headers.map(() => client.me()))
  assert.deepEqual(responses.map(value => client.idempotencyOf(value)), ['new', 'replayed', null, null])
  assert.ok(responses.every(value => Object.keys(value).join() === 'idempotency,content'))
  assert.equal(client.idempotencyOf({ ...responses[0] }), null)
  assert.equal(client.idempotencyOf(null), null)
  assert.equal(index, 4, 'reading metadata sent no additional request')
})

test('metadata survives binary replies and errors without associating empty replies', async () => {
  let index = 0
  const client = new MnemionClient({ baseUrl: 'https://example.invalid', apiKey: 'fixture', retries: 0, fetch: async () => {
    if (index++ === 0) return new Response(new Uint8Array([1, 2, 3]), { headers: { 'X-Mnemion-Idempotency': 'new' } })
    if (index === 2) return new Response(null, { status: 204, headers: { 'X-Mnemion-Idempotency': 'replayed' } })
    return Response.json({ error: { code: 'conflict', message: 'PRIVATE_SENTINEL' } }, {
      status: 409, headers: { 'X-Mnemion-Idempotency': 'replayed' },
    })
  } })
  const bytes = await client.exportObsidian()
  assert.equal(bytes.byteLength, 3)
  assert.equal(client.idempotencyOf(bytes), 'new')
  const empty = await client.revokeKey('fixture')
  assert.equal(empty, undefined)
  assert.equal(client.idempotencyOf(empty), null)
  let failure
  try { await client.me() } catch (error) { failure = error }
  assert.ok(failure instanceof MnemionError)
  assert.equal(failure.message, 'PRIVATE_SENTINEL', 'the SDK still delivers the original diagnostic to its caller')
  assert.equal(client.idempotencyOf(failure), 'replayed')
})
