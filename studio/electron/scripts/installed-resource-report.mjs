import { verifyNativeResources } from './native-resources.mjs'

/** Allowlisted owned-launch evidence and the single-product package order. */

const TOKEN = /^[A-Za-z0-9_.:-]{1,80}$/
const STARTUP_FAILURE_CATEGORIES = new Set([
  'isolated_profile', 'invalid_resource_config', 'invalid_hosting_config', 'non_loopback_destination',
  'session_connection', 'workspace_bridge', 'workspace_handle', 'memory_client', 'not_packaged',
  'memory_save', 'memory_fetch', 'memory_recall', 'workload_incomplete', 'delivery_settlement',
  'private_evidence', 'disposable_profile', 'unclassified',
])
const MNEMION_PRODUCT = /^Mnemion Studio/
const IDENTITY = /^[0-9]{1,10}:[0-9]{1,20}$/
const FRACTION = /^[0-9]{1,6}\.[0-9]{6}$/
const HEX50 = /^[0-9a-f]{50}$/

function token(value) {
  return typeof value === 'string' && TOKEN.test(value) ? value : null
}

function failureCategory(report) {
  if (token(report?.failure_stage) !== 'startup-error') return null
  return STARTUP_FAILURE_CATEGORIES.has(report?.failure_category) ? report.failure_category : null
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

function absentOwnedReport(withheld = false) {
  const report = {
    present: false,
    launched: null,
    resource_acceptance: false,
    qualification: 'unqualified',
    missing_recorded_as_zero: false,
  }
  if (withheld) report.private_content_withheld = true
  return report
}

function plainReport(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

function hasCount(value) {
  return plainReport(value) && Object.values(value).some(item => Number.isInteger(item))
}

export function publicOwnedReport(report) {
  if (!plainReport(report)) return absentOwnedReport()
  if (report.private_content_withheld === true) return absentOwnedReport(true)
  const executable = report.observer?.executable
  const rows = Array.isArray(report.ledger) ? report.ledger.map(ledgerRow).filter(Boolean).slice(0, 512) : []
  const coldProcesses = Array.isArray(report.cold_start?.processes)
    ? report.cold_start.processes.filter(row => row && IDENTITY.test(row.identity || '') && Number.isInteger(row.working_set_bytes) && row.working_set_bytes >= 0)
      .slice(0, 512)
      .map(row => ({ identity: row.identity, working_set_bytes: row.working_set_bytes }))
    : []
  const unavailable = Array.isArray(report.unavailable_counters)
    ? report.unavailable_counters.filter(name => token(name)).slice(0, 32)
    : []
  const phases = Array.isArray(report.phases) ? report.phases.filter(phase => phase && typeof phase.name === 'string' && token(phase.name)).slice(0, 64).map(phase => ({
    name: phase.name,
    active: flag(phase.active),
    cpu_microseconds: phase.cpu_microseconds == null ? null : count(phase.cpu_microseconds),
    start_offset_ns: phase.start_offset_ns == null ? null : count(phase.start_offset_ns),
    end_offset_ns: phase.end_offset_ns == null ? null : count(phase.end_offset_ns),
    canonical_operations_at_start: phase.canonical_operations_at_start == null ? null : count(phase.canonical_operations_at_start, 1000000),
    canonical_operations_at_end: phase.canonical_operations_at_end == null ? null : count(phase.canonical_operations_at_end, 1000000),
  })) : []
  const bounds = plainReport(report.bounds) ? report.bounds : {}
  const sampleSeconds = typeof bounds.sample_seconds === 'number' && Number.isFinite(bounds.sample_seconds) && bounds.sample_seconds > 0 && bounds.sample_seconds <= 1
    ? bounds.sample_seconds : null
  const lifetimeCap = typeof bounds.lifetime_seconds_cap === 'number' && Number.isFinite(bounds.lifetime_seconds_cap) && bounds.lifetime_seconds_cap > 0 && bounds.lifetime_seconds_cap <= 120
    ? bounds.lifetime_seconds_cap : null
  const fraction = typeof report.active_core_fraction === 'string' && FRACTION.test(report.active_core_fraction)
    ? report.active_core_fraction : null
  const lifetime = report.lifetime_cpu_microseconds == null ? null : count(report.lifetime_cpu_microseconds)
  const activeCpu = report.active_cpu_microseconds == null ? null : count(report.active_cpu_microseconds)
  const activeWall = report.active_wall_microseconds == null ? null : count(report.active_wall_microseconds)
  const identitiesMissing = report.identities_missing == null ? null : count(report.identities_missing)
  const copiedCoverage = coverage(report.coverage)
  const copiedKernel = numericObject(
    report.kernel,
    ['total_user_100ns', 'total_kernel_100ns', 'total_processes', 'active_processes', 'processes_no_longer_active', 'terminated_by_limit', 'peak_process_commit_bytes', 'peak_job_commit_bytes', 'cpu_usage_usec', 'cgroup_memory_peak_bytes', 'wait4_direct_child_cpu_microseconds'],
    ['commit_counters_are_working_set', 'cpu_usage_includes_descendant_cgroups', 'cgroup_memory_peak_is_per_process_rss', 'includes_only_reaped_descendants', 'footprint_used_as_rss'],
  )
  const copiedPeaks = numericObject(report.sampled_peaks, ['sum_working_set_bytes'], ['sum_double_counts_shared', 'not_a_budget_measurement', 'sampled_pid_cpu_is_complete'])
  const unsupported = token(report.honest_unsupported)
  const explicitLaunch = flag(report.launched)
  const cleanup = plainReport(report.cleanup) ? report.cleanup : null
  const cleanupFailure = cleanup ? token(cleanup.failure) : null
  const cleanupOk = cleanup ? flag(cleanup.ok) : null
  const cleanupTerminated = cleanup ? flag(cleanup.terminated_owned_group) : null
  const platformMethod = token(report.platform_method)
  const canonicalCompleted = count(report.canonical_operations_completed, 1000000)
  const canonicalKnown = flag(report.canonical_operations_known)
  const observationError = token(report.observation_error)
  const markerApplied = report.marker_applied === false ? false : null
  const observerFlag = flag(report.observer_in_measured_group)
  const coldKind = report.cold_start?.kind === 'first_observed_absolute' ? 'first_observed_absolute' : null
  const coldSubtracted = flag(report.cold_start?.subtracted)
  const ledgerTruncated = flag(report.ledger_truncated)
  const timedOut = flag(bounds.timed_out)
  const sampleTruncated = flag(bounds.sample_truncated)
  const sampleError = token(bounds.sample_error)
  const processEvidence = Boolean(
    rows.length || coldProcesses.length || lifetime !== null || activeCpu !== null || activeWall !== null
    || identitiesMissing !== null || fraction !== null || hasCount(copiedPeaks) || hasCount(copiedKernel),
  )
  const independent = Boolean(
    processEvidence || platformMethod || Object.values(copiedCoverage).some(item => item !== null) || phases.length
    || coldKind || coldSubtracted !== null || canonicalCompleted !== null || canonicalKnown !== null
    || unavailable.length || cleanupFailure || cleanupOk === true || cleanupTerminated !== null
    || (cleanup && cleanup.retried === true) || observerFlag !== null || observationError
    || markerApplied === false || unsupported || ledgerTruncated !== null
    || lifetimeCap !== null || timedOut !== null || sampleSeconds !== null || sampleTruncated !== null
    || sampleError || (copiedPeaks && Object.values(copiedPeaks).some(item => item !== null))
    || (copiedKernel && Object.values(copiedKernel).some(item => item !== null)),
  )
  if (report.present === false && !independent) return absentOwnedReport()
  let launched = null
  if (unsupported || explicitLaunch === false) launched = false
  else if (explicitLaunch === true) launched = true
  else if (processEvidence) launched = true
  const present = independent || explicitLaunch !== null || Boolean(unsupported)
  if (!present) return absentOwnedReport()
  return {
    qualification: 'unqualified',
    resource_acceptance: false,
    present,
    launched,
    honest_unsupported: unsupported,
    canonical_operations_completed: count(report?.canonical_operations_completed, 1000000),
    canonical_operations_known: flag(report?.canonical_operations_known),
    hosting_ready: report?.hosting_ready === true,
    root_exit_code: Number.isInteger(report?.root_exit_code) ? report.root_exit_code : null,
    failure_stage: token(report?.failure_stage),
    failure_category: failureCategory(report),
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

export function resourceVerificationRoot(manifest, packageName) {
  if (packageName !== 'inactive' && packageName !== 'active') {
    throw new Error('Resource package preparation is missing')
  }
  const sourceRoot = manifest?.packages?.[packageName]?.source_root
  if (typeof sourceRoot !== 'string' || sourceRoot.length === 0) {
    throw new Error('Resource package preparation is missing')
  }
  return sourceRoot
}

export function verifyPreparedPackage(manifest, packageName, resources) {
  return verifyNativeResources(resources, resourceVerificationRoot(manifest, packageName))
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

function windowsPathKey(value) {
  if (typeof value !== 'string') return ''
  let text = value.trim().replaceAll('/', '\\').replaceAll('"', '')
  while (text.endsWith('\\')) text = text.slice(0, -1)
  return text.toLowerCase()
}

function productEntries(value) {
  if (Array.isArray(value)) return value
  if (value && typeof value === 'object') return [value]
  return []
}

/** NSIS waits for uninstall only when _?= is last and unquoted, including spaces. */
export function nsisSilentUninstallArgs(directory) {
  if (typeof directory !== 'string' || directory.length === 0 || directory.length > 240 || /["\r\n\u0000]/.test(directory)) {
    throw new Error('uninstall_failed')
  }
  return ['/S', `_?=${directory}`]
}

export function classifyWindowsProducts(entries, directory) {
  const ownedKey = windowsPathKey(directory)
  let ownedPresent = false
  let otherPresent = false
  for (const entry of productEntries(entries)) {
    const name = entry && typeof entry.displayName === 'string' ? entry.displayName : ''
    if (!MNEMION_PRODUCT.test(name)) continue
    const location = windowsPathKey(entry.installLocation)
    const uninstall = windowsPathKey(entry.uninstallString)
    const owned = ownedKey.length > 0 && (location === ownedKey || uninstall === ownedKey || uninstall.startsWith(`${ownedKey}\\`))
    if (owned) ownedPresent = true
    else otherPresent = true
  }
  return { ownedPresent, otherPresent }
}

export function windowsInstallBlocked(entries) {
  return productEntries(entries).some(entry => entry && typeof entry.displayName === 'string' && MNEMION_PRODUCT.test(entry.displayName))
}

export function windowsProductRefusalScript() {
  return '$ErrorActionPreference="Stop"; $entries=Get-ItemProperty -Path "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*","HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*","HKLM:\\Software\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*" -ErrorAction SilentlyContinue; '
    + 'if ($entries | Where-Object { $_.DisplayName -like "Mnemion Studio*" }) { throw "Refusing to modify an existing Mnemion installation" }'
}

export function windowsProductReadScript() {
  return '$ErrorActionPreference="Stop"; $paths=@("HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*","HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*","HKLM:\\Software\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*"); '
    + '$entries=@(Get-ItemProperty -Path $paths -ErrorAction SilentlyContinue | Where-Object { $_.DisplayName -like "Mnemion Studio*" } | ForEach-Object { [PSCustomObject]@{ displayName=[string]$_.DisplayName; installLocation=[string]$_.InstallLocation; uninstallString=[string]$_.UninstallString } }); '
    + 'if ($entries.Count -eq 0) { "[]" } else { $entries | ConvertTo-Json -Compress }'
}

export function waitForOwnedWindowsRemoval(directory, readEntries, sleep, attempts = 60) {
  if (typeof readEntries !== 'function' || typeof sleep !== 'function' || !Number.isInteger(attempts) || attempts < 1 || attempts > 80) {
    throw new Error('uninstall_failed')
  }
  let otherPresent = false
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    const classified = classifyWindowsProducts(readEntries(), directory)
    otherPresent = classified.otherPresent
    if (!classified.ownedPresent) return { cleared: true, otherPresent }
    if (attempt + 1 < attempts) sleep()
  }
  throw new Error('uninstall_failed')
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
