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

test('awake work retains only the latest committed stamp and the existing cadence', async () => {
  let now = 0, reservations = 0
  const seen = []
  const owner = new TelemetryActivity({ available: () => true,
    reserve: async expected => { reservations++; seen.push({ ...expected }); expected.revision = 99; return null },
    send: async () => assert.fail('No report was reserved'), cancel: async () => {} }, () => now)
  owner.awake(); await owner.settled()
  assert.equal(reservations, 0, 'Activity alone cannot invent an originating stamp')
  const first = { ...stamp }
  owner.offer(first); await owner.settled()
  first.revision = 20
  const second = { ...stamp, revision: 2 }
  owner.offer(second); second.revision = 30
  for (let index = 0; index < 100; index++) owner.awake()
  await owner.settled()
  assert.equal(reservations, 1)
  now = 60001
  owner.pause('suspend'); owner.awake(); await owner.settled()
  assert.equal(reservations, 1)
  owner.resume('suspend'); owner.awake(); await owner.settled()
  assert.deepEqual(seen, [stamp, { ...stamp, revision: 2 }])
  owner.close(); now = 120002; owner.awake(); await owner.settled()
  assert.equal(reservations, 2)
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

test('manual approval gets one immediate check after an automatic preflight', async () => {
  let reservations = 0, now = 0
  const owner = new TelemetryActivity({ available: () => true,
    reserve: async () => { reservations++; return null },
    send: async () => assert.fail('No report was reserved'), cancel: async () => {} }, () => now)
  owner.offer(stamp); await owner.settled()
  assert.equal(reservations, 1)
  owner.offer(stamp, true); await owner.settled()
  assert.equal(reservations, 2)
  for (let index = 0; index < 10; index++) { owner.offer(stamp); owner.offer(stamp, true) }
  await owner.settled()
  assert.equal(reservations, 2, 'Repeated approvals cannot create a burst of preflights')
  now = 60001
  owner.offer(stamp, true); await owner.settled()
  assert.equal(reservations, 3)
  owner.close()
})

test('one explicit approval follows active cleanup with its original policy stamp', async () => {
  let finish, reservations = 0
  const pending = new Promise(resolve => { finish = resolve })
  const seen = []
  const owner = new TelemetryActivity({ available: () => true,
    reserve: async expected => { seen.push({ ...expected }); if (++reservations === 1) await pending; return null },
    send: async () => assert.fail('No report was reserved'), cancel: async () => {} }, () => 0)
  owner.offer(stamp); await Promise.resolve()
  const approval = { ...stamp, revision: 2 }
  owner.offer(approval, true); owner.offer(approval, true)
  approval.revision = 99
  finish(); await owner.settled()
  assert.deepEqual(seen, [stamp, { ...stamp, revision: 2 }])
  owner.close()
})

for (const transition of ['pause', 'close']) test('pending approval is discarded on ' + transition, async () => {
  let finish, reservations = 0
  const pending = new Promise(resolve => { finish = resolve })
  const owner = new TelemetryActivity({ available: () => true,
    reserve: async () => { reservations++; await pending; return null },
    send: async () => assert.fail('No report was reserved'), cancel: async () => {} }, () => 0)
  owner.offer(stamp); await Promise.resolve()
  owner.offer(stamp, true)
  if (transition === 'pause') owner.pause('lifecycle')
  else owner.close()
  finish(); await owner.settled()
  assert.equal(reservations, 1)
  owner.close()
})
