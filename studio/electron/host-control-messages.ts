/** Fixed public messages; raw host diagnostics never enter renderer errors. */
export const hostMessages: Record<string, string> = {
  host_identity_changed: 'This server key differs from the enrolled host. Ask its owner to verify the new fingerprint before changing this connection.',
  host_access_denied: 'The host did not accept this operator key. Ask a current custodian to check or renew your grant.',
  invalid_operator_key: 'This enrollment belongs to another operator key. Use the connection issued for this device.',
  host_connection_timeout: 'The host reply did not arrive in time. Inspect the saved operation before retrying it.',
  host_control_unavailable: 'The independent host connection is unavailable. Check the host address, firewall and provider status. Keep the saved operation for inspection.',
  invalid_host_response: 'The host response could not be verified. Inspect the saved operation after reconnecting.',
  invalid_request: 'Use the host operation schema and its explicit approvals.',
  forbidden: 'Your current host role does not allow this operation.',
  request_expired: 'This approval expired. Inspect the previous operation before approving new work.',
  host_changed: 'Host configuration changed. Refresh its status and review a new plan.',
  revision_changed: 'Host authority changed. Refresh the people list before making this change.',
  recovery_required: 'This host has an interrupted update. Review and resume its existing recovery plan.',
  operation_not_found: 'The host has no visible receipt for that operation. Keep the original request when checking or retrying.',
  host_unavailable: 'The memory service needs inspection. Read its status and operation history.',
  last_custodian: 'Keep at least one permanent custodian on this host.',
  source_unavailable: 'The native host helper could not confirm this operation. Inspect its saved status.',
}
