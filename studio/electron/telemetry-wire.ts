/** Small locally randomized reports shared by browser and native clients.
 * No networking, implicit consent, identity, caller objects or policy cache.
 */
import { TelemetryCatalog } from './telemetry-catalog.js'
import type { TelemetryFormatExample, TelemetryWirePreview } from '../shared/product-telemetry.js'

type View = { id: number; name: string; group: string; weight: number; domain: number; values: string[];
  source: { metric?: string; field?: string; cohort?: string } }
export type TelemetryWireSpec = { version: number; maximum_rows: number; maximum_cell_count: number;
  protected_unit: string; views: View[] }
type RandomBelow = (limit: number) => number
const invalid = () => new Error('telemetry_invalid_report')
const integer = (value: unknown, minimum: number, maximum: number): value is number =>
  typeof value === 'number' && Number.isInteger(value) && value >= minimum && value <= maximum
const record = (value: unknown): value is Record<string, unknown> =>
  Boolean(value) && typeof value === 'object' && !Array.isArray(value)
const groups = ['usage', 'reliability', 'performance', 'resources']

/** Unbiased bounded CSPRNG draws; failure suppresses optional telemetry. */
export function secureRandomBelow(limit: number): number {
  if (!integer(limit, 1, 131072)) throw invalid()
  const ceiling = Math.floor(0x100000000 / limit) * limit
  const sample = new Uint32Array(1)
  for (let attempt = 0; attempt < 8; attempt++) {
    globalThis.crypto.getRandomValues(sample)
    if (sample[0] < ceiling) return sample[0] % limit
  }
  throw invalid()
}

export class TelemetryWire {
  constructor(readonly specification: TelemetryWireSpec, private readonly catalog: TelemetryCatalog) {
    if (specification.version !== 2 || specification.views.length !== 23 ||
      specification.maximum_rows !== 512 || specification.maximum_cell_count !== 255 ||
      specification.views.some((view, id) => view.id !== id || !groups.includes(view.group) ||
        !integer(view.weight, 1, 256) || !integer(view.domain, 2, 128) || (view.domain & (view.domain - 1)) !== 0 ||
        view.values[0] !== 'unobserved' || view.values.length > view.domain)) throw invalid()
  }

  private view(id: unknown): View {
    if (!integer(id, 0, this.specification.views.length - 1)) throw invalid()
    return this.specification.views[id]
  }

  private draw(limit: number, random: RandomBelow): number {
    const value = random(limit)
    if (!integer(value, 0, limit - 1)) throw invalid()
    return value
  }

  encode(id: number, category: number, random: RandomBelow = secureRandomBelow, reviewed = false): Uint8Array {
    const view = this.view(id)
    if (typeof reviewed !== 'boolean' || !integer(category, 0, view.values.length - 1)) throw invalid()
    if (reviewed) return new Uint8Array([this.specification.version, id, 0, 2])
    const column = this.draw(view.domain, random)
    let masked = category & column, positive = true
    while (masked) { positive = !positive; masked &= masked - 1 }
    if (this.draw(4, random) === 3) positive = !positive
    return new Uint8Array([this.specification.version, id, column, Number(positive) | (reviewed ? 2 : 0)])
  }

  decode(packet: Uint8Array): { view: number; coordinate: number; sign: number; reviewed: boolean } {
    if (!(packet instanceof Uint8Array) || packet.length !== 4 || packet[0] !== this.specification.version) throw invalid()
    const view = this.view(packet[1])
    if (packet[2] >= view.domain || packet[3] > 3) throw invalid()
    if (packet[3] & 2 && (packet[2] !== 0 || packet[3] !== 2)) throw invalid()
    return { view: view.id, coordinate: packet[2], sign: packet[3] & 1 ? 1 : -1, reviewed: Boolean(packet[3] & 2) }
  }

