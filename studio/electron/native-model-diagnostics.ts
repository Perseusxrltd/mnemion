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
const operations = ['listener_start', 'status', 'app_idle', 'apply', 'restart_status', 'read_view',
  'private_state', 'public_choices', 'open_setup', 'app_choices', 'restore_view'] as const
const actionFailures = ['app_busy', 'local_busy', 'closing', 'revision_changed', 'settings_timeout',
  'settings_unconfirmed', 'stop_timeout', 'runtime_timeout', 'runtime_unavailable', 'runtime_invalid',
  'operator_timeout', 'operator_unavailable', 'operator_exchange', 'operator_result', 'operator_output_limit',
  'model_configuration', 'private_state_missing', 'private_state_denied', 'resource_pressure', 'unclassified'] as const

// Exact public messages only. Never copy an exception, path, URL, credential or
// provider response into the uploaded installed-app evidence.
const messages: ReadonlyArray<readonly [string, typeof actionFailures[number]]> = [
  ['Save or discard edits and finish pending requests in the app before restarting its workspace.', 'app_busy'],
  ['Wait for the current local operation before changing model settings.', 'local_busy'],
  ['The local workspace is stopping. Wait for it to finish before trying again.', 'local_busy'],
  ['The app is closing.', 'closing'],
  ['Host settings changed. Refresh before saving them again.', 'revision_changed'],
  ['Model settings changed. Refresh and review them again.', 'revision_changed'],
  ['Refresh the current workspace and model settings before continuing.', 'revision_changed'],
  ['The host settings change could not be confirmed. Refresh its status before retrying.', 'settings_timeout'],
  ['The saved model settings could not be confirmed. Refresh before retrying.', 'settings_unconfirmed'],
  ['The local workspace is still stopping. Refresh before retrying.', 'stop_timeout'],
  ['The local runtime check timed out. Try again.', 'runtime_timeout'],
  ['The local runtime could not start. Reinstall the complete app.', 'runtime_unavailable'],
  ['The complete local runtime is missing. Reinstall Mnemion Studio to create a workspace on this computer.', 'runtime_unavailable'],
  ['The local runtime returned an invalid status.', 'runtime_invalid'],
  ['The local runtime could not read its settings.', 'runtime_invalid'],
  ['The local runtime does not match this app. Reinstall the complete app.', 'runtime_invalid'],
  ['The installed operator client timed out.', 'operator_timeout'],
  ['The installed operator client could not start.', 'operator_unavailable'],
  ['Desktop control could not complete. Start Mnemion Studio under this OS account, check the private control directory and request, then refresh status before retrying a change.', 'operator_exchange'],
  ['The installed operator client did not return a bounded matching result.', 'operator_result'],
  ['The installed operator client returned excessive output.', 'operator_output_limit'],
  ['Invalid local model settings status.', 'model_configuration'],
  ['Invalid private model status.', 'model_configuration'],
  ['Model profiles must have distinct identifiers, up to eight of each kind.', 'model_configuration'],
]

export function modelActionFailure(error: unknown): typeof actionFailures[number] {
  if (!(error instanceof Error)) return 'unclassified'
  const message = error.message.replace(/^Installed operator (?:local\.models|status) failed: /, '')
  const known = messages.find(([text]) => text === message)
  if (known) return known[1]
  const code = (error as NodeJS.ErrnoException).code
  if (code === 'ENOENT') return 'private_state_missing'
  if (code === 'EACCES' || code === 'EPERM') return 'private_state_denied'
  if (code === 'ENOMEM' || code === 'EMFILE' || code === 'ENFILE') return 'resource_pressure'
  return 'unclassified'
}

export type ModelSetupPhase = typeof phases[number]
export type ModelSetupReason = typeof reasons[number]
export type ModelSetupOperation = typeof operations[number]
type Context = { operation?: ModelSetupOperation; actionFailure?: typeof actionFailures[number] }
export type ModelSetupDiagnostic = {
  phase: ModelSetupPhase; reason: ModelSetupReason;
  state: typeof states[number]; stage: typeof stages[number];
  cleanup: 'not_started' | 'failed'; engineDiagnostic?: LocalDiagnostic;
} & Context

export function modelSetupDiagnostic(input: unknown): ModelSetupDiagnostic {
  if (!input || typeof input !== 'object' || Array.isArray(input)) throw new Error('Invalid model-setup diagnostic')
  const value = input as ModelSetupDiagnostic
  if (Object.keys(value).some(key => !['phase', 'reason', 'state', 'stage', 'cleanup', 'engineDiagnostic', 'operation', 'actionFailure'].includes(key)) ||
      !phases.includes(value.phase) || !reasons.includes(value.reason) || !states.includes(value.state) || !stages.includes(value.stage) ||
      !['not_started', 'failed'].includes(value.cleanup) ||
      ('operation' in value && !operations.includes(value.operation!)) ||
      ('actionFailure' in value && !actionFailures.includes(value.actionFailure!))) throw new Error('Invalid model-setup diagnostic')
  const { engineDiagnostic, ...fixed } = value
  const engine = localDiagnostic(engineDiagnostic)
  return { ...fixed, ...(engine ? { engineDiagnostic: engine } : {}) }
}

export class ModelSetupFailure extends Error {
  readonly diagnostic: ModelSetupDiagnostic
  constructor(phase: ModelSetupPhase, reason: ModelSetupReason, status?: LocalStatus, context: Context = {}) {
    let engineDiagnostic: LocalDiagnostic | undefined
    try { engineDiagnostic = localDiagnostic(status?.diagnostic) } catch { /* Never forward arbitrary runtime detail. */ }
    const diagnostic = modelSetupDiagnostic({ phase, reason,
      state: states.includes(status?.state as any) ? status!.state : 'unknown',
      stage: stages.includes(status?.stage as any) ? status!.stage : 'unknown',
      cleanup: phase.startsWith('remove_') || phase === 'restore_view' ? 'failed' : 'not_started',
      ...context,
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
