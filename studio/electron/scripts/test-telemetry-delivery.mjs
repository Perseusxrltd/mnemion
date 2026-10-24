import test from 'node:test'
import assert from 'node:assert/strict'
import { mkdtemp, rm, readFile, access } from 'node:fs/promises'
import { spawnSync, spawn } from 'node:child_process'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { NativeTelemetryDelivery } from '../dist/telemetry-delivery.js'
import { nativeTelemetryDefinitions } from '../dist/telemetry-store.js'

const repository = resolve(dirname(fileURLToPath(import.meta.url)), '../../..')
const python = process.env.MNEMION_TEST_PYTHON || (process.platform === 'win32' ? 'python' : 'python3')
const environment = { ...process.env, PYTHONPATH: repository, PYTHONNOUSERSITE: '1' }
const observation = { kind: 'submission', workflow: 'memory.recall', surface: 'desktop' }
const network = { network: 'unmetered', constrained: false }
const program = `
import json,sys,sqlite3
from contextlib import closing
from pathlib import Path
from mnemion.product_telemetry import policy,aggregate,delivery
request=json.loads(sys.stdin.readline())
root,company=Path(request['root']),Path(request['company'])
policy.COLLECTION_AVAILABLE=True
policy.COLLECTOR_URL='https://example.invalid/v1/report'
policy.company_policy_file=lambda:company
aggregate._day=lambda:request['now']//86400000
delivery._now_ms=lambda:request['now']
if request.get('wait'):
 print('ready',flush=True)
 sys.stdin.readline()
action=request['action']
if action=='init': result=policy.configure(root,{'enabled':True,'expected_revision':0,'disclosure_version':1})
elif action=='off': result=policy.configure(root,{'enabled':False,'expected_revision':0})
elif action=='on':
 state=policy.status(root)
 result=policy.configure(root,{'enabled':True,'expected_revision':state['revision'],'expected_generation':state['store_generation'],'disclosure_version':1})
elif action=='company':
 company.write_text(json.dumps(request['value']))
 result=True
elif action=='reserve':
 state=policy.status(root)
 result=delivery.DeliveryBudget(root,policy_path=company).reserve(expected_revision=state['revision'],expected_generation=state['store_generation'],network='unmetered',constrained=False) is not None
elif action=='fill':
 state=policy.status(root)
 result=aggregate.record(root,{'kind':'submission','workflow':'memory.recall','surface':'native_agent'},expected_revision=state['revision'],expected_generation=state['store_generation'])
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
  t.after(() => rm(temporary, { recursive: true, force: true }))
  const root = join(temporary, 'private'), company = join(temporary, 'policy.json')
  let now = 1700000000000
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
  return { root, company, store, stamp, invoke, request, definitions, active,
    setNow: value => { now = value }, now: () => now,
    fill: async () => assert.equal(await store.record(observation, await store.snapshot(), Math.floor(now / 86400000)), true) }
}

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

test('simultaneous real Python and native reservations can consume the queue only once', async t => {
  const f = await fixture(t)
  await f.fill()
  const child = spawn(python, ['-c', program], { env: environment, stdio: ['pipe', 'pipe', 'pipe'] })
  t.after(() => child.kill())
  let stdout = '', stderr = ''
  child.stdout.on('data', data => { stdout += data })
  child.stderr.on('data', data => { stderr += data })
  const completed = new Promise((resolve, reject) => { child.once('error', reject); child.once('exit', resolve) })
  child.stdin.write(f.request('reserve', { wait: true }))
  await new Promise((resolve, reject) => { child.stdout.once('data', resolve); child.once('error', reject) })
  assert.match(stdout, /^ready\n/)
  const pending = f.store.reserve(f.stamp, network)
  child.stdin.end('go\n')
  const report = await pending
  assert.equal(await completed, 0, stderr)
  assert.equal(stderr, '')
  const pythonWon = JSON.parse(stdout.trim().split('\n').at(-1))
  assert.equal(Number(Boolean(report)) + Number(pythonWon), 1)
  assert.equal(f.invoke('inspect').attempts, 1)
  if (report) await f.store.cancel(report)
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

for (const abortFails of [false, true]) test(`active-attempt watcher observes Python opt-out with abort failure=${abortFails}`, async t => {
  const f = await fixture(t)
  await f.fill()
  const report = await f.store.reserve(f.stamp, network)
  assert.ok(report)
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
