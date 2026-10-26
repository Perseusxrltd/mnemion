import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createHash } from 'node:crypto'
import { spawnSync } from 'node:child_process'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { TelemetryCatalog } from '../dist/telemetry-catalog.js'
import { TelemetryWire, secureRandomBelow } from '../dist/telemetry-wire.js'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../../..')
const specification = JSON.parse(readFileSync(new URL('../dist/telemetry-wire-v2.json', import.meta.url), 'utf8'))
const catalog = new TelemetryCatalog(JSON.parse(readFileSync(new URL('../dist/telemetry-catalog.json', import.meta.url), 'utf8')))
const wire = new TelemetryWire(specification, catalog)
const draws = (...values) => () => values.shift()
const python = source => {
  const child = spawnSync(process.env.MNEMION_TEST_PYTHON || (process.platform === 'win32' ? 'python' : 'python3'), ['-c', source], {
    cwd: root, env: { ...process.env, PYTHONPATH: root, PYTHONNOUSERSITE: '1' }, encoding: 'utf8', timeout: 20000,
  })
  assert.equal(child.status, 0, child.stderr)
  assert.equal(child.stderr, '')
  return JSON.parse(child.stdout)
}

test('offline synthetic format example agrees across native and Python controls', () => {
  const example = wire.formatExample()
  assert.deepEqual(Buffer.from(example.body_base64, 'base64'), Buffer.from([2, 0, 7, 0]))
  assert.equal(example.kind, 'synthetic_example')
  assert.equal(example.body_encoding, 'base64')
  assert.deepEqual(example, python('import json; from mnemion.product_telemetry.wire import format_example; print(json.dumps(format_example()))'))
  assert.deepEqual(wire.formatExample(), example)
})

test('every native packet matches Python across every view, category, coordinate and coin', () => {
  const digest = createHash('sha256')
  let reports = 0
  for (const reviewed of [false, true]) for (const view of specification.views) for (let category = 0; category < view.values.length; category++) {
    for (let column = 0; column < view.domain; column++) for (let coin = 0; coin < 4; coin++) {
      const packet = wire.encode(view.id, category, draws(column, coin), reviewed)
      digest.update(packet); reports++
      assert.equal(packet.length, 4)
      assert.equal(wire.decode(packet).coordinate, reviewed ? 0 : column)
      assert.equal(wire.decode(packet).reviewed, reviewed)
    }
  }
  const expected = python(`
import hashlib,json
from mnemion.product_telemetry.wire import VIEWS,encode
digest=hashlib.sha256();reports=0
for reviewed in (False,True):
 for view in VIEWS:
  for category in range(len(view['values'])):
   for column in range(view['domain']):
    for coin in range(4):
     values=iter((column,coin))
     digest.update(encode(view['id'],category,reviewed=reviewed,random_below=lambda _:next(values)))
     reports+=1
print(json.dumps({'reports':reports,'digest':digest.hexdigest()}))
`)
  assert.deepEqual({ reports, digest: digest.digest('hex') }, expected)
})

test('Python and native producers sample the same bounded cells and independent cohorts', () => {
  const observation = { kind: 'submission', workflow: 'memory.recall', surface: 'desktop' }
  const rows = [[catalog.observation(observation).cells[0], 3], [catalog.observation({ kind: 'resource', metric: 'rss_bytes', value: 123456 }).cells[0], 1]]
  const groups = ['usage', 'reliability', 'performance', 'resources']
  const cohorts = { platform: 'linux', architecture: 'x64', release_family: '4' }
  const results = []
  for (let seed = 0; seed < 128; seed++) {
    let state = seed
    const random = limit => { state = (state * 1664525 + 1013904223) >>> 0; return state % limit }
    results.push(Buffer.from(wire.prepare(rows, groups, cohorts, random)).toString('hex'))
  }
  assert.deepEqual(results, python(`
import json
from mnemion.product_telemetry import catalog,wire
rows=[(catalog.observation({'kind':'submission','workflow':'memory.recall','surface':'desktop'})[1][0],3),
 (catalog.observation({'kind':'resource','metric':'rss_bytes','value':123456})[1][0],1)]
results=[]
for seed in range(128):
 state=[seed]
 def random(limit):
  state[0]=(state[0]*1664525+1013904223)&0xffffffff
  return state[0]%limit
 results.append(wire.prepare(rows,groups=['usage','reliability','performance','resources'],
  cohorts={'platform':'linux','architecture':'x64','release_family':'4'},random_below=random).hex())
print(json.dumps(results))
`))
})

