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

function publishTwice(samples) {
  const once = publicProcessRoleRun(samples)
  const twice = publicProcessRoleRun(once.checkpoints)
  return { once, twice }
}

function assertUnqualified(published) {
  const compared = compareInstalledProcessRoleRss([
    resourceCase(1, 'unavailable', published),
    resourceCase(1, 'opted_out', run(110)),
    resourceCase(1, 'enabled', run(120)),
  ])
  assert.equal(compared.resource_acceptance, false)
  assert.equal(compared.scoped_role_comparison_available, false)
  assert.equal(compared.budget.status, 'UNACCEPTED')
  assert.equal(compared.budget.compared, false)
  assert.equal(compared.budget.additional_rss_bytes_per_process, 8_388_608)
  assert.equal(compared.budget.cpu_one_core_fraction, 0.005)
  const main = roleRow(compared.repeats[0].comparisons[0], 'app_main')
  assert.equal(main.compared, false)
  assert.equal(main.ownership_blocks_comparison, true)
  return compared
}

test('repeated publication keeps rejection, truncation, and capping unqualified', () => {
  const rejectedCanary = 'PRIVATE_REJECTED_ROW_CANARY'
  const observed = PHASES.map((phase, index) => index === 0
    ? sample(phase, 100, { extra: [{ pid: 50, type: 'Audio Service', creationTime: 1_700_000_000_500, workingSetKilobytes: 3, name: rejectedCanary, url: 'http://127.0.0.1/rejected-row' }] })
    : sample(phase, 100))
  assert.equal(observed[0].rejected_rows, 1)
  assert.equal(observed[0].truncated, false)
  const rejected = publishTwice(observed)
  for (const published of [rejected.once, rejected.twice]) {
    assert.equal(published.checkpoints[0].rejected_rows, 1)
    assert.equal(published.checkpoints[0].truncated, false)
    assert.equal(published.checkpoints[0].processes.length, 2)
    assert.equal(published.ownership_valid, false)
  }
  const rejectedText = JSON.stringify(rejected.twice) + JSON.stringify(assertUnqualified(rejected.twice))
  assert.equal(rejectedText.includes(rejectedCanary), false)
  assert.equal(rejectedText.includes('http://127.0.0.1/rejected-row'), false)
  assert.equal(rejectedText.includes('Audio Service'), false)

  const wide = PHASES.map(phase => sample(phase, 100, {
    extra: Array.from({ length: 33 }, (_, index) => metric(1_000 + index, 'Utility', 1_700_000_000_000 + index, 1)),
  }))
  assert.equal(wide[0].truncated, true)
  assert.equal(wide[0].processes.length, 32)
  assert.equal(wide[0].metrics_overflow, false)
  const truncated = publishTwice(wide)
  for (const published of [truncated.once, truncated.twice]) {
    const checkpoint = published.checkpoints[0]
    assert.equal(checkpoint.truncated, true)
    assert.equal(checkpoint.rejected_rows, 0)
    assert.equal(checkpoint.processes.length, 32)
    assert.equal(checkpoint.processes.some(row => row.pid === 11 && row.role === 'app_main'), true)
    assert.equal(checkpoint.processes.some(row => row.pid === 1_000), true)
    assert.equal(checkpoint.processes.some(row => row.pid === 1_032), false)
    assert.equal(published.ownership_valid, false)
  }
  assertUnqualified(truncated.twice)

  const capped = publishTwice(PHASES.map(phase => sample(phase, 100, { windowCount: 65 })))
  for (const published of [capped.once, capped.twice]) {
    assert.equal(published.checkpoints[0].window_count, 64)
    assert.equal(published.checkpoints[0].window_count_capped, true)
    assert.equal(published.checkpoints[0].truncated, true)
    assert.equal(published.ownership_valid, false)
  }

  const inflated = rejected.once.checkpoints.map(checkpoint => ({ ...checkpoint, rejected_rows: 1e20, private_note: rejectedCanary }))
  const bounded = publicProcessRoleRun(inflated)
  assert.equal(bounded.checkpoints[0].rejected_rows, 64)
  assert.equal(bounded.checkpoints[0].truncated, true)
  assert.equal(bounded.ownership_valid, false)
  assert.equal(JSON.stringify(bounded).includes(rejectedCanary), false)
  assert.equal(JSON.stringify(bounded).includes('1e+20'), false)
})

