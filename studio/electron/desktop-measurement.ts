/** Ownership boundary outside the numeric encoder. Never inspect free text. */
import { readFileSync } from 'node:fs'
import { TelemetryWorkflow, TelemetryWorkflowChoice, type WorkflowStore } from './telemetry-workflow.js'
import { takeWorkspaceSelection, type WorkspaceSelection } from './workspace-selection.js'

type Spec = { workflow?: string; completion?: string; selector?: string; variants?: Record<string, string>; variant_exclusions?: Record<string, string>; local_status?: boolean; fresh_receipt?: boolean; exclusion?: string }
type IpcSpec = { action?: string; actions?: Record<string, string>; exclusion?: string }
export const desktopTelemetryOrigins: { version: number; ownership: string; exclusions: Record<string, string>; operations: Record<string, Spec>; ipc?: Record<string, IpcSpec> } = (() => {
  try { return JSON.parse(readFileSync(new URL('./telemetry-desktop-origins.json', import.meta.url), 'utf8')) }
  catch { return { version: 1, ownership: '', exclusions: {}, operations: {} } }
})()

export function desktopTelemetrySelection(action: string, input: Record<string, unknown>): { workflow: string; completion: string; localStatus: boolean; freshReceipt: boolean; workspaceSelection?: Record<WorkspaceSelection, string> } | null {
  const spec = Object.hasOwn(desktopTelemetryOrigins.operations, action) ? desktopTelemetryOrigins.operations[action] : undefined
  if (!spec || spec.exclusion) return null
  if (spec.selector === 'workspace.selection') {
    const opened = spec.variants?.opened, switched = spec.variants?.switched
    return opened && switched && spec.completion ? { workflow: opened, completion: spec.completion,
      localStatus: false, freshReceipt: false, workspaceSelection: { opened, switched } } : null
  }
  // Only a reviewed boolean or the fixed host-action enum may select a row.
  // Keys, host identity, command arguments and receipt contents are not inputs.
  let variant = spec.selector === 'enabled' && typeof input.enabled === 'boolean' ? String(input.enabled) : null
  if (spec.selector === 'request.action') {
    const request = input.request
    if (request && typeof request === 'object' && !Array.isArray(request) && 'action' in request && typeof request.action === 'string') variant = request.action
  }
  const workflow = spec.variants ? (variant && Object.hasOwn(spec.variants, variant) ? spec.variants[variant] : null) : spec.workflow
  return workflow && spec.completion ? { workflow, completion: spec.completion, localStatus: spec.local_status === true, freshReceipt: spec.fresh_receipt === true } : null
}

/** Only these explicit UI controls own a local action. Polling and the generic
 * service transport have no entry; remote UI workflows own their own scope. */
export const desktopIpcOrigins: Record<string, string> = Object.fromEntries(
  Object.entries(desktopTelemetryOrigins.ipc ?? {}).flatMap(([channel, spec]) =>
    spec.action && !spec.exclusion ? [[channel, spec.action]] : []))

export function desktopIpcSelection(channel: string, arguments_: unknown[]): { action: string; input: Record<string, unknown> } | null {
  if (Object.hasOwn(desktopIpcOrigins, channel)) return { action: desktopIpcOrigins[channel], input: {} }
  const entries = desktopTelemetryOrigins.ipc
  const spec = entries && Object.hasOwn(entries, channel) ? entries[channel] : undefined
  const selected = arguments_[0]
  if (!spec?.actions || spec.exclusion || typeof selected !== 'string' || !Object.hasOwn(spec.actions, selected)) return null
  const action = spec.actions[selected]
  if (desktopTelemetryOrigins.operations[action]?.exclusion) return null
  if (channel === 'hosts:action' && action !== 'host.request') return { action, input: {} }
  if (channel === 'hosts:action' && action === 'host.request') {
    const value = arguments_[1], request = value && typeof value === 'object' && 'request' in value ? value.request : undefined
    if (!request || typeof request !== 'object' || Array.isArray(request) || !('action' in request) || typeof request.action !== 'string') return null
    const input = { request: { action: request.action } }
    return desktopTelemetrySelection(action, input) ? { action, input } : null
  }
  if (channel !== 'sources:control') return null
  const value = arguments_[1]
  const enabled = value && typeof value === 'object' && 'enabled' in value ? value.enabled : undefined
  return { action, input: typeof enabled === 'boolean' ? { enabled } : {} }
}

