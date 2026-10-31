/** Installed Electron process-role evidence.

Samples come from app.getAppMetrics at the nine workload checkpoints.
Electron creationTime is milliseconds since epoch and is not the operating-system
birth counter used by the native owned-launch ledger. workingSetSize is kilobytes.
*/

export const INSTALLED_PROCESS_CHECKPOINTS = Object.freeze([
  'before_workspace_connect',
  'workspace_connected',
  'first_memory_cycle_and_delivery',
  '8_memory_cycles',
  '16_memory_cycles',
  '32_memory_cycles',
  '64_memory_cycles',
  '96_memory_cycles',
  '128_memory_cycles',
])

const HELPER_ROLES = Object.freeze({
  Utility: 'utility',
  Zygote: 'zygote',
  'Sandbox helper': 'sandbox_helper',
  GPU: 'gpu',
  'Pepper Plugin': 'pepper_plugin',
  'Pepper Plugin Broker': 'pepper_plugin_broker',
  Unknown: 'unknown',
})

const ROLE_SORT = Object.freeze({
  app_main: 0,
  app_renderer: 1,
  utility: 2,
  zygote: 3,
  sandbox_helper: 4,
  gpu: 5,
  pepper_plugin: 6,
  pepper_plugin_broker: 7,
  unknown: 8,
  unassigned_browser: 9,
  unassigned_tab: 10,
})

const MATCHED_ROLES = Object.freeze([
  'app_main',
  'app_renderer',
  'utility',
  'zygote',
  'sandbox_helper',
  'gpu',
  'pepper_plugin',
  'pepper_plugin_broker',
  'unknown',
])

const CONDITIONS = Object.freeze(['unavailable', 'opted_out', 'enabled'])
const PROCESS_CAP = 32
const READ_CAP = 64
const MEMORY_CAP = 2 ** 62
const CREATION_TEXT = /^[0-9]{1,15}(?:\.[0-9]{3})?$/

const SCOPE = [
  'Per-role absolute resident set at the same named checkpoints.',
  'Each repeat compares enabled and opted-out against that repeat\'s unavailable launch.',
  'The first checkpoint is the first observation, not full startup coverage.',
  'Electron creationTime is not the operating-system birth counter and does not cover exited or unseen helpers.',
  'These rows stay separate from the native owned-launch identity ledger.',
  'Matching does not use PID across launches, RSS rank, or helper order.',
  'A scoped result is not process-lifetime acceptance.',
].join(' ')

