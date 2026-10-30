import test from 'node:test'
import assert from 'node:assert/strict'
import {
  copyAdmissionGuard,
  createAdmissionNote,
  resourceAdmissionEnabled,
  runDiagnosticAdmission,
  sanitizeAdmissionOutcome,
  unknownAdmissionOutcome,
} from '../admission-outcome.mjs'

const secret = 'mnm_private_fixture_key'
const path = 'C:\\Users\\secret\\probe.json'

function probeEnv(extra) {
  return { MNEMION_STUDIO_HOSTING_PROBE: 'owned-probe', ...extra }
}

test('resource admission is off unless the packaged probe opts in', () => {
  assert.equal(resourceAdmissionEnabled(undefined, false), false)
  assert.equal(resourceAdmissionEnabled(null, true), false)
  assert.equal(resourceAdmissionEnabled({}, true), false)
  assert.equal(resourceAdmissionEnabled(probeEnv({ MNEMION_TELEMETRY_RESOURCE_ADMISSION: '1' }), false), false)
  assert.equal(resourceAdmissionEnabled({ MNEMION_TELEMETRY_RESOURCE_ADMISSION: '1' }, true), false)
  assert.equal(resourceAdmissionEnabled(probeEnv({ MNEMION_TELEMETRY_RESOURCE_ADMISSION: 'true' }), true), false)
  assert.equal(resourceAdmissionEnabled(probeEnv({
    MNEMION_TELEMETRY_RESOURCE_ADMISSION: '1',
    MNEMION_TELEMETRY_INSTALLED_DELIVERY: '1',
  }), true), false)
  assert.equal(resourceAdmissionEnabled(probeEnv({ MNEMION_TELEMETRY_RESOURCE_ADMISSION: '1' }), true), true)
})

test('one admission outcome strips corrupt fields and private names', () => {
  const validGuard = {
    schema_version: 1, network: 'unmetered', constrained: true, reason: 'cpu_unobserved', path, credential: secret,
  }
  const cases = [
    [null, null],
    [[], null],
    ['reserved', null],
    [{ schema_version: 1, outcome: ['reserved'] }, null],
    [{ schema_version: 1, outcome: { stage: 'reserved' } }, null],
    [{ schema_version: true, outcome: 'reserved' }, null],
    [{ schema_version: '1', outcome: 'reserved' }, null],
    [{ schema_version: 1, outcome: 'nope', path }, null],
    [{ schema_version: 1, outcome: 'reserved', guard: [], secret },
      { schema_version: 1, outcome: 'reserved', guard: null }],
    [{ schema_version: 1, outcome: 'prepare_refused', guard: { ...validGuard, network: ['unmetered'] }, token: secret },
      { schema_version: 1, outcome: 'prepare_refused', guard: null }],
    [{ schema_version: 1, outcome: 'aborted', guard: { ...validGuard, schema_version: true } },
      { schema_version: 1, outcome: 'aborted', guard: null }],
    [{ schema_version: 1, outcome: 'reserve_refused', guard: { ...validGuard, reason: { code: 'memory' } } },
      { schema_version: 1, outcome: 'reserve_refused', guard: null }],
    [{ schema_version: 1, outcome: 'reserved', guard: { ...validGuard, constrained: 1 } },
      { schema_version: 1, outcome: 'reserved', guard: null }],
    [{ schema_version: 1, outcome: 'eligible_refused', guard: validGuard, api_key: secret },
      { schema_version: 1, outcome: 'eligible_refused', guard: null }],
    [{ schema_version: 1, outcome: 'unknown', guard: validGuard, path },
      { schema_version: 1, outcome: 'unknown', guard: null }],
    [{ schema_version: 1, outcome: 'prepare_refused', guard: validGuard, secret },
      { schema_version: 1, outcome: 'prepare_refused', guard: { schema_version: 1, network: 'unmetered', constrained: true, reason: 'cpu_unobserved' } }],
  ]
  for (const [input, expected] of cases) {
    const got = sanitizeAdmissionOutcome(input)
    assert.deepEqual(got, expected)
    assert.equal(JSON.stringify(got ?? {}).includes(secret), false)
    assert.equal(JSON.stringify(got ?? {}).includes('Users'), false)
    if (got) assert.deepEqual(Object.keys(got).sort(), ['guard', 'outcome', 'schema_version'])
  }
  assert.equal(copyAdmissionGuard(['unmetered']), null)
  assert.equal(copyAdmissionGuard({ schema_version: 1, network: { kind: 'wifi' }, constrained: false, reason: 'allowed' }), null)
  const unknown = unknownAdmissionOutcome()
  assert.deepEqual(unknown, { schema_version: 1, outcome: 'unknown', guard: null })
  const snapshot = sanitizeAdmissionOutcome({ schema_version: 1, outcome: 'reserved', guard: null })
  assert.equal(snapshot.outcome, 'reserved')
  assert.equal(unknown.schema_version, snapshot.schema_version)
})