test('a zero or non-canonical birth never becomes an identity', () => {
  const zero = publishTwice(PHASES.map(phase => sample(phase, 100, { creation: 0, rendererCreation: 0 })))
  for (const published of [zero.once, zero.twice]) {
    assert.equal(published.ownership_valid, false)
    assert.equal(published.checkpoints.every(checkpoint => checkpoint.processes.every(row => row.identity == null && row.electron_creation_time_ms == null)), true)
  }
  const zeroCompared = compareInstalledProcessRoleRss([
    resourceCase(1, 'unavailable', zero.twice),
    resourceCase(1, 'opted_out', run(100, { creation: 0, rendererCreation: 0 })),
    resourceCase(1, 'enabled', run(110, { creation: 0, rendererCreation: 0 })),
  ])
  assert.equal(zeroCompared.scoped_role_comparison_available, false)
  assert.equal(zeroCompared.resource_acceptance, false)
  assert.equal(roleRow(zeroCompared.repeats[0].comparisons[0], 'app_main').compared, false)
  assert.equal(roleRow(zeroCompared.repeats[0].comparisons[1], 'app_main').compared, false)
  assert.equal(JSON.stringify(zeroCompared).includes('11:0'), false)

  const unavailableBirths = [-0, 1e15, Number.POSITIVE_INFINITY]
  for (const birth of unavailableBirths) {
    const checkpoint = sample(PHASES[0], 100, { creation: birth, rendererCreation: birth })
    assert.equal(checkpoint.processes.every(row => row.identity == null), true)
  }

  const forged = run(100)
  for (const token of ['0', '0001', '1.230', '1.000', '1e14', '100000000000001']) {
    const rewritten = publicProcessRoleRun(forged.checkpoints.map(checkpoint => ({
      ...checkpoint,
      processes: checkpoint.processes.map(row => ({
        ...row,
        electron_creation_time_ms: token,
        identity: `forged:${token}`,
      })),
    })))
    const again = publicProcessRoleRun(rewritten.checkpoints)
    for (const published of [rewritten, again]) {
      assert.equal(published.ownership_valid, false)
      assert.equal(published.checkpoints[0].processes.every(row => row.identity == null && row.electron_creation_time_ms == null), true)
      const text = JSON.stringify(published)
      assert.equal(text.includes(`forged:${token}`), false)
      assert.equal(text.includes(`"${token}"`), false)
    }
  }

  const exact = publicProcessRoleRun(forged.checkpoints.map(checkpoint => ({
    ...checkpoint,
    processes: checkpoint.processes.map(row => ({
      ...row,
      electron_creation_time_ms: '1700000000000',
      identity: 'forged:1700000000000',
    })),
  })))
  const exactAgain = publicProcessRoleRun(exact.checkpoints)
  assert.equal(exact.ownership_valid, true)
  assert.equal(exactAgain.ownership_valid, true)
  assert.equal(exactAgain.checkpoints[0].processes.find(row => row.role === 'app_main').identity, '11:1700000000000')
  assert.equal(exactAgain.checkpoints[0].processes.find(row => row.role === 'app_renderer').identity, '21:1700000000000')
  assert.equal(JSON.stringify(exactAgain).includes('forged:'), false)

  assert.equal((1.2341).toFixed(3), (1.2344).toFixed(3))
  const shifted = publishTwice(PHASES.map((phase, index) => sample(phase, 100, {
    creation: index < 4 ? 1.2341 : 1.2344,
    rendererCreation: 1_700_000_000_100,
  })))
  assert.equal(shifted.twice.checkpoints[0].processes.find(row => row.role === 'app_main').identity, '11:1.2341')
  assert.equal(shifted.twice.checkpoints[4].processes.find(row => row.role === 'app_main').identity, '11:1.2344')
  const shiftCompared = compareInstalledProcessRoleRss([
    resourceCase(1, 'unavailable', shifted.twice),
    resourceCase(1, 'enabled', run(130, { mainPid: 15, rendererPid: 25, creation: 1_710_000_000_000, rendererCreation: 1_710_000_000_100 })),
  ])
  const shiftedMain = roleRow(shiftCompared.repeats[0].comparisons[1], 'app_main')
  assert.equal(shiftedMain.identity_changed_within_run, true)
  assert.equal(shiftedMain.compared, false)
  assert.equal(shiftedMain.phases[0].signed_difference_bytes, null)
  assert.equal(shiftedMain.phases[0].reasons.includes('identity_changed'), true)
  assert.equal(shiftCompared.resource_acceptance, false)
})

