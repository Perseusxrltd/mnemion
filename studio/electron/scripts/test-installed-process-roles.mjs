import assert from 'node:assert/strict'
import test from 'node:test'
import { compareInstalledProcessRoleRss, observeInstalledProcessCheckpoint, publicProcessRoleRun } from './installed-resource-report.mjs'
import { publicOwnedReport } from './installed-resource-report.mjs'

const PHASES = [
  'before_workspace_connect', 'workspace_connected', 'first_memory_cycle_and_delivery',
  '8_memory_cycles', '16_memory_cycles', '32_memory_cycles', '64_memory_cycles', '96_memory_cycles', '128_memory_cycles',
]

function metric(pid, type, creation, kilobytes, extra) {
  return { pid, type, creationTime: creation, workingSetKilobytes: kilobytes, ...extra }
}

function sample(phase, mainKilobytes, options = {}) {
  const mainPid = options.mainPid ?? 11
  const rendererPid = options.rendererPid ?? 21
  return observeInstalledProcessCheckpoint({
    phase,
    mainPid,
    rendererPid,
    windowCount: options.windowCount ?? 1,
    appWindowCount: options.appWindowCount ?? 1,
    devtoolsPresent: options.devtoolsPresent ?? false,
    metrics: [
      metric(mainPid, 'Browser', options.creation ?? 1_700_000_000_000, mainKilobytes),
      metric(rendererPid, 'Tab', options.rendererCreation ?? 1_700_000_000_100, options.rendererKilobytes ?? 80),
      ...(options.extra ?? []),
    ],
  })
}

function run(mainKilobytes, options = {}) {
  const values = Array.isArray(mainKilobytes) ? mainKilobytes : PHASES.map(() => mainKilobytes)
  return publicProcessRoleRun(PHASES.map((phase, index) => sample(phase, values[index], typeof options === 'function' ? options(phase, index) : options)))
}

function resourceCase(replicate, condition, processRoles) {
  return {
    replicate,
    condition,
    label: `r${replicate}-${condition}`,
    process_roles: processRoles,
    ledger: [{ identity: '9:999', peak_working_set_bytes: 999_999_999 }],
  }
}

function roleRow(comparison, role) {
  return comparison.roles.find(row => row.role === role)
}

test('a valid pair keeps the initial absolute RSS difference', () => {
  const baselineMain = [100, 100, 100, 100, 100, 100, 100, 100, 400]
  const currentMain = [250, 110, 110, 110, 110, 110, 110, 110, 410]
  const baseline = run(baselineMain, { mainPid: 11, rendererPid: 21, creation: 1_700_000_000_000, rendererCreation: 1_700_000_000_100 })
  const current = run(currentMain, { mainPid: 31, rendererPid: 41, creation: 1_800_000_000_000, rendererCreation: 1_800_000_000_100, rendererKilobytes: 70 })
  const compared = compareInstalledProcessRoleRss([
    resourceCase(1, 'unavailable', baseline),
    resourceCase(1, 'enabled', current),
  ])
  const enabled = compared.repeats[0].comparisons[1]
  const main = roleRow(enabled, 'app_main')
  const renderer = roleRow(enabled, 'app_renderer')
  assert.equal(main.compared, true)
  assert.equal(main.baseline_identity, '11:1700000000000')
  assert.equal(main.current_identity, '31:1800000000000')
  assert.notEqual(main.baseline_identity, main.current_identity)
  assert.equal(main.phases[0].baseline_rss_bytes, 100 * 1024)
  assert.equal(main.phases[0].current_rss_bytes, 250 * 1024)
  assert.equal(main.phases[0].signed_difference_bytes, 150 * 1024)
  assert.equal(main.first_observed_difference_bytes, 150 * 1024)
  assert.equal(main.phases[8].signed_difference_bytes, 10 * 1024)
  assert.equal(main.maximum_matched_phase_difference_bytes, 150 * 1024)
  assert.equal(renderer.phases[0].signed_difference_bytes, -10 * 1024)
  assert.equal(renderer.maximum_matched_phase_difference_bytes, -10 * 1024)
  assert.equal(compared.initial_rss_subtracted, false)
  assert.equal(compared.aligned_by_pid_across_runs, false)
  assert.equal(compared.resource_acceptance, false)
  assert.equal(compared.budget.status, 'UNACCEPTED')
  assert.equal(compared.budget.compared, false)
  assert.equal(compared.separate_from_native_ledger, true)
  assert.equal(compared.electron_creation_time_is_os_birth, false)
  assert.equal(compared.first_checkpoint_covers_startup, false)
  assert.equal(compared.covers_exited_or_unseen_helpers, false)
  assert.equal(main.phases[0].signed_difference_bytes === 999_999_999, false)
})

