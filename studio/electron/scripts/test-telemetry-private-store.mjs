import test from 'node:test'
import assert from 'node:assert/strict'
import { EventEmitter } from 'node:events'
import { WindowsTelemetryPrivateProbe } from '../dist/telemetry-private-store.js'

class Helper extends EventEmitter {
  pid = 123
  kills = 0
  unrefs = 0
  kill() { this.kills++; return true }
  unref() { this.unrefs++; return this }
}

function fixture(t) {
  const children = [], arguments_ = []
  const probe = new WindowsTelemetryPrivateProbe((root, database) => {
    arguments_.push([root, database])
    const child = new Helper()
    children.push(child)
    return child
  })
  t.after(() => { for (const child of children) child.emit('exit', 1) })
  return { probe, children, arguments_ }
}

test('a concurrent permission check is dropped rather than borrowing another path approval', async t => {
  const { probe, children, arguments_ } = fixture(t)
  const first = probe.read('first root', 'first database')
  assert.equal(await probe.read('other root', 'other database'), false)
  assert.equal(children.length, 1)
  children[0].emit('exit', 0)
  assert.equal(await first, true)
  const second = probe.read('other root', 'other database')
  children[1].emit('exit', 1)
  assert.equal(await second, false)
  assert.deepEqual(arguments_, [['first root', 'first database'], ['other root', 'other database']])
})

test('a timeout refuses permission but holds the helper slot until actual exit', async t => {
  const { probe, children } = fixture(t)
  // Only the test owns this lifetime; a timed-out native helper must not keep
  // the application's event loop alive or allow replacement helpers to pile up.
  const awake = setTimeout(() => {}, 3000)
  t.after(() => clearTimeout(awake))
  const first = probe.read('root', 'database')
  assert.equal(await first, false)
  assert.equal(children[0].kills, 1)
  assert.equal(children[0].unrefs, 1)
  for (let index = 0; index < 32; index++) assert.equal(await probe.read('root', 'database'), false)
  assert.equal(children.length, 1)
  children[0].emit('exit', 0)
  assert.equal(await first, false, 'a late success cannot grant the timed-out check')
  const second = probe.read('root', 'database')
  children[1].emit('exit', 0)
  assert.equal(await second, true)
})

test('a live-process error cannot free its slot, and repeated errors cannot escape', async t => {
  const { probe, children } = fixture(t)
  const first = probe.read('root', 'database')
  children[0].emit('error', new Error('simulated kill refusal'))
  assert.equal(await first, false)
  assert.equal(await probe.read('root', 'database'), false)
  assert.equal(children.length, 1)
  assert.ok(children[0].unrefs > 0)
  assert.doesNotThrow(() => children[0].emit('error', new Error('later process error')))
  children[0].emit('exit', 1)
  const next = probe.read('root', 'database')
  children[1].emit('exit', 0)
  assert.equal(await next, true)
})

test('a spawn failure frees its own slot without a stale callback releasing the successor', async t => {
  const { probe, children } = fixture(t)
  const first = probe.read('root', 'database')
  children[0].pid = undefined
  children[0].emit('error', new Error('executable unavailable'))
  assert.equal(await first, false)
  const second = probe.read('root', 'database')
  children[0].emit('exit', 1)
  assert.equal(await probe.read('root', 'database'), false)
  assert.equal(children.length, 2)
  children[1].emit('exit', 0)
  assert.equal(await second, true)
})

test('a synchronous launch failure never retains a helper slot', async () => {
  let calls = 0
  const probe = new WindowsTelemetryPrivateProbe(() => { calls++; throw new Error('invalid launch') })
  assert.equal(await probe.read('root', 'database'), false)
  assert.equal(await probe.read('root', 'database'), false)
  assert.equal(calls, 2)
})
