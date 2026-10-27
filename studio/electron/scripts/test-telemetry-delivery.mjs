import test from 'node:test'
import assert from 'node:assert/strict'
import { mkdtemp, rm, readFile, access } from 'node:fs/promises'
import { spawnSync } from 'node:child_process'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { DatabaseSync } from 'node:sqlite'
import { NativeTelemetryDelivery } from '../dist/telemetry-delivery.js'
import { nativeTelemetryDefinitions } from '../dist/telemetry-store.js'
import { TelemetryWire } from '../dist/telemetry-wire.js'
import { TelemetryFixtureChildren, waitForTelemetryFixture } from './telemetry-fixture-children.mjs'

const repository = resolve(dirname(fileURLToPath(import.meta.url)), '../../..')
const python = process.env.MNEMION_TEST_PYTHON || (process.platform === 'win32' ? 'python' : 'python3')
const environment = { ...process.env, PYTHONPATH: repository, PYTHONNOUSERSITE: '1' }
const observation = { kind: 'submission', workflow: 'memory.recall', surface: 'desktop' }
const network = { network: 'unmetered', constrained: false }
const program = `
import json,sys,sqlite3
from contextlib import closing
from pathlib import Path
from mnemion.product_telemetry import policy,aggregate,delivery,inspection
request=json.loads(sys.stdin.readline())
root,company=Path(request['root']),Path(request['company'])
policy.COLLECTION_AVAILABLE=True
policy.COLLECTOR_URL='https://example.invalid/v1/report'
policy.company_policy_file=lambda:company
policy.transport_available=lambda:True
aggregate._day=lambda:request['now']//86400000
delivery._now_ms=lambda:request['now']
inspection._now_ms=lambda:request['now']
if request.get('wait'):
 print('ready',flush=True)
 sys.stdin.readline()
action=request['action']
if action=='init': result=policy.configure(root,{'enabled':True,'expected_revision':0,'disclosure_version':1})
elif action=='off': result=policy.configure(root,{'enabled':False,'expected_revision':0})
elif action=='on':
 state=policy.status(root)
 result=policy.configure(root,{'enabled':True,'expected_revision':state['revision'],'expected_generation':state['store_generation'],'disclosure_version':1})
elif action=='mode':
 state=policy.status(root)
 result=policy.configure(root,{'enabled':True,'expected_revision':state['revision'],'expected_generation':state['store_generation'],'disclosure_version':1,'connection_mode':request['value']})
elif action=='company':
 company.write_text(json.dumps(request['value']))
 result=True
elif action=='reserve':
 state=policy.status(root)
 result=delivery.DeliveryBudget(root,policy_path=company).reserve(expected_revision=state['revision'],expected_generation=state['store_generation'],network='unmetered',constrained=False) is not None
elif action=='fill':
 state=policy.status(root)
 result=aggregate.record(root,{'kind':'submission','workflow':'memory.recall','surface':'native_agent'},expected_revision=state['revision'],expected_generation=state['store_generation'])
elif action=='review_status': result=inspection.status(root)
elif action in ('review_mode','inspect_report','approve_report','discard_report'):
 state=inspection.status(root)
 control={'expected_revision':state['status']['revision'],'expected_generation':state['status']['store_generation'],'expected_review_token':state['review']['token']}
 if action=='review_mode': control['mode']=request['value']
 result=inspection.execute(root,action,control)
else:
 with closing(sqlite3.connect(root / policy.DATABASE_NAME)) as db:
  clock,next_ms,ticket,deadline=db.execute('SELECT clock_ms,next_ms,lease_token,lease_deadline_ms FROM delivery_state').fetchone()
  result={'next':next_ms,'has_lease':ticket is not None,'attempts':db.execute('SELECT count(*) FROM delivery_attempts').fetchone()[0],
   'bytes':db.execute('SELECT coalesce(sum(reserved_bytes),0) FROM delivery_attempts').fetchone()[0],
   'pending':db.execute('SELECT count(*) FROM pending').fetchone()[0], 'status':policy.status(root)['delivery_budget']}
print(json.dumps(result),flush=True)
`

