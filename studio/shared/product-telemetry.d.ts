/** Shared declaration-only contract; local controls contain no analytics IDs. */
export type TelemetryGroup = 'usage' | 'reliability' | 'performance' | 'resources'
export type TelemetryAction = 'status' | 'configure' | 'schema' | 'preview' | 'review_status' | 'review_mode' | 'inspect_report' | 'approve_report' | 'discard_report'
export type TelemetryReviewAction = 'review_mode' | 'inspect_report' | 'approve_report' | 'discard_report'
export type TelemetryReviewChoice = {
  expected_revision: number; expected_generation: string | null; expected_review_token: string | null
  mode?: 'automatic' | 'review'
}
export type TelemetryReview = {
  schema_version: 1; status: TelemetryStatus
  review: { mode: 'automatic' | 'review'; token: string | null; outcome: string; report_available: boolean;
    created_ms: number | null; expires_ms: number | null } | null
  packet: TelemetryWirePreview | null; message: string; interactive_privacy_qualified: false
}
export type TelemetryConnectionMode = 'auto' | 'unmetered' | 'metered'
export type TelemetryChoice = { enabled: boolean; expected_revision: number; expected_generation?: string | null; disclosure_version?: number; connection_mode?: TelemetryConnectionMode }
export type TelemetryStamp = { revision: number; store_generation: string | null }
export type TelemetryCompanyPolicy = {
  state: 'unmanaged' | 'restricted' | 'unreadable'
  enabled: boolean
  metric_groups: string[]
}
export type TelemetryDisclosure = {
  version: number
  default_enabled: boolean
  purpose: string
  destination: string | null
  collection_available: boolean
  includes: string[]
  excludes: string[]
  choice_scope: string
  disable: string
  operational_records: string
  limits: { pending_bytes: number; pending_records: number; pending_age_seconds: number; batch_bytes: number; wire_bytes_per_day: number }
}
export type TelemetryStatus = {
  schema_version: number
  revision: number
  store_generation: string | null
  default_enabled: boolean
  user_enabled: boolean
  connection_mode: TelemetryConnectionMode
  effective_enabled: boolean
  reason: 'storage_unavailable' | 'coordination_unavailable' | 'user_disabled' | 'company_policy' | 'browser_privacy' | 'disclosure_required' | 'collection_unavailable' | 'enabled'
  storage: 'new' | 'ready' | 'unreadable'
  disclosure_version: number
  required_disclosure_version: number
  company_policy: TelemetryCompanyPolicy
  pending_records: number | null
  collection_available: boolean
  disclosure: TelemetryDisclosure
  delivery_budget?: {
    state: 'not_initialized' | 'upgrade_required' | 'clock_rollback' | 'in_flight' | 'cooldown' | 'ready' | 'unavailable'
    maximum_attempts_per_rolling_week: number
    minimum_attempt_spacing_seconds: number
    wire_reservation_per_attempt_bytes: number
    wire_budget_per_rolling_day_bytes: number
    attempts_in_rolling_week: number | null
    reserved_wire_bytes_in_rolling_day: number | null
    transport_available: boolean
  }
}
export type TelemetryWirePreview = {
  schema_version: number
  body_base64: string
  body_bytes: number
  view: string
  coordinate: number
  randomized_sign: number | null
  protected_unit: string
  report_selection: 'automatic' | 'reviewed'
  aggregation: 'automatic_categorical_estimates' | 'coarse_global_volume_only'
  randomization_privacy_loss: 'ln(3)' | null
  per_report_privacy_loss: 'ln(3)' | null
  privacy_bound_scope: 'packet_independent_inclusion' | 'fixed_body_for_permitted_groups'
  participation_or_lifetime_guarantee: false
}
export type TelemetryFormatExample = TelemetryWirePreview & {
  kind: 'synthetic_example'
  body_encoding: 'base64'
}
export type TelemetryPreview = {
  schema_version: number
  status: TelemetryStatus
  outbound_body: string | null
  outbound_bytes: number
  outbound_state?: 'not_inspected'
  illustrative_packet?: TelemetryFormatExample
  transport_available: boolean
  message: string
  measurement_catalog?: {
    version: number
    workflows: Record<string, string[]>
    ownership: { measured: string; exclusions: Record<string, string> }
  }
  local_aggregates?: Record<string, string | number>[]
}
