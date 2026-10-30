import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import {
  acceptObservation,
  bumpObservation,
  deliveryObservationEnabled,
  emptyObservation,
  mergeObservationSample,
  noteAcl,
  noteObservation,
  publicObservation,
  sanitizeObservation,
} from '../telemetry-observation-diagnostic.mjs'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const secret = 'C:\\Users\\secret\\probe.json'
const credential = 'mnm_private_fixture_key'

function restore(name, value) {
  if (value === undefined) delete process.env[name]
  else process.env[name] = value
}

test('delivery counters stay bounded and omit private fields', () => {
  const state = emptyObservation()
  for (let count = 0; count < 300; count += 1) bumpObservation(state, 'acl_timed_out')
  assert.equal(state.counts.acl_timed_out, 255)
  const merged = mergeObservationSample(state, {
    cycle: 1,
    readiness: 'memory_observations',
    pending: 'no_observations',
    path: secret,
    credential,
    error: 'raw sqlite failure',
    observed_at: '2026-10-30T07:17:15Z',
    renderer: {
      snapshot_deadline: 2,
      snapshot_elapsed_ge_25: 2,
      snapshot_admitted: 300,
      path: secret,
    },
  })
  assert.equal(merged.cycle, 1)
  assert.equal(merged.readiness, 'memory_observations')
  assert.equal(merged.pending, 'no_observations')
  assert.equal(merged.acl_timed_out, 255)
  assert.equal(merged.snapshot_deadline, 2)
  assert.equal(merged.snapshot_admitted, 0)
  const text = JSON.stringify(merged)
  assert.equal(text.includes(secret), false)
  assert.equal(text.includes(credential), false)
  assert.equal(text.includes('sqlite'), false)
  assert.equal(text.includes('2026-10-30'), false)
  const dirty = { ...merged, path: secret, credential, error: 'raw' }
  const clean = sanitizeObservation(dirty)
  assert.equal(JSON.stringify(clean).includes(secret), false)
  assert.equal(clean.path, undefined)
  assert.equal(sanitizeObservation({ ...merged, readiness: secret }), null)
  assert.equal(sanitizeObservation({ ...merged, pending: credential }), null)
})

test('hosting and resource probes do not arm delivery counters', () => {
  const probe = process.env.MNEMION_STUDIO_HOSTING_PROBE
  const delivery = process.env.MNEMION_TELEMETRY_INSTALLED_DELIVERY
  try {
    process.env.MNEMION_STUDIO_HOSTING_PROBE = secret
    delete process.env.MNEMION_TELEMETRY_INSTALLED_DELIVERY
    assert.equal(deliveryObservationEnabled(), false)
    noteObservation('record_attempted')
    noteAcl('accepted', 4)
    assert.equal(publicObservation(), null)
    assert.equal(acceptObservation({ cycle: 2, readiness: 'before_permission', pending: 'connection_pending', path: secret }), null)
    process.env.MNEMION_TELEMETRY_INSTALLED_DELIVERY = '1'
    const armed = publicObservation()
    assert.equal(armed.record_attempted, 0)
    assert.equal(armed.acl_accepted, 0)
    assert.equal(armed.acl_duration_lt_50, 0)
    assert.equal(armed.readiness, 'none')
    assert.equal(JSON.stringify(armed).includes('secret'), false)
  } finally {
    restore('MNEMION_STUDIO_HOSTING_PROBE', probe)
    restore('MNEMION_TELEMETRY_INSTALLED_DELIVERY', delivery)
  }
})

test('the connection change waits for a visible enabled settled control', () => {
  const probe = readFileSync(resolve(root, 'native-telemetry-delivery-probe.ts'), 'utf8')
  const client = readFileSync(resolve(root, '../frontend/src/workspace/measured-client.ts'), 'utf8')
  const gate = probe.slice(probe.indexOf("getElementById('telemetry-connection-mode')"), probe.indexOf("setValue(connection, 'unmetered')"))
  assert.match(gate, /node instanceof HTMLSelectElement/)
  assert.match(gate, /node\.disabled/)
  assert.match(gate, /getClientRects\(\)\.length/)
  assert.match(gate, /reviewSettled/)
  assert.equal(gate.includes('Missing connection choice'), false)
  const race = client.slice(client.indexOf('measurement = await Promise.race'), client.indexOf("outcome = deadline"))
  assert.match(race, /finally \{[\s\S]*elapsed = performance\.now\(\) - started/)
  assert.equal(race.includes("outcome = 'rejected'"), false)
})
