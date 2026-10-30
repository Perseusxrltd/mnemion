export function telemetrySnapshotDecision(
  snapshot: unknown,
  accept: (value: Record<string, any>) => true | string,
): { ready: boolean; gate: string; snapshot?: Record<string, any> }

export function telemetryWorkspaceSettled(view: unknown): boolean

export function telemetryPrivacyGate(
  view: unknown,
): 'none' | 'privacy_navigation' | 'privacy_page' | 'privacy_state' | 'privacy_control'

export function telemetryReadinessError(phase: string, gate: string): string
