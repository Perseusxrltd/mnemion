/** Delivery belongs to the desktop's existing lifetime, including remote work. */
import { NativeTelemetryDelivery, type PreparedTelemetryReport } from './telemetry-delivery.js'
import { TelemetryActivity } from './telemetry-owner.js'
import type { NativeTelemetryDisclosure } from './telemetry-store.js'
import type { MeasurementCatalog } from './telemetry-catalog.js'
import type { TelemetryStamp } from '../shared/product-telemetry.js'
import { nativeTelemetryRoute, validCertificateAuthorities } from './telemetry-route.js'

export type TelemetryConditions = { network: 'unknown' | 'metered' | 'unmetered'; constrained: boolean }

/** The public destination and fixed address must both belong to this release. */
function releaseAddress(): string | null {
  return nativeTelemetryRoute()?.address ?? null
}

export class DesktopTelemetryActivity extends NativeTelemetryDelivery {
  private readonly activity: TelemetryActivity<PreparedTelemetryReport>
  constructor(root: string, disclosure: NativeTelemetryDisclosure, catalog: MeasurementCatalog,
    conditions: () => TelemetryConditions, companyFile?: string, address: string | null = releaseAddress(),
    gauges?: { prepare: (stop: AbortSignal) => Promise<boolean>; close: () => void },
    certificateAuthorities: readonly string[] = nativeTelemetryRoute()?.certificate_authorities ?? []) {
    super(root, disclosure, catalog, companyFile, undefined, undefined, conditions)
    const authorities = Object.freeze([...certificateAuthorities])
    this.activity = new TelemetryActivity({
      available: () => this.available && address !== null && validCertificateAuthorities(authorities),
      reserve: async (stamp, stop) => {
        if (gauges && (!await this.eligible(stamp) || !await gauges.prepare(stop) || stop.aborted)) return null
        return this.reserve(stamp)
      },
      send: async (report, stop) => {
        const { TelemetryEndpoint, sendNativeTelemetry } = await import('./telemetry-transport.js')
        if (stop.aborted || !this.disclosure.destination || !address) return
        const url = new URL(this.disclosure.destination)
        const endpoint = new TelemetryEndpoint(url.hostname, address, url.port ? Number(url.port) : 443, authorities)
        await sendNativeTelemetry(this, report, endpoint, stop)
      },
      cancel: report => this.cancel(report),
      cleanup: () => gauges?.close(),
    })
  }

  override async recordMany(inputs: unknown[], stamp: TelemetryStamp, day = Math.floor(Date.now() / 86400000)): Promise<boolean> {
    const expected = { revision: stamp?.revision, store_generation: stamp?.store_generation }
    const recorded = await super.recordMany(inputs, expected, day)
    // super has committed and closed its SQLite transaction before offering.
    if (recorded) this.activity.offer(expected)
    return recorded
  }
  pauseDelivery(reason?: string): void { this.activity.pause(reason) }
  offerApproved(stamp: TelemetryStamp): void { this.activity.offer(stamp) }
  resumeDelivery(reason?: string): void { this.activity.resume(reason) }
  closeDelivery(): void { this.activity.close() }
  deliverySettled(): Promise<void> { return this.activity.settled() }
}
