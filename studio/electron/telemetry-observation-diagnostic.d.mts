export const OBSERVATION_COUNTERS: readonly string[]

export function emptyObservation(): {
  counts: Record<string, number>
  cycle: number
  readiness: string
  pending: string
}

export function bumpObservation(state: { counts: Record<string, number> } | null | undefined, name: string): void

export function bumpElapsed(state: { counts: Record<string, number> } | null | undefined, kind: 'acl' | 'snapshot', elapsed: number): void

export function mergeObservationSample(state: {
  counts: Record<string, number>
  cycle: number
  readiness: string
  pending: string
} | null | undefined, sample: unknown): Record<string, unknown> | null

export function sanitizeObservation(value: unknown): Record<string, unknown> | null

export function deliveryObservationEnabled(): boolean

export function noteObservation(name: string): void

export function noteAcl(outcome: 'accepted' | 'refused' | 'timed_out', elapsed: number): void

export function acceptObservation(sample: unknown): Record<string, unknown> | null

export function publicObservation(): Record<string, unknown> | null
