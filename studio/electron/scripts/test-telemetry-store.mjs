import test from 'node:test'
import assert from 'node:assert/strict'
import { mkdtemp, rm, access, readFile, stat, link } from 'node:fs/promises'
import { spawnSync } from 'node:child_process'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import url, { fileURLToPath } from 'node:url'
import { syncBuiltinESMExports } from 'node:module'
import { createHash } from 'node:crypto'
import { DatabaseSync } from 'node:sqlite'
import { NativeTelemetryStore, nativeTelemetryDefinitions } from '../dist/telemetry-store.js'
import { TelemetryWorkflow, TelemetryWorkflowChoice } from '../dist/telemetry-workflow.js'
import { measureDesktop } from '../dist/desktop-measurement.js'
import { markWorkspaceSelection } from '../dist/workspace-selection.js'
import { TelemetryFixtureChildren, waitForTelemetryFixture } from './telemetry-fixture-children.mjs'

const repository = resolve(dirname(fileURLToPath(import.meta.url)), '../../..')
const python = process.env.MNEMION_TEST_PYTHON || (process.platform === 'win32' ? 'python' : 'python3')
// Node writes UTF-8 JSON frames. Windows Python otherwise reads those bytes
// with its ANSI code page and creates a different non-ASCII fixture path.
const environment = { ...process.env, PYTHONPATH: repository, PYTHONNOUSERSITE: '1', PYTHONIOENCODING: 'utf-8' }
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

async function fixture(t, directory = 'private choice') {
  const temporary = await mkdtemp(join(tmpdir(), 'mnemion-native-telemetry-'))
  const children = new TelemetryFixtureChildren(python, environment)
  t.after(async () => {
    await children.close()
    await rm(temporary, { recursive: true, force: true })
  })
  const root = join(temporary, directory), company = join(temporary, 'company.json')
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
  return { root, company, invoke, store, initial, definitions, children }
}

test('inactive native collection reads no choice and creates no store', async t => {
  const temporary = await mkdtemp(join(tmpdir(), 'mnemion-inactive-telemetry-'))
  t.after(() => rm(temporary, { recursive: true, force: true }))
  const root = join(temporary, 'absent'), definitions = nativeTelemetryDefinitions()
  const store = new NativeTelemetryStore(root, definitions.disclosure, definitions.catalog)
  store.noteUserDisabled(performance.now() + 60000)
  assert.equal(await store.snapshot(), null)
  assert.equal(await store.record({ private: 'PRIVATE_SENTINEL' }, { revision: 0, store_generation: null }), false)
  await assert.rejects(access(root))
})

test('a known disabled reply avoids a duplicate SQLite read without changing the choice', async t => {
  const { store, invoke, initial } = await fixture(t)
  const disabled = invoke('configure', { choice: { enabled: false, expected_revision: initial.revision } })
  let opens = 0
  const open = store.open.bind(store)
  store.open = (...args) => { opens++; return open(...args) }
  // Optional invocation also lets the original source expose its redundant
  // database read instead of failing merely because the new method is absent.
  store.noteUserDisabled?.(performance.now() + 60000)
  assert.equal(await store.snapshot('memory.recall', 'desktop'), null)
  assert.equal(opens, 0, 'The control process already confirmed this opt-out')
  assert.deepEqual(invoke('status'), disabled)
  assert.deepEqual(invoke('preview'), [])
})

test('control denial expires at its original deadline and cannot preserve authority', async t => {
  const { store, invoke, initial } = await fixture(t)
  let now = 1000, opens = 0
  t.mock.method(performance, 'now', () => now)
  const open = store.open.bind(store)
  store.open = (...args) => { opens++; return open(...args) }
  // Simulate a delayed disabled reply after another process already enabled
  // collection. It may drop an optional sample, but cannot grant permission.
  store.noteUserDisabled(1200)
  assert.equal(await store.snapshot('memory.recall', 'desktop'), null)
  assert.equal(opens, 0)
  now = 1201
  assert.deepEqual(await store.snapshot('memory.recall', 'desktop'), stampOf(initial))
  assert.equal(opens, 1, 'A delayed hint must not acquire a fresh sixty-second lifetime')
  invoke('configure', { choice: { enabled: false, expected_revision: initial.revision } })
  assert.equal(await store.record(observation(), stampOf(initial), 20000), false)
  assert.deepEqual(invoke('preview'), [])
})

