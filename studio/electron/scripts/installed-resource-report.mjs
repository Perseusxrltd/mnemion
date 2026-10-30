/** Allowlisted owned-launch evidence and the single-product package order. */

const TOKEN = /^[A-Za-z0-9_.:-]{1,80}$/
const IDENTITY = /^[0-9]{1,10}:[0-9]{1,20}$/
const FRACTION = /^[0-9]{1,6}\.[0-9]{6}$/
const HEX50 = /^[0-9a-f]{50}$/

function token(value) {
  return typeof value === 'string' && TOKEN.test(value) ? value : null
}

function count(value, limit = Number.MAX_SAFE_INTEGER) {
  return Number.isInteger(value) && value >= 0 && value <= limit ? value : null
}

function flag(value) {
  return typeof value === 'boolean' ? value : null
}

function memory(value) {
  return count(value, 2 ** 62)
}

function ledgerRow(row) {
  if (!row || typeof row !== 'object') return null
  const pid = row.pid
  const creation = row.creation
  if (!Number.isInteger(pid) || pid <= 0 || pid >= 2 ** 32) return null
  if (typeof creation !== 'string' || !/^[0-9]{1,20}$/.test(creation)) return null
  const identity = `${pid}:${creation}`
  if (row.identity !== identity) return null
  return {
    pid,
    creation,
    identity,
    peak_working_set_bytes: row.peak_working_set_bytes == null ? null : memory(row.peak_working_set_bytes),
    first_working_set_bytes: row.first_working_set_bytes == null ? null : memory(row.first_working_set_bytes),
    last_working_set_bytes: row.last_working_set_bytes == null ? null : memory(row.last_working_set_bytes),
    kernel_high_water_while_observed: row.kernel_high_water_while_observed === true,
  }
}

function coverage(value) {
  const source = value && typeof value === 'object' ? value : {}
  const text = {}
  for (const key of ['platform', 'status', 'rss_high_water', 'process_lifetime_count']) {
    text[key] = token(source[key])
  }
  for (const key of [
    'cpu_lifetime_complete', 'cpu_includes_exited_descendants', 'sampled_pid_cpu_is_complete',
    'rss_high_water_covers_unseen_exited_processes', 'cgroup_memory_peak_is_per_process_rss',
  ]) text[key] = flag(source[key])
  return text
}

function numericObject(source, ints, flags) {
  if (!source || typeof source !== 'object') return null
  const copy = {}
  for (const key of ints) copy[key] = source[key] == null ? null : memory(source[key])
  for (const key of flags) copy[key] = flag(source[key])
  return copy
}