function plain(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

function pid(value) {
  return Number.isSafeInteger(value) && value > 0 && value < 2 ** 32 ? value : null
}

function boundedCount(value, limit) {
  if (!Number.isSafeInteger(value) || value < 0) return { value: null, capped: false, invalid: true }
  if (value > limit) return { value: limit, capped: true, invalid: false }
  return { value, capped: false, invalid: false }
}

function creationToken(value) {
  if (typeof value === 'string') return CREATION_TEXT.test(value) ? value : null
  if (typeof value !== 'number' || !Number.isFinite(value) || Object.is(value, -0) || value < 0 || value > 1e14) return null
  const text = Number.isSafeInteger(value) ? String(value) : value.toFixed(3)
  return CREATION_TEXT.test(text) ? text : null
}

function rssBytes(value) {
  if (!Number.isSafeInteger(value) || value < 0 || value > MEMORY_CAP) return null
  return value
}

function rssFromKilobytes(value) {
  if (!Number.isSafeInteger(value) || value < 0) return null
  const bytes = value * 1024
  return rssBytes(bytes)
}

function knownPhase(value) {
  return INSTALLED_PROCESS_CHECKPOINTS.includes(value) ? value : null
}

function publicProcess(row) {
  if (!plain(row) || !Object.hasOwn(ROLE_SORT, row.role)) return null
  const processId = pid(row.pid)
  if (processId == null) return null
  const creation = creationToken(row.electron_creation_time_ms)
  return {
    role: row.role,
    pid: processId,
    electron_creation_time_ms: creation,
    identity: creation == null ? null : `${processId}:${creation}`,
    working_set_bytes: rssBytes(row.working_set_bytes),
  }
}

function assignedRole(metric, mainPid, rendererPid) {
  const type = typeof metric.type === 'string' ? metric.type : ''
  if (type === 'Browser' && metric.pid === mainPid) return 'app_main'
  if (type === 'Tab' && rendererPid != null && metric.pid === rendererPid) return 'app_renderer'
  if (Object.hasOwn(HELPER_ROLES, type)) return HELPER_ROLES[type]
  if (type === 'Browser') return 'unassigned_browser'
  if (type === 'Tab') return 'unassigned_tab'
  return null
}

function emptySample(phase, flags) {
  return {
    phase,
    phase_rejected: flags.phase_rejected === true,
    phase_mismatch: flags.phase_mismatch === true,
    missing: flags.missing === true,
    observation_failed: flags.observation_failed === true,
    window_count: null,
    app_window_count: null,
    window_count_capped: false,
    extra_windows: null,
    devtools_present: null,
    app_main_rows: 0,
    app_renderer_rows: 0,
    rejected_rows: 0,
    metrics_overflow: false,
    truncated: false,
    processes: [],
  }
}

function classifyMetrics(metrics, mainPid, rendererPid) {
  const rejected = { value: 0, capped: false }
  const processes = []
  if (!Array.isArray(metrics)) return { processes, rejected: 0, rejected_capped: false, metrics_absent: true, metrics_overflow: false }
  const overflow = metrics.length > READ_CAP
  for (const metric of metrics.slice(0, READ_CAP)) {
    if (!plain(metric)) {
      if (rejected.value < READ_CAP) rejected.value += 1
      else rejected.capped = true
      continue
    }
    const role = assignedRole({ type: metric.type, pid: pid(metric.pid) }, mainPid, rendererPid)
    const drafted = publicProcess({
      role,
      pid: metric.pid,
      electron_creation_time_ms: metric.creationTime,
      working_set_bytes: rssFromKilobytes(metric.workingSetKilobytes),
    })
    if (!drafted) {
      if (rejected.value < READ_CAP) rejected.value += 1
      else rejected.capped = true
      continue
    }
    processes.push(drafted)
  }
  processes.sort((left, right) => ROLE_SORT[left.role] - ROLE_SORT[right.role]
    || left.pid - right.pid
    || String(left.electron_creation_time_ms).localeCompare(String(right.electron_creation_time_ms))
    || (left.working_set_bytes ?? -1) - (right.working_set_bytes ?? -1))
  return {
    processes,
    rejected: rejected.value,
    rejected_capped: rejected.capped,
    metrics_absent: false,
    metrics_overflow: overflow,
  }
}

function finishSample(phase, body) {
  const rows = body.processes.slice(0, PROCESS_CAP)
  const truncated = body.processes.length > PROCESS_CAP || body.metrics_overflow === true || body.rejected_capped === true || body.window_count_capped === true
  const appMain = rows.filter(row => row.role === 'app_main').length
  const appRenderer = rows.filter(row => row.role === 'app_renderer').length
  return {
    phase,
    phase_rejected: false,
    phase_mismatch: false,
    missing: false,
    observation_failed: false,
    window_count: body.window_count,
    app_window_count: body.app_window_count,
    window_count_capped: body.window_count_capped === true,
    extra_windows: body.extra_windows,
    devtools_present: body.devtools_present,
    app_main_rows: appMain,
    app_renderer_rows: appRenderer,
    rejected_rows: body.rejected,
    metrics_overflow: body.metrics_overflow === true,
    truncated,
    processes: rows,
  }
}

export function observeInstalledProcessCheckpoint(input) {
  const source = plain(input) ? input : {}
  const phase = knownPhase(source.phase)
  if (source.observationFailed === true) return { ...emptySample(phase, { phase_rejected: phase == null, observation_failed: true }), observation_failed: true }
  if (phase == null) return emptySample(null, { phase_rejected: true })
  const mainPid = pid(source.mainPid)
  const rendererPid = source.rendererPid == null ? null : pid(source.rendererPid)
  const windows = boundedCount(source.windowCount, READ_CAP)
  const appWindows = boundedCount(source.appWindowCount, READ_CAP)
  const classified = classifyMetrics(source.metrics, mainPid, rendererPid)
  const extra = windows.invalid || appWindows.invalid
    ? null
    : windows.value !== 1 || appWindows.value !== 1
  const devtools = source.devtoolsPresent === true ? true : source.devtoolsPresent === false ? false : null
  return finishSample(phase, {
    window_count: windows.value,
    app_window_count: appWindows.value,
    window_count_capped: windows.capped || appWindows.capped,
    extra_windows: extra,
    devtools_present: devtools,
    ...classified,
  })
}

function resanitizeSample(value, expectedPhase) {
  if (!plain(value)) return emptySample(expectedPhase, { missing: true, phase_mismatch: true })
  // A second allowlist pass must keep an already rejected slot. Rewriting its
  // phase to the expected name would make the mismatch look aligned.
  if (value.phase_mismatch === true || value.missing === true || value.phase_rejected === true) {
    return emptySample(expectedPhase, {
      missing: value.missing === true,
      phase_mismatch: value.phase_mismatch === true || value.phase_rejected === true,
      phase_rejected: value.phase_rejected === true,
      observation_failed: value.observation_failed === true,
    })
  }
  if (value.observation_failed === true) {
    const sample = emptySample(expectedPhase, { observation_failed: true })
    sample.phase_mismatch = knownPhase(value.phase) !== expectedPhase
    return sample
  }
  if (knownPhase(value.phase) !== expectedPhase) return emptySample(expectedPhase, { phase_mismatch: true })
  const processes = []
  let rejected = 0
  const rawProcesses = Array.isArray(value.processes) ? value.processes.slice(0, READ_CAP) : []
  const processOverflow = Array.isArray(value.processes) && value.processes.length > READ_CAP
  for (const row of rawProcesses) {
    const copied = publicProcess(row)
    if (copied) processes.push(copied)
    else if (rejected < READ_CAP) rejected += 1
  }
  const windows = boundedCount(value.window_count, READ_CAP)
  const appWindows = boundedCount(value.app_window_count, READ_CAP)
  const devtools = value.devtools_present === true ? true : value.devtools_present === false ? false : null
  const sample = finishSample(expectedPhase, {
    window_count: windows.value,
    app_window_count: appWindows.value,
    window_count_capped: windows.capped || appWindows.capped,
    extra_windows: windows.invalid || appWindows.invalid ? null : windows.value !== 1 || appWindows.value !== 1,
    devtools_present: devtools,
    processes,
    rejected,
    rejected_capped: rejected >= READ_CAP,
    metrics_absent: false,
    metrics_overflow: value.metrics_overflow === true || processOverflow,
  })
  if (value.phase_rejected === true) sample.phase_rejected = true
  return sample
}

function readyAppRow(sample, role) {
  const rows = sample.processes.filter(row => row.role === role)
  return rows.length === 1 && rows[0].identity != null && Number.isSafeInteger(rows[0].working_set_bytes)
}

function sampleOwnershipValid(sample) {
  if (!sample || sample.missing || sample.phase_mismatch || sample.observation_failed || sample.truncated) return false
  if (sample.rejected_rows !== 0 || sample.metrics_overflow === true) return false
  if (sample.window_count !== 1 || sample.app_window_count !== 1 || sample.extra_windows !== false) return false
  if (sample.devtools_present !== false) return false
  if (!readyAppRow(sample, 'app_main') || !readyAppRow(sample, 'app_renderer')) return false
  return sample.processes.every(row => row.role !== 'unassigned_browser' && row.role !== 'unassigned_tab')
}

export function publicProcessRoleRun(samples) {
  const list = Array.isArray(samples) ? samples : []
  const checkpoints = INSTALLED_PROCESS_CHECKPOINTS.map((phase, index) => {
    if (index >= list.length) return emptySample(phase, { missing: true })
    return resanitizeSample(list[index], phase)
  })
  const present = list.length > 0
  return {
    schema_version: 1,
    present,
    samples_present: present && list.length === INSTALLED_PROCESS_CHECKPOINTS.length && checkpoints.every(sample => sample.missing !== true && sample.phase_mismatch !== true && sample.phase_rejected !== true),
    source: 'electron_app_metrics',
    separate_from_native_ledger: true,
    electron_creation_time_is_os_birth: false,
    covers_exited_or_unseen_helpers: false,
    first_checkpoint_covers_startup: false,
    checkpoint_overflow: list.length > INSTALLED_PROCESS_CHECKPOINTS.length,
    phases_aligned: present && checkpoints.every(sample => sample.phase_mismatch !== true && sample.missing !== true),
    ownership_valid: checkpoints.every(sampleOwnershipValid),
    checkpoints,
  }
}

function slot(run, phase) {
  if (!run || !Array.isArray(run.checkpoints)) return null
  return run.checkpoints.find(sample => sample && sample.phase === phase) ?? null
}

function rowsFor(sample, role) {
  if (!sample || sample.missing || sample.phase_mismatch || sample.observation_failed) return null
  return sample.processes.filter(row => row.role === role)
}

function roleState(run, role) {
  if (!run?.samples_present) return { samplesAbsent: true, ambiguous: false, missing: true, changed: false, identityMissing: true, identity: null }
  let ambiguous = false
  let missing = false
  let identityMissing = false
  const identities = []
  for (const phase of INSTALLED_PROCESS_CHECKPOINTS) {
    const rows = rowsFor(slot(run, phase), role)
    if (rows == null || rows.length === 0) {
      missing = true
      continue
    }
    if (rows.length !== 1) {
      ambiguous = true
      continue
    }
    if (rows[0].identity == null) identityMissing = true
    else identities.push(rows[0].identity)
  }
  const unique = [...new Set(identities)]
  return {
    samplesAbsent: false,
    ambiguous,
    missing,
    changed: unique.length > 1,
    identityMissing: identityMissing || unique.length === 0,
    identity: unique.length === 1 ? unique[0] : null,
  }
}

function rolesSeen(run) {
  const seen = new Set()
  if (!run?.samples_present) return seen
  for (const sample of run.checkpoints) {
    if (!sample || !Array.isArray(sample.processes)) continue
    for (const row of sample.processes) {
      if (MATCHED_ROLES.includes(row.role) || row.role === 'unassigned_browser' || row.role === 'unassigned_tab') seen.add(row.role)
    }
  }
  return seen
}

function compareRole(baseline, current, role) {
  const left = roleState(baseline, role)
  const right = roleState(current, role)
  const ownershipBlocked = baseline?.ownership_valid !== true || current?.ownership_valid !== true
  const phases = []
  for (const phase of INSTALLED_PROCESS_CHECKPOINTS) {
    const baseSample = slot(baseline, phase)
    const currentSample = slot(current, phase)
    const baseRows = rowsFor(baseSample, role)
    const currentRows = rowsFor(currentSample, role)
    const reasons = []
    if (!baseline?.samples_present || !current?.samples_present) reasons.push('samples_absent')
    if (baseSample?.phase_mismatch || currentSample?.phase_mismatch || baseSample?.missing || currentSample?.missing) reasons.push('phase_mismatch')
    if (left.ambiguous || right.ambiguous || (baseRows && baseRows.length > 1) || (currentRows && currentRows.length > 1)) reasons.push('ambiguous')
    if (!reasons.includes('ambiguous') && !reasons.includes('samples_absent') && (baseRows == null || currentRows == null || baseRows.length === 0 || currentRows.length === 0)) reasons.push('missing_role')
    const baseRow = baseRows && baseRows.length === 1 ? baseRows[0] : null
    const currentRow = currentRows && currentRows.length === 1 ? currentRows[0] : null
    if (baseRow && currentRow) {
      if (left.changed || right.changed) reasons.push('identity_changed')
      if (baseRow.identity == null || currentRow.identity == null || left.identityMissing || right.identityMissing) reasons.push('identity_missing')
      if (baseRow.working_set_bytes == null || currentRow.working_set_bytes == null) reasons.push('counter_absent')
    }
    if (ownershipBlocked) reasons.push('ownership_blocked')
    const uniqueReasons = [...new Set(reasons)]
    const blocksNumber = uniqueReasons.some(reason => reason !== 'ownership_blocked')
    const signed = !blocksNumber && baseRow && currentRow
      ? currentRow.working_set_bytes - baseRow.working_set_bytes
      : null
    phases.push({
      phase,
      baseline_row_count: baseRows == null ? null : baseRows.length,
      current_row_count: currentRows == null ? null : currentRows.length,
      baseline_identity: baseRow ? baseRow.identity : null,
      current_identity: currentRow ? currentRow.identity : null,
      baseline_rss_bytes: baseRow ? baseRow.working_set_bytes : null,
      current_rss_bytes: currentRow ? currentRow.working_set_bytes : null,
      signed_difference_bytes: signed,
      reasons: uniqueReasons,
    })
  }
  const matched = phases.filter(phase => Number.isSafeInteger(phase.signed_difference_bytes))
  const comparable = matched.length === INSTALLED_PROCESS_CHECKPOINTS.length
    && !left.ambiguous && !right.ambiguous
    && !left.changed && !right.changed
    && !left.identityMissing && !right.identityMissing
    && !left.missing && !right.missing
    && !ownershipBlocked
    && baseline?.samples_present === true
    && current?.samples_present === true
  return {
    role,
    compared: comparable,
    ambiguous: left.ambiguous || right.ambiguous,
    missing: left.missing || right.missing,
    identity_changed_within_run: left.changed || right.changed,
    identity_missing: left.identityMissing || right.identityMissing,
    baseline_identity: left.identity,
    current_identity: right.identity,
    ownership_blocks_comparison: ownershipBlocked,
    phases,
    first_observed_difference_bytes: phases[0] ? phases[0].signed_difference_bytes : null,
    maximum_matched_phase_difference_bytes: matched.length ? Math.max(...matched.map(phase => phase.signed_difference_bytes)) : null,
    all_phases_matched: comparable,
  }
}

function caseIdentity(row) {
  if (!plain(row)) return null
  if (row.replicate !== 1 && row.replicate !== 2) return null
  if (!CONDITIONS.includes(row.condition)) return null
  return `${row.replicate}:${row.condition}`
}

function runFromCase(row) {
  if (!plain(row) || !Object.hasOwn(row, 'process_roles')) return publicProcessRoleRun(undefined)
  const value = row.process_roles
  if (Array.isArray(value)) return publicProcessRoleRun(value)
  if (plain(value) && Array.isArray(value.checkpoints)) return publicProcessRoleRun(value.checkpoints)
  return publicProcessRoleRun(undefined)
}

export function compareInstalledProcessRoleRss(cases) {
  const list = Array.isArray(cases) ? cases.slice(0, 16) : []
  const grouped = new Map()
  let unrecognized = 0
  for (const row of list) {
    const key = caseIdentity(row)
    if (key == null) {
      if (unrecognized < READ_CAP) unrecognized += 1
      continue
    }
    const found = grouped.get(key)
    if (found) found.push(row)
    else grouped.set(key, [row])
  }
  const repeats = [1, 2].map(replicate => {
    const baselineKey = `${replicate}:unavailable`
    const baselineRows = grouped.get(baselineKey) ?? []
    const baseline = baselineRows.length === 1 ? runFromCase(baselineRows[0]) : publicProcessRoleRun(undefined)
    return {
      replicate,
      baseline_condition: 'unavailable',
      baseline_present: baselineRows.length === 1,
      baseline_ambiguous: baselineRows.length > 1,
      comparisons: ['opted_out', 'enabled'].map(condition => {
        const rows = grouped.get(`${replicate}:${condition}`) ?? []
        const current = rows.length === 1 ? runFromCase(rows[0]) : publicProcessRoleRun(undefined)
        const seen = new Set([...rolesSeen(baseline), ...rolesSeen(current)])
        const roles = MATCHED_ROLES.filter(role => seen.has(role)).map(role => compareRole(baseline, current, role))
        const unmatchedPhases = INSTALLED_PROCESS_CHECKPOINTS.filter(phase => {
          const left = slot(baseline, phase)
          const right = slot(current, phase)
          return !left || !right || left.missing || right.missing || left.phase_mismatch || right.phase_mismatch
        })
        return {
          condition,
          case_present: rows.length === 1,
          case_ambiguous: rows.length > 1,
          samples_present: baseline.samples_present === true && current.samples_present === true,
          rescored: false,
          phases_aligned: baseline.phases_aligned === true && current.phases_aligned === true && unmatchedPhases.length === 0,
          unmatched_phases: unmatchedPhases,
          ambiguous_roles: roles.filter(role => role.ambiguous).map(role => role.role),
          missing_roles: roles.filter(role => role.missing).map(role => role.role),
          uncompared_roles: ['unassigned_browser', 'unassigned_tab'].filter(role => seen.has(role)),
          roles,
        }
      }),
    }
  })
  const scoped = repeats.every(repeat => repeat.baseline_present && !repeat.baseline_ambiguous && repeat.comparisons.every(comparison => {
    if (!comparison.case_present || comparison.case_ambiguous || !comparison.samples_present) return false
    const main = comparison.roles.find(role => role.role === 'app_main')
    const renderer = comparison.roles.find(role => role.role === 'app_renderer')
    return main?.compared === true && renderer?.compared === true
  }))
  return {
    schema_version: 1,
    kind: 'per_role_matched_phase_absolute_rss',
    resource_acceptance: false,
    scoped_role_comparison_available: scoped,
    rescored_without_samples: false,
    initial_rss_subtracted: false,
    aligned_by_pid_across_runs: false,
    aligned_by_rss_rank: false,
    electron_creation_time_is_os_birth: false,
    covers_exited_or_unseen_helpers: false,
    first_checkpoint_covers_startup: false,
    separate_from_native_ledger: true,
    unrecognized_cases: unrecognized,
    case_overflow: Array.isArray(cases) && cases.length > 16,
    repeats,
    budget: {
      additional_rss_bytes_per_process: 8388608,
      cpu_one_core_fraction: 0.005,
      status: 'UNACCEPTED',
      compared: false,
    },
    scope: SCOPE,
  }
}
