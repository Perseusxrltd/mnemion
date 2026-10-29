/** Compare the shared TypeScript v3 codec with the Python packets for one fixture. */
import { createRequire } from 'node:module'
import { existsSync, readFileSync } from 'node:fs'
import { spawnSync } from 'node:child_process'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import assert from 'node:assert/strict'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const typescript = [
  resolve(root, 'studio/electron/node_modules/typescript/lib/typescript.js'),
  resolve(root, 'studio/frontend/node_modules/typescript/lib/typescript.js'),
  process.env.MNEMION_TEST_TYPESCRIPT,
].find(candidate => candidate && existsSync(candidate))
if (!typescript) {
  throw new Error('pinned TypeScript was not found; set MNEMION_TEST_TYPESCRIPT to typescript.js for this run')
}
const ts = createRequire(typescript)(typescript)
const modules = new Map()

function load(url) {
  if (modules.has(url.href)) return modules.get(url.href)
  const exported = {}
  modules.set(url.href, exported)
  const code = ts.transpileModule(readFileSync(url, 'utf8'), { compilerOptions: {
    target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, esModuleInterop: true,
  } }).outputText
  const local = createRequire(url)
  new Function('require', 'exports', code)(name => {
    if (!name.startsWith('.')) return local(name)
    const next = new URL(name.replace(/\.js$/, '') + '.ts', url)
    return load(next)
  }, exported)
  return exported
}

const { TelemetryCatalog } = load(new URL('../studio/electron/telemetry-catalog.ts', import.meta.url))
const { TelemetryWireV3 } = load(new URL('../studio/electron/telemetry-wire-v3.ts', import.meta.url))
const wireSpec = JSON.parse(readFileSync(new URL('../mnemion/product_telemetry/wire-v3.json', import.meta.url), 'utf8'))
const catalogSpec = JSON.parse(readFileSync(new URL('../mnemion/product_telemetry/catalog.json', import.meta.url), 'utf8'))
const wireV2 = JSON.parse(readFileSync(new URL('../mnemion/product_telemetry/wire-v2.json', import.meta.url), 'utf8'))
const fixture = JSON.parse(readFileSync(new URL('./fixtures/telemetry-v3-client-vectors.json', import.meta.url), 'utf8'))
const catalog = new TelemetryCatalog(catalogSpec)
const wire = new TelemetryWireV3(wireSpec, catalog)
assert.throws(() => new TelemetryWireV3(wireV2, catalog), /telemetry_invalid_v3_report/)

function draws(values) {
  let index = 0
  const random = limit => {
    if (index >= values.length) throw new Error('extra draw')
    const value = values[index++]
    if (!Number.isInteger(value) || value < 0 || value >= limit) throw new Error(`draw ${value} of ${limit}`)
    return value
  }
  random.used = () => index
  return random
}

function rowsFor(caseItem) {
  if (caseItem.repeat) return Array.from({ length: caseItem.repeat }, () => [0, 1])
  if (caseItem.rows) return caseItem.rows
  if (caseItem.rows_from) {
    return caseItem.rows_from.map(item => {
      const picked = catalog.observation(item.observation).cells.filter(cell => catalog.describe(cell).metric === item.metric)
      assert.equal(picked.length, 1)
      return [picked[0], item.count]
    })
  }
  const totals = new Map()
  for (const item of caseItem.observations ?? []) {
    for (const cell of catalog.observation(item).cells) totals.set(cell, (totals.get(cell) ?? 0) + 1)
  }
  return [...totals].map(([cell, count]) => [cell, count])
}

function call(method, caseItem, rows) {
  const random = draws(caseItem.draws)
  const packet = wire[method](
    method === 'summarize' ? caseItem.observations : rows,
    caseItem.groups ?? fixture.groups,
    caseItem.release ?? fixture.release,
    caseItem.operating_system ?? 'linux',
    random,
  )
  assert.equal(random.used(), caseItem.draws.length)
  return Buffer.from(packet).toString('hex')
}

const local = []
for (const caseItem of fixture.cases) {
  const rows = rowsFor(caseItem)
  if (caseItem.error) {
    assert.throws(() => call('prepare', caseItem, rows), /telemetry_invalid_v3_report/)
    local.push({ name: caseItem.name, error: true })
    continue
  }
  const item = { name: caseItem.name, prepare: call('prepare', caseItem, rows) }
  if (caseItem.observations) {
    item.summarize = call('summarize', caseItem, rows)
    assert.equal(item.summarize, item.prepare)
  }
  const decoded = wire.decode(Buffer.from(item.prepare, 'hex'))
  const expect = caseItem.expect
  if (expect.axis) assert.equal(decoded.axis, expect.axis)
  if (expect.cohort) assert.equal(decoded.cohortId, expect.cohort)
  if (expect.cohort_index !== undefined) assert.equal(decoded.cohortIndex, expect.cohort_index)
  for (const [metric, label] of Object.entries(expect.metrics ?? {})) {
    const index = wire.metrics.findIndex(item => item.id === metric)
    assert.equal(wire.bucketLabel(metric, decoded.buckets[index]), label, caseItem.name)
  }
  local.push(item)
}

const events = []
const random = limit => { events.push(['draw', limit]); return 0 }
const proxy = new Proxy([[0, 1]], { get(target, property, receiver) {
  events.push('rows')
  return Reflect.get(target, property, receiver)
} })
wire.prepare(proxy, fixture.groups, fixture.release, 'linux', random)
assert.equal(events[0][0], 'draw')
assert.equal(events[0][1], 2)
events.length = 0
assert.throws(() => wire.prepare(proxy, [], fixture.release, 'linux', random), /telemetry_invalid_v3_report/)
assert.deepEqual(events, [['draw', 2]])

const python = process.env.MNEMION_TEST_PYTHON || (process.platform === 'win32' ? 'python' : 'python3')
const child = spawnSync(python, [resolve(root, 'tests/check_telemetry_v3_client_packets.py')], {
  cwd: root, env: { ...process.env, PYTHONPATH: root, PYTHONNOUSERSITE: '1' }, encoding: 'utf8',
})
assert.equal(child.status, 0, child.stderr)
const remote = JSON.parse(child.stdout)
assert.equal(remote.length, local.length)
for (let index = 0; index < local.length; index++) assert.deepEqual(local[index], remote[index])
console.log(`v3 client parity ${local.length} cases`)
