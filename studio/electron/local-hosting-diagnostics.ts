/** Fixed classifications for disposable installed-workspace acceptance only. */
const fields = {
  route: ['workspace', 'help', 'other'],
  view: ['local_setup', 'workspace', 'loading', 'connection', 'error', 'other'],
  localState: ['new', 'starting', 'running', 'stopping', 'stopped', 'error', 'unknown'],
  localSelected: ['yes', 'no', 'unknown'],
  authenticated: ['yes', 'no', 'unknown'],
  identityMatches: ['yes', 'no', 'unknown'],
  openControl: ['enabled', 'disabled', 'absent'],
  error: ['none', 'unreachable', 'not_ready', 'access', 'identity', 'selection', 'busy', 'file_access', 'timeout', 'other'],
} as const

export type WorkspaceOpenDiagnostic = { [K in keyof typeof fields]: typeof fields[K][number] }

export function workspaceOpenDiagnostic(input: unknown): WorkspaceOpenDiagnostic {
  if (!input || typeof input !== 'object' || Array.isArray(input)) throw new Error('Invalid workspace-open diagnostic')
  const value = input as Record<string, unknown>
  if (Object.keys(value).length !== Object.keys(fields).length || Object.keys(value).some(key => !(key in fields))) {
    throw new Error('Invalid workspace-open diagnostic')
  }
  for (const [key, allowed] of Object.entries(fields)) {
    if (typeof value[key] !== 'string' || !(allowed as readonly string[]).includes(value[key] as string)) {
      throw new Error('Invalid workspace-open diagnostic')
    }
  }
  return Object.fromEntries(Object.keys(fields).map(key => [key, value[key]])) as WorkspaceOpenDiagnostic
}

// This self-contained function is also used inside the disposable renderer.
// Only the classification leaves it; never return any part of the UI message.
export function workspaceOpenError(message: unknown): WorkspaceOpenDiagnostic['error'] {
  if (typeof message !== 'string' || !message.trim()) return 'none'
  if (message.length > 8192) return 'other'
  if (message.includes('The workspace could not be reached.')) return 'unreachable'
  if (message.includes('The workspace is not ready.')) return 'not_ready'
  if (message.includes('This key is expired, revoked or does not grant workspace access.')) return 'access'
  if (message.includes('did not return a Mnemion workspace identity') || message.includes('returned an invalid identity')) return 'identity'
  if (message.includes('Another workspace connection was selected.') || message.includes('A newer connection was selected.')) return 'selection'
  if (message.includes('Wait for the local workspace checks to finish') || message.includes('A local agent operation is finishing.') || message.includes('The local workspace is switching.')) return 'busy'
  if (/\b(?:EACCES|EPERM|EBUSY)\b/.test(message)) return 'file_access'
  if (/\b(?:TimeoutError|AbortError)\b|request timed out/i.test(message)) return 'timeout'
  return 'other'
}

export function workspaceOpenFailure(error: unknown): WorkspaceOpenDiagnostic | undefined {
  if (typeof error !== 'string' || error.length > 2048) return undefined
  const match = /^Error: Installed workspace open failed: (\{[^\n]+\})$/.exec(error)
  if (!match) return undefined
  try { return workspaceOpenDiagnostic(JSON.parse(match[1])) } catch { return undefined }
}