test('another process re-enabling invalidates the hint at the existing file-check cadence', async t => {
  const { store, invoke, initial } = await fixture(t)
  const disabled = invoke('configure', { choice: { enabled: false, expected_revision: initial.revision } })
  let now = 1000, opens = 0
  t.mock.method(performance, 'now', () => now)
  const open = store.open.bind(store)
  store.open = (...args) => { opens++; return open(...args) }
  store.noteUserDisabled(61000)
  assert.equal(await store.snapshot('memory.recall', 'desktop'), null)
  assert.equal(opens, 0)
  const enabled = invoke('configure', { choice: { enabled: true, expected_revision: disabled.revision,
    expected_generation: disabled.store_generation, disclosure_version: 1 } })
  now = 1251
  assert.deepEqual(await store.snapshot('memory.recall', 'desktop'), stampOf(enabled))
  assert.equal(opens, 1)
})

test('invalid denial lifetimes never replace a fresh policy read', async t => {
  const { root, company, initial, definitions } = await fixture(t)
  t.mock.method(performance, 'now', () => 1000)
  for (const until of [NaN, Infinity, 999, 61001]) {
    const store = new NativeTelemetryStore(root, { ...definitions.disclosure,
      collection_available: true, destination: 'https://example.invalid/telemetry' }, definitions.catalog, company)
    let opens = 0
    const open = store.open.bind(store)
    store.open = (...args) => { opens++; return open(...args) }
    store.noteUserDisabled(until)
    assert.deepEqual(await store.snapshot('memory.recall', 'desktop'), stampOf(initial))
    assert.equal(opens, 1)
  }
})

test('recreated private storage invalidates a prior control hint and old write stamps', async t => {
  const { store, invoke, initial } = await fixture(t)
  invoke('configure', { choice: { enabled: false, expected_revision: initial.revision } })
  let now = 1000
  t.mock.method(performance, 'now', () => now)
  store.noteUserDisabled(61000)
  assert.equal(await store.snapshot('memory.recall', 'desktop'), null)
  const recreated = invoke('recreate', { value: observation() })
  now = 1251
  assert.deepEqual(await store.snapshot('memory.recall', 'desktop'), stampOf(recreated))
  assert.notEqual(recreated.store_generation, initial.store_generation)
  assert.equal(await store.record(observation(), stampOf(initial), 20000), false)
})

test('store URI derivation is reused while the current choice remains fresh', async t => {
  const { root, invoke, store, initial } = await fixture(t, 'private choice % # é')
  const path = join(root, 'product-telemetry.sqlite3'), original = url.pathToFileURL
  let conversions = 0
  url.pathToFileURL = (...args) => {
    if (args[0] === path) conversions++
    return original(...args)
  }
  syncBuiltinESMExports()
  try {
    const stamp = await store.snapshot()
    assert.deepEqual(stamp, stampOf(initial))
    assert.equal(await store.record(observation(), stamp, 20000), true)
    assert.deepEqual(await store.snapshot(), stamp)
    invoke('configure', { choice: { enabled: false, expected_revision: initial.revision } })
    assert.equal(await store.snapshot(), null, 'URI reuse must never preserve permission')
    assert.equal(await store.record(observation(), stamp, 20000), false)
    assert.deepEqual(invoke('preview'), [])
    assert.equal(conversions, 1, 'An immutable filesystem location needs one URL encoding')
  } finally {
    url.pathToFileURL = original
    syncBuiltinESMExports()
  }
})