test('a shared main and renderer PID stays explicit and unqualified', () => {
  const shared = publishTwice(PHASES.map(phase => sample(phase, 100, {
    mainPid: 11,
    rendererPid: 11,
    creation: 1_700_000_000_000,
    rendererCreation: 1_700_000_000_100,
  })))
  for (const published of [shared.once, shared.twice]) {
    const checkpoint = published.checkpoints[0]
    assert.equal(checkpoint.duplicate_identity, true)
    assert.equal(checkpoint.truncated, false)
    assert.equal(checkpoint.rejected_rows, 0)
    assert.equal(checkpoint.app_main_rows, 1)
    assert.equal(checkpoint.app_renderer_rows, 1)
    assert.equal(checkpoint.processes.filter(row => row.pid === 11).length, 2)
    assert.equal(published.ownership_valid, false)
  }
  const compared = assertUnqualified(shared.twice)
  assert.equal(JSON.stringify(compared).includes('11:1700000000000'), true)
  const stripped = publicProcessRoleRun(shared.once.checkpoints.map(checkpoint => ({
    ...checkpoint,
    processes: checkpoint.processes.filter(row => row.role === 'app_main'),
  })))
  assert.equal(stripped.checkpoints[0].duplicate_identity, true)
  assert.equal(stripped.checkpoints[0].processes.length, 1)
  assert.equal(stripped.ownership_valid, false)
})

test('a tenth checkpoint stays overflowed through comparison and republication', () => {
  const extra = sample(PHASES[0], 100)
  extra.private_note = 'PRIVATE_CHECKPOINT_OVERFLOW_CANARY'
  const published = publicProcessRoleRun([...PHASES.map(phase => sample(phase, 100)), extra])
  assert.equal(published.checkpoint_overflow, true)
  assert.equal(published.samples_present, false)
  assert.equal(published.ownership_valid, false)
  assert.equal(published.checkpoints.length, 9)
  assert.equal(published.checkpoints[0].checkpoint_overflow, true)
  assert.equal(published.checkpoints[0].processes.find(row => row.role === 'app_main').working_set_bytes, 100 * 1024)
  for (const republished of [publicProcessRoleRun(published), publicProcessRoleRun(published.checkpoints)]) {
    assert.equal(republished.checkpoint_overflow, true)
    assert.equal(republished.samples_present, false)
    assert.equal(republished.ownership_valid, false)
    assert.equal(republished.checkpoints.length, 9)
    assert.equal(republished.checkpoints[8].processes.find(row => row.role === 'app_main').working_set_bytes, 100 * 1024)
  }
  const compared = compareInstalledProcessRoleRss([1, 2].flatMap(replicate =>
    ['unavailable', 'opted_out', 'enabled'].map(condition => resourceCase(replicate, condition, published)),
  ))
  assert.equal(compared.scoped_role_comparison_available, false)
  assert.equal(compared.resource_acceptance, false)
  assert.equal(compared.budget.status, 'UNACCEPTED')
  assert.equal(compared.budget.compared, false)
  assert.equal(compared.budget.additional_rss_bytes_per_process, 8_388_608)
  assert.equal(compared.budget.cpu_one_core_fraction, 0.005)
  assert.equal(compared.repeats.every(repeat => repeat.comparisons.every(row => row.samples_present === false && row.checkpoint_overflow === true && row.roles.every(role => role.compared === false))), true)
  const text = JSON.stringify(published) + JSON.stringify(compared)
  assert.equal(text.includes('PRIVATE_CHECKPOINT_OVERFLOW_CANARY'), false)
})