test('all four scoped pairs can be available without accepting the budget', () => {
  const cases = []
  for (const replicate of [2, 1]) {
    for (const condition of ['enabled', 'unavailable', 'opted_out']) {
      const shift = condition === 'unavailable' ? 0 : 8
      cases.push(resourceCase(replicate, condition, run(100 + shift, {
        mainPid: 10 * replicate + (condition === 'unavailable' ? 1 : 2),
        rendererPid: 40 * replicate + (condition === 'unavailable' ? 1 : 2),
        creation: 1_700_000_000_000 + replicate,
        rendererCreation: 1_700_000_000_100 + replicate,
      })))
    }
  }
  const compared = compareInstalledProcessRoleRss(cases)
  assert.deepEqual(compared.repeats.map(repeat => [repeat.replicate, repeat.comparisons.map(row => row.condition)]), [
    [1, ['opted_out', 'enabled']],
    [2, ['opted_out', 'enabled']],
  ])
  assert.equal(compared.scoped_role_comparison_available, true)
  assert.equal(compared.resource_acceptance, false)
  assert.equal(compared.budget.additional_rss_bytes_per_process, 8_388_608)
  assert.equal(compared.budget.cpu_one_core_fraction, 0.005)
  assert.equal(compared.repeats[0].comparisons[1].roles.find(row => row.role === 'app_main').first_observed_difference_bytes, 8 * 1024)
})

test('mismatched phases stay visible and do not become zero', () => {
  const samples = PHASES.map((phase, index) => sample(phase, 100 + index))
  samples[6] = sample('96_memory_cycles', 100)
  const compared = compareInstalledProcessRoleRss([
    resourceCase(1, 'unavailable', publicProcessRoleRun(samples)),
    resourceCase(1, 'opted_out', run(120)),
  ])
  const opted = compared.repeats[0].comparisons[0]
  assert.equal(opted.phases_aligned, false)
  assert.deepEqual(opted.unmatched_phases, ['64_memory_cycles'])
  const main = roleRow(opted, 'app_main')
  assert.equal(main.compared, false)
  assert.equal(main.phases[6].signed_difference_bytes, null)
  assert.equal(main.phases[6].reasons.includes('phase_mismatch'), true)
  assert.equal(main.maximum_matched_phase_difference_bytes === 0, false)
  assert.equal(JSON.stringify(opted).includes('96_memory_cycles'), true)
  assert.equal(opted.roles.some(row => row.phases[6].signed_difference_bytes === 0), false)
})

test('duplicate helpers are not matched by RSS rank or process order', () => {
  const crowded = run(100, (phase, index) => ({
    extra: index === 0 ? [] : [
      metric(50, 'Utility', 1_700_000_000_050, 1),
      metric(60, 'Utility', 1_700_000_000_060, 99_999),
    ],
  }))
  const plain = run(110, { mainPid: 12, rendererPid: 22, creation: 1_700_000_000_001, rendererCreation: 1_700_000_000_101 })
  const first = crowded.checkpoints[3]
  assert.deepEqual(first.processes.filter(row => row.role === 'utility').map(row => row.working_set_bytes), [1024, 99_999 * 1024])
  const compared = compareInstalledProcessRoleRss([
    resourceCase(1, 'unavailable', crowded),
    resourceCase(1, 'enabled', plain),
  ])
  const enabled = compared.repeats[0].comparisons[1]
  const utility = roleRow(enabled, 'utility')
  assert.equal(utility.ambiguous, true)
  assert.equal(utility.compared, false)
  assert.equal(utility.maximum_matched_phase_difference_bytes, null)
  assert.equal(utility.phases[3].baseline_row_count, 2)
  assert.equal(utility.phases[3].signed_difference_bytes, null)
  assert.equal(enabled.ambiguous_roles.includes('utility'), true)
  assert.equal(roleRow(enabled, 'app_main').compared, true)
})

