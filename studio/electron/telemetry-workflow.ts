/** Fixed local observations only. Never pass requests, results or errors here. */
import type { TelemetryStamp } from '../shared/product-telemetry.js'
import type { TelemetryCatalog } from './telemetry-catalog.js'

const monotonicNow = () => performance.now()

export type WorkflowStore = {
  readonly available: boolean
  readonly catalog: TelemetryCatalog
  snapshot(workflow?: string, surface?: string): Promise<TelemetryStamp | null> | null
  recordMany(values: unknown[], stamp: TelemetryStamp): Promise<boolean>
}

export class TelemetryWorkflow {
  private finished = false
  private readonly started: number
  protected constructor(
    private readonly store: WorkflowStore,
    private readonly stamp: TelemetryStamp,
    private readonly workflow: string,
    private readonly surface: string,
    private readonly clock: () => number,
    started = clock(),
  ) { this.started = started }

  static begin(store: WorkflowStore, workflow: string, surface: string, clock = monotonicNow): Promise<TelemetryWorkflow | null> | null {
    try {
      if (!store.available || !store.catalog.workflows.includes(workflow) || !store.catalog.specification.surfaces.includes(surface)) return null
      const started = clock()
      const pending = store.snapshot(workflow, surface)
      if (pending === null) return null
      return pending.then(stamp => stamp && Number.isInteger(stamp.revision) && typeof stamp.store_generation === 'string' && /^[0-9a-f]{32}$/.test(stamp.store_generation)
        ? new TelemetryWorkflow(store, { ...stamp }, workflow, surface, clock, started) : null).catch(() => null)
    } catch { return null }
  }

  discard(): void { this.finished = true }

  async resources(samples: { metric: string; value: number }[]): Promise<void> {
    if (this.finished) return
    try {
      if (!Array.isArray(samples) || !samples.length || samples.length > 2) return
      const values = samples.map(sample => ({ kind: 'resource', metric: sample.metric, value: sample.value }))
      for (const value of values) this.store.catalog.validateObservation(value)
      await this.store.recordMany(values, this.stamp)
    } catch { /* Unavailable sensors and optional storage never affect work. */ }
  }

  finish(outcome: string, reason = 'none', metrics: Record<string, number> = {}): Promise<void> {
    return this.complete(this.workflow, outcome, reason, metrics)
  }

  /** A known completion with no observable phase start must not invent a duration. */
  finishObserved(outcome: string, reason = 'none'): Promise<void> {
    return this.complete(this.workflow, outcome, reason, {}, false)
  }

  /** Capture callback completion before waiting for the original policy read. */
  finishAt(completedAt: number, outcome: string, reason = 'none'): Promise<void> {
    if (!Number.isFinite(completedAt) || completedAt < this.started) { this.discard(); return Promise.resolve() }
    return this.complete(this.workflow, outcome, reason, {}, true, completedAt)
  }

  protected async complete(workflow: string, outcome: string, reason: string, metrics: Record<string, number>, timed = true, completedAt?: number): Promise<void> {
    if (this.finished) return
    this.finished = true
    try {
      if (Object.keys(metrics).some(key => key === 'latency_ms' || !Object.hasOwn(this.store.catalog.specification.metrics, key))) return
      const result = { kind: 'outcome', workflow, surface: this.surface, outcome, reason,
        ...metrics, ...(timed ? { latency_ms: Math.max(0, (completedAt ?? this.clock()) - this.started) } : {}) }
      // Validate before admitting even the submission. The store immediately
      // turns these primitives into fixed numeric cells before its first await.
      this.store.catalog.validateObservation(result)
      await this.store.recordMany([{ kind: 'submission', workflow, surface: this.surface }, result], this.stamp)
    } catch { /* An optional measurement never changes the original action. */ }
  }
}

/** Classify one operation using its original permission and time, never a
 * second snapshot after the result. Only the declared choices are admissible. */
export class TelemetryWorkflowChoice extends TelemetryWorkflow {
  private constructor(store: WorkflowStore, stamp: TelemetryStamp, private readonly choices: readonly string[], surface: string, clock: () => number, started: number) {
    super(store, stamp, choices[0], surface, clock, started)
  }

  static choose(store: WorkflowStore, choices: readonly string[], surface: string, clock = monotonicNow): Promise<TelemetryWorkflowChoice | null> | null {
    try {
      if (!store.available || !Array.isArray(choices) || choices.length < 2 || choices.length > 4 ||
        new Set(choices).size !== choices.length || !choices.every(name => store.catalog.workflows.includes(name)) ||
        !store.catalog.specification.surfaces.includes(surface)) return null
      const fixed = Object.freeze([...choices])
      const started = clock()
      // No single-category exhaustion hint can stand for the other choices.
      // recordMany enforces the selected category's atomic contribution limit.
      const pending = store.snapshot()
      if (pending === null) return null
      return pending.then(stamp => stamp && Number.isInteger(stamp.revision) && typeof stamp.store_generation === 'string' && /^[0-9a-f]{32}$/.test(stamp.store_generation)
        ? new TelemetryWorkflowChoice(store, { ...stamp }, fixed, surface, clock, started) : null).catch(() => null)
    } catch { return null }
  }

  finishChoice(choice: string, outcome: string, reason = 'none', metrics: Record<string, number> = {}): Promise<void> {
    if (!this.choices.includes(choice)) { this.discard(); return Promise.resolve() }
    return this.complete(choice, outcome, reason, metrics)
  }
}
