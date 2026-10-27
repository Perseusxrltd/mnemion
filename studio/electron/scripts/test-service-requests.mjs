import assert from 'node:assert/strict'
import { randomUUID } from 'node:crypto'
import { once } from 'node:events'
import { createServer } from 'node:http'
import test from 'node:test'
import { ServiceRequests } from '../dist/service-requests.js'
import { workspaceFetch } from '../dist/workspace-fetch.js'

function held(registry, owner, id = randomUUID(), cooperative = true) {
  let signal, finish
  const pending = registry.run(owner, id, async stop => {
    signal = stop
    return new Promise((resolve, reject) => {
      finish = resolve
      if (cooperative) stop.addEventListener('abort', () => reject(stop.reason), { once: true })
    })
  })
  return { id, pending, signal: () => signal, finish: () => finish('settled') }
}

test('cancellation belongs to its actual renderer, even with the same token', async () => {
  const registry = new ServiceRequests(), id = randomUUID()
  const first = held(registry, 1, id), second = held(registry, 2, id)
  assert.equal(registry.cancel(3, id), false)
  assert.equal(registry.cancel(1, 'invalid-private-id'), false)
  assert.equal(registry.cancel(1, id), true)
  await assert.rejects(first.pending, /cancelled/)
  assert.equal(second.signal().aborted, false)
  assert.equal(registry.cancel(1, id), false)
  registry.closeOwner(2)
  await assert.rejects(second.pending, /page closed/)
})

test('an aborted but unsettled native lifetime cannot be overwritten', async () => {
  const registry = new ServiceRequests(), first = held(registry, 1, randomUUID(), false)
  assert.equal(registry.cancel(1, first.id), true)
  assert.equal(first.signal().aborted, true)
  await assert.rejects(registry.run(1, first.id, async () => assert.fail('Duplicate work')), /already active/)
  first.finish()
  await first.pending
  assert.equal(await registry.run(1, first.id, async () => 'fresh'), 'fresh')
})

test('lifetime capacity includes cancelled work until actual settlement', async () => {
  const registry = new ServiceRequests(), work = []
  try {
    for (let index = 0; index < registry.maximum; index++) work.push(held(registry, 1, randomUUID(), false))
    registry.closeOwner(1)
    assert.ok(work.every(item => item.signal().aborted))
    await assert.rejects(registry.run(2, randomUUID(), async () => assert.fail('Over-capacity work')), /Too many/)
  } finally { for (const item of work) item.finish(); await Promise.all(work.map(item => item.pending)) }
  assert.equal(await registry.run(2, randomUUID(), async () => 'available'), 'available')
})

test('shutdown aborts all owners and refuses new requests', async () => {
  const registry = new ServiceRequests(), first = held(registry, 1), second = held(registry, 2)
  registry.close()
  await Promise.all([assert.rejects(first.pending, /Studio closed/), assert.rejects(second.pending, /Studio closed/)])
  await assert.rejects(registry.run(1, randomUUID(), async () => assert.fail('Post-shutdown work')), /shutting down/)
})

test('invalid tokens and failures cannot acquire or leak a live slot', async () => {
  const registry = new ServiceRequests()
  for (const id of ['', 'x'.repeat(4096), 42, {}, null]) {
    await assert.rejects(registry.run(1, id, async () => assert.fail('Invalid token dispatched')), /Invalid/)
  }
  const id = randomUUID(), original = new Error('Original network failure')
  await assert.rejects(registry.run(1, id, async () => { throw original }), error => error === original)
  assert.equal(registry.cancel(1, id), false)
  assert.equal(await registry.run(1, undefined, async signal => !signal.aborted), true, 'legacy callers remain bounded')
})

for (const phase of ['headers', 'body']) test(`cancellation closes a real HTTP request while waiting for ${phase}`, { timeout: 10_000 }, async t => {
  const registry = new ServiceRequests(), id = randomUUID()
  let entered, closed, headers
  const started = new Promise(resolve => { entered = resolve })
  const ended = new Promise(resolve => { closed = resolve })
  const server = createServer((request, response) => {
    headers = request.headers
    response.once('close', closed)
    if (phase === 'body') { response.writeHead(200, { 'Content-Type': 'application/json' }); response.write('{"pending":') }
    entered()
  })
  server.listen(0, '127.0.0.1')
  await once(server, 'listening')
  t.after(() => new Promise(resolve => { registry.close(); server.close(resolve); server.closeAllConnections() }))
  const pending = registry.run(1, id, async signal => {
    const response = await workspaceFetch(fetch, `http://127.0.0.1:${server.address().port}/v1/recall`, {
      method: 'POST', headers: { Authorization: 'Bearer fixture-only', 'Content-Type': 'application/json' },
      body: '{"query":"fixture"}', signal,
    })
    return response.text()
  })
  await started
  assert.equal(registry.cancel(1, id), true)
  await assert.rejects(pending)
  await Promise.race([ended, new Promise((_, reject) => {
    const timer = setTimeout(() => reject(new Error('Cancelled socket did not close')), 5000)
    timer.unref(); ended.finally(() => clearTimeout(timer))
  })])
  assert.equal(headers.authorization, 'Bearer fixture-only')
  assert.equal(headers['ngrok-skip-browser-warning'], 'mnemion')
  assert.ok(!JSON.stringify(headers).includes(id), 'local cancellation token is never a server header')
  assert.equal(registry.cancel(1, id), false)
})