test('native encoder rejects private fields, malformed cells and unsupported frames', () => {
  for (const rows of [[], [[0, 0]], [[0, true]], [[0, 256]], [[0, 1], [0, 1]], [[65535, 1]], [{ private: 'PRIVATE_SENTINEL' }]]) {
    assert.throws(() => wire.prepare(rows, ['usage']), /telemetry_invalid_/)
  }
  for (const packet of [new Uint8Array(), new Uint8Array([2, 255, 0, 1]), new Uint8Array([2, 0, 16, 1]), new Uint8Array([2, 0, 0, 4]), new Uint8Array([1, 0, 0, 1]), [2, 0, 0, 1]]) {
    assert.throws(() => wire.decode(packet), /telemetry_invalid_report/)
  }
  assert.throws(() => wire.prepare([[0, 1]], ['resources'], { platform: 'PRIVATE_HOST' }), /telemetry_invalid_report/)
  assert.throws(() => wire.prepare([[0, 1]], ['resources'], { device: 'PRIVATE_ID' }), /telemetry_invalid_report/)
  assert.throws(() => wire.prepare([[0, 1]], []), /telemetry_invalid_report/)
  assert.throws(() => wire.encode(0, true), /telemetry_invalid_report/)
  assert.throws(() => wire.encode(0, 1, draws(7, 0), 'PRIVATE_VALUE'), /telemetry_invalid_report/)
})

test('only permitted views are selected, including unknown sensors without fabricated zeros', () => {
  const rss = catalog.observation({ kind: 'resource', metric: 'rss_bytes', value: 0 }).cells[0]
  const packet = wire.prepare([[rss, 1]], ['resources'], {}, draws(0, 2, 0))
  const decoded = wire.decode(packet)
  assert.equal(specification.views[decoded.view].name, 'queue_items')
  assert.deepEqual(packet, wire.encode(decoded.view, 0, draws(2, 0)))
  for (let position = 0; position < 112; position++) {
    // A broad fixed draw modulo the permitted total never selects another group.
    const total = specification.views.filter(view => view.group === 'resources').reduce((sum, view) => sum + view.weight, 0)
    const result = wire.prepare([[0, 1]], ['resources'], {}, draws(position % total, 0, 0))
    assert.equal(specification.views[wire.decode(result).view].group, 'resources')
  }
})

test('preview is the exact four-byte body without a decoded private value', () => {
  const packet = wire.encode(0, 3, draws(7, 3)), preview = wire.preview(packet)
  assert.deepEqual(Buffer.from(preview.body_base64, 'base64'), Buffer.from(packet))
  assert.equal(preview.body_bytes, 4)
  assert.equal(preview.participation_or_lifetime_guarantee, false)
  assert.ok(!Object.hasOwn(preview, 'category') && !Object.hasOwn(preview, 'identity'))
})

test('manual packet preview marks volume-only aggregation without a selected-report privacy claim', () => {
  const packet = wire.encode(0, 1, draws(7, 0), true), preview = wire.preview(packet)
  assert.equal(preview.report_selection, 'reviewed')
  assert.equal(preview.aggregation, 'coarse_global_volume_only')
  assert.equal(preview.per_report_privacy_loss, null)
  assert.equal(preview.randomization_privacy_loss, null)
  assert.equal(preview.randomized_sign, null)
  assert.equal(preview.privacy_bound_scope, 'fixed_body_for_permitted_groups')
  assert.deepEqual(preview, python("import json; from mnemion.product_telemetry import wire; print(json.dumps(wire.preview(bytes([2,0,0,2]))))"))
})

test('review preparation has a constant permitted body with no entropy or category output', () => {
  const noEntropy = () => assert.fail('Reviewed volume must not draw entropy')
  const one = catalog.observation({ kind: 'submission', workflow: 'memory.recall', surface: 'desktop' }).cells[0]
  const two = catalog.observation({ kind: 'submission', workflow: 'backup.create', surface: 'desktop' }).cells[0]
  for (const groups of [['usage', 'resources'], ['performance'], ['resources', 'reliability']]) {
    const expected = specification.views.find(view => groups.includes(view.group)).id
    for (const rows of [[[one, 1]], [[two, 255]]]) assert.deepEqual(
      wire.prepare(rows, groups, {}, noEntropy, true), new Uint8Array([2, expected, 0, 2]))
  }
  for (const packet of [[2, 0, 1, 2], [2, 0, 0, 3]]) assert.throws(() => wire.decode(new Uint8Array(packet)), /telemetry_invalid_report/)
})

test('CSPRNG range reduction rejects bias and stops after bounded entropy failures', t => {
  let calls = 0
  t.mock.method(globalThis.crypto, 'getRandomValues', sample => {
    sample[0] = calls++ === 0 ? 0xffffffff : 4
    return sample
  })
  assert.equal(secureRandomBelow(3), 1)
  assert.equal(calls, 2)
  t.mock.restoreAll()
  t.mock.method(globalThis.crypto, 'getRandomValues', sample => { sample[0] = 0xffffffff; return sample })
  assert.throws(() => secureRandomBelow(3), /telemetry_invalid_report/)
  for (const invalid of [0, -1, true, 1.5, 131073]) assert.throws(() => secureRandomBelow(invalid), /telemetry_invalid_report/)
})
