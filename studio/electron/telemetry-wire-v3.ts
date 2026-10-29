/** Fixed v3 summaries shared by the browser and Electron clients.
 * The caller passes the reviewed wire contract and catalog. This module does
 * not read a config file, send a packet, or apply publication noise.
 */
import { TelemetryCatalog, type CellDescription } from './telemetry-catalog.js'
import { secureRandomBelow } from './telemetry-wire.js'

type Metric = {
  id: string
  group: string
  kind: string
  categories?: string[]
  upper_bounds?: number[]
  unit?: string
  wire_index_origin: number
}
type ReleaseSlot = { slot: number; major: number; minor: number; patch: number; id: string }
export type WireV3Contract = {
  version: number
  mechanism: string
  privacy_model: string
  not_v2_local_randomization: boolean
  packet_bytes: number
  version_byte: number
  axis_byte: { release: number; os: number }
  reserved_cohort_byte: number
  axis_rule: {
    name: string
    choices: string[]
    reads_report_contents: boolean
    source: string
    both_axes_in_one_window: boolean
    joined_release_by_os_profile: boolean
  }
  release_allowlist: ReleaseSlot[]
  allowlist_maximum_slots: number
  unlisted_release_id: string
  operating_systems: string[]
  state_bins: string[]
  metrics: Metric[]
  contribution: {
    weight_per_metric: number
    denominator_weight: number
    clip_per_bucket: number
    maximum_observations: number
  }
  privacy: { unit: string; epsilon: string; l1_sensitivity: number }
}
export type WireV3Summary = { axis: 'release' | 'os'; cohortId: string; cohortIndex: number; buckets: number[] }
type RandomBelow = (limit: number) => number
type Weights = Record<string, number[]>

const GROUPS = ['usage', 'reliability', 'performance', 'resources']
const invalid = () => new Error('telemetry_invalid_v3_report')
const integer = (value: unknown, minimum: number, maximum: number): value is number =>
  typeof value === 'number' && Number.isInteger(value) && value >= minimum && value <= maximum
const sameList = (left: readonly unknown[] | undefined, right: readonly unknown[]): boolean =>
  Array.isArray(left) && left.length === right.length && left.every((item, index) => item === right[index])

export class TelemetryWireV3 {
  readonly metrics: Metric[]
  private readonly byCoordinate = new Map<string, ReleaseSlot>()
  private readonly clip: number
  private readonly maximumRows: number

  constructor(readonly specification: WireV3Contract, private readonly catalog: TelemetryCatalog) {
    if (!(catalog instanceof TelemetryCatalog) || catalog.specification.version !== 2) throw invalid()
    const privacy = specification?.privacy
    const contribution = specification?.contribution
    const axis = specification?.axis_rule
    const metrics = specification?.metrics
    if (
      specification?.version !== 3 || specification.not_v2_local_randomization !== true
      || specification.mechanism !== 'bounded_normalized_summary_publication_discrete_laplace'
      || specification.privacy_model !== 'trusted_first_party_aggregation_publication_differential_privacy'
      || specification.packet_bytes !== 25 || specification.version_byte !== 3
      || specification.reserved_cohort_byte !== 0
      || specification.axis_byte?.release !== 1 || specification.axis_byte?.os !== 2
      || !privacy || privacy.epsilon !== 'ln(3)' || privacy.l1_sensitivity !== 20
      || privacy.unit !== 'add_or_remove_one_input_report_including_admission_and_clipping'
      || !contribution || contribution.clip_per_bucket !== 255 || contribution.maximum_observations !== 512
      || contribution.weight_per_metric !== 1 || contribution.denominator_weight !== 1
      || !sameList(specification.state_bins, ['group_disabled', 'sensor_missing'])
      || !sameList(specification.operating_systems, ['windows', 'macos', 'linux', 'other'])
      || specification.unlisted_release_id !== 'unlisted'
      || axis?.name !== 'per_report_secure_coin' || axis.reads_report_contents !== false
      || axis.source !== 'summary_path_secrets_randbelow' || axis.both_axes_in_one_window !== true
      || axis.joined_release_by_os_profile !== false
      || !sameList(axis.choices, ['release', 'os'])
      || !Array.isArray(metrics) || metrics.length !== 19
      || specification.packet_bytes !== 6 + metrics.length
    ) throw invalid()
    this.metrics = metrics
    this.clip = contribution.clip_per_bucket
    this.maximumRows = contribution.maximum_observations
    this.checkAllowlist()
    this.checkMetrics()
  }

