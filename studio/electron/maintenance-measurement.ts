/** Owned device work only. No logs, identifiers, versions or remote job history. */
import { TelemetryWorkflow, TelemetryWorkflowChoice, type WorkflowStore } from './telemetry-workflow.js'

export type MaintenanceStore = () => WorkflowStore
const workflows = new Set(['sources.scan', 'capture.collect', 'update.download', 'update.apply'])

export async function beginMaintenance(store: MaintenanceStore | undefined, workflow: string): Promise<TelemetryWorkflow | null> {
  if (!store || !workflows.has(workflow)) return null
  let timer: ReturnType<typeof setTimeout> | undefined
  try {
    const pending = workflow === 'capture.collect'
      ? TelemetryWorkflowChoice.choose(store(), ['capture.collect', 'capture.deliver'], 'desktop')
      : TelemetryWorkflow.begin(store(), workflow, 'desktop')
    if (pending === null) return null
    return await Promise.race([pending,
      new Promise<null>(resolve => { timer = setTimeout(() => resolve(null), 25) })])
  } catch { return null }
  finally { if (timer) clearTimeout(timer) }
}

type SourceResult = {
  completed: boolean; changed: number; removed: number; conflicts: number; remote_sync_available: boolean
  capture?: { locally_accepted: number; pending_events: number; remote_committed_events: number;
    newly_stored_events?: number | null;
    database_bytes: number; capture_complete: boolean; delivery_complete: boolean; reason_code?: string | null }
}

export function finishSource(measurement: TelemetryWorkflow | null, report: SourceResult, resources?: { rss: number; limit: number }): void {
  if (!measurement) return
  try {
    const capture = report.capture
    if (capture && !(measurement instanceof TelemetryWorkflowChoice)) { measurement.discard(); return }
    const fresh = capture && Number.isSafeInteger(capture.newly_stored_events) &&
      capture.newly_stored_events! >= 0 && capture.newly_stored_events! <= capture.remote_committed_events
      ? capture.newly_stored_events! : undefined
    const worked = capture ? capture.locally_accepted + (fresh ?? 0)
      : report.changed + report.removed + report.conflicts
    // A timer finding nothing new is not a user action or a completed work item.
    if (report.completed && worked === 0) { measurement.discard(); return }
    const metrics: Record<string, number> = capture
      ? { work_items: capture.locally_accepted, queue_items: capture.pending_events, stored_bytes: capture.database_bytes,
        ...(fresh !== undefined ? { result_items: fresh } : {}) }
      : { work_items: report.changed + report.removed, result_items: report.changed }
    const denied = capture?.reason_code === 'capture_authorization_revoked'
    const outcome = report.completed ? 'success' : denied ? 'denied' : 'deferred'
    const reason = report.completed ? 'none' : denied ? 'authorization' : !report.remote_sync_available ? 'offline' : 'other_failure'
    // These samples describe only this owned worker, never host-wide totals.
    if (resources && resources.rss > 0) void measurement.resources([
      { metric: 'rss_bytes', value: resources.rss }, { metric: 'resource_budget_bytes', value: resources.limit },
    ])
    if (capture && measurement instanceof TelemetryWorkflowChoice) {
      const choice = capture.locally_accepted === 0 && fresh !== undefined && fresh > 0 ? 'capture.deliver' : 'capture.collect'
      void measurement.finishChoice(choice, outcome, reason, metrics)
    } else void measurement.finish(outcome, reason, metrics)
  } catch { measurement.discard() }
}

/** A download including its retry/verification steps has one terminal outcome. */
export class UpdateMeasurement {
  private download?: Promise<TelemetryWorkflow | null>
  constructor(private readonly store?: MaintenanceStore) {}
  downloading(): void { this.download ??= beginMaintenance(this.store, 'update.download') }
  finish(outcome: 'success' | 'failed' | 'cancelled'): void {
    const pending = this.download
    this.download = undefined
    void pending?.then(value => value?.finish(outcome, outcome === 'failed' ? 'other_failure' : 'none')).catch(() => {})
  }
  discard(): void {
    const pending = this.download
    this.download = undefined
    void pending?.then(value => value?.discard()).catch(() => {})
  }
  applying(): Promise<TelemetryWorkflow | null> { return beginMaintenance(this.store, 'update.apply') }
}
