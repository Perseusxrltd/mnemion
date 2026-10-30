/** Bounded installed-journey gates. A null review is unreadiness, never a mode.
 * Each function keeps its own allowlist: the packaged page receives function
 * source only, with no module closure. */

export function telemetrySnapshotDecision(snapshot, accept) {
  const allowed = [
    'unavailable', 'not_initialized', 'upgrade_required', 'stored_snapshot', 'inactive', 'paused',
    'held', 'discarded', 'approved', 'consumed', 'expired', 'invalidated', 'no_report', 'no_observations',
    'collection_not_permitted', 'transport_unavailable', 'delivery_not_ready', 'control_unavailable',
    'review_unavailable', 'review_not_paused', 'connection_pending', 'collection_pending',
    'observations_pending', 'report_not_held', 'report_not_discarded', 'report_not_consumed',
  ]
  if (!snapshot || typeof snapshot !== 'object' || Array.isArray(snapshot)) {
    return { ready: false, gate: 'control_unavailable' }
  }
  const review = snapshot.review
  if (!review || typeof review !== 'object' || Array.isArray(review)) {
    const message = snapshot.message
    return { ready: false, gate: typeof message === 'string' && allowed.includes(message) ? message : 'review_unavailable' }
  }
  const decision = accept(snapshot)
  if (decision === true) return { ready: true, gate: '', snapshot }
  return { ready: false, gate: typeof decision === 'string' && allowed.includes(decision) ? decision : 'review_unavailable' }
}

/** True only after the workspace shell is visible and the index redirect has committed.
 * Welcome-text absence is not ownership: Shell renders "Loading workspace…" with neither
 * .ws-shell nor its post-paint <Navigate to="memories">. */
export function telemetryWorkspaceSettled(view) {
  if (!view || typeof view !== 'object' || Array.isArray(view)) return false
  if (view.shell !== true || view.name !== true) return false
  const hash = typeof view.hash === 'string' ? view.hash : ''
  const route = hash.split('?')[0].replace(/\/+$/, '')
  return route === '#/workspace/memories'
}

/** Fixed privacy readiness. The return is an allowlisted gate, never page text. */
export function telemetryPrivacyGate(view) {
  if (!view || typeof view !== 'object' || Array.isArray(view)) return 'privacy_page'
  const hash = typeof view.hash === 'string' ? view.hash : ''
  const route = hash.split('?')[0].replace(/\/+$/, '')
  if (route !== '#/privacy') return 'privacy_navigation'
  if (view.heading !== true) return 'privacy_page'
  if (view.control === 'disabled' || view.control === 'hidden') return 'privacy_control'
  if (view.control !== 'ready') return 'privacy_state'
  return 'none'
}

export function telemetryReadinessError(phase, gate) {
  const allowed = [
    'unavailable', 'not_initialized', 'upgrade_required', 'stored_snapshot', 'inactive', 'paused',
    'held', 'discarded', 'approved', 'consumed', 'expired', 'invalidated', 'no_report', 'no_observations',
    'collection_not_permitted', 'transport_unavailable', 'delivery_not_ready', 'control_unavailable',
    'review_unavailable', 'review_not_paused', 'connection_pending', 'collection_pending',
    'observations_pending', 'report_not_held', 'report_not_discarded', 'report_not_consumed',
  ]
  const safePhase = typeof phase === 'string' && /^[a-z_]{1,64}$/.test(phase) ? phase : 'unknown_phase'
  const safeGate = typeof gate === 'string' && allowed.includes(gate) ? gate : 'review_unavailable'
  return `Installed telemetry was not ready: phase=${safePhase} gate=${safeGate}`
}