  private checkAllowlist(): void {
    const allow = this.specification.release_allowlist
    const limit = this.specification.allowlist_maximum_slots
    if (!Array.isArray(allow) || !integer(limit, 1, 32) || allow.length < 1 || allow.length > limit) throw invalid()
    const seen = new Set<string>()
    for (let slot = 0; slot < allow.length; slot++) {
      const item = allow[slot]
      if (!item || item.slot !== slot || !integer(item.major, 0, 255)
        || !integer(item.minor, 0, 255) || !integer(item.patch, 0, 255)) throw invalid()
      const id = `${item.major}.${item.minor}.${item.patch}`
      if (item.id !== id || seen.has(id) || id === 'unlisted') throw invalid()
      seen.add(id)
      this.byCoordinate.set(id, item)
    }
  }

  private checkMetrics(): void {
    const families: string[] = []
    for (const workflow of this.catalog.workflows) {
      const family = workflow.split('.')[0]
      if (!families.includes(family)) families.push(family)
    }
    const reasons = this.catalog.specification.reasons
    if (!Array.isArray(reasons) || reasons[0] !== 'none') throw invalid()
    const seen = new Set<string>()
    for (const metric of this.metrics) {
      if (!metric || typeof metric.id !== 'string' || seen.has(metric.id) || !GROUPS.includes(metric.group)
        || metric.wire_index_origin !== 2 || this.bins(metric) > 256) throw invalid()
      seen.add(metric.id)
      if (metric.kind === 'categories') {
        const expected = metric.id === 'feature' ? this.catalog.workflows
          : metric.id === 'feature_family' ? families
            : metric.id === 'outcome' ? this.catalog.specification.outcomes
              : metric.id === 'reason' ? ['no_failure', ...reasons.slice(1)]
                : undefined
        if (!expected || !sameList(metric.categories, expected)) throw invalid()
      } else if (metric.kind === 'ordered') {
        const bounds = this.catalog.specification.metrics[metric.id]?.upper_bounds
          ?? this.catalog.specification.resource_metrics[metric.id]?.upper_bounds
        if (!sameList(metric.upper_bounds, bounds ?? []) || !metric.upper_bounds || metric.upper_bounds.length < 2
          || metric.upper_bounds.some((bound, index) => !integer(bound, 0, Number.MAX_SAFE_INTEGER)
            || (index > 0 && bound <= metric.upper_bounds![index - 1]))) throw invalid()
      } else throw invalid()
    }
    for (const id of ['feature_family', 'feature', 'outcome', 'reason']) if (!seen.has(id)) throw invalid()
  }

  private bins(metric: Metric): number {
    const width = metric.kind === 'ordered' ? metric.upper_bounds?.length ?? 0 : metric.categories?.length ?? 0
    return 2 + width
  }

  private draw(limit: number, random: RandomBelow): number {
    const value = random(limit)
    if (!integer(value, 0, limit - 1)) throw invalid()
    return value
  }

  private blank(): Weights {
    return Object.fromEntries(this.metrics.map(metric => [metric.id, new Array(this.bins(metric) - 2).fill(0)]))
  }

  private metric(id: string): Metric {
    const metric = this.metrics.find(item => item.id === id)
    if (!metric) throw invalid()
    return metric
  }

  private add(weights: Weights, id: string, key: unknown, count: number): void {
    const metric = this.metric(id)
    if (!integer(count, 1, Number.MAX_SAFE_INTEGER)) throw invalid()
    let index = -1
    if (metric.kind === 'ordered') {
      if (!integer(key, 0, (metric.upper_bounds?.length ?? 0) - 1)) throw invalid()
      index = key
    } else index = metric.categories?.indexOf(String(key)) ?? -1
    const row = weights[id]
    if (!row || index < 0 || index >= row.length) throw invalid()
    row[index] = Math.min(this.clip, row[index] + count)
  }

