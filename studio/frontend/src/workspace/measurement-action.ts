/** App-owned actions only. The callback keeps all private inputs and results. */
import origins from '../../../../mnemion/product_telemetry/ui-origins.json'
import { TelemetryWorkflow, type WorkflowStore } from '../../../electron/telemetry-workflow'
import { productWorkflowStore, telemetrySurface } from './telemetry-policy'

type Spec = { workflow: string; completion: string; result_flag?: string }
export const uiMeasurementOrigins = origins

export async function measureUiAction<T>(
  boundary: 'browser' | 'legacy', action: string, run: () => T | Promise<T>, signal?: AbortSignal,
  store: WorkflowStore = productWorkflowStore, surface: 'desktop' | 'browser' = telemetrySurface(),
): Promise<T> {
  let measurement: TelemetryWorkflow | null = null, spec: Spec | undefined
  try {
    const entries: Record<string, Spec> = origins[boundary]
    spec = Object.hasOwn(entries, action) ? entries[action] : undefined
    if (spec && store.available && (boundary !== 'browser' || surface === 'browser')) {
      let timer: ReturnType<typeof setTimeout> | undefined
      try { measurement = await Promise.race([TelemetryWorkflow.begin(store, spec.workflow, surface),
        new Promise<null>(resolve => { timer = setTimeout(() => resolve(null), 25) })]) }
      finally { if (timer) clearTimeout(timer) }
    }
  } catch { /* Optional collection cannot prevent the original action. */ }
  let result: T
  try { result = await run() }
  catch (error) {
    void measurement?.finish(signal?.aborted ? 'cancelled' : 'failed', signal?.aborted ? 'none' : 'other_failure')
    throw error
  }
  try {
    if (signal?.aborted) void measurement?.finish('cancelled')
    else if (spec?.result_flag) {
      const value = result && typeof result === 'object' ? Reflect.get(result, spec.result_flag) : undefined
      if (typeof value === 'boolean') void measurement?.finish(value ? spec.completion : 'failed', value ? 'none' : 'other_failure')
      else measurement?.discard()
    } else if (spec) void measurement?.finish(spec.completion)
  } catch { /* Unfamiliar responses never affect the delivered result. */ }
  return result
}

export function measuredLegacyClient<T extends object>(client: T, store?: WorkflowStore, surface?: 'desktop' | 'browser'): T {
  const bound = new Map<PropertyKey, unknown>()
  return new Proxy(client, { get(target, key) {
    const value = Reflect.get(target, key, target)
    if (typeof value !== 'function' || typeof key !== 'string' || !Object.hasOwn(origins.legacy, key)) return value
    if (!bound.has(key)) bound.set(key, (...args: unknown[]) => measureUiAction('legacy', key, () => value.apply(target, args), undefined, store, surface))
    return bound.get(key)
  } })
}
