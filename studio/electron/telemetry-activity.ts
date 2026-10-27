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
    let releaseTrustValid: boolean | undefined
    this.activity = new TelemetryActivity({
      // Only the copied immutable release metadata is retained. Consent,
      // current policy, the endpoint and TLS are checked at their own gates.
      available: () => this.available && address !== null &&
        (releaseTrustValid ??= validCertificateAuthorities(authorities)),
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

  override snapshot(workflow?: string, surface?: string): Promise<TelemetryStamp | null> | null {
    const pending = super.snapshot(workflow, surface)
    // A saturated workflow can stop before recordMany. Its already-awake
    // owner may revisit an older queue without admitting a new observation.
    // Unscoped inspection and unknown categories remain strictly read-only.
    if (pending === null && this.available && workflow !== undefined && surface !== undefined &&
        this.catalog.workflows.includes(workflow) && this.catalog.specification.surfaces.includes(surface)) this.activity.awake()
    return pending
  }

  override async recordMany(inputs: unknown[], stamp: TelemetryStamp, day = Math.floor(Date.now() / 86400000)): Promise<boolean> {
    const expected = { revision: stamp?.revision, store_generation: stamp?.store_generation }
    const recorded = await super.recordMany(inputs, expected, day)
    // super has committed and closed its SQLite transaction before offering.
    if (recorded) this.activity.offer(expected)
    // Saturated collection must not strand earlier authorized queue contents.
    // Only a previously committed stamp can be offered; current policy wins.
    else this.activity.awake()
    return recorded
  }
  pauseDelivery(reason?: string): void { this.activity.pause(reason) }
  offerApproved(stamp: TelemetryStamp): void { this.activity.offer(stamp, true) }
  resumeDelivery(reason?: string): void { this.activity.resume(reason) }
  closeDelivery(): void { this.activity.close() }
  deliverySettled(): Promise<void> { return this.activity.settled() }
}