export function publicOwnedReport(report) {
  const executable = report?.observer?.executable
  const rows = Array.isArray(report?.ledger) ? report.ledger.map(ledgerRow).filter(Boolean).slice(0, 512) : []
  const coldProcesses = Array.isArray(report?.cold_start?.processes)
    ? report.cold_start.processes.filter(row => row && IDENTITY.test(row.identity || '') && Number.isInteger(row.working_set_bytes) && row.working_set_bytes >= 0)
      .slice(0, 512)
      .map(row => ({ identity: row.identity, working_set_bytes: row.working_set_bytes }))
    : []
  const unavailable = Array.isArray(report?.unavailable_counters)
    ? report.unavailable_counters.filter(name => token(name)).slice(0, 32)
    : []
  const phases = Array.isArray(report?.phases) ? report.phases.filter(phase => phase && typeof phase.name === 'string' && token(phase.name)).slice(0, 64).map(phase => ({
    name: phase.name,
    active: flag(phase.active),
    cpu_microseconds: phase.cpu_microseconds == null ? null : count(phase.cpu_microseconds),
    start_offset_ns: phase.start_offset_ns == null ? null : count(phase.start_offset_ns),
    end_offset_ns: phase.end_offset_ns == null ? null : count(phase.end_offset_ns),
    canonical_operations_at_start: phase.canonical_operations_at_start == null ? null : count(phase.canonical_operations_at_start, 1000000),
    canonical_operations_at_end: phase.canonical_operations_at_end == null ? null : count(phase.canonical_operations_at_end, 1000000),
  })) : []
  const bounds = report?.bounds && typeof report.bounds === 'object' ? report.bounds : {}
  const sampleSeconds = typeof bounds.sample_seconds === 'number' && Number.isFinite(bounds.sample_seconds) && bounds.sample_seconds > 0 && bounds.sample_seconds <= 1
    ? bounds.sample_seconds : null
  const lifetimeCap = typeof bounds.lifetime_seconds_cap === 'number' && Number.isFinite(bounds.lifetime_seconds_cap) && bounds.lifetime_seconds_cap > 0 && bounds.lifetime_seconds_cap <= 120
    ? bounds.lifetime_seconds_cap : null
  const fraction = typeof report?.active_core_fraction === 'string' && FRACTION.test(report.active_core_fraction)
    ? report.active_core_fraction : null
  return {
    qualification: 'unqualified',
    resource_acceptance: false,
    launched: report?.launched !== false && !report?.honest_unsupported,
    honest_unsupported: token(report?.honest_unsupported),
    canonical_operations_completed: count(report?.canonical_operations_completed, 1000000),
    canonical_operations_known: flag(report?.canonical_operations_known),
    hosting_ready: report?.hosting_ready === true,
    root_exit_code: Number.isInteger(report?.root_exit_code) ? report.root_exit_code : null,
    failure_stage: token(report?.failure_stage),
    delivery_diagnostics_enabled: report?.delivery_diagnostics_enabled === true,
    platform_method: token(report?.platform_method),
    lifetime_cpu_microseconds: report?.lifetime_cpu_microseconds == null ? null : count(report.lifetime_cpu_microseconds),
    active_cpu_microseconds: report?.active_cpu_microseconds == null ? null : count(report.active_cpu_microseconds),
    active_wall_microseconds: report?.active_wall_microseconds == null ? null : count(report.active_wall_microseconds),
    active_core_fraction: fraction,
    identities_missing: report?.identities_missing == null ? null : count(report.identities_missing),
    missing_recorded_as_zero: false,
    observation_error: token(report?.observation_error),
    marker_applied: report?.marker_applied === false ? false : null,
    coverage: coverage(report?.coverage),
    unavailable_counters: unavailable,
    cold_start: {
      kind: report?.cold_start?.kind === 'first_observed_absolute' ? 'first_observed_absolute' : null,
      subtracted: flag(report?.cold_start?.subtracted),
      processes: coldProcesses,
    },
    ledger: rows,
    ledger_truncated: flag(report?.ledger_truncated),
    sampled_peaks: numericObject(report?.sampled_peaks, ['sum_working_set_bytes'], ['sum_double_counts_shared', 'not_a_budget_measurement', 'sampled_pid_cpu_is_complete']),
    kernel: numericObject(
      report?.kernel,
      ['total_user_100ns', 'total_kernel_100ns', 'total_processes', 'active_processes', 'processes_no_longer_active', 'terminated_by_limit', 'peak_process_commit_bytes', 'peak_job_commit_bytes', 'cpu_usage_usec', 'cgroup_memory_peak_bytes', 'wait4_direct_child_cpu_microseconds'],
      ['commit_counters_are_working_set', 'cpu_usage_includes_descendant_cgroups', 'cgroup_memory_peak_is_per_process_rss', 'includes_only_reaped_descendants', 'footprint_used_as_rss'],
    ),
    observer_in_measured_group: flag(report?.observer_in_measured_group),
    cleanup: report?.cleanup && typeof report.cleanup === 'object'
      ? {
        ok: flag(report.cleanup.ok),
        failure: token(report.cleanup.failure),
        retried: report.cleanup.retried === true,
        terminated_owned_group: flag(report.cleanup.terminated_owned_group),
      }
      : { ok: false, failure: null, retried: false, terminated_owned_group: null },
    phases,
    bounds: {
      lifetime_seconds_cap: lifetimeCap,
      timed_out: flag(bounds.timed_out),
      sample_seconds: sampleSeconds,
      sample_truncated: flag(bounds.sample_truncated),
      sample_error: token(bounds.sample_error),
    },
    budget: {
      additional_rss_bytes_per_process: 8388608,
      cpu_one_core_fraction: 0.005,
      status: 'UNACCEPTED',
      compared: false,
    },
    observer: typeof executable === 'string' && token(executable) && !executable.includes('/') && !executable.includes('\\') ? { executable } : {},
  }
}

export function resourceInstallSteps(cases) {
  const steps = [{ action: 'refuse-preexisting' }]
  let current = null
  let nextId = 1
  for (const row of cases) {
    if (!current || current.package !== row.package) {
      if (current) steps.push({ action: 'uninstall', id: current.id, package: current.package })
      const id = nextId++
      steps.push({ action: 'install', id, package: row.package, refuseExisting: true })
      current = { id, package: row.package }
    }
    steps.push({ action: 'use', label: row.label, id: current.id, package: row.package })
  }
  if (current) steps.push({ action: 'uninstall', id: current.id, package: current.package })
  return steps
}

export async function performOwnedInstall(installations, record, actions) {
  if (!record || !Number.isInteger(record.id) || typeof record.directory !== 'string' || record.directory.length === 0 ||
      typeof record.package !== 'string' || !actions) {
    throw new Error('resource_install_invalid')
  }
  await actions.refusePreexisting()
  const owned = { id: record.id, directory: record.directory, package: record.package, state: 'allocated' }
  installations.push(owned)
  try {
    await actions.installProduct(owned)
  } catch (error) {
    owned.state = 'installer_failed'
    throw error
  }
  owned.state = 'installed'
  try {
    const result = await actions.verify(owned)
    owned.state = 'verified'
    return result
  } catch (error) {
    owned.state = 'verification_failed'
    throw error
  }
}

export function finishResourceCleanup(pending, removedIds, retire) {
  const failures = []
  for (const item of pending) {
    if (removedIds.has(item.id)) continue
    try { retire(item) }
    catch { failures.push('uninstall_failed') }
  }
  return failures
}

export function resourceCaseStoreReady(row, store) {
  if (!store || store.fixture_content_absent !== true) return false
  if (!Number.isInteger(store.attempts) || !Number.isInteger(store.reserved_bytes)) return false
  if (row?.enabled === true) {
    return store.present === true && store.attempts === 1 && store.reserved_bytes === 65536
  }
  if (row?.condition === 'unavailable') {
    return store.present === false && store.attempts === 0 && store.reserved_bytes === 0
  }
  if (row?.condition === 'opted_out') return store.attempts === 0 && store.reserved_bytes === 0
  return false
}

export function inspectedBodyHex(value) {
  return typeof value === 'string' && HEX50.test(value) ? value : null
}