test('native and Python agree on every numeric telemetry cell privacy group', () => {
  const definitions = nativeTelemetryDefinitions()
  const catalog = new NativeTelemetryStore('unused', definitions.disclosure, definitions.catalog).catalog
  const child = spawnSync(python, ['-c', `
import hashlib,json
from mnemion.product_telemetry.catalog import describe,MeasurementError
digest=hashlib.sha256()
accepted=0
for cell in range(65536):
 try:
  group=describe(cell)['group']
  accepted+=1
 except MeasurementError:
  group='-'
 digest.update((group+'\\n').encode())
print(json.dumps({'accepted':accepted,'digest':digest.hexdigest()}))
`], { env: environment, encoding: 'utf8', timeout: 20000 })
  assert.equal(child.status, 0, child.stderr)
  const digest = createHash('sha256')
  let accepted = 0
  for (let cell = 0; cell < 65536; cell++) {
    let group
    try { group = catalog.group(cell); accepted++ }
    catch (error) { assert.equal(error.message, 'telemetry_invalid_measurement'); group = '-' }
    digest.update(group + '\n')
  }
  assert.deepEqual({ accepted, digest: digest.digest('hex') }, JSON.parse(child.stdout))
  for (const cell of [-1, 65536, NaN, 1.5, '0', null]) {
    assert.throws(() => catalog.group(cell), /^Error: telemetry_invalid_measurement$/)
  }
})

test('group filtering preserves company restrictions without making descriptions', async t => {
  const { invoke, store, initial } = await fixture(t)
  invoke('company', { value: { schema_version: 1, enabled: true, metric_groups: ['usage'] } })
  let descriptions = 0
  const describe = store.catalog.describe.bind(store.catalog)
  t.mock.method(store.catalog, 'describe', cell => { descriptions++; return describe(cell) })
  assert.equal(await store.record(observation({ latency_ms: 20, result_items: 7 }), stampOf(initial), 20000), true)
  const rows = invoke('preview')
  assert.ok(rows.length > 0)
  assert.ok(rows.every(row => row.group === 'usage'))
  assert.equal(descriptions, 0, 'Filtering numeric cells does not need preview objects')
})

test('fixed workflow choices preserve one original snapshot and clock and finish once', async t => {
  const { invoke, store } = await fixture(t), choices = ['capture.collect', 'capture.deliver']
  const snapshot = store.snapshot.bind(store)
  let reads = 0, now = 10
  store.snapshot = (...args) => { reads++; return snapshot(...args) }
  const pending = TelemetryWorkflowChoice.choose(store, choices, 'desktop', () => now)
  choices[1] = 'memory.save'
  const active = await pending
  assert.ok(active)
  assert.equal(reads, 1)
  now += 250
  await active.finishChoice('capture.deliver', 'success', 'none', { work_items: 0, result_items: 3 })
  await active.finishChoice('capture.collect', 'failed')
  await active.finish('failed')
  assert.equal(reads, 1, 'completion does not acquire new permission')
  const rows = invoke('preview', { day: Math.floor(Date.now() / 86400000) })
  assert.deepEqual([...new Set(rows.map(row => row.workflow))], ['capture.deliver'])
  assert.equal(rows.filter(row => row.metric === 'submissions').reduce((n, row) => n + row.count, 0), 1)
  assert.equal(rows.find(row => row.metric === 'latency_ms').bucket, 3)
})

test('choice validation and undeclared completion never create another workflow', async t => {
  const { invoke, store } = await fixture(t)
  const snapshot = store.snapshot.bind(store)
  let reads = 0
  store.snapshot = (...args) => { reads++; return snapshot(...args) }
  for (const choices of [[], ['capture.collect'], ['capture.collect', 'capture.collect'],
    ['capture.collect', 'PRIVATE_CHOICE'], ['capture.collect', 'capture.deliver', 'sources.scan', 'memory.read', 'memory.save']]) {
    assert.equal(TelemetryWorkflowChoice.choose(store, choices, 'desktop'), null)
  }
  assert.equal(reads, 0)
  const active = await TelemetryWorkflowChoice.choose(store, ['capture.collect', 'capture.deliver'], 'desktop')
  await active.finishChoice('memory.save', 'success')
  await active.finishChoice('capture.deliver', 'success')
  assert.equal(reads, 1)
  assert.deepEqual(invoke('preview'), [])
})

