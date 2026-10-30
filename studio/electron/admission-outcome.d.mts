/** Types for the admission outcome module. The runtime file is copied beside the compiled main process. */

export type AdmissionNetwork = 'unknown' | 'metered' | 'unmetered'

export type AdmissionReason =
  | 'allowed'
  | 'clock'
  | 'network_not_allowed'
  | 'network_constrained'
  | 'offline'
  | 'cpu_busy'
  | 'cpu_unobserved'
  | 'memory'
  | 'thermal'
  | 'read_failed'

export type AdmissionOutcomeName =
  | 'unknown'
  | 'release_unavailable'
  | 'eligible_refused'
  | 'prepare_refused'
  | 'aborted'
  | 'reserve_refused'
  | 'reserved'

export type AdmissionGuard = {
  schema_version: 1
  network: AdmissionNetwork
  constrained: boolean
  reason: AdmissionReason
}

/** Every stage, including unknown. Callers accept a real snapshot through this type. */
export type AdmissionOutcome = {
  schema_version: 1
  outcome: AdmissionOutcomeName
  guard: AdmissionGuard | null
}

export const ADMISSION_OUTCOMES: readonly AdmissionOutcomeName[]

export function resourceAdmissionEnabled(
  env: { [key: string]: string | undefined } | null | undefined,
  packaged: boolean,
): boolean

export function copyAdmissionGuard(value: unknown): AdmissionGuard | null

export function sanitizeAdmissionOutcome(value: unknown): AdmissionOutcome | null

export function unknownAdmissionOutcome(): AdmissionOutcome

export function createAdmissionNote(conditions: {
  traceAdmission: boolean
  admissionGuard?: AdmissionGuard | null
}): {
  begin(): void
  finish(name: string): void
  snapshot(): AdmissionOutcome
}

/** Report is the payload reserve() returns. Early refusals become null without widening that payload away. */
export function runDiagnosticAdmission<Report>(input: {
  begin: () => void
  finish: (outcome: string) => void
  eligible: () => boolean | Promise<boolean>
  prepare: (stop: AbortSignal) => boolean | Promise<boolean>
  reserve: () => Report | Promise<Report>
  stop: AbortSignal
}): Promise<Report | null>
