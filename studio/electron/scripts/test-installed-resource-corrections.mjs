import assert from 'node:assert/strict'
import test from 'node:test'
import { canonicalTerminalMarker, resourceProgress } from '../canonical-memory-cycles.mjs'
import { finishResourceCleanup, publicOwnedReport, resourceCaseStoreReady, resourceInstallSteps } from './installed-resource-report.mjs'

const CASES = [
  { label: 'r1-unavailable', condition: 'unavailable', package: 'inactive' },
  { label: 'r1-opted_out', condition: 'opted_out', package: 'active' },
  { label: 'r1-enabled', condition: 'enabled', package: 'active' },
  { label: 'r2-enabled', condition: 'enabled', package: 'active' },
  { label: 'r2-opted_out', condition: 'opted_out', package: 'active' },
  { label: 'r2-unavailable', condition: 'unavailable', package: 'inactive' },
]

test('in-flight work keeps the verified lower bound and marks the total unknown', () => {
  let progress = { progressKnown: false }
  progress = resourceProgress(progress, { settled: 96 })
  assert.equal(progress.verified, 96)
  assert.equal(progress.progressKnown, true)
  progress = resourceProgress(progress, 'inflight')
  assert.equal(progress.verified, 96)
  assert.equal(progress.progressKnown, false)
  progress = resourceProgress(progress, {})
  assert.deepEqual(canonicalTerminalMarker('failed', progress.verified, progress.progressKnown), {
    phase: 'failed', completed: 96, completed_known: false,
  })
  assert.equal(Object.hasOwn(canonicalTerminalMarker('closed', undefined, false), 'completed'), false)
  assert.equal(canonicalTerminalMarker('finished', 128, false).completed, 128)
  assert.equal(canonicalTerminalMarker('finished', 128, false).completed_known, false)
})

test('windows package changes install and remove one product before the next', () => {
  const steps = resourceInstallSteps(CASES)
  assert.deepEqual(steps.map(step => step.action === 'use' ? `use:${step.label}` : `${step.action}:${step.package || ''}`), [
    'refuse-preexisting:',
    'install:inactive',
    'use:r1-unavailable',
    'uninstall:inactive',
    'install:active',
    'use:r1-opted_out',
    'use:r1-enabled',
    'use:r2-enabled',
    'use:r2-opted_out',
    'uninstall:active',
    'install:inactive',
    'use:r2-unavailable',
    'uninstall:inactive',
  ])
  assert.ok(steps.filter(step => step.action === 'install').every(step => step.refuseExisting === true))
  let open = 0
  for (const step of steps) {
    if (step.action === 'install') open += 1
    if (step.action === 'uninstall') open -= 1
    assert.ok(open <= 1 && open >= 0)
  }
})

test('cleanup tries every installation created when one uninstall fails', () => {
  const calls = []
  const failures = finishResourceCleanup(
    [{ id: 1, package: 'inactive' }, { id: 2, package: 'active' }, { id: 3, package: 'inactive' }],
    new Set([1]),
    item => {
      calls.push(item.id)
      if (item.id === 2) throw new Error('C:\\secret\\uninstall')
    },
  )
  assert.deepEqual(calls, [2, 3])
  assert.deepEqual(failures, ['uninstall_failed'])
})

test('store evidence requires one reservation only for an enabled case', () => {
  const clean = { fixture_content_absent: true }
  assert.equal(resourceCaseStoreReady(
    { enabled: true, condition: 'enabled' },
    { ...clean, present: true, attempts: 1, reserved_bytes: 65536 },
  ), true)
  assert.equal(resourceCaseStoreReady(
    { enabled: true, condition: 'enabled' },
    { ...clean, present: true, attempts: 0, reserved_bytes: 0 },
  ), false)
  assert.equal(resourceCaseStoreReady(
    { enabled: false, condition: 'opted_out' },
    { ...clean, present: true, attempts: 0, reserved_bytes: 0 },
  ), true)
  assert.equal(resourceCaseStoreReady(
    { enabled: false, condition: 'unavailable' },
    { ...clean, present: false, attempts: 0, reserved_bytes: 0 },
  ), true)
  assert.equal(resourceCaseStoreReady(
    { enabled: false, condition: 'unavailable' },
    { ...clean, present: true, attempts: 1, reserved_bytes: 65536 },
  ), false)
})

test('the public report keeps partial ram and drops a path', () => {
  const report = publicOwnedReport({
    ledger: [{
      pid: 40, creation: '9', identity: '40:9',
      peak_working_set_bytes: 9000000, first_working_set_bytes: 1000000,
      last_working_set_bytes: 2000000, kernel_high_water_while_observed: true,
    }, {
      pid: 41, creation: '9', identity: '41:9',
      peak_working_set_bytes: null, first_working_set_bytes: null,
      last_working_set_bytes: null, kernel_high_water_while_observed: false,
    }],
    cold_start: { kind: 'first_observed_absolute', subtracted: false, processes: [{ identity: '40:9', working_set_bytes: 1000000 }] },
    coverage: { status: 'partial', platform: 'windows', rss_high_water: 'per_process_kernel_while_alive_partial', cpu_lifetime_complete: true },
    unavailable_counters: ['unseen_or_unsampled_process_working_set'],
    sampled_peaks: { sum_working_set_bytes: 9000000, sum_double_counts_shared: true, not_a_budget_measurement: true, sampled_pid_cpu_is_complete: false },
    canonical_operations_completed: 96,
    canonical_operations_known: false,
    lifetime_cpu_microseconds: null,
    trace: 'C:\\secret-trace\\probe.py',
    resource_acceptance: true,
  })
  assert.equal(report.ledger[0].peak_working_set_bytes, 9000000)
  assert.equal(report.ledger[1].peak_working_set_bytes, null)
  assert.equal(report.cold_start.processes[0].working_set_bytes, 1000000)
  assert.equal(report.coverage.status, 'partial')
  assert.equal(report.canonical_operations_known, false)
  assert.equal(report.resource_acceptance, false)
  assert.equal(report.budget.compared, false)
  assert.equal(JSON.stringify(report).includes('secret-trace'), false)
})
