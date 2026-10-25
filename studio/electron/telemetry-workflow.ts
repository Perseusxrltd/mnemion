/** Fixed local observations only. Never pass requests, results or errors here. */
import type { TelemetryStamp } from '../shared/product-telemetry.js'
import type { TelemetryCatalog } from './telemetry-catalog.js'

const monotonicNow = () => performance.now()

export type WorkflowStore = {
  readonly available: boolean
  readonly catalog: TelemetryCatalog
  snapshot(workflow?: string, surface?: string): Promise<TelemetryStamp | null>
  recordMany(values: unknown[], stamp: TelemetryStamp): Promise<boolean>
}

export class TelemetryWorkflow {
  private finished = false
  private readonly started: number
  private constructor(
    private readonly store: WorkflowStore,
    private readonly stamp: TelemetryStamp,
    private readonly workflow: string,
    private readonly surface: string,
    private readonly clock: () => number,
  ) { this.started = clock() }

  static async begin(store: WorkflowStore, workflow: string, surface: string, clock = monotonicNow): Promise<TelemetryWorkflow | null> {
    try {
      if (!store.available || !store.catalog.workflows.includes(workflow) || !store.catalog.specification.surfaces.includes(surface)) return null
      const stamp = await store.snapshot(workflow, surface)
      return stamp && Number.isInteger(stamp.revision) && typeof stamp.store_generation === 'string' && /^[0-9a-f]{32}$/.test(stamp.store_generation)
        ? new TelemetryWorkflow(store, { ...stamp }, workflow, surface, clock) : null
    } catch { return null }
  }

  discard(): void { this.finished = true }

  async resources(samples: { metric: string; value: number }[]): Promise<void> {
    if (this.finished) return
    try {
      if (!Array.isArray(samples) || !samples.length || samples.length > 2) return
      const values = samples.map(sample => ({ kind: 'resource', metric: sample.metric, value: sample.value }))
      for (const value of values) this.store.catalog.observation(value)
      await this.store.recordMany(values, this.stamp)
    } catch { /* Unavailable sensors and optional storage never affect work. */ }
  }

  async finish(outcome: string, reason = 'none', metrics: Record<string, number> = {}): Promise<void> {
    if (this.finished) return
    this.finished = true
    try {
      if (Object.keys(metrics).some(key => key === 'latency_ms' || !Object.hasOwn(this.store.catalog.specification.metrics, key))) return
      const result = { kind: 'outcome', workflow: this.workflow, surface: this.surface, outcome, reason,
        ...metrics, latency_ms: Math.max(0, this.clock() - this.started) }
      // Validate before admitting even the submission. The store immediately
      // turns these primitives into fixed numeric cells before its first await.
      this.store.catalog.observation(result)
      await this.store.recordMany([{ kind: 'submission', workflow: this.workflow, surface: this.surface }, result], this.stamp)
    } catch { /* An optional measurement never changes the original action. */ }
  }
}
