import measurementCatalog from '../../../../mnemion/product_telemetry/catalog.json'
import { TelemetryCatalog } from '../../../electron/telemetry-catalog'

export const telemetryCatalog = new TelemetryCatalog(measurementCatalog)
export type PendingCell = { cell: number; count: number; window_day: number }
type Contribution = { scope: number; count: number; window_day: number }
export type PendingState = { catalog_version: number; entries: PendingCell[]; contributions: Contribution[] }
const invalid = () => new Error('telemetry_storage_unavailable')
const object = (value: unknown): value is Record<string, unknown> => Boolean(value) && typeof value === 'object' && !Array.isArray(value)
const integer = (value: unknown, maximum: number, minimum = 0): value is number => typeof value === 'number' && Number.isInteger(value) && value >= minimum && value <= maximum
const workflowCounts: Record<string, number> = measurementCatalog.workflow_counts

export function pendingState(raw: string | null): PendingState {
  if (raw === null) return { catalog_version: measurementCatalog.version, entries: [], contributions: [] }
  // Check the string bound before encoding/parsing an untrusted local file.
  if (raw.length > 131072 || new TextEncoder().encode(raw).byteLength > 262144) throw invalid()
  const value: unknown = JSON.parse(raw)
  if (!object(value) || Object.keys(value).length !== 3 || !integer(value.catalog_version, measurementCatalog.version, 1) ||
      !integer(workflowCounts[String(value.catalog_version)], telemetryCatalog.workflows.length, 1) ||
      !Array.isArray(value.entries) || !Array.isArray(value.contributions) ||
      value.entries.length > 512 || value.contributions.length > 512) throw invalid()
  const workflowCount = workflowCounts[String(value.catalog_version)]
  const cells = new Set<number>(), scopes = new Set<number>()
  for (const row of value.entries) {
    if (!object(row) || Object.keys(row).length !== 3 || !integer(row.cell, 65535) ||
        !integer(row.count, 255, 1) || !integer(row.window_day, 1000000) || cells.has(row.cell) ||
        (row.cell < 61440 && Math.floor(row.cell / 512) >= workflowCount)) throw invalid()
    telemetryCatalog.group(row.cell)
    cells.add(row.cell)
  }
  for (const row of value.contributions) {
    if (!object(row) || Object.keys(row).length !== 3 || !integer(row.scope, 1023) ||
        !integer(row.count, 64, 1) || !integer(row.window_day, 1000000) || scopes.has(row.scope) ||
        (row.scope >= workflowCount * 4 &&
          (row.scope < 512 || row.scope >= 512 + Object.keys(measurementCatalog.resource_metrics).length))) throw invalid()
    scopes.add(row.scope)
  }
  return value as PendingState
}

/** Caller holds the shared privacy Web Lock and rechecks current policy. */
export function collect(state: PendingState, input: unknown, day: number, groups: string[]): { state: PendingState; recorded: boolean } {
  if (!integer(day, 1000000)) throw invalid()
  const { scope, cells } = telemetryCatalog.observation(input)
  const entries = state.entries.filter(row => row.window_day >= day - 1 && row.window_day <= day && groups.includes(telemetryCatalog.group(row.cell)))
  const contributions = state.contributions.filter(row => row.window_day === day)
  const filtered = cells.filter(cell => groups.includes(telemetryCatalog.group(cell)))
  const next = { catalog_version: measurementCatalog.version, entries, contributions }
  const prior = contributions.find(row => row.scope === scope)
  const limit = scope >= 512 ? measurementCatalog.limits.resource_observations_per_day : measurementCatalog.limits.observations_per_workflow_day
  if (!filtered.length || (prior && prior.count >= limit) || new Set([...entries.map(row => row.cell), ...filtered]).size > 512) return { state: next, recorded: false }
  if (prior) prior.count++
  else contributions.push({ scope, count: 1, window_day: day })
  for (const cell of filtered) {
    const row = entries.find(row => row.cell === cell)
    if (row) { row.count = row.window_day === day ? Math.min(row.count + 1, 255) : 1; row.window_day = day }
    else entries.push({ cell, count: 1, window_day: day })
  }
  return { state: next, recorded: true }
}