test('a PID or creation change inside one run cannot pass', () => {
  const changed = run(100, (phase, index) => ({ creation: index < 4 ? 1_700_000_000_000 : 1_700_000_000_500 }))
  const other = run(130, { mainPid: 15, rendererPid: 25, creation: 1_710_000_000_000, rendererCreation: 1_710_000_000_100 })
  const compared = compareInstalledProcessRoleRss([
    resourceCase(1, 'unavailable', changed),
    resourceCase(1, 'enabled', other),
  ])
  const main = roleRow(compared.repeats[0].comparisons[1], 'app_main')
  assert.equal(main.identity_changed_within_run, true)
  assert.equal(main.compared, false)
  assert.equal(main.maximum_matched_phase_difference_bytes, null)
  assert.equal(main.phases[0].baseline_rss_bytes, 100 * 1024)
  assert.equal(main.phases[4].baseline_rss_bytes, 100 * 1024)
  assert.equal(main.phases[0].baseline_identity, '11:1700000000000')
  assert.equal(main.phases[4].baseline_identity, '11:1700000000500')
  assert.equal(main.phases[0].signed_difference_bytes, null)
  assert.equal(main.phases[0].reasons.includes('identity_changed'), true)
})

test('extra windows, devtools, and a renderer chosen by PID rather than the window stay explicit', () => {
  const dirty = run(100, { windowCount: 2, devtoolsPresent: true })
  assert.equal(dirty.checkpoints[0].extra_windows, true)
  assert.equal(dirty.checkpoints[0].devtools_present, true)
  assert.equal(dirty.ownership_valid, false)
  const wrongRenderer = publicProcessRoleRun(PHASES.map(phase => observeInstalledProcessCheckpoint({
    phase,
    mainPid: 11,
    rendererPid: 21,
    windowCount: 1,
    appWindowCount: 1,
    devtoolsPresent: false,
    metrics: [
      metric(11, 'Browser', 1_700_000_000_000, 100),
      metric(99, 'Tab', 1_700_000_000_900, 500),
    ],
  })))
  assert.equal(wrongRenderer.checkpoints[0].app_renderer_rows, 0)
  assert.equal(wrongRenderer.checkpoints[0].processes.some(row => row.role === 'app_renderer'), false)
  assert.equal(wrongRenderer.checkpoints[0].processes.some(row => row.role === 'unassigned_tab' && row.pid === 99), true)
  const compared = compareInstalledProcessRoleRss([
    resourceCase(1, 'unavailable', dirty),
    resourceCase(1, 'enabled', wrongRenderer),
  ])
  const enabled = compared.repeats[0].comparisons[1]
  assert.equal(enabled.uncompared_roles.includes('unassigned_tab'), true)
  assert.equal(roleRow(enabled, 'app_main').ownership_blocks_comparison, true)
  assert.equal(roleRow(enabled, 'app_main').compared, false)
  assert.equal(compared.scoped_role_comparison_available, false)
})

