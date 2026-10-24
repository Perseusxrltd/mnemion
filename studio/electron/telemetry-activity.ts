/** Delivery belongs to the desktop's existing lifetime, including remote work. */
import { readFileSync } from 'node:fs'
import { NativeTelemetryDelivery, type PreparedTelemetryReport } from './telemetry-delivery.js'
import { TelemetryActivity } from './telemetry-owner.js'
import type { NativeTelemetryDisclosure } from './telemetry-store.js'
import type { MeasurementCatalog } from './telemetry-catalog.js'
import type { TelemetryStamp } from '../shared/product-telemetry.js'

export type TelemetryConditions = { network: 'unknown' | 'metered' | 'unmetered'; constrained: boolean }

/** The public destination and fixed address must both belong to this release. */
function releaseAddress(): string | null {
  try {
    const route = JSON.parse(readFileSync(new URL('./telemetry-transport-route.json', import.meta.url), 'utf8'))
    return route?.version === 1 && Object.keys(route).sort().join() === 'address,version' &&
      typeof route.address === 'string' && route.address.length <= 45 ? route.address : null
  } catch { return null }
}

export class DesktopTelemetryActivity extends NativeTelemetryDelivery {
  private readonly activity: TelemetryActivity<PreparedTelemetryReport>
  constructor(root: string, disclosure: NativeTelemetryDisclosure, catalog: MeasurementCatalog,
    conditions: () => TelemetryConditions, companyFile?: string, address: string | null = releaseAddress()) {
    super(root, disclosure, catalog, companyFile, undefined, undefined, conditions)
    this.activity = new TelemetryActivity({
      available: () => this.available && address !== null,
      reserve: stamp => this.reserve(stamp),
      send: async (report, stop) => {
        const { TelemetryEndpoint, sendNativeTelemetry } = await import('./telemetry-transport.js')
        if (stop.aborted || !this.disclosure.destination || !address) return
        const url = new URL(this.disclosure.destination)
        const endpoint = new TelemetryEndpoint(url.hostname, address, url.port ? Number(url.port) : 443)
        await sendNativeTelemetry(this, report, endpoint, stop)
      },
      cancel: report => this.cancel(report),
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
  resumeDelivery(reason?: string): void { this.activity.resume(reason) }
  closeDelivery(): void { this.activity.close() }
  deliverySettled(): Promise<void> { return this.activity.settled() }
}
