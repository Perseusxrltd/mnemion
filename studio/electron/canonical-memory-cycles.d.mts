/** Types for the shared cycle module. The runtime file is copied beside the compiled main process. */
export function canonicalLaunchPrefix(): string
export function canonicalProgressWriter(directory: string): (record: object) => void
export function canonicalMemoryCycles(input: { number: number; space: string }): Promise<void>
export function canonicalRemainingBatches(comparison: boolean): Array<[number, number]>
export function canonicalTerminalMarker(
  phase: 'finished' | 'closed' | 'failed',
  completed?: number,
  known?: boolean,
): { phase: string; completed?: number; completed_known: boolean }
export function resourceProgress(
  state: { verified?: number; progressKnown: boolean },
  event: 'inflight' | { settled?: number },
): { verified?: number; progressKnown: boolean }
