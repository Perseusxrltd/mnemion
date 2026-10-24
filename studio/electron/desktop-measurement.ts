/** Ownership boundary outside the numeric encoder. Never inspect free text. */
import { readFileSync } from 'node:fs'
import { TelemetryWorkflow, type WorkflowStore } from './telemetry-workflow.js'

type Spec = { workflow?: string; completion?: string; selector?: string; variants?: Record<string, string>; local_status?: boolean; exclusion?: string }
export const desktopTelemetryOrigins: { version: number; ownership: string; exclusions: Record<string, string>; operations: Record<string, Spec> } = (() => {
  try { return JSON.parse(readFileSync(new URL('./telemetry-desktop-origins.json', import.meta.url), 'utf8')) }
  catch { return { version: 1, ownership: '', exclusions: {}, operations: {} } }
})()

export function desktopTelemetrySelection(action: string, input: Record<string, unknown>): { workflow: string; completion: string; localStatus: boolean } | null {
  const spec = Object.hasOwn(desktopTelemetryOrigins.operations, action) ? desktopTelemetryOrigins.operations[action] : undefined
  if (!spec || spec.exclusion) return null
  // The sole selector is a reviewed boolean. It cannot export arbitrary fields.
  const variant = spec.selector === 'enabled' && typeof input.enabled === 'boolean' ? String(input.enabled) : null
  const workflow = spec.variants ? (variant && Object.hasOwn(spec.variants, variant) ? spec.variants[variant] : null) : spec.workflow
  return workflow && spec.completion ? { workflow, completion: spec.completion, localStatus: spec.local_status === true } : null
}

/** Only these explicit UI controls own a local action. Polling and the generic
 * service transport have no entry; remote UI workflows own their own scope. */
export const desktopIpcOrigins: Record<string, string> = {
  'workspaces:resume': 'workspace.restore', 'workspaces:connect': 'workspace.connect',
  'workspaces:sign-in': 'workspace.sign-in', 'workspaces:company-sign-in': 'workspace.sign-in',
  'workspaces:invitation-accept': 'workspace.sign-in', 'workspaces:restore': 'workspace.restore',
  'workspaces:forget': 'workspace.forget', 'workspaces:disconnect': 'workspace.disconnect',
  'agents:install': 'agent.install', 'agents:remove': 'agent.remove',
  'sources:configure': 'source.configure', 'sources:backup': 'source.backup',
  'sources:backup-inspect': 'source.backup.inspect', 'sources:restore': 'source.restore',
  'sources:drain': 'source.drain', 'sources:restore-finish': 'source.restore.finish',
  'sources:restore-discard': 'source.restore.discard',
  'local:create': 'local.create', 'local:start': 'local.start', 'local:open': 'local.open',
  'local:stop': 'local.stop', 'local:memory': 'local.memory', 'local:port': 'local.port',
  'local:remote': 'local.remote', 'local:remote-check': 'local.remote-check',
  'local:models': 'local.models', 'local:company': 'local.company', 'local:vault': 'local.vault',
  'local:journal': 'local.journal', 'local:backup-configure': 'backup.configure',
  'local:backup-prune': 'backup.prune', 'local:backup-run': 'backup.run',
  'local:backup-inspect': 'backup.inspect', 'local:backup-restore': 'backup.restore',
  'local:recovery-use': 'recovery.use',
}

export function desktopIpcSelection(channel: string, arguments_: unknown[]): { action: string; input: Record<string, unknown> } | null {
  if (Object.hasOwn(desktopIpcOrigins, channel)) return { action: desktopIpcOrigins[channel], input: {} }
  const action = arguments_[0]
  if (channel === 'hosts:action' && typeof action === 'string' && ['host.create', 'host.enroll', 'host.forget'].includes(action)) return { action, input: {} }
  if (channel !== 'sources:control' || typeof action !== 'string' || !['pause', 'sync', 'remove', 'repair'].includes(action)) return null
  const value = arguments_[1]
  const enabled = value && typeof value === 'object' && 'enabled' in value ? value.enabled : undefined
  return { action: 'source.' + action, input: typeof enabled === 'boolean' ? { enabled } : {} }
}

export async function measureDesktop<T>(store: WorkflowStore, action: string, input: Record<string, unknown>, surface: 'desktop' | 'native_agent', run: () => T | Promise<T>): Promise<T> {
  let measurement: TelemetryWorkflow | null = null
  let selection: ReturnType<typeof desktopTelemetrySelection> = null
  try {
    selection = desktopTelemetrySelection(action, input)
    if (selection && store.available) {
      // Slow, blocked or unavailable optional privacy I/O cannot hold an app
      // action for the helper's timeout. A late snapshot produces no sample.
      let timer: ReturnType<typeof setTimeout> | undefined
      try { measurement = await Promise.race([TelemetryWorkflow.begin(store, selection.workflow, surface),
        new Promise<null>(resolve => { timer = setTimeout(() => resolve(null), 25) })]) }
      finally { if (timer) clearTimeout(timer) }
    }
  } catch { /* Keep the original action available without telemetry. */ }
  let result: T
  try { result = await run() }
  catch (error) {
    // An exception message can contain a path or provider response. It is
    // deliberately not classified or passed to the measurement boundary.
    void measurement?.finish('failed', 'other_failure')
    throw error
  }
  try {
    let outcome = selection?.completion ?? 'accepted', reason = 'none'
    if (selection?.localStatus && result && typeof result === 'object' && 'state' in result && result.state === 'error') {
      outcome = 'failed'; reason = 'other_failure'
    }
    if (action === 'local.stop' && (result === false || (result && typeof result === 'object' && 'stopped' in result && result.stopped === false))) {
      outcome = 'deferred'; reason = 'host_busy'
    }
    void measurement?.finish(outcome, reason)
  } catch { /* Unexpected result shape must not change the original result. */ }
  return result
}
