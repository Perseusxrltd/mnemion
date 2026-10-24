import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import assert from 'node:assert/strict'
import { test } from 'node:test'
import ts from 'typescript'

const path = new URL('../src/workspace/telemetry-policy.ts', import.meta.url)
const code = ts.transpileModule(readFileSync(path, 'utf8'), { compilerOptions: {
  target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, esModuleInterop: true,
} }).outputText
const exported = {}
new Function('require', 'exports', code)(createRequire(path), exported)
const { BrowserTelemetry, choiceKey, queueKey } = exported

function installation() {
  const values = new Map()
  const storage = { getItem: key => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value), removeItem: key => values.delete(key) }
  let company = { state: 'unmanaged', enabled: true, metric_groups: ['usage'] }
  const client = () => new BrowserTelemetry(() => storage, () => company, () => false, () => true)
  return { values, storage, client, company: value => { company = value } }
}

test('reading the browser policy creates nothing and requires actual disclosure', () => {
  const { client, values } = installation()
  assert.equal(client().status().reason, 'disclosure_required')
  assert.equal(client().status().user_enabled, true)
  assert.equal(values.size, 0)
  assert.equal(client().preview().outbound_bytes, 0)
})

test('another tab cannot re-enable after a newer opt-out even if it was already off', () => {
  const { client, storage } = installation()
  const first = client(), second = client()
  const off = first.configure({ enabled: false, expected_revision: 0 })
  storage.setItem(queueKey, '[{"cell":7,"count":2,"window_day":20000}]')
  const repeated = second.configure({ enabled: false, expected_revision: 0 })
  assert.ok(repeated.revision > off.revision)
  assert.equal(storage.getItem(queueKey), null)
  assert.throws(() => first.configure({ enabled: true, expected_revision: off.revision }), /changed in another tab/)
  const on = first.configure({ enabled: true, expected_revision: repeated.revision })
  assert.equal(on.reason, 'disclosure_required')
  assert.equal(on.pending_records, 0)
  assert.deepEqual(client().status(), on)
})

test('a permissive company policy cannot override an explicit opt-out', () => {
  const instance = installation(), client = instance.client()
  instance.company({ state: 'restricted', enabled: false, metric_groups: [] })
  assert.equal(client.status().reason, 'company_policy')
  client.configure({ enabled: false, expected_revision: 0 })
  instance.company({ state: 'restricted', enabled: true, metric_groups: ['usage'] })
  assert.equal(client.status().reason, 'user_disabled')
})

test('corrupt private preference and pending bytes stay out of status and preview', () => {
  for (const key of [choiceKey, queueKey]) {
    const { storage, client } = installation()
    storage.setItem(key, 'PRIVATE_SENTINEL')
    const result = client().preview()
    assert.equal(result.status.reason, 'storage_unavailable')
    assert.equal(result.status.effective_enabled, false)
    assert.equal(result.status.pending_records, null)
    assert.ok(!JSON.stringify(result).includes('PRIVATE_SENTINEL'))
    assert.equal(storage.getItem(key), 'PRIVATE_SENTINEL')
  }
})

test('failed preference writes keep the current tab off even when reads still work', () => {
  const { storage, client } = installation()
  const current = client()
  storage.setItem = () => { throw new Error('PRIVATE_SENTINEL quota failure') }
  assert.throws(() => current.configure({ enabled: false, expected_revision: 0 }), /Product telemetry stays off/)
  assert.equal(current.status().reason, 'storage_unavailable')
  assert.equal(current.status().effective_enabled, false)
  assert.ok(!JSON.stringify(current.status()).includes('PRIVATE_SENTINEL'))
})

test('unavailable coordination and browser privacy each prevent an effective opt-in', () => {
  const { storage } = installation()
  const company = () => ({ state: 'unmanaged', enabled: true, metric_groups: ['usage'] })
  assert.equal(new BrowserTelemetry(() => storage, company, () => false, () => false).status().reason, 'coordination_unavailable')
  assert.equal(new BrowserTelemetry(() => storage, company, () => true, () => true).status().reason, 'browser_privacy')
})

test('unknown fields and a not-yet-available collector cannot be preapproved', () => {
  const { client, values } = installation()
  assert.throws(() => client().configure({ enabled: false, expected_revision: 0, token: 'PRIVATE_SENTINEL' }), /Choose whether/)
  assert.throws(() => client().configure({ enabled: true, expected_revision: 0, disclosure_version: 1 }), /Collection is not available/)
  assert.equal(values.size, 0)
})