async function fixture(t) {
  const temporary = await mkdtemp(join(tmpdir(), 'mnemion-delivery-budget-'))
  const children = new TelemetryFixtureChildren(python, environment)
  t.after(async () => {
    await children.close()
    await rm(temporary, { recursive: true, force: true })
  })
  const root = join(temporary, 'private'), company = join(temporary, 'policy.json')
  let now = 1700000000000
  // The supported Windows ARM desktop uses an x64 Python engine. Python must
  // use its own normal clock loader, including the compiler-free OS reader,
  // instead of trying to load the desktop architecture's Node binary.
  const request = (action, extra = {}) => JSON.stringify({ action, root, company, now, ...extra }) + '\n'
  const invoke = (action, extra = {}) => {
    const child = spawnSync(python, ['-c', program], { env: environment, encoding: 'utf8', timeout: 20000, input: request(action, extra) })
    assert.equal(child.status, 0, child.stderr)
    assert.equal(child.stderr, '')
    return JSON.parse(child.stdout)
  }
  const definitions = nativeTelemetryDefinitions()
  assert.equal(definitions.disclosure.collection_available, false)
  const active = { ...definitions.disclosure, collection_available: true, destination: 'https://example.invalid/v1/report' }
  const store = new NativeTelemetryDelivery(root, active, definitions.catalog, company, () => now)
  const initial = invoke('init'), stamp = { revision: initial.revision, store_generation: initial.store_generation }
  return { root, company, store, stamp, invoke, request, definitions, active, children,
    setNow: value => { now = value }, now: () => now,
    fill: async () => assert.equal(await store.record(observation, await store.snapshot(), Math.floor(now / 86400000)), true) }
}

test('Python inspection holds native delivery until approval and preserves exact bytes and later observations', async t => {
  const f = await fixture(t)
  f.setNow(Date.now())
  f.invoke('review_mode', { value: 'review' })
  await f.fill()
  const inspected = f.invoke('inspect_report')
  assert.equal(inspected.review.outcome, 'held')
  assert.equal(inspected.packet.body_bytes, 4)
  assert.equal(await f.store.reserve(f.stamp, network), null)
  assert.equal(f.invoke('inspect').attempts, 0)
  await f.fill()
  assert.equal(f.invoke('inspect').pending, 1)
  assert.equal(f.invoke('approve_report').review.outcome, 'approved')
  const prepare = TelemetryWire.prototype.prepare
  let redraws = 0
  TelemetryWire.prototype.prepare = function (...args) { redraws++; return prepare.apply(this, args) }
  try {
    const report = await f.store.reserve(f.stamp, network)
    assert.ok(report)
    assert.equal(report.reviewed, true)
    assert.equal(Buffer.from(report.body()).toString('base64'), inspected.packet.body_base64)
    assert.equal(redraws, 0)
    const bodies = []
    assert.equal(await f.store.guardedWrite(report, body => { bodies.push(Buffer.from(body).toString('base64')); return true }), true)
    assert.deepEqual(bodies, [inspected.packet.body_base64])
    assert.deepEqual([f.invoke('inspect').attempts, f.invoke('inspect').pending], [1, 1])
    const state = f.invoke('review_status')
    assert.equal(state.review.outcome, 'consumed')
    assert.equal(state.review.report_available, false)
    assert.equal(state.packet, null)
    await f.store.cancel(report)
    assert.equal(await f.store.reserve(f.stamp, network), null)
  } finally { TelemetryWire.prototype.prepare = prepare }
})

test('a changed full review scope blocks native handoff even when the selected metric group remains allowed', async t => {
  const f = await fixture(t)
  f.setNow(Date.now())
  f.invoke('review_mode', { value: 'review' })
  await f.fill()
  f.invoke('inspect_report')
  f.invoke('approve_report')
  const report = await f.store.reserve(f.stamp, network)
  assert.ok(report)
  const wire = new TelemetryWire(JSON.parse(await readFile(new URL('../dist/telemetry-wire-v2.json', import.meta.url), 'utf8')), f.definitions.catalog)
  const group = wire.specification.views[wire.decode(report.body()).view].group
  f.invoke('company', { value: { schema_version: 1, enabled: true, metric_groups: [group] } })
  let writes = 0
  assert.equal(await f.store.guardedWrite(report, () => { writes++; return true }), false)
  assert.equal(writes, 0)
  assert.deepEqual([...report.body()], [0, 0, 0, 0])
  assert.equal(f.invoke('inspect').attempts, 1)
  assert.equal(f.invoke('inspect').has_lease, false)
})