export async function measureDesktop<T>(store: WorkflowStore, action: string, input: Record<string, unknown>, surface: 'desktop' | 'native_agent', run: () => T | Promise<T>): Promise<T> {
  let measurement: TelemetryWorkflow | null = null
  let selection: ReturnType<typeof desktopTelemetrySelection> = null
  try {
    selection = desktopTelemetrySelection(action, input)
    if (selection && store.available) {
      // Slow, blocked or unavailable optional privacy I/O cannot hold an app
      // action for the helper's timeout. A late snapshot produces no sample.
      const pending = selection.workspaceSelection
        ? TelemetryWorkflowChoice.choose(store, [selection.workspaceSelection.opened, selection.workspaceSelection.switched], surface)
        : TelemetryWorkflow.begin(store, selection.workflow, surface)
      if (pending !== null) {
        let timer: ReturnType<typeof setTimeout> | undefined
        try { measurement = await Promise.race([pending,
          new Promise<null>(resolve => { timer = setTimeout(() => resolve(null), 25) })]) }
        finally { if (timer) clearTimeout(timer) }
      }
    }
  } catch { /* Keep the original action available without telemetry. */ }
  let result: T
  try { result = await run() }
  catch (error) {
    // An exception message can contain a path or provider response. It is
    // deliberately not classified or passed to the measurement boundary.
    if (selection?.freshReceipt) measurement?.discard()
    else void measurement?.finish('failed', 'other_failure')
    throw error
  }
  try {
    if (selection?.freshReceipt) {
      // Only an authenticated fresh intake can contribute. A lost response,
      // legacy host, lookup or replay cannot authorize a second observation.
      const reply = result && typeof result === 'object' && !Array.isArray(result) && Object.hasOwn(result, 'ok') && 'ok' in result && result.ok === true && Object.hasOwn(result, 'result') && 'result' in result ? result.result : null
      if (!reply || typeof reply !== 'object' || Array.isArray(reply) || !Object.hasOwn(reply, 'request_disposition') || !('request_disposition' in reply) || reply.request_disposition !== 'new') {
        measurement?.discard()
        return result
      }
    }
    let outcome = selection?.completion ?? 'accepted', reason = 'none'
    if (action === 'app.preferences') {
      const applied = result && typeof result === 'object' && 'applied' in result ? result.applied : undefined
      if (applied !== true) { outcome = applied === false ? 'failed' : 'unconfirmed'; reason = 'other_failure' }
    }
    if (selection?.localStatus && result && typeof result === 'object' && 'state' in result && result.state === 'error') {
      outcome = 'failed'; reason = 'other_failure'
    }
    if (action === 'local.stop' && (result === false || (result && typeof result === 'object' && 'stopped' in result && result.stopped === false))) {
      outcome = 'deferred'; reason = 'host_busy'
    }
    if (selection?.workspaceSelection) {
      // Consume even when policy refused this action: renewed consent cannot
      // turn a retained result into fresh work. Never inspect its private fields.
      const selected = takeWorkspaceSelection(result)
      if (!selected || !(measurement instanceof TelemetryWorkflowChoice)) measurement?.discard()
      else void measurement.finishChoice(selection.workspaceSelection[selected], outcome, reason)
    } else void measurement?.finish(outcome, reason)
  } catch { /* Unexpected result shape must not change the original result. */ }
  return result
}
