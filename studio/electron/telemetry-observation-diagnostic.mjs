/** Diagnostic counters for one installed hosting probe. Production never calls in. */
const LIMIT = 255

export const OBSERVATION_COUNTERS = [
  'snapshot_admitted',
  'snapshot_null',
  'snapshot_rejected',
  'snapshot_deadline',
  'snapshot_elapsed_lt_5',
  'snapshot_elapsed_lt_25',
  'snapshot_elapsed_ge_25',
  'acl_accepted',
  'acl_refused',
  'acl_timed_out',
  'acl_duration_lt_50',
  'acl_duration_lt_250',
  'acl_duration_lt_1000',
  'acl_duration_ge_1000',
  'snapshot_suppressed_owner',
  'snapshot_suppressed_hint',
  'record_attempted',
  'record_committed',
  'record_refused_owner',
  'record_refused_stamp',
  'record_refused_policy',
  'record_refused_storage',
]

const RENDERER_COUNTERS = [
  'snapshot_admitted',
  'snapshot_null',
  'snapshot_rejected',
  'snapshot_deadline',
  'snapshot_elapsed_lt_5',
  'snapshot_elapsed_lt_25',
  'snapshot_elapsed_ge_25',
]

const READINESS = new Set([
  'none',
  'manual_review',
  'before_permission',
  'collection_enabled',
  'memory_observations',
  'report_inspect',
  'report_bytes',
  'report_held',
  'invalidated_report',
  'collection_reenabled',
  'report_discard',
  'report_discarded',
  'report_approve',
  'report_consumed',
  'final_opt_out',
  'restart_review',
  'review_request',
  'unknown_phase',
])

const PENDING = new Set([
  'none',
  'unavailable',
  'not_initialized',
  'upgrade_required',
  'stored_snapshot',
  'inactive',
  'paused',
  'held',
  'discarded',
  'approved',
  'consumed',
  'expired',
  'invalidated',
  'no_report',
  'no_observations',
  'collection_not_permitted',
  'transport_unavailable',
  'delivery_not_ready',
  'control_unavailable',
  'review_unavailable',
  'review_not_paused',
  'connection_pending',
  'collection_pending',
  'observations_pending',
  'report_not_held',
  'report_not_discarded',
  'report_not_consumed',
])

export function emptyObservation() {
  return {
    counts: Object.fromEntries(OBSERVATION_COUNTERS.map(name => [name, 0])),
    cycle: 0,
    readiness: 'none',
    pending: 'none',
  }
}

export function bumpObservation(state, name) {
  if (!state?.counts || !Object.hasOwn(state.counts, name)) return
  if (state.counts[name] < LIMIT) state.counts[name] += 1
}

export function bumpElapsed(state, kind, elapsed) {
  const safe = typeof elapsed === 'number' && Number.isFinite(elapsed) && elapsed >= 0 ? elapsed : Number.POSITIVE_INFINITY
  const name = kind === 'acl'
    ? (safe < 50 ? 'acl_duration_lt_50' : safe < 250 ? 'acl_duration_lt_250' : safe < 1000 ? 'acl_duration_lt_1000' : 'acl_duration_ge_1000')
    : (safe < 5 ? 'snapshot_elapsed_lt_5' : safe < 25 ? 'snapshot_elapsed_lt_25' : 'snapshot_elapsed_ge_25')
  bumpObservation(state, name)
}

function boundedInteger(value) {
  return Number.isInteger(value) && value >= 0 && value <= LIMIT ? value : null
}

export function mergeObservationSample(state, sample) {
  if (!state?.counts || !sample || typeof sample !== 'object' || Array.isArray(sample)) return publicFrom(state)
  const renderer = sample.renderer
  if (renderer && typeof renderer === 'object' && !Array.isArray(renderer)) {
    for (const name of RENDERER_COUNTERS) {
      const number = boundedInteger(renderer[name])
      if (number !== null) state.counts[name] = number
    }
  }
  if (boundedInteger(sample.cycle) !== null && sample.cycle <= 3) state.cycle = sample.cycle
  if (typeof sample.readiness === 'string') state.readiness = READINESS.has(sample.readiness) ? sample.readiness : 'unknown_phase'
  if (typeof sample.pending === 'string') state.pending = PENDING.has(sample.pending) ? sample.pending : 'review_unavailable'
  return publicFrom(state)
}

function publicFrom(state) {
  if (!state?.counts) return null
  return { ...state.counts, cycle: state.cycle, readiness: state.readiness, pending: state.pending }
}

export function sanitizeObservation(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const safe = {}
  for (const name of OBSERVATION_COUNTERS) {
    const number = boundedInteger(value[name])
    if (number === null) return null
    safe[name] = number
  }
  if (boundedInteger(value.cycle) === null || value.cycle > 3) return null
  if (typeof value.readiness !== 'string' || !READINESS.has(value.readiness)) return null
  if (typeof value.pending !== 'string' || !PENDING.has(value.pending)) return null
  safe.cycle = value.cycle
  safe.readiness = value.readiness
  safe.pending = value.pending
  return safe
}

let state = null

export function deliveryObservationEnabled() {
  return Boolean(process.env.MNEMION_STUDIO_HOSTING_PROBE) && process.env.MNEMION_TELEMETRY_INSTALLED_DELIVERY === '1'
}

function armed() {
  if (!deliveryObservationEnabled()) return null
  if (!state) state = emptyObservation()
  return state
}

export function noteObservation(name) {
  const current = armed()
  if (!current) return
  bumpObservation(current, name)
}

export function noteAcl(outcome, elapsed) {
  const current = armed()
  if (!current) return
  bumpObservation(current, outcome === 'accepted' ? 'acl_accepted' : outcome === 'timed_out' ? 'acl_timed_out' : 'acl_refused')
  bumpElapsed(current, 'acl', elapsed)
}

export function acceptObservation(sample) {
  const current = armed()
  if (!current) return null
  return mergeObservationSample(current, sample)
}

export function publicObservation() {
  const current = armed()
  return current ? publicFrom(current) : null
}