  prepare(rows: unknown, permitted: unknown, cohorts: unknown = {}, random: RandomBelow = secureRandomBelow, reviewed = false): Uint8Array {
    if (typeof reviewed !== 'boolean' || !Array.isArray(permitted) || !permitted.length || permitted.length > groups.length ||
      permitted.some(group => typeof group !== 'string' || !groups.includes(group)) ||
      new Set(permitted).size !== permitted.length || !Array.isArray(rows) || !rows.length ||
      rows.length > this.specification.maximum_rows || !record(cohorts)) throw invalid()
    const views = this.specification.views.filter(view => permitted.includes(view.group))
    const cohortViews = this.specification.views.filter(view => view.source.cohort)
    if (Object.keys(cohorts).some(name => {
      const view = cohortViews.find(item => item.source.cohort === name)
      return !view || typeof cohorts[name] !== 'string' || !view.values.includes(cohorts[name] as string)
    })) throw invalid()
    // Select the permitted question without examining the measurement values.
    let position = 0, view = views[0]
    if (!reviewed) {
      position = this.draw(views.reduce((sum, view) => sum + view.weight, 0), random)
      for (const item of views) {
        if (position < item.weight) { view = item; break }
        position -= item.weight
      }
    }
    const counts = new Uint32Array(view.values.length), seen = new Set<number>()
    for (const row of rows) {
      if (!Array.isArray(row) || row.length !== 2 || !integer(row[0], 0, 65535) ||
        !integer(row[1], 1, this.specification.maximum_cell_count) || seen.has(row[0])) throw invalid()
      seen.add(row[0])
      const cell = this.catalog.describe(row[0])
      if (view.source.metric !== cell.metric || view.group !== cell.group) continue
      const value = view.source.field === 'family' ? cell.workflow?.split('.', 1)[0] :
        cell[view.source.field as keyof typeof cell]
      const index = typeof value === 'number' ? value + 1 : typeof value === 'string' ? view.values.indexOf(value) : -1
      if (!integer(index, 1, counts.length - 1)) throw invalid()
      counts[index] += row[1]
    }
    let category = 0
    if (reviewed) return this.encode(view.id, 0, random, true)
    if (view.source.cohort) category = view.values.indexOf((cohorts[view.source.cohort] as string | undefined) ?? 'unobserved')
    else {
      const total = counts.reduce((sum, count) => sum + count, 0)
      if (total) {
        position = this.draw(total, random)
        for (let index = 0; index < counts.length; index++) {
          if (position < counts[index]) { category = index; break }
          position -= counts[index]
        }
      }
    }
    return this.encode(view.id, category, random, reviewed)
  }

  preview(packet: Uint8Array): TelemetryWirePreview {
    const decoded = this.decode(packet)
    return { schema_version: this.specification.version, body_base64: globalThis.btoa(String.fromCharCode(...packet)),
      body_bytes: packet.length, view: this.view(decoded.view).name, coordinate: decoded.coordinate,
      randomized_sign: decoded.reviewed ? null : decoded.sign, protected_unit: decoded.reviewed
        ? 'Fixed body within permitted metric groups; no category is transmitted. Participation and policy choice are not protected.'
        : this.specification.protected_unit,
      report_selection: decoded.reviewed ? 'reviewed' : 'automatic',
      aggregation: decoded.reviewed ? 'coarse_global_volume_only' : 'automatic_categorical_estimates',
      randomization_privacy_loss: decoded.reviewed ? null : 'ln(3)', per_report_privacy_loss: decoded.reviewed ? null : 'ln(3)',
      privacy_bound_scope: decoded.reviewed ? 'fixed_body_for_permitted_groups' : 'packet_independent_inclusion',
      participation_or_lifetime_guarantee: false }
  }

  formatExample(): TelemetryFormatExample {
    // No queue input, random draw, reservation or acknowledgement is involved.
    return { kind: 'synthetic_example', body_encoding: 'base64',
      ...this.preview(new Uint8Array([this.specification.version, 0, 7, 0])) }
  }
}
