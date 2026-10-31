/** Types for the installed process-role module. The runtime file is copied beside the compiled main process. */

export const INSTALLED_PROCESS_CHECKPOINTS: readonly string[]

export function observeInstalledProcessCheckpoint(input: {
  phase?: string
  mainPid?: number
  rendererPid?: number | null
  windowCount?: number
  appWindowCount?: number
  devtoolsPresent?: boolean
  observationFailed?: boolean
  metrics?: Array<{
    pid?: number
    type?: string
    creationTime?: number
    workingSetKilobytes?: number
  }>
}): Record<string, unknown>

export function publicProcessRoleRun(samples: unknown): Record<string, unknown>

export function compareInstalledProcessRoleRss(cases: unknown): Record<string, unknown>