test('diagnostic admission records one real flow outcome and drops the report body', async () => {
  const stop = () => new AbortController().signal
  const flows = [
    {
      name: 'eligible_refused',
      eligible: async () => false,
      prepare: async () => { throw new Error(secret) },
      reserve: async () => ({ api_key: secret }),
      aborted: false,
    },
    {
      name: 'prepare_refused',
      eligible: async () => true,
      prepare: async conditions => {
        conditions.admissionGuard = {
          schema_version: 1, network: 'unmetered', constrained: true, reason: 'cpu_unobserved', path, credential: secret,
        }
        return false
      },
      reserve: async () => ({ api_key: secret }),
      aborted: false,
    },
    {
      name: 'aborted',
      eligible: async () => true,
      prepare: async conditions => {
        conditions.admissionGuard = {
          schema_version: 1, network: 'unmetered', constrained: true, reason: 'cpu_busy', path,
        }
        return false
      },
      reserve: async () => ({ api_key: secret }),
      aborted: true,
    },
    {
      name: 'reserve_refused',
      eligible: async () => true,
      prepare: async conditions => {
        conditions.admissionGuard = {
          schema_version: 1, network: 'metered', constrained: false, reason: 'network_not_allowed', path,
        }
        return true
      },
      reserve: async () => null,
      aborted: false,
    },
    {
      name: 'reserved',
      eligible: async () => true,
      prepare: async conditions => {
        conditions.admissionGuard = {
          schema_version: 1, network: 'unmetered', constrained: false, reason: 'allowed', path,
        }
        return true
      },
      reserve: async () => ({ accepted: true, api_key: secret }),
      aborted: false,
    },
  ]
  for (const flow of flows) {
    const conditions = { traceAdmission: false, admissionGuard: undefined }
    const note = createAdmissionNote(conditions)
    const controller = new AbortController()
    if (flow.aborted) controller.abort()
    const report = await runDiagnosticAdmission({
      begin: () => note.begin(),
      finish: name => note.finish(name),
      eligible: flow.eligible,
      prepare: () => flow.prepare(conditions),
      reserve: flow.reserve,
      stop: flow.aborted ? controller.signal : stop(),
    })
    const outcome = note.snapshot()
    note.finish('eligible_refused')
    note.begin()
    assert.equal(note.snapshot(), outcome)
    assert.equal(outcome.outcome, flow.name)
    assert.equal(outcome.schema_version, 1)
    assert.equal(JSON.stringify(outcome).includes(secret), false)
    assert.equal(JSON.stringify(outcome).includes('Users'), false)
    if (flow.name === 'eligible_refused' || flow.name === 'release_unavailable') assert.equal(outcome.guard, null)
    if (flow.name === 'prepare_refused') assert.equal(outcome.guard.reason, 'cpu_unobserved')
    if (flow.name === 'aborted') assert.equal(outcome.guard.reason, 'cpu_busy')
    if (flow.name === 'reserve_refused') assert.equal(outcome.guard.reason, 'network_not_allowed')
    if (flow.name === 'reserved') {
      assert.equal(outcome.guard.reason, 'allowed')
      assert.equal(report.accepted, true)
      assert.equal(report.api_key, secret)
    } else {
      assert.equal(report, null)
    }
    assert.deepEqual(Object.keys(outcome).sort(), ['guard', 'outcome', 'schema_version'])
  }
  assert.equal(stop().aborted, false)
})
