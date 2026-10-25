import test from 'node:test'
import assert from 'node:assert/strict'
import { mkdtemp, rm, access, readFile, stat, link } from 'node:fs/promises'
import { spawnSync, spawn } from 'node:child_process'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { NativeTelemetryStore, nativeTelemetryDefinitions } from '../dist/telemetry-store.js'
import { TelemetryWorkflow } from '../dist/telemetry-workflow.js'

const repository = resolve(dirname(fileURLToPath(import.meta.url)), '../../..')
const python = process.env.MNEMION_TEST_PYTHON || (process.platform === 'win32' ? 'python' : 'python3')
const environment = { ...process.env, PYTHONPATH: repository, PYTHONNOUSERSITE: '1' }
const program = `
import json,os,shutil,sqlite3,sys
from pathlib import Path
from mnemion.product_telemetry import policy,aggregate
request=json.load(sys.stdin)
root,company=Path(request['root']),Path(request['company'])
policy.COLLECTION_AVAILABLE=True
policy.COLLECTOR_URL='https://example.invalid/telemetry'
policy.company_policy_file=lambda:company
aggregate._day=lambda:request.get('day',20000)
action=request['action']
if action=='configure': result=policy.configure(root,request['choice'])
elif action=='recreate':
 shutil.rmtree(root)
 result=policy.configure(root,{'enabled':True,'expected_revision':0,'disclosure_version':1})
 aggregate.record(root,request['value'],expected_revision=result['revision'],expected_generation=result['store_generation'])
elif action=='record':
 result=[aggregate.record(root,request['value'],expected_revision=request['stamp']['revision'],expected_generation=request['stamp']['store_generation']) for _ in range(request.get('repeat',1))]
elif action=='company':
 company.write_text(json.dumps(request['value']))
 result=True
elif action=='grant':
 import subprocess
 target=root if request.get('directory') else root / policy.DATABASE_NAME
 permissions='*S-1-1-0:(OI)(CI)(R)' if request.get('directory') else '*S-1-1-0:(R)'
 subprocess.run(['icacls',str(target),'/grant',permissions,'/q'],check=True,capture_output=True)
 result=True
elif action=='private_read':
 from mnemion.private_input import read_private
 try: result=bool(read_private(root / policy.DATABASE_NAME,maximum=98304))
 except OSError: result=False
elif action=='preview': result=aggregate.preview(root)
else: result=policy.status(root)
print(json.dumps(result))
`
const observation = extra => ({ kind: 'outcome', workflow: 'memory.recall', surface: 'desktop', outcome: 'success', ...extra })
const stampOf = status => ({ revision: status.revision, store_generation: status.store_generation })

async function fixture(t) {
  const temporary = await mkdtemp(join(tmpdir(), 'mnemion-native-telemetry-'))
  t.after(() => rm(temporary, { recursive: true, force: true }))
  const root = join(temporary, 'private choice'), company = join(temporary, 'company.json')
  const invoke = (action, extra = {}) => {
    const child = spawnSync(python, ['-c', program], { env: environment, encoding: 'utf8', timeout: 20000,
      input: JSON.stringify({ action, root, company, ...extra }) })
    assert.equal(child.status, 0, child.stderr)
    assert.equal(child.stderr, '')
    return JSON.parse(child.stdout)
  }
  const definitions = nativeTelemetryDefinitions()
  assert.equal(definitions.disclosure.collection_available, false, 'test never changes the shipped collection gate')
  const active = { ...definitions.disclosure, collection_available: true, destination: 'https://example.invalid/telemetry' }
  const store = new NativeTelemetryStore(root, active, definitions.catalog, company)
  const initial = invoke('configure', { choice: { enabled: true, expected_revision: 0, disclosure_version: 1 } })
  return { root, company, invoke, store, initial, definitions }
}