test('a chosen completion cannot inherit permission from opt-out followed by reenable', async t => {
  const { invoke, store, initial } = await fixture(t)
  const active = await TelemetryWorkflowChoice.choose(store, ['capture.collect', 'capture.deliver'], 'desktop')
  const off = invoke('configure', { choice: { enabled: false, expected_revision: initial.revision } })
  invoke('configure', { choice: { enabled: true, expected_revision: off.revision, expected_generation: off.store_generation, disclosure_version: 1 } })
  await active.finishChoice('capture.deliver', 'success')
  assert.deepEqual(invoke('preview', { day: Math.floor(Date.now() / 86400000) }), [])
})

test('collection exhaustion leaves delivery choice available and enforces its own quota', async t => {
  const { invoke, store, initial } = await fixture(t), stamp = stampOf(initial)
  const day = Math.floor(Date.now() / 86400000)
  const collected = observation({ workflow: 'capture.collect' })
  assert.equal(invoke('record', { value: collected, stamp, repeat: 64, day }).filter(Boolean).length, 64)
  assert.equal(await store.record(collected, stamp, day), false)
  assert.equal(await TelemetryWorkflow.begin(store, 'capture.collect', 'desktop'), null)
  const blocked = await TelemetryWorkflowChoice.choose(store, ['capture.collect', 'capture.deliver'], 'desktop')
  assert.ok(blocked)
  await blocked.finishChoice('capture.collect', 'success')
  const active = await TelemetryWorkflowChoice.choose(store, ['capture.collect', 'capture.deliver'], 'desktop')
  assert.ok(active)
  await active.finishChoice('capture.deliver', 'success')
  const outcomes = invoke('preview', { day }).filter(row => row.metric === 'outcomes')
  assert.deepEqual(Object.fromEntries(outcomes.map(row => [row.workflow, row.count])), { 'capture.collect': 64, 'capture.deliver': 1 })
})

test('workspace restoration cannot reuse a result after a real cross-runtime opt-out and reenable', async t => {
  const { invoke, store, initial } = await fixture(t)
  const recordMany = store.recordMany.bind(store), pending = [], result = { private: 'PRIVATE_WORKSPACE' }
  store.recordMany = (...args) => { const work = recordMany(...args); pending.push(work); return work }
  const measure = async run => {
    // Read actual current SQLite authority and Windows ACLs before each action.
    // This test isolates generation/result ownership from optional 25 ms
    // admission; the existing late-selection test owns that deadline behavior.
    const stamp = await store.snapshot()
    assert.ok(stamp, 'the real private store must authorize each fresh start')
    let snapshots = 0
    const admitted = { available: store.available, catalog: store.catalog,
      snapshot: () => { snapshots++; return Promise.resolve(stamp) },
      recordMany: (...args) => store.recordMany(...args) }
    const value = await measureDesktop(admitted, 'workspace.restore', {}, 'desktop', run)
    assert.equal(snapshots, 1)
    return value
  }
  await measure(() => {
    const off = invoke('configure', { choice: { enabled: false, expected_revision: initial.revision } })
    invoke('configure', { choice: { enabled: true, expected_revision: off.revision,
      expected_generation: off.store_generation, disclosure_version: 1 } })
    return markWorkspaceSelection(result, 'switched')
  })
  await Promise.all(pending)
  const day = Math.floor(Date.now() / 86400000)
  assert.deepEqual(invoke('preview', { day }), [])
  await measure(() => result)
  await Promise.all(pending)
  assert.deepEqual(invoke('preview', { day }), [], 'renewed consent cannot re-own the retained result')
  const fresh = { private: 'ANOTHER_PRIVATE_WORKSPACE' }
  await measure(() => markWorkspaceSelection(fresh, 'switched'))
  await Promise.all(pending)
  const rows = invoke('preview', { day })
  assert.equal(rows.filter(row => row.metric === 'submissions').reduce((n, row) => n + row.count, 0), 1)
  assert.ok(rows.every(row => row.workflow === 'workspace.switch'))
  assert.equal(JSON.stringify(rows).includes('PRIVATE_WORKSPACE'), false)
})