test('absent counters stay null and a measured zero stays zero', () => {
  const measured = PHASES.map(phase => sample(phase, 0, { mainPid: 12, rendererPid: 22, creation: 1_700_000_000_002, rendererCreation: 1_700_000_000_102 }))
  measured[2] = observeInstalledProcessCheckpoint({
    phase: PHASES[2],
    mainPid: 12,
    rendererPid: 22,
    windowCount: 1,
    appWindowCount: 1,
    devtoolsPresent: false,
    metrics: [
      metric(12, 'Browser', 1_700_000_000_002, 0),
      { pid: 22, type: 'Tab', creationTime: 1_700_000_000_102, workingSetKilobytes: true },
    ],
  })
  const absent = publicProcessRoleRun(PHASES.map((phase, index) => observeInstalledProcessCheckpoint({
    phase,
    mainPid: 11,
    rendererPid: 21,
    windowCount: 1,
    appWindowCount: 1,
    devtoolsPresent: false,
    metrics: [
      { pid: 11, type: 'Browser', creationTime: 1_700_000_000_000, workingSetKilobytes: index === 2 ? undefined : 100 },
      metric(21, 'Tab', 1_700_000_000_100, 80),
    ],
  })))
  assert.equal(absent.checkpoints[2].processes.find(row => row.role === 'app_main').working_set_bytes, null)
  const compared = compareInstalledProcessRoleRss([
    resourceCase(1, 'unavailable', absent),
    resourceCase(1, 'enabled', publicProcessRoleRun(measured)),
  ])
  const main = roleRow(compared.repeats[0].comparisons[1], 'app_main')
  const renderer = roleRow(compared.repeats[0].comparisons[1], 'app_renderer')
  assert.equal(main.phases[2].baseline_rss_bytes, null)
  assert.equal(main.phases[2].signed_difference_bytes, null)
  assert.equal(main.phases[2].reasons.includes('counter_absent'), true)
  assert.equal(main.compared, false)
  assert.equal(renderer.phases[0].current_rss_bytes, 80 * 1024)
  assert.equal(renderer.phases[2].current_rss_bytes, null)
  assert.equal(main.phases[0].current_rss_bytes, 0)
  assert.equal(main.phases[0].signed_difference_bytes, -100 * 1024)
})

test('hostile strings are dropped and old runs are not rescored as zero', () => {
  const hostile = observeInstalledProcessCheckpoint({
    phase: 'C:\\Users\\secret\\profile',
    mainPid: 11,
    rendererPid: 21,
    windowCount: 1,
    appWindowCount: 1,
    devtoolsPresent: false,
    metrics: [
      { pid: 11, type: 'PRIVATE_RENDERER_MEMORY_CANARY', creationTime: 'PRIVATE_RENDERER_MEMORY_CANARY', workingSetKilobytes: 10, name: 'Audio Service', url: 'http://127.0.0.1/secret', path: 'C:\\Users\\secret\\key.pem' },
      metric(11, 'Browser', 1_700_000_000_000, 10),
      metric(21, 'Tab', 1_700_000_000_100, 10),
    ],
  })
  assert.equal(hostile.phase, null)
  assert.equal(hostile.phase_rejected, true)
  const text = JSON.stringify(publicProcessRoleRun([hostile, ...PHASES.slice(1).map(phase => sample(phase, 10))]))
  for (const secret of ['PRIVATE_RENDERER_MEMORY_CANARY', 'Audio Service', 'http://127.0.0.1/secret', 'C:\\Users\\secret\\key.pem', 'C:\\Users\\secret\\profile']) {
    assert.equal(text.includes(secret), false)
  }
  const old = compareInstalledProcessRoleRss([
    { replicate: 1, condition: 'unavailable', label: 'r1-unavailable' },
    { replicate: 1, condition: 'enabled', label: 'r1-enabled', process_roles: null },
  ])
  assert.equal(old.scoped_role_comparison_available, false)
  assert.equal(old.rescored_without_samples, false)
  assert.equal(old.repeats[0].comparisons[1].samples_present, false)
  assert.equal(old.repeats[0].comparisons[1].rescored, false)
  assert.deepEqual(old.repeats[0].comparisons[1].unmatched_phases, PHASES)
  assert.deepEqual(old.repeats[0].comparisons[1].roles, [])
  const owned = publicOwnedReport({
    launched: true,
    ledger: [{ pid: 4, creation: '10', identity: '4:10', peak_working_set_bytes: 100 }],
    process_roles: { checkpoints: [{ phase: 'before_workspace_connect', processes: [{ role: 'app_main', working_set_bytes: 5 }] }] },
    process_role_rss: { resource_acceptance: true },
  })
  assert.equal(Object.hasOwn(owned, 'process_roles'), false)
  assert.equal(Object.hasOwn(owned, 'process_role_rss'), false)
  assert.equal(owned.resource_acceptance, false)
  assert.equal(owned.budget.status, 'UNACCEPTED')
  assert.equal(owned.budget.compared, false)
  assert.equal(owned.ledger[0].identity, '4:10')
})
