/** Numeric catalog coordinates shared by native and browser producers.
 * The reviewed catalog is supplied by the caller; observations never supply it.
 * No request/result/exception object may enter this boundary.
 */
type Metric = { group: string; unit: string; upper_bounds: number[]; families?: string | string[] }
export type MeasurementCatalog = {
  version: number
  surfaces: string[]
  workflows: Record<string, string[]>
  workflow_order?: string[]
  workflow_counts?: Record<string, number>
  outcomes: string[]
  reasons: string[]
  metrics: Record<string, Metric>
  resource_metrics: Record<string, Metric>
  limits: { observations_per_workflow_day: number; resource_observations_per_day: number; count_per_cell_day: number; cells_per_observation: number }
}
export type CellDescription = { workflow?: string; surface?: string; metric: string; group: string; bucket?: string | number; unit?: string }
export type EncodedObservation = { scope: number; cells: number[] }
const invalid = () => new Error('telemetry_invalid_measurement')
const isObject = (value: unknown): value is Record<string, unknown> => Boolean(value) && typeof value === 'object' && !Array.isArray(value)

export class TelemetryCatalog {
  readonly workflows: string[]
  private readonly workflowFamilies: string[]
  private readonly slots: [string, number, Metric][]
  private readonly outcomeFields: string[]
  private readonly resources: [string, Metric][]
  private readonly resourceNames: string[]
  constructor(readonly specification: MeasurementCatalog) {
    // These are release-owned definitions, not consent or measurement values.
    // Reuse their lookup arrays while policy and queue authority stay fresh.
    if (![1, 2].includes(specification.version)) throw invalid()
    this.workflows = specification.version === 1
      ? Object.entries(specification.workflows).flatMap(([family, operations]) => operations.map(operation => `${family}.${operation}`))
      : specification.workflow_order?.slice() || []
    this.workflowFamilies = this.workflows.map(workflow => workflow.split('.')[0])
    if (!this.workflows.length || new Set(this.workflows).size !== this.workflows.length ||
        Object.values(specification.workflows).reduce((count, operations) => count + operations.length, 0) !== this.workflows.length ||
        this.workflows.some(workflow => {
          const parts = workflow.split('.')
          return parts.length !== 2 || !specification.workflows[parts[0]]?.includes(parts[1])
        }) || (specification.version === 2 && specification.workflow_counts?.['2'] !== this.workflows.length)) throw invalid()
    let offset = 1 + specification.outcomes.length + specification.reasons.length
    this.slots = Object.entries(specification.metrics).map(([name, metric]) => {
      const result: [string, number, Metric] = [name, offset, metric]
      offset += metric.upper_bounds.length
      return result
    })
    this.outcomeFields = ['kind', 'workflow', 'surface', 'outcome', 'reason', ...this.slots.map(([name]) => name)]
    this.resources = Object.entries(specification.resource_metrics)
    this.resourceNames = this.resources.map(([name]) => name)
    if (specification.surfaces.length !== 4 || offset > 128 || this.workflows.length * 512 > 61440) throw invalid()
  }

  bucket(value: unknown, bounds: number[]): number {
    if (typeof value !== 'number' || !Number.isFinite(value) || value < 0 || value > Number.MAX_SAFE_INTEGER) throw invalid()
    for (let index = 0; index < bounds.length; index++) if (value <= bounds[index]) return index
    return bounds.length - 1
  }

  observation(value: unknown): EncodedObservation {
    return this.walk(value, true)
  }

  /** Same refusal as observation(), without a cell list or encoded object to discard. */
  validateObservation(value: unknown): void {
    this.walk(value, false)
  }

