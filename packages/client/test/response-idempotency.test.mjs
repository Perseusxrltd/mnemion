import { test } from 'node:test'
import assert from 'node:assert/strict'
import { MnemionClient, MnemionError } from '../dist/index.js'

test('capture action methods preserve reviewed bodies, escape path IDs and do not retry an unconfirmed write', async () => {
  const requests = []
  const input = { expected_version: 3, review_token: 'PRIVATE_REVIEW', capture_policy: { include: ['PRIVATE_PATH'] }, previous_grants: 'retain', confirm: true }
  const failure = new Error('PRIVATE_LOST_REPLY')
  const client = new MnemionClient({ baseUrl: 'https://example.invalid', apiKey: 'fixture', fetch: async (url, options) => {
    requests.push({ url, options })
    if (requests.length === 1) return Response.json({ source: { name: 'PRIVATE_SOURCE' } }, { headers: { 'X-Mnemion-Idempotency': 'new' } })
    throw failure
  } })
  const result = await client.changeCapturePolicy('connector/a', 'source?b', 'transition#c', input)
  assert.equal(client.idempotencyOf(result), 'new')
  assert.equal(requests[0].url, 'https://example.invalid/v1/connectors/connector%2Fa/capture-sources/source%3Fb/policy-transitions/transition%23c')
  assert.equal(requests[0].options.method, 'PUT')
  assert.deepEqual(JSON.parse(requests[0].options.body), input)
  assert.equal(requests[0].options.headers['Idempotency-Key'], undefined)
  await assert.rejects(client.revokeCaptureGrant('grant/a'), error => error === failure)
  assert.equal(requests.length, 2)
  assert.equal(requests[1].url, 'https://example.invalid/v1/capture-grants/grant%2Fa')
  assert.equal(requests[1].options.method, 'DELETE')
  assert.equal(requests[1].options.body, undefined)
})

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
