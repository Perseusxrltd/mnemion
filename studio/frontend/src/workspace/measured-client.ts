/** Studio ownership only; the reusable SDK never enables analytics itself. */
import { MnemionClient, MnemionError } from '@mnemion/client'
import controls from '../../../../mnemion/product_telemetry/control-origins.json'
import methods from '../../../../mnemion/product_telemetry/studio-methods.json'
import { TelemetryWorkflow, type WorkflowStore } from '../../../electron/telemetry-workflow'
import { productWorkflowStore, telemetrySurface } from './telemetry-policy'

type Selection = { workflow: string; completion: string; fresh: boolean }
type Control = { workflow?: string; variants?: Record<string, string>; completion?: string; fresh_receipt?: boolean; exclusion?: string }

export function studioMeasurementSelection(method: string, arguments_: unknown[]): Selection | null {
  const name = Object.hasOwn(methods.methods, method) ? methods.methods[method as keyof typeof methods.methods] : null
  if (!name) return null
  const spec: Control = controls.operations[name as keyof typeof controls.operations]
  if (!spec || spec.exclusion) return null
  const index = methods.variant_arguments[method as keyof typeof methods.variant_arguments]
  const variant = typeof index === 'number' ? arguments_[index] : undefined
  const workflow = spec.variants
    ? (typeof variant === 'string' && Object.hasOwn(spec.variants, variant) ? spec.variants[variant] : null) : spec.workflow
  return workflow && spec.completion ? { workflow, completion: spec.completion, fresh: spec.fresh_receipt === true } : null
}

async function observed<T>(client: MnemionClient, store: WorkflowStore, method: string, arguments_: unknown[], run: () => Promise<T>, surface: 'desktop' | 'browser'): Promise<T> {
  let selection: Selection | null = null, measurement: TelemetryWorkflow | null = null
  try {
    selection = studioMeasurementSelection(method, arguments_)
    if (selection && store.available) {
      let timer: ReturnType<typeof setTimeout> | undefined
      try { measurement = await Promise.race([TelemetryWorkflow.begin(store, selection.workflow, surface),
        new Promise<null>(resolve => { timer = setTimeout(() => resolve(null), 25) })]) }
      finally { if (timer) clearTimeout(timer) }
    }
  } catch { /* Optional collection cannot prevent the user's action. */ }
  let result: T
  try { result = await run() }
  catch (error) {
    try {
      if (selection?.fresh && client.idempotencyOf(error) !== 'new') measurement?.discard()
      else {
        let outcome = 'failed', reason = 'other_failure'
        if (error instanceof MnemionError) {
          if ([401, 403].includes(error.status)) { outcome = 'denied'; reason = 'authorization' }
          else if ([400, 422].includes(error.status)) reason = 'invalid_input'
          else if (error.status === 409) reason = 'conflict'
          else if (error.code === 'inference_busy') { outcome = 'deferred'; reason = 'resource_pressure' }
          else if (error.code === 'tunnel_offline') reason = 'offline'
        }
        void measurement?.finish(outcome, reason)
      }
    } catch { /* Never forward the exception, request ID or response text. */ }
    throw error
  }
  try {
    const disposition = client.idempotencyOf(result)
    if (disposition === 'replayed' || (selection?.fresh && disposition !== 'new')) measurement?.discard()
    else if (selection) {
      const metrics: Record<string, number> = {}
      // Only these exact numeric sensors are reviewed. In particular, vault
      // contents, counts and sizes never become performance measurements.
      if (result && typeof result === 'object') {
        if (selection.workflow === 'memory.recall' && 'hits' in result && Array.isArray(result.hits)) metrics.result_items = result.hits.length
        if (selection.workflow === 'memory.context' && 'citations' in result && Array.isArray(result.citations)) metrics.result_items = result.citations.length
        if (['memory.export', 'evaluation.export', 'memory.read'].includes(selection.workflow) && result instanceof ArrayBuffer) metrics.payload_bytes_received = result.byteLength
      }
      void measurement?.finish(selection.completion, 'none', metrics)
    }
  } catch { /* An unfamiliar result never changes the delivered result. */ }
  return result
}

const wrapped = new WeakSet<MnemionClient>()
export function measuredStudioClient(client: MnemionClient, store: WorkflowStore = productWorkflowStore, surface: 'desktop' | 'browser' = telemetrySurface()): MnemionClient {
  if (wrapped.has(client)) return client
  const bound = new Map<PropertyKey, unknown>()
  const result = new Proxy(client, {
    get(target, property) {
      const value = Reflect.get(target, property, target)
      if (typeof value !== 'function' || property === 'constructor') return value
      if (!bound.has(property)) {
        const run = value.bind(target)
        bound.set(property, typeof property === 'string' && Object.hasOwn(methods.methods, property)
          ? (...args: unknown[]) => observed(target, store, property, args, () => run(...args), surface) : run)
      }
      return bound.get(property)
    },
  })
  wrapped.add(result)
  return result
}