test('inactive native collection reads no choice and creates no store', async t => {
  const temporary = await mkdtemp(join(tmpdir(), 'mnemion-inactive-telemetry-'))
  t.after(() => rm(temporary, { recursive: true, force: true }))
  const root = join(temporary, 'absent'), definitions = nativeTelemetryDefinitions()
  const store = new NativeTelemetryStore(root, definitions.disclosure, definitions.catalog)
  assert.equal(await store.snapshot(), null)
  assert.equal(await store.record({ private: 'PRIVATE_SENTINEL' }, { revision: 0, store_generation: null }), false)
  await assert.rejects(access(root))
})

test('native app and Python commit to one private bounded SQLite aggregate', async t => {
  const { root, invoke, store, initial } = await fixture(t)
  const stamp = await store.snapshot()
  assert.deepEqual(stamp, stampOf(initial))
  assert.equal(await store.record(observation({ latency_ms: 123.456, result_items: 37 }), stamp, 20000), true)
  assert.deepEqual(invoke('record', { value: observation({ latency_ms: 123.456, result_items: 37 }), stamp }), [true])
  const rows = invoke('preview')
  assert.equal(rows.length, 3)
  assert.ok(rows.every(row => row.count === 2))
  const input = observation({ latency_ms: 123.456 })
  const pending = store.record(input, stamp, 20000)
  input.latency_ms = 'PRIVATE_SENTINEL'
  assert.equal(await pending, true, 'fixed numeric buckets were copied before yielding')
  assert.equal(await store.record(observation({ query: 'PRIVATE_SENTINEL' }), stamp, 20000), false)
  const data = await readFile(join(root, 'product-telemetry.sqlite3'))
  assert.ok(!data.includes(Buffer.from('123.456')) && !data.includes(Buffer.from('PRIVATE_SENTINEL')))
  assert.ok(data.length <= 96 * 1024)
  if (process.platform !== 'win32') assert.equal((await stat(root)).mode & 0o077, 0)
})

test('a complete workflow shares one bounded transaction and validates both observations first', async t => {
  const { invoke, store } = await fixture(t), stamp = await store.snapshot()
  const submission = { kind: 'submission', workflow: 'memory.recall', surface: 'desktop' }
  assert.equal(await store.recordMany([submission, observation({ latency_ms: 20 })], stamp, 20000), true)
  const before = invoke('preview')
  assert.deepEqual(before.map(row => row.metric).sort(), ['latency_ms', 'outcomes', 'submissions'])
  assert.ok(before.every(row => row.count === 1))
  assert.equal(await store.recordMany([submission, observation({ secret: 'PRIVATE_SENTINEL' })], stamp, 20000), false)
  assert.deepEqual(invoke('preview'), before, 'invalid outcome did not leave a new submission')
})

test('Python opt-out wins over a pending app measurement and a later re-enable', async t => {
  const { invoke, store } = await fixture(t)
  const stamp = await store.snapshot(), pending = store.record(observation(), stamp, 20000)
  const off = invoke('configure', { choice: { enabled: false, expected_revision: stamp.revision } })
  const on = invoke('configure', { choice: { enabled: true, expected_revision: off.revision,
    expected_generation: off.store_generation, disclosure_version: 1 } })
  assert.equal(await pending, false)
  assert.deepEqual(invoke('preview'), [])
  assert.equal(await store.record(observation(), stamp, 20000), false)
  assert.equal(await store.record(observation(), stampOf(on), 20000), true)
})

test('recreated settings and caller stamp mutation cannot resurrect an older observation', async t => {
  const { invoke, store } = await fixture(t)
  const stamp = await store.snapshot(), old = { ...stamp }
  const pending = store.record(observation({ latency_ms: 999 }), stamp, 20000)
  const recreated = invoke('recreate', { value: observation() })
  assert.equal(recreated.revision, old.revision)
  assert.notEqual(recreated.store_generation, old.store_generation)
  Object.assign(stamp, stampOf(recreated))
  assert.equal(await pending, false)
  assert.deepEqual(invoke('preview').map(row => [row.metric, row.count]), [['outcomes', 1]])
})

