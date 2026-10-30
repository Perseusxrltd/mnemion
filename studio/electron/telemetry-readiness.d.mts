export function telemetrySnapshotDecision(
  snapshot: unknown,
  accept: (value: Record<string, any>) => true | string,
): { ready: boolean; gate: string; snapshot?: Record<string, any> }

export function telemetryReadinessError(phase: string, gate: string): string