  private apply(weights: Weights, described: CellDescription, count: number, permitted: ReadonlySet<string>): void {
    if (described.metric === 'submissions') {
      if (!permitted.has('usage')) return
      if (typeof described.workflow !== 'string') throw invalid()
      this.add(weights, 'feature_family', described.workflow.split('.', 1)[0], count)
      this.add(weights, 'feature', described.workflow, count)
      return
    }
    if (described.metric === 'outcomes') {
      if (!permitted.has('usage')) return
      this.add(weights, 'outcome', described.bucket, count)
      return
    }
    if (described.metric === 'reasons') {
      if (!permitted.has('reliability')) return
      this.add(weights, 'reason', described.bucket, count)
      return
    }
    const spec = this.metrics.find(item => item.id === described.metric)
    if (!spec || !permitted.has(spec.group)) return
    this.add(weights, described.metric, described.bucket, count)
  }

  private choose(weights: readonly number[], random: RandomBelow): number {
    const total = weights.reduce((sum, weight) => sum + weight, 0)
    if (total <= 0) throw invalid()
    if (weights.filter(weight => weight === 0).length === weights.length - 1) {
      return weights.findIndex(weight => weight > 0)
    }
    let position = this.draw(total, random)
    for (let index = 0; index < weights.length; index++) {
      if (position < weights[index]) return index
      position -= weights[index]
    }
    throw invalid()
  }

  /** `no_failure` is only clipped success/accepted mass. Other outcomes stay unresolved. */
  private reasonIndex(weights: Weights, random: RandomBelow): number {
    const outcome = weights.outcome
    const explicit = weights.reason
    const names = this.metric('outcome').categories ?? []
    let quiet = 0
    let unresolved = 0
    for (let index = 0; index < names.length; index++) {
      if (names[index] === 'success' || names[index] === 'accepted') quiet += outcome[index]
      else unresolved += outcome[index]
    }
    const known = explicit.slice()
    known[0] = Math.min(this.clip, known[0] + Math.min(this.clip, quiet))
    const unknown = Math.max(0, unresolved - explicit.reduce((sum, weight) => sum + weight, 0))
    const knownMass = known.reduce((sum, weight) => sum + weight, 0)
    if (knownMass === 0) return 1
    if (unknown === 0) return 2 + this.choose(known, random)
    let position = this.draw(knownMass + unknown, random)
    if (position < unknown) return 1
    position -= unknown
    for (let index = 0; index < known.length; index++) {
      if (position < known[index]) return 2 + index
      position -= known[index]
    }
    throw invalid()
  }

  private indexes(weights: Weights, permitted: ReadonlySet<string>, random: RandomBelow): number[] {
    return this.metrics.map(metric => {
      if (!permitted.has(metric.group)) return 0
      if (metric.id === 'reason') return this.reasonIndex(weights, random)
      const row = weights[metric.id]
      return row.reduce((sum, weight) => sum + weight, 0) === 0 ? 1 : 2 + this.choose(row, random)
    })
  }

  private permitted(groups: unknown): Set<string> {
    if (!Array.isArray(groups) || groups.length < 1 || groups.length > GROUPS.length
      || groups.some(group => typeof group !== 'string' || !GROUPS.includes(group))
      || new Set(groups).size !== groups.length) throw invalid()
    return new Set(groups)
  }

  private coordinates(release: readonly number[], operatingSystem: string): void {
    if (!Array.isArray(release) || release.length !== 3 || release.some(part => !integer(part, 0, 255))
      || typeof operatingSystem !== 'string' || !this.specification.operating_systems.includes(operatingSystem)) {
      throw invalid()
    }
  }

  private finish(axis: 'release' | 'os', weights: Weights, permitted: ReadonlySet<string>, random: RandomBelow,
    release: readonly number[], operatingSystem: string): Uint8Array {
    return this.encode(axis, this.indexes(weights, permitted, random), release, operatingSystem)
  }

  private guard(body: () => void): void {
    try {
      body()
    } catch (error) {
      if (error instanceof Error && error.message === 'telemetry_invalid_v3_report') throw error
      if (error instanceof TypeError || (error instanceof Error && error.message === 'telemetry_invalid_measurement')) {
        throw invalid()
      }
      throw error
    }
  }

  summarize(observations: unknown, groups: unknown, release: readonly number[], operatingSystem: string,
    random: RandomBelow = secureRandomBelow): Uint8Array {
    const axis = this.draw(2, random) === 0 ? 'release' : 'os'
    const permitted = this.permitted(groups)
    this.coordinates(release, operatingSystem)
    if (!Array.isArray(observations) || observations.length < 1 || observations.length > this.maximumRows) throw invalid()
    const weights = this.blank()
    this.guard(() => {
      for (const item of observations) {
        for (const cell of this.catalog.observation(item).cells) this.apply(weights, this.catalog.describe(cell), 1, permitted)
      }
    })
    return this.finish(axis, weights, permitted, random, release, operatingSystem)
  }