test('helper readiness accepts split CRLF and rejected helpers are fully reaped', { timeout: 15000 }, async t => {
  const children = new TelemetryFixtureChildren(python, environment)
  t.after(() => children.close())
  const split = children.start(['-c',
    'import sys,time; sys.stdout.buffer.write(b"rea"); sys.stdout.buffer.flush(); time.sleep(.03); sys.stdout.buffer.write(b"dy\\r"); sys.stdout.buffer.flush(); time.sleep(.03); sys.stdout.buffer.write(b"\\n"); sys.stdout.buffer.flush(); sys.stdin.read()'])
  await waitForTelemetryFixture(split)
  const rejected = children.start(['-c', 'import sys; print("unexpected",flush=True); sys.stdin.read()'])
  await assert.rejects(waitForTelemetryFixture(rejected), /Unexpected Python fixture readiness/)
  await children.close()
  assert.ok(split.exitCode !== null || split.signalCode !== null)
  assert.ok(rejected.exitCode !== null || rejected.signalCode !== null)
})

test('inactive delivery never creates a store or treats unknown networking as permitted', async t => {
  const f = await fixture(t)
  const missing = join(f.root, 'absent')
  const inactive = new NativeTelemetryDelivery(missing, f.definitions.disclosure, f.definitions.catalog, f.company)
  assert.equal(await inactive.reserve(f.stamp, network), null)
  await assert.rejects(access(missing))
  await f.fill()
  assert.equal(await f.store.reserve(f.stamp), null)
  assert.equal(await f.store.reserve(f.stamp, { network: 'metered', constrained: false }), null)
  assert.equal(await f.store.reserve(f.stamp, { network: 'unmetered', constrained: true }), null)
  assert.equal(f.invoke('inspect').attempts, 0)
})

test('invalid and overflowing pending snapshots remain unspent and unchanged', async t => {
  for (const damage of ['invalid count', 'overflow']) await t.test(damage, async t => {
    const f = await fixture(t)
    const path = join(f.root, 'product-telemetry.sqlite3'), database = new DatabaseSync(path)
    let seeded = 0
    try {
      if (damage === 'overflow') database.exec('DROP TRIGGER pending_bound')
      const insert = database.prepare('INSERT INTO pending VALUES (?, ?, ?)')
      for (let cell = 0; cell < 65536 && seeded < (damage === 'overflow' ? 513 : 2); cell++) {
        try { f.store.catalog.group(cell) } catch { continue }
        insert.run(cell, damage === 'invalid count' && seeded === 1 ? 256 : 1, Math.floor(f.now() / 86400000))
        seeded++
      }
    } finally { database.close() }
    assert.equal(seeded, damage === 'overflow' ? 513 : 2)
    assert.equal(await f.store.reserve(f.stamp, network), null)
    const inspect = new DatabaseSync(path, { readOnly: true })
    try {
      assert.equal(inspect.prepare('SELECT count(*) AS count FROM pending').get().count, seeded)
      assert.equal(inspect.prepare('SELECT count(*) AS count FROM delivery_attempts').get().count, 0)
      assert.deepEqual({ ...inspect.prepare('SELECT clock_ms, next_ms, lease_token, lease_deadline_ms FROM delivery_state').get() },
        { clock_ms: 0, next_ms: 0, lease_token: null, lease_deadline_ms: 0 })
    } finally { inspect.close() }
  })
})

test('native reservation consumes one shared attempt and survives restart, cancellation and reenable', async t => {
  const f = await fixture(t)
  await f.fill()
  const report = await f.store.reserve(f.stamp, network)
  assert.ok(report)
  assert.equal(report.body().length, 4)
  assert.equal(await f.store.current(report), true)
  assert.equal(f.invoke('reserve'), false)
  assert.deepEqual([f.invoke('inspect').attempts, f.invoke('inspect').bytes, f.invoke('inspect').pending], [1, 65536, 0])
  await f.store.cancel(report)
  assert.deepEqual([...report.body()], [0, 0, 0, 0])
  f.invoke('off')
  const state = f.invoke('on'), stamp = { revision: state.revision, store_generation: state.store_generation }
  const restarted = new NativeTelemetryDelivery(f.root, f.active, f.definitions.catalog, f.company, f.now)
  await f.fill()
  assert.equal(await restarted.reserve(stamp, network), null)
  assert.equal(f.invoke('inspect').attempts, 1)
  assert.equal(f.invoke('inspect').has_lease, false)
})

