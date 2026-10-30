/** One allowlisted first-attempt outcome. Off unless a resource launch opts in.
 * Not a report, a wire field, a history, or a measurement. */

const NETWORKS = ['unknown', 'metered', 'unmetered']
const REASONS = ['allowed', 'clock', 'network_not_allowed', 'network_constrained', 'offline',
  'cpu_busy', 'cpu_unobserved', 'memory', 'thermal', 'read_failed']
const OUTCOMES = ['unknown', 'release_unavailable', 'eligible_refused', 'prepare_refused',
  'aborted', 'reserve_refused', 'reserved']
const SAMPLED = new Set(['prepare_refused', 'aborted', 'reserve_refused', 'reserved'])

export const ADMISSION_OUTCOMES = Object.freeze([...OUTCOMES])

export function resourceAdmissionEnabled(env, packaged) {
  return packaged === true
    && Boolean(env && env.MNEMION_STUDIO_HOSTING_PROBE)
    && env.MNEMION_TELEMETRY_RESOURCE_ADMISSION === '1'
    && env.MNEMION_TELEMETRY_INSTALLED_DELIVERY !== '1'
}

export function copyAdmissionGuard(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  if (value.schema_version !== 1 || typeof value.constrained !== 'boolean') return null
  if (!NETWORKS.includes(value.network) || !REASONS.includes(value.reason)) return null
  return { schema_version: 1, network: value.network, constrained: value.constrained, reason: value.reason }
}

export function sanitizeAdmissionOutcome(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  if (value.schema_version !== 1 || !OUTCOMES.includes(value.outcome)) return null
  const sampled = SAMPLED.has(value.outcome)
  return {
    schema_version: 1,
    outcome: value.outcome,
    guard: sampled ? copyAdmissionGuard(value.guard) : null,
  }
}

export function unknownAdmissionOutcome() {
  return { schema_version: 1, outcome: 'unknown', guard: null }
}

/** The note stores the first finish only. Later begins do not allocate another trace. */
export function createAdmissionNote(conditions) {
  let stored = null
  return {
    begin() {
      if (stored) return
      conditions.admissionGuard = undefined
      conditions.traceAdmission = true
    },
    finish(name) {
      if (stored) return
      const guard = SAMPLED.has(name) ? conditions.admissionGuard : null
      conditions.traceAdmission = false
      conditions.admissionGuard = undefined
      stored = sanitizeAdmissionOutcome({ schema_version: 1, outcome: name, guard }) ?? unknownAdmissionOutcome()
    },
    snapshot() {
      return stored ?? unknownAdmissionOutcome()
    },
  }
}

/** Diagnostic branch of DesktopTelemetryActivity.reserve. Ordinary attempts do not call this. */
export async function runDiagnosticAdmission({ begin, finish, eligible, prepare, reserve, stop }) {
  let outcome = 'unknown'
  try {
    begin()
    if (!await eligible()) outcome = 'eligible_refused'
    else if (!await prepare(stop) || stop.aborted) outcome = stop.aborted ? 'aborted' : 'prepare_refused'
    else {
      const report = await reserve()
      outcome = report ? 'reserved' : 'reserve_refused'
      return report
    }
    return null
  } finally {
    finish(outcome)
  }
}