  prepare(rows: unknown, groups: unknown, release: readonly number[], operatingSystem: string,
    random: RandomBelow = secureRandomBelow): Uint8Array {
    const axis = this.draw(2, random) === 0 ? 'release' : 'os'
    const permitted = this.permitted(groups)
    this.coordinates(release, operatingSystem)
    if (!Array.isArray(rows) || rows.length < 1 || rows.length > this.maximumRows) throw invalid()
    const weights = this.blank()
    const seen = new Set<number>()
    this.guard(() => {
      for (const row of rows) {
        if (!Array.isArray(row) || row.length !== 2 || !integer(row[0], 0, 65535)
          || !integer(row[1], 1, this.clip) || seen.has(row[0])) throw invalid()
        seen.add(row[0])
        this.apply(weights, this.catalog.describe(row[0]), row[1], permitted)
      }
    })
    return this.finish(axis, weights, permitted, random, release, operatingSystem)
  }

  encode(axis: string, buckets: readonly number[], release: readonly number[], operatingSystem: string): Uint8Array {
    if ((axis !== 'release' && axis !== 'os') || !Array.isArray(buckets) || buckets.length !== this.metrics.length
      || buckets.some((value, index) => !integer(value, 0, this.bins(this.metrics[index]) - 1))) throw invalid()
    const packet = new Uint8Array(this.specification.packet_bytes)
    packet[0] = this.specification.version_byte
    packet[1] = axis === 'release' ? this.specification.axis_byte.release : this.specification.axis_byte.os
    if (axis === 'release') {
      if (!Array.isArray(release) || release.length !== 3 || release.some(part => !integer(part, 0, 255))) throw invalid()
      packet[2] = release[0]
      packet[3] = release[1]
      packet[4] = release[2]
    } else {
      const index = this.specification.operating_systems.indexOf(operatingSystem)
      if (index < 0) throw invalid()
      packet[2] = index
    }
    packet.set(buckets, 6)
    return packet
  }

  decode(packet: Uint8Array): WireV3Summary {
    if (!(packet instanceof Uint8Array) || packet.length !== this.specification.packet_bytes
      || packet[0] !== this.specification.version_byte || packet[5] !== this.specification.reserved_cohort_byte) {
      throw invalid()
    }
    const buckets = Array.from(packet.subarray(6))
    if (buckets.some((value, index) => value >= this.bins(this.metrics[index]))) throw invalid()
    if (packet[1] === this.specification.axis_byte.release) {
      const item = this.byCoordinate.get(`${packet[2]}.${packet[3]}.${packet[4]}`)
      if (!item) {
        return { axis: 'release', cohortId: this.specification.unlisted_release_id,
          cohortIndex: this.specification.release_allowlist.length, buckets }
      }
      return { axis: 'release', cohortId: item.id, cohortIndex: item.slot, buckets }
    }
    if (packet[1] === this.specification.axis_byte.os) {
      if (packet[3] !== 0 || packet[4] !== 0 || packet[2] >= this.specification.operating_systems.length) throw invalid()
      return { axis: 'os', cohortId: this.specification.operating_systems[packet[2]], cohortIndex: packet[2], buckets }
    }
    throw invalid()
  }

  releaseSlot(major: number, minor: number, patch: number): number | null {
    if (!integer(major, 0, 255) || !integer(minor, 0, 255) || !integer(patch, 0, 255)) throw invalid()
    return this.byCoordinate.get(`${major}.${minor}.${patch}`)?.slot ?? null
  }

  bucketLabel(metricId: string, index: number): string {
    const metric = this.metric(metricId)
    if (!integer(index, 0, this.bins(metric) - 1)) throw invalid()
    if (index === 0) return 'group_disabled'
    if (index === 1) return 'sensor_missing'
    const slot = index - 2
    if (metric.kind === 'categories') return metric.categories?.[slot] ?? ''
    const bounds = metric.upper_bounds ?? []
    if (slot === 0) return `0-${bounds[0]}`
    if (slot === bounds.length - 1) return `>${bounds[slot - 1]}`
    return `${bounds[slot - 1] + 1}-${bounds[slot]}`
  }
}
