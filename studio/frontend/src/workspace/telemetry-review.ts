/** Origin-local review protocol binding, never an analytics payload. */
import contract from '../../../../mnemion/product_telemetry/disclosure.json'
import route from '../../../../mnemion/product_telemetry/transport-route.json'
import wire from '../../../../mnemion/product_telemetry/wire-v1.json'
import catalog from '../../../../mnemion/product_telemetry/catalog.json'
import type { TelemetryReviewAction, TelemetryReviewChoice, TelemetryStatus } from '../../../shared/product-telemetry'
import { reviewContext } from '../../../electron/telemetry-review'

export function browserReviewContext(status: TelemetryStatus) {
  return reviewContext({ stamp: { revision: status.revision, store_generation: status.store_generation },
    groups: status.company_policy.metric_groups, binding: { disclosure_version: contract.version,
      wire_version: wire.version, catalog_version: catalog.version, destination: contract.destination,
      route_address: route.address } })
}

export function reviewRequest(action: TelemetryReviewAction, value: TelemetryReviewChoice): TelemetryReviewChoice {
  const keys = ['expected_revision', 'expected_generation', 'expected_review_token', ...(action === 'review_mode' ? ['mode'] : [])]
  const token = (value: unknown) => value === null || (typeof value === 'string' && /^[0-9a-f]{32}$/.test(value))
  if (!['review_mode', 'inspect_report', 'approve_report', 'discard_report'].includes(action) ||
      !value || typeof value !== 'object' || Array.isArray(value) || Object.keys(value).sort().join() !== keys.sort().join() ||
      !Number.isInteger(value.expected_revision) || value.expected_revision < 0 || value.expected_revision >= 2147483647 ||
      !token(value.expected_generation) || !token(value.expected_review_token) ||
      (action === 'review_mode' && !['automatic', 'review'].includes(value.mode!))) throw new Error('telemetry_invalid_review')
  return { ...value }
}
