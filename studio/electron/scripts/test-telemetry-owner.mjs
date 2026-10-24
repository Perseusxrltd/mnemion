import test from 'node:test'
import assert from 'node:assert/strict'
import { TelemetryActivity } from '../dist/telemetry-owner.js'

const stamp = { revision: 1, store_generation: 'a'.repeat(32) }

test('awake work is coalesced and paused reasons cannot resume each other', async () => {
  let reservations = 0, sends = 0, releases = 0, now = 0, finish
  const pending = new Promise(resolve => { finish = resolve })
  const report = {}
  const owner = new TelemetryActivity({ available: () => true,
    reserve: async () => { reservations++; await pending; return report },
    send: async () => { sends++ }, cancel: async value => { assert.equal(value, report); releases++ } }, () => now)
  owner.offer(stamp); owner.offer(stamp)
  await Promise.resolve()
  assert.equal(reservations, 1)
  owner.pause('suspend'); owner.pause('update'); owner.resume('suspend')
  finish(); await owner.settled()
  assert.equal(sends, 0); assert.equal(releases, 1)
  owner.offer(stamp); await owner.settled()
  assert.equal(reservations, 1)
  owner.resume('update'); owner.offer(stamp); await owner.settled()
  assert.equal(sends, 1)
  owner.offer(stamp); await owner.settled()
  assert.equal(reservations, 2)
  now = 60001; owner.offer(stamp); await owner.settled()
  assert.equal(reservations, 3)
  owner.close(); now = 120002; owner.resume(); owner.offer(stamp); await owner.settled()
  assert.equal(reservations, 3)
})

test('unavailable owners and a shutdown before dispatch create no reservation', async () => {
  let reservations = 0, enabled = false
  const owner = new TelemetryActivity({ available: () => enabled,
    reserve: async () => { reservations++; return {} }, send: async () => {}, cancel: async () => {} })
  owner.offer(stamp); await owner.settled()
  assert.equal(reservations, 0)
  enabled = true; owner.offer(stamp); owner.close(); await owner.settled()
  assert.equal(reservations, 0)
})

test('an active send receives cancellation without replay or a shutdown flush', async () => {
  let entered, signals = 0, attempts = 0
  const started = new Promise(resolve => { entered = resolve })
  const owner = new TelemetryActivity({ available: () => true,
    reserve: async () => { attempts++; return {} }, cancel: async () => {},
    send: async (_report, stop) => { entered(); await new Promise(resolve => stop.addEventListener('abort', () => { signals++; resolve() }, { once: true })) } })
  owner.offer(stamp); await started; owner.close(); await owner.settled()
  assert.equal(signals, 1); assert.equal(attempts, 1)
})