test('the native sender observes the agent connection setting without overriding detected limits', async t => {
  const f = await fixture(t)
  const stamp = f.invoke('mode', { value: 'unmetered' })
  await f.fill()
  assert.equal(await f.store.reserve(stamp, { network: 'metered', constrained: false }), null)
  assert.equal(await f.store.reserve(stamp, { network: 'unknown', constrained: true }), null)
  assert.equal(f.invoke('inspect').attempts, 0)
  const report = await f.store.reserve(stamp, { network: 'unknown', constrained: false })
  assert.ok(report)
  f.invoke('mode', { value: 'metered' })
  assert.equal(await f.store.current(report), false)
  assert.deepEqual([f.invoke('inspect').attempts, f.invoke('inspect').has_lease], [1, false])
})

test('a crashed Python reserver prevents a second native attempt until its persisted due time', async t => {
  const f = await fixture(t)
  assert.equal(f.invoke('fill'), true)
  assert.equal(f.invoke('reserve'), true)
  await f.fill()
  assert.equal(await f.store.reserve(f.stamp, network), null)
  const due = f.invoke('inspect').next
  f.setNow(due - 1)
  await f.fill()
  assert.equal(await f.store.reserve(f.stamp, network), null)
  f.setNow(due)
  const report = await f.store.reserve(f.stamp, network)
  assert.ok(report)
  assert.equal(f.invoke('inspect').attempts, 2)
  await f.store.cancel(report)
})

test('simultaneous real Python and native reservations can consume the queue only once', { timeout: 30000 }, async t => {
  const f = await fixture(t)
  await f.fill()
  const child = f.children.start(['-c', program])
  let stdout = '', stderr = ''
  child.stdout.on('data', data => { stdout += data })
  child.stderr.on('data', data => { stderr += data })
  child.stdin.write(f.request('reserve', { wait: true }))
  await waitForTelemetryFixture(child)
  const pending = f.store.reserve(f.stamp, network)
  child.stdin.end('go\n')
  const report = await pending
  assert.equal(await f.children.exited(child), 0, stderr)
  assert.equal(stderr, '')
  const pythonWon = JSON.parse(stdout.trim().split('\n').at(-1))
  const winners = Number(Boolean(report)) + Number(pythonWon)
  assert.ok(winners <= 1, 'contending processes cannot consume the same queue twice')
  const state = f.invoke('inspect')
  assert.equal(state.attempts, winners)
  assert.equal(state.bytes, 65536 * winners)
  assert.equal(state.pending, winners ? 0 : 1)
  // Zero lock waiting also permits both processes to defer if a reader
  // overlaps a commit. A later explicit attempt must find the intact queue.
  if (!winners) {
    const later = await f.store.reserve(f.stamp, network)
    assert.ok(later)
    assert.deepEqual([f.invoke('inspect').attempts, f.invoke('inspect').pending], [1, 0])
    await f.store.cancel(later)
  }
  if (report) await f.store.cancel(report)
})

test('a contended commit leaves both runtimes an unspent and recoverable queue', { timeout: 30000 }, async t => {
  const f = await fixture(t)
  await f.fill()
  const reader = f.children.start(['-c',
    'import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); c.execute("BEGIN"); c.execute("SELECT count(*) FROM pending").fetchall(); print("ready",flush=True); sys.stdin.read(); c.rollback(); c.close()',
    join(f.root, 'product-telemetry.sqlite3')])
  let errors = ''
  reader.stderr.on('data', data => { errors += data })
  await waitForTelemetryFixture(reader)
  assert.equal(await f.store.reserve(f.stamp, network), null)
  assert.equal(f.invoke('reserve'), false)
  reader.stdin.end()
  assert.equal(await f.children.exited(reader), 0, errors)
  assert.equal(errors, '')
  const retained = f.invoke('inspect')
  assert.deepEqual([retained.attempts, retained.bytes, retained.pending, retained.has_lease], [0, 0, 1, false])
  const report = await f.store.reserve(f.stamp, network)
  assert.ok(report)
  const spent = f.invoke('inspect')
  assert.deepEqual([spent.attempts, spent.bytes, spent.pending], [1, 65536, 0])
  await f.store.cancel(report)
})

test('Python opt-out defeats a pending native reserve and the final native write', async t => {
  const f = await fixture(t)
  await f.fill()
  const pending = f.store.reserve(f.stamp, network)
  f.invoke('off')
  assert.equal(await pending, null)
  const state = f.invoke('on'), stamp = { revision: state.revision, store_generation: state.store_generation }
  await f.fill()
  const report = await f.store.reserve(stamp, network)
  assert.ok(report)
  f.invoke('off')
  let calls = 0
  assert.equal(await f.store.guardedWrite(report, () => { calls++; return true }), false)
  assert.equal(calls, 0)
  assert.deepEqual([...report.body()], [0, 0, 0, 0])
  assert.equal(f.invoke('inspect').has_lease, false)
})

