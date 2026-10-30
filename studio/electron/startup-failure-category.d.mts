/** Types for the startup category module. The runtime file is copied beside the compiled main process. */

export const STARTUP_FAILURE_CATEGORIES: readonly string[]

export function startupFailureCategory(error: unknown): string | null
