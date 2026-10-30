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

const OBSERVATION_LIMIT = 255
type ObservationTally = {
  snapshot_admitted: number
  snapshot_null: number
  snapshot_rejected: number
  snapshot_deadline: number
  snapshot_elapsed_lt_5: number
  snapshot_elapsed_lt_25: number
  snapshot_elapsed_ge_25: number
}

function deliveryObservationEnabled(): boolean {
  if (typeof window === 'undefined' || typeof globalThis === 'undefined') return false
  return typeof window.mnemion?.observationDiagnostic === 'function'
}

function observationTally(): ObservationTally | null {
  if (!deliveryObservationEnabled()) return null
  const holder = globalThis as typeof globalThis & { __mnObservationDiagnostic?: ObservationTally }
  holder.__mnObservationDiagnostic ??= {
    snapshot_admitted: 0, snapshot_null: 0, snapshot_rejected: 0, snapshot_deadline: 0,
    snapshot_elapsed_lt_5: 0, snapshot_elapsed_lt_25: 0, snapshot_elapsed_ge_25: 0,
  }
  return holder.__mnObservationDiagnostic
}

function tallyObservation(outcome: 'admitted' | 'null' | 'rejected' | 'deadline', elapsed: number): void {
  const counts = observationTally()
  if (!counts) return
  const name = outcome === 'admitted' ? 'snapshot_admitted' : outcome === 'null' ? 'snapshot_null' : outcome === 'rejected' ? 'snapshot_rejected' : 'snapshot_deadline'
  if (counts[name] < OBSERVATION_LIMIT) counts[name] += 1
  const bucket = Number.isFinite(elapsed) && elapsed >= 0 && elapsed < 5 ? 'snapshot_elapsed_lt_5'
    : Number.isFinite(elapsed) && elapsed >= 0 && elapsed < 25 ? 'snapshot_elapsed_lt_25'
    : 'snapshot_elapsed_ge_25'
  if (counts[bucket] < OBSERVATION_LIMIT) counts[bucket] += 1
}

async function observed<T>(client: MnemionClient, store: WorkflowStore, method: string, arguments_: unknown[], run: () => Promise<T>, surface: 'desktop' | 'browser'): Promise<T> {
  let selection: Selection | null = null, measurement: TelemetryWorkflow | null = null
  let outcome: 'admitted' | 'null' | 'rejected' | 'deadline' | null = null
  let elapsed = 0
  const diagnose = deliveryObservationEnabled()
  try {
    selection = store.available ? studioMeasurementSelection(method, arguments_) : null
    if (selection) {
      const pending = TelemetryWorkflow.begin(store, selection.workflow, surface)
      if (pending !== null) {
        let timer: ReturnType<typeof setTimeout> | undefined
        let deadline = false
        const clock = diagnose && typeof performance !== 'undefined' && typeof performance.now === 'function'
        let started = 0
        try {
          if (clock) started = performance.now()
          measurement = await Promise.race([pending,
            new Promise<null>(resolve => { timer = setTimeout(() => { deadline = true; resolve(null) }, 25) })])
        } finally {
          if (timer) clearTimeout(timer)
          if (clock) {
            try { elapsed = performance.now() - started } catch { elapsed = Number.POSITIVE_INFINITY }
          } else if (diagnose) elapsed = Number.POSITIVE_INFINITY
        }
        outcome = deadline && !measurement ? 'deadline' : measurement ? 'admitted' : 'null'
      } else outcome = 'null'
    }
  } catch {
    outcome = 'rejected'
    measurement = null
  }
  if (diagnose && outcome) {
    try { tallyObservation(outcome, elapsed) } catch { /* Diagnosis never changes the action. */ }
  }
  // A refused or expired observation has no reason to inspect the result,
  // retry receipt or exception. Run outside the optional-work catch so a
  // synchronous action failure cannot invoke the callback a second time.
  if (!measurement || !selection) return run()
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
