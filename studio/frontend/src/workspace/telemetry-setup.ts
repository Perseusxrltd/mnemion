/** A displayed disclosure can authorize only its original local choice. */
import type { TelemetryChoice, TelemetryStatus } from '../../../shared/product-telemetry'

export function needsTelemetrySetup(status: TelemetryStatus): boolean {
  return status.reason === 'disclosure_required' && status.user_enabled && !status.effective_enabled &&
    status.storage !== 'unreadable' && status.collection_available && status.disclosure.collection_available &&
    Boolean(status.disclosure.destination) && status.company_policy.enabled && status.company_policy.metric_groups.length > 0 &&
    status.required_disclosure_version > 0 && status.required_disclosure_version === status.disclosure.version
}

export function telemetrySetupChoice(status: TelemetryStatus, enabled: boolean): TelemetryChoice | null {
  if (typeof enabled !== 'boolean' || !needsTelemetrySetup(status)) return null
  return { enabled, expected_revision: status.revision, expected_generation: status.store_generation,
    disclosure_version: enabled ? status.required_disclosure_version : 0 }
}