test('only one final handoff can succeed and its private nonce never enters the four-byte body', async t => {
  const f = await fixture(t)
  await f.fill()
  const report = await f.store.reserve(f.stamp, network), writes = []
  assert.ok(report)
  const first = f.store.guardedWrite(report, body => { writes.push([...body]); return true })
  const second = f.store.guardedWrite(report, body => { writes.push([...body]); return true })
  const results = await Promise.all([first, second])
  assert.equal(results.filter(Boolean).length, 1)
  assert.equal(writes.length, 1)
  assert.equal(writes[0].length, 4)
  assert.deepEqual([...report.body()], [0, 0, 0, 0])
  assert.equal(await f.store.current(report), true)
  assert.equal(f.invoke('inspect').has_lease, true)
  await f.store.cancel(report)
  assert.equal(f.invoke('inspect').has_lease, false)
  const raw = await readFile(join(f.root, 'product-telemetry.sqlite3'))
  assert.ok(raw.length <= 96 * 1024)
})

test('expiry and narrower company policy erase the durable lease without refund', async t => {
  const f = await fixture(t)
  f.invoke('company', { value: { schema_version: 1, enabled: true, metric_groups: ['usage'] } })
  await f.fill()
  const report = await f.store.reserve(f.stamp, network)
  assert.ok(report)
  f.invoke('company', { value: { schema_version: 1, enabled: true, metric_groups: ['resources'] } })
  assert.equal(await f.store.current(report), false)
  assert.equal(f.invoke('inspect').has_lease, false)
  f.invoke('company', { value: { schema_version: 1, enabled: true, metric_groups: ['usage'] } })
  f.setNow(f.invoke('inspect').next)
  await f.fill()
  const later = await f.store.reserve(f.stamp, network)
  assert.ok(later)
  f.setNow(f.now() + 5000)
  assert.equal(await f.store.current(later), false)
  assert.equal(f.invoke('inspect').has_lease, false)
  assert.equal(f.invoke('inspect').attempts, 2)
})

for (const handedOff of [false, true]) for (const abortFails of [false, true]) test(`active-attempt watcher observes Python opt-out, handedOff=${handedOff}, abort failure=${abortFails}`, async t => {
  const f = await fixture(t)
  await f.fill()
  const report = await f.store.reserve(f.stamp, network)
  assert.ok(report)
  if (handedOff) {
    assert.equal(await f.store.guardedWrite(report, () => true), true)
    assert.equal(await f.store.current(report), true)
  }
  const stop = new AbortController()
  t.after(() => stop.abort())
  let cancelled
  const observed = new Promise(resolve => { cancelled = resolve })
  let calls = 0
  const running = f.store.watch(report, () => {
    calls++
    cancelled()
    if (abortFails) throw new Error('PRIVATE_ABORT_SENTINEL')
  }, stop.signal)
  f.invoke('off')
  let timer
  try {
    await Promise.race([observed, new Promise((_, reject) => { timer = setTimeout(() => reject(new Error('cancellation timed out')), 2000) })])
  } finally { clearTimeout(timer) }
  await running
  assert.equal(calls, 1)
  assert.deepEqual([...report.body()], [0, 0, 0, 0])
  assert.equal(f.invoke('inspect').attempts, 1)
  assert.equal(f.invoke('inspect').has_lease, false)
})

test('a stalled wall clock cannot extend a native prepared report lifetime', async t => {
  const f = await fixture(t)
  let elapsed = 1000
  const store = new NativeTelemetryDelivery(f.root, f.active, f.definitions.catalog, f.company, f.now, () => elapsed)
  await f.fill()
  const report = await store.reserve(f.stamp, network)
  assert.ok(report)
  assert.equal(await store.current(report), true)
  elapsed += 5001
  let calls = 0
  assert.equal(await store.guardedWrite(report, () => { calls++; return true }), false)
  assert.equal(calls, 0)
  assert.deepEqual([...report.body()], [0, 0, 0, 0])
  assert.equal(f.invoke('inspect').has_lease, false)
  assert.equal(f.invoke('inspect').attempts, 1)
})