test('native transactions preserve every supported schema without migrating a producer store', async t => {
  for (const version of [3, 4, 5, 6]) await t.test(`schema ${version}`, async t => {
    const { root, store, initial } = await fixture(t)
    const path = join(root, 'product-telemetry.sqlite3'), database = new DatabaseSync(path)
    try {
      if (version < 6) database.exec('DROP TABLE report_review')
      if (version < 5) database.exec('ALTER TABLE preferences DROP COLUMN connection_mode')
      else database.exec("UPDATE preferences SET connection_mode='unmetered'")
      if (version < 4) database.exec('DROP TABLE delivery_state; DROP TABLE delivery_attempts')
      database.exec(`PRAGMA user_version=${version}`)
    } finally { database.close() }
    const stamp = await store.snapshot()
    assert.deepEqual(stamp, stampOf(initial))
    assert.equal(await store.record(observation(), stamp, 20000), true)
    const connection = await store.open()
    try {
      connection.exec('BEGIN')
      const preference = store.preferences(connection)
      assert.equal(preference.connection_mode, version < 5 ? 'auto' : 'unmetered')
      assert.equal(connection.prepare('PRAGMA user_version').get().user_version, version)
      assert.equal(connection.prepare('SELECT count(*) AS count FROM pending').get().count, 1)
    } finally { store.closeDatabase(connection) }
  })
})