test('company restrictions remove disallowed groups and cannot override an opt-out', async t => {
  const { invoke, store } = await fixture(t)
  const stamp = await store.snapshot()
  assert.equal(await store.record(observation({ latency_ms: 1 }), stamp, 20000), true)
  invoke('company', { value: { schema_version: 1, enabled: true, metric_groups: ['usage'] } })
  assert.equal(await store.record(observation({ latency_ms: 1 }), stamp, 20000), true)
  assert.deepEqual(invoke('preview').map(row => row.metric), ['outcomes'])
  invoke('company', { value: { schema_version: 1, enabled: false, metric_groups: [] } })
  assert.equal(await store.snapshot(), null)
  assert.equal(await store.record(observation(), stamp, 20000), false)
  assert.equal(invoke('status').pending_records, 0)
  invoke('company', { value: { schema_version: 1, enabled: true, metric_groups: ['usage'] } })
  invoke('configure', { choice: { enabled: false, expected_revision: stamp.revision } })
  assert.equal(await store.snapshot(), null)
})

test('both runtimes share daily contribution limits and prune expired or future cells', async t => {
  const { invoke, store } = await fixture(t)
  const stamp = await store.snapshot()
  assert.equal(await store.record(observation(), stamp, 20000), true)
  assert.equal(invoke('record', { value: observation(), stamp, repeat: 70 }).filter(Boolean).length, 63)
  assert.equal(await store.record(observation(), stamp, 20000), false)
  assert.equal(await store.record(observation(), stamp, 20003), true)
  assert.deepEqual(invoke('preview', { day: 20003 }).map(row => row.count), [1])
  assert.equal(await store.record(observation({ latency_ms: 100 }), stamp, 20001), true)
  assert.equal(invoke('preview', { day: 20001 }).length, 2)
})

test('exhausted workflows drop before SQLite and fresh choices still use the privacy fence', async t => {
  const { invoke, store } = await fixture(t), stamp = await store.snapshot()
  const day = Math.floor(Date.now() / 86400000)
  assert.equal(invoke('record', { value: observation(), stamp, repeat: 64, day }).filter(Boolean).length, 64)
  assert.equal(await store.record(observation(), stamp, day), false)
  let opens = 0
  const open = store.open.bind(store)
  store.open = (...args) => { opens++; return open(...args) }
  for (let index = 0; index < 512; index++) {
    assert.equal(await TelemetryWorkflow.begin(store, 'memory.recall', 'desktop'), null)
    assert.equal(await store.record(observation(), stamp, day), false)
  }
  assert.equal(opens, 0, 'exhausted observations create no SQLite connections or Windows ACL helpers')
  assert.ok(await TelemetryWorkflow.begin(store, 'memory.read', 'desktop'), 'other scopes remain eligible')
  assert.ok(opens > 0)
  const off = invoke('configure', { choice: { enabled: false, expected_revision: stamp.revision } })
  assert.equal(await TelemetryWorkflow.begin(store, 'memory.recall', 'desktop'), null)
  const on = invoke('configure', { choice: { enabled: true, expected_revision: off.revision,
    expected_generation: off.store_generation, disclosure_version: 1 } })
  const fresh = await TelemetryWorkflow.begin(store, 'memory.recall', 'desktop')
  assert.ok(fresh, 'changing the private choice invalidates only the negative cache')
  await fresh.finish('success')
  assert.deepEqual(invoke('preview', { day }).map(row => row.count), [1, 1, 1])
  assert.equal(await store.record(observation(), stamp, day), false, 'old revisions remain forbidden')
  assert.equal((await store.snapshot()).revision, on.revision)
})

test('cached exhaustion never survives a recreated or missing store', async t => {
  const { root, invoke, store } = await fixture(t), stamp = await store.snapshot()
  const day = Math.floor(Date.now() / 86400000)
  invoke('record', { value: observation(), stamp, repeat: 64, day })
  assert.equal(await store.record(observation(), stamp, day), false)
  const recreated = invoke('recreate', { value: observation(), day })
  const current = await store.snapshot('memory.recall', 'desktop')
  assert.deepEqual(current, stampOf(recreated))
  assert.equal(await store.record(observation(), stamp, day), false)
  await rm(join(root, 'product-telemetry.sqlite3'))
  assert.equal(await store.snapshot('memory.recall', 'desktop'), null)
  await assert.rejects(access(join(root, 'product-telemetry.sqlite3')))
})

