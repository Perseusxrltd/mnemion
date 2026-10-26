/** Closed diagnostics for model setup in the disposable installed-app probe. */
import type { LocalDiagnostic, LocalStatus } from '../shared/local-workspace.js'
import { localDiagnostic } from './local-diagnostics.js'

const phases = ['initial', 'save_embedding', 'save_librarian', 'inspect', 'app',
  'restore_view', 'remove_embedding', 'remove_librarian'] as const
const reasons = ['action_failed', 'missing_status', 'pending_app_work', 'restart_error', 'restart_timeout',
  'private_key_exposed', 'profiles_missing', 'private_credentials_missing', 'permissions',
  'public_choices_invalid', 'app_choices_missing', 'unselected_network', 'cleanup_profiles_remain'] as const
const states = ['new', 'starting', 'running', 'stopping', 'stopped', 'error', 'unknown'] as const
const stages = ['starting', 'database', 'access', 'model', 'service', 'verification', 'ready', 'unknown'] as const

export type ModelSetupPhase = typeof phases[number]
export type ModelSetupReason = typeof reasons[number]
export type ModelSetupDiagnostic = {
  phase: ModelSetupPhase; reason: ModelSetupReason;
  state: typeof states[number]; stage: typeof stages[number];
  cleanup: 'not_started' | 'failed'; engineDiagnostic?: LocalDiagnostic;
}

export function modelSetupDiagnostic(input: unknown): ModelSetupDiagnostic {
  if (!input || typeof input !== 'object' || Array.isArray(input)) throw new Error('Invalid model-setup diagnostic')
  const value = input as ModelSetupDiagnostic
  if (Object.keys(value).some(key => !['phase', 'reason', 'state', 'stage', 'cleanup', 'engineDiagnostic'].includes(key)) ||
      !phases.includes(value.phase) || !reasons.includes(value.reason) || !states.includes(value.state) || !stages.includes(value.stage) ||
      !['not_started', 'failed'].includes(value.cleanup)) throw new Error('Invalid model-setup diagnostic')
  const { engineDiagnostic, ...fixed } = value
  const engine = localDiagnostic(engineDiagnostic)
  return { ...fixed, ...(engine ? { engineDiagnostic: engine } : {}) }
}

export class ModelSetupFailure extends Error {
  readonly diagnostic: ModelSetupDiagnostic
  constructor(phase: ModelSetupPhase, reason: ModelSetupReason, status?: LocalStatus) {
    let engineDiagnostic: LocalDiagnostic | undefined
    try { engineDiagnostic = localDiagnostic(status?.diagnostic) } catch { /* Never forward arbitrary runtime detail. */ }
    const diagnostic = modelSetupDiagnostic({ phase, reason,
      state: states.includes(status?.state as any) ? status!.state : 'unknown',
      stage: stages.includes(status?.stage as any) ? status!.stage : 'unknown',
      cleanup: phase.startsWith('remove_') || phase === 'restore_view' ? 'failed' : 'not_started',
      ...(engineDiagnostic ? { engineDiagnostic } : {}) })
    super('Installed model setup failed: ' + JSON.stringify(diagnostic))
    this.diagnostic = diagnostic
  }
}

export function modelSetupFailure(error: unknown): ModelSetupDiagnostic | undefined {
  if (typeof error !== 'string' || error.length > 4096) return undefined
  const match = /^Error: Installed model setup failed: (\{[^\n]+\})$/.exec(error)
  if (!match) return undefined
  try { return modelSetupDiagnostic(JSON.parse(match[1])) } catch { return undefined }
}