  private walk(value: unknown, encode: true): EncodedObservation
  private walk(value: unknown, encode: false): void
  private walk(value: unknown, encode: boolean): EncodedObservation | void {
    if (!isObject(value) || typeof value.kind !== 'string') throw invalid()
    const catalog = this.specification
    if (value.kind === 'resource') {
      if (Object.keys(value).length !== 3 || !Object.hasOwn(value, 'metric') || !Object.hasOwn(value, 'value') ||
          typeof value.metric !== 'string') throw invalid()
      const index = this.resourceNames.indexOf(value.metric)
      if (index < 0) throw invalid()
      const bucket = this.bucket(value.value, this.resources[index][1].upper_bounds)
      if (!encode) return
      return { scope: 512 + index, cells: [61440 + index * 16 + bucket] }
    }
    if (!['submission', 'outcome'].includes(value.kind) || typeof value.workflow !== 'string' || typeof value.surface !== 'string') throw invalid()
    const workflow = this.workflows.indexOf(value.workflow), surface = catalog.surfaces.indexOf(value.surface)
    if (workflow < 0 || surface < 0) throw invalid()
    const scope = workflow * 4 + surface, base = scope * 128
    if (value.kind === 'submission') {
      if (Object.keys(value).length !== 3) throw invalid()
      if (!encode) return
      return { scope, cells: [base] }
    }
    if (Object.keys(value).some(key => !this.outcomeFields.includes(key)) || typeof value.outcome !== 'string' ||
        !catalog.outcomes.includes(value.outcome)) throw invalid()
    const reason = value.reason === undefined ? 'none' : value.reason
    if (typeof reason !== 'string' || !catalog.reasons.includes(reason) || (reason !== 'none' && ['success', 'accepted'].includes(value.outcome))) throw invalid()
    // Counting is enough to enforce the cell limit. The array exists only for the encoder.
    const cells = encode ? [base + 1 + catalog.outcomes.indexOf(value.outcome)] : undefined
    let count = 1
    if (reason !== 'none') {
      count += 1
      cells?.push(base + 1 + catalog.outcomes.length + catalog.reasons.indexOf(reason))
    }
    const family = this.workflowFamilies[workflow]
    for (const [name, offset, metric] of this.slots) {
      if (!Object.hasOwn(value, name)) continue
      if (metric.families !== 'all' && !metric.families?.includes(family)) throw invalid()
      const bucket = this.bucket(value[name], metric.upper_bounds)
      count += 1
      if (cells) cells.push(base + offset + bucket)
    }
    if (count > catalog.limits.cells_per_observation) throw invalid()
    if (cells) return { scope, cells }
  }

  describe(cell: number): CellDescription {
    return this.decode(cell, true) as CellDescription
  }

  /** Validate a coordinate without constructing a full preview description. */
  group(cell: number): string {
    return this.decode(cell, false) as string
  }

  private decode(cell: number, detailed: boolean): CellDescription | string {
    if (!Number.isInteger(cell) || cell < 0 || cell > 65535) throw invalid()
    const catalog = this.specification
    if (cell >= 61440) {
      const index = Math.floor((cell - 61440) / 16), offset = (cell - 61440) % 16
      const entry = this.resources[index]
      if (!entry || offset >= entry[1].upper_bounds.length) throw invalid()
      return detailed ? { metric: entry[0], group: entry[1].group, bucket: offset, unit: entry[1].unit } : entry[1].group
    }
    const workflow = Math.floor(cell / 512), surface = Math.floor((cell % 512) / 128), offset = cell % 128
    if (workflow >= this.workflows.length) throw invalid()
    const context = detailed ? { workflow: this.workflows[workflow], surface: catalog.surfaces[surface] } : undefined
    if (offset === 0) return detailed ? { ...context, metric: 'submissions', group: 'usage' } : 'usage'
    if (offset <= catalog.outcomes.length) return detailed
      ? { ...context, metric: 'outcomes', group: 'usage', bucket: catalog.outcomes[offset - 1] } : 'usage'
    const reason = offset - 1 - catalog.outcomes.length
    if (reason >= 0 && reason < catalog.reasons.length) {
      if (reason === 0) throw invalid()
      return detailed ? { ...context, metric: 'reasons', group: 'reliability', bucket: catalog.reasons[reason] } : 'reliability'
    }
    const family = this.workflowFamilies[workflow]
    for (const [name, start, metric] of this.slots) {
      if (offset < start || offset >= start + metric.upper_bounds.length) continue
      if (metric.families !== 'all' && !metric.families?.includes(family)) throw invalid()
      return detailed ? { ...context, metric: name, group: metric.group, bucket: offset - start, unit: metric.unit } : metric.group
    }
    throw invalid()
  }
}