test('an observed opt-out stays quiet and re-enabling still requires a fresh read', async t => {
  const { invoke, store } = await fixture(t), stamp = await store.snapshot()
  const off = invoke('configure', { choice: { enabled: false, expected_revision: stamp.revision } })
  assert.equal(await store.snapshot(), null)
  let opens = 0
  const open = store.open.bind(store)
  store.open = (...args) => { opens++; return open(...args) }
  for (let index = 0; index < 512; index++) {
    assert.equal(await TelemetryWorkflow.begin(store, 'memory.recall', 'desktop'), null)
    assert.equal(await store.snapshot(), null)
    assert.equal(await store.record(observation(), stamp), false)
  }
  assert.equal(opens, 0, 'a verified opt-out does not repeatedly reopen SQLite')
  invoke('configure', { choice: { enabled: true, expected_revision: off.revision,
    expected_generation: off.store_generation, disclosure_version: 1 } })
  assert.ok(await TelemetryWorkflow.begin(store, 'memory.recall', 'desktop'))
  assert.ok(opens > 0, 'a negative hint never supplies permission')
  assert.equal(await store.record(observation(), stamp), false)
})

test('another SQLite writer causes an immediate drop rather than a queued retry', async t => {
  const { root, store } = await fixture(t), stamp = await store.snapshot()
  const child = spawn(python, ['-c', 'import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); c.execute("BEGIN IMMEDIATE"); print("ready",flush=True); sys.stdin.read(); c.rollback()', join(root, 'product-telemetry.sqlite3')],
    { env: environment, stdio: ['pipe', 'pipe', 'pipe'] })
  t.after(() => { child.stdin.end(); child.kill() })
  await new Promise((resolve, reject) => { child.stdout.once('data', resolve); child.once('error', reject); child.once('exit', code => reject(new Error(`lock fixture exited ${code}`))) })
  const started = performance.now()
  assert.equal(await store.record(observation(), stamp, 20000), false)
  assert.ok(performance.now() - started < 1500)
  child.stdin.end()
  await new Promise(resolve => child.once('exit', resolve))
})

test('missing or hard-linked databases never become a replacement choice', async t => {
  const { root, invoke, store } = await fixture(t), stamp = await store.snapshot()
  const path = join(root, 'product-telemetry.sqlite3'), other = join(root, 'linked.sqlite3')
  await link(path, other)
  assert.equal(await store.snapshot(), null)
  assert.equal(invoke('status').reason, 'storage_unavailable')
  assert.equal(await store.record(observation(), stamp, 20000), false)
  await rm(other)
  await rm(path)
  assert.equal(await store.record(observation(), stamp, 20000), false)
  await assert.rejects(access(path))
})

test('Windows app and Python reject public read access without repairing it', { skip: process.platform !== 'win32' }, async t => {
  const { root, invoke, store } = await fixture(t), stamp = await store.snapshot()
  const before = await readFile(join(root, 'product-telemetry.sqlite3'))
  assert.equal(invoke('private_read'), true, 'ordinary private credential reads remain supported')
  invoke('grant')
  assert.equal(await store.snapshot(), null)
  assert.equal(await store.record(observation(), stamp, 20000), false)
  assert.equal(invoke('status').reason, 'storage_unavailable')
  assert.equal(invoke('private_read'), false)
  assert.deepEqual(await readFile(join(root, 'product-telemetry.sqlite3')), before)
  assert.equal(await store.snapshot(), null, 'the read did not silently repair the ACL')
})

test('Windows refuses a directory that can expose new SQLite journal files', { skip: process.platform !== 'win32' }, async t => {
  const { invoke, store } = await fixture(t), stamp = await store.snapshot()
  invoke('grant', { directory: true })
  assert.equal(await store.record(observation(), stamp, 20000), false)
  assert.equal(invoke('status').reason, 'storage_unavailable')
})