test('native authority checks reject damaged metadata and lookalike pragma tables', async t => {
  const cases = [
    ['foreign application', 'PRAGMA application_id=1'],
    ['unknown format', 'PRAGMA user_version=7'],
    ['unsafe journal', 'PRAGMA journal_mode=WAL'],
    ['invalid connection choice', "PRAGMA ignore_check_constraints=ON; UPDATE preferences SET connection_mode='unknown'"],
    ['missing current connection choice', 'ALTER TABLE preferences DROP COLUMN connection_mode'],
    ['application pragma impostor', 'PRAGMA application_id=1; CREATE TABLE pragma_application_id(application_id); INSERT INTO pragma_application_id VALUES(1296979024)'],
    ['journal pragma impostor', "PRAGMA journal_mode=WAL; CREATE TABLE pragma_journal_mode(journal_mode); INSERT INTO pragma_journal_mode VALUES('delete')"],
  ]
  for (const [name, damage] of cases) await t.test(name, async t => {
    const { root, store, initial } = await fixture(t)
    const path = join(root, 'product-telemetry.sqlite3'), database = new DatabaseSync(path)
    try { database.exec(damage) } finally { database.close() }
    assert.equal(await store.snapshot(), null)
    assert.equal(await store.record(observation(), stampOf(initial), 20000), false)
    const inspect = new DatabaseSync(path, { readOnly: true })
    try { assert.equal(inspect.prepare('SELECT count(*) AS count FROM pending').get().count, 0) }
    finally { inspect.close() }
  })
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

test('concurrent callers share one process storage slot and never queue SQLite handles', async t => {
  const { root, company, store, definitions } = await fixture(t)
  const other = new NativeTelemetryStore(root, store.disclosure, definitions.catalog, company)
  const handles = new Set()
  let peak = 0
  for (const candidate of [store, other]) {
    const open = candidate.open.bind(candidate), close = candidate.closeDatabase.bind(candidate)
    candidate.open = async (...args) => {
      const database = await open(...args)
      handles.add(database); peak = Math.max(peak, handles.size)
      return database
    }
    candidate.closeDatabase = database => {
      close(database)
      if (database) handles.delete(database)
    }
  }
  const snapshots = await Promise.all(Array.from({ length: 32 }, (_, index) =>
    (index % 2 ? store : other).snapshot()))
  t.diagnostic(JSON.stringify({ offered: snapshots.length, accepted: snapshots.filter(Boolean).length,
    peak_live_connections: peak, remaining_connections: handles.size }))
  assert.equal(peak, 1, 'optional callers must drop before another SQLite connection is opened')
  assert.equal(snapshots.filter(Boolean).length, 1, 'competing samples are dropped, never delayed in a queue')
  assert.equal(handles.size, 0)
  const next = await store.snapshot()
  assert.ok(next, 'the next independent sample can use the released slot')
  assert.equal(await store.record(observation(), next, 20000), true)
})

test('failed admission and competing cleanup cannot steal a live connection slot', async t => {
  const { root, company, store, definitions } = await fixture(t)
  const missing = new NativeTelemetryStore(join(root, 'missing'), store.disclosure, definitions.catalog, company)
  assert.equal(await missing.snapshot(), null)
  assert.ok(await store.snapshot(), 'a failure before opening SQLite releases its own slot')
  const database = await store.open()
  try {
    await assert.rejects(missing.open())
    missing.closeDatabase(undefined)
    assert.equal(store.snapshot(), null, 'a rejected caller cannot release another live connection')
  } finally { store.closeDatabase(database) }
  assert.ok(await store.snapshot())
})

test('an unclosed SQLite handle retains ownership until actual cleanup succeeds', async t => {
  const { store } = await fixture(t)
  const stamp = await store.snapshot(), database = await store.open()
  const original = database.close.bind(database)
  t.after(() => { database.close = original; store.closeDatabase(database) })
  database.close = () => { throw new Error('Simulated native close failure') }
  store.closeDatabase(database)
  assert.equal(database.isOpen, true)
  assert.equal(store.snapshot(), null)
  assert.equal(await store.record(observation(), stamp, 20000), false)
  database.close = original
  store.closeDatabase(database)
  assert.equal(database.isOpen, false)
  assert.ok(await store.snapshot(), 'successful cleanup releases the slot without a policy cache')
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
  let now = 0
  t.mock.method(performance, 'now', () => now)
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
  now = 250
  const fresh = await TelemetryWorkflow.begin(store, 'memory.recall', 'desktop')
  assert.ok(fresh, 'changing the private choice invalidates only the negative cache')
  await fresh.finish('success')
  assert.deepEqual(invoke('preview', { day }).map(row => row.count), [1, 1, 1])
  assert.equal(await store.record(observation(), stamp, day), false, 'old revisions remain forbidden')
  assert.equal((await store.snapshot()).revision, on.revision)
})

test('alternating exhausted scopes stay quiet without extending an older denial', async t => {
  const { invoke, store } = await fixture(t), stamp = await store.snapshot()
  const day = Math.floor(Date.now() / 86400000)
  const scopes = ['memory.recall', 'memory.read']
  for (const workflow of scopes) {
    assert.equal(invoke('record', { value: observation({ workflow }), stamp, repeat: 64, day }).filter(Boolean).length, 64)
  }
  let now = 0
  t.mock.method(performance, 'now', () => now)
  assert.equal(await store.record(observation(), stamp, day), false)
  now = 59000
  assert.equal(await store.record(observation({ workflow: 'memory.read' }), stamp, day), false)
  let opens = 0
  const open = store.open.bind(store)
  store.open = (...args) => { opens++; return open(...args) }
  for (let index = 0; index < 32; index++) for (const workflow of scopes) {
    assert.equal(await TelemetryWorkflow.begin(store, workflow, 'desktop'), null)
  }
  assert.equal(opens, 0, 'different exhausted scopes share only the same unchanged private file')
  now = 60000
  assert.ok(await store.snapshot('memory.recall', 'desktop'), 'an expired denial falls back to a fresh policy read')
  assert.ok(opens > 0, 'remembering a second scope cannot extend the first scope indefinitely')
})

test('a recreated or missing store cannot be admitted by a cached denial', async t => {
  const { root, invoke, store } = await fixture(t), stamp = await store.snapshot()
  let now = 0
  t.mock.method(performance, 'now', () => now)
  const day = Math.floor(Date.now() / 86400000)
  invoke('record', { value: observation(), stamp, repeat: 64, day })
  assert.equal(await store.record(observation(), stamp, day), false)
  const recreated = invoke('recreate', { value: observation(), day })
  assert.equal(await store.snapshot('memory.recall', 'desktop'), null, 'the quiet interval can only drop another optional sample')
  now = 250
  const current = await store.snapshot('memory.recall', 'desktop')
  assert.deepEqual(current, stampOf(recreated))
  assert.equal(await store.record(observation(), stamp, day), false)
  await rm(join(root, 'product-telemetry.sqlite3'))
  assert.equal(await store.snapshot('memory.recall', 'desktop'), null)
  await assert.rejects(access(join(root, 'product-telemetry.sqlite3')))
})

test('an observed opt-out stays quiet and re-enabling still requires a fresh read', async t => {
  const { invoke, store } = await fixture(t), stamp = await store.snapshot()
  let now = 0
  t.mock.method(performance, 'now', () => now)
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
  assert.equal(await TelemetryWorkflow.begin(store, 'memory.recall', 'desktop'), null)
  now = 250
  assert.ok(await TelemetryWorkflow.begin(store, 'memory.recall', 'desktop'))
  assert.ok(opens > 0, 'a negative hint never supplies permission')
  assert.equal(await store.record(observation(), stamp), false)
})

test('denied bursts reuse filesystem observations only for a bounded quiet interval', async t => {
  const { invoke, store } = await fixture(t), stamp = await store.snapshot()
  let now = 0, observations = 0
  t.mock.method(performance, 'now', () => now)
  const day = Math.floor(Date.now() / 86400000)
  invoke('record', { value: observation(), stamp, repeat: 64, day })
  assert.equal(await store.record(observation(), stamp, day), false)
  const version = store.saturationFile.bind(store)
  t.mock.method(store, 'saturationFile', () => { observations++; return version() })
  for (let index = 0; index < 512; index++) assert.equal(await TelemetryWorkflow.begin(store, 'memory.recall', 'desktop'), null)
  assert.equal(observations, 0, 'the denied burst allocates no filesystem statistics')
  now = 250
  assert.equal(await TelemetryWorkflow.begin(store, 'memory.recall', 'desktop'), null)
  assert.equal(observations, 1)
  now = 499
  assert.equal(await TelemetryWorkflow.begin(store, 'memory.recall', 'desktop'), null)
  assert.equal(observations, 1)
  now = 500
  assert.equal(await TelemetryWorkflow.begin(store, 'memory.recall', 'desktop'), null)
  assert.equal(observations, 2, 'continued work rechecks the file without extending the original hint')
  const entry = await TelemetryWorkflow.begin(store, 'memory.read', 'desktop')
  assert.ok(entry)
  invoke('configure', { choice: { enabled: false, expected_revision: stamp.revision } })
  await entry.finish('success')
  assert.deepEqual(invoke('preview', { day }), [], 'an admitted scope still observes opt-out before writing')
})

test('another SQLite writer causes an immediate drop rather than a queued retry', async t => {
  const { root, store, children } = await fixture(t), stamp = await store.snapshot()
  const child = children.start(['-c', 'import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); c.execute("BEGIN IMMEDIATE"); print("ready",flush=True); sys.stdin.read(); c.rollback()', join(root, 'product-telemetry.sqlite3')])
  await waitForTelemetryFixture(child)
  const started = performance.now()
  assert.equal(await store.record(observation(), stamp, 20000), false)
  assert.ok(performance.now() - started < 1500)
  child.stdin.end()
  assert.equal(await children.exited(child), 0)
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
