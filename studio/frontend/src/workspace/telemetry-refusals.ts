/** Negative hints only; a native permission stamp is always read afresh. */
import type { TelemetryStamp } from '../../../shared/product-telemetry'

export class TelemetrySnapshotReader {
  private readonly scopes: string[]
  private readonly since: Float64Array
  private readonly until: Float64Array
  private epoch = 0
  constructor(
    readonly invoke: (workflow?: string) => Promise<TelemetryStamp | null>,
    workflows: readonly string[],
    private readonly clock = () => performance.now(),
  ) {
    // Future catalog entries beyond this bound still get fresh native reads.
    this.scopes = workflows.slice(0, 128)
    this.since = new Float64Array(this.scopes.length)
    this.until = new Float64Array(this.scopes.length)
  }

  clear(): void {
    this.epoch++
    this.since.fill(0)
    this.until.fill(0)
  }

  read(workflow?: string): Promise<TelemetryStamp | null> | null {
    const index = workflow === undefined ? -1 : this.scopes.indexOf(workflow)
    if (index < 0) return this.invoke(workflow)
    const started = this.clock(), epoch = this.epoch
    if (started >= this.since[index] && started < this.until[index]) return null
    this.until[index] = 0
    return this.invoke(workflow).then(stamp => {
      const finished = this.clock()
      if (epoch === this.epoch) {
        if (stamp === null && finished >= started && finished - started < 1000) {
          // Measure expiry from request start, never from a delayed response.
          this.since[index] = started
          this.until[index] = started + 1000
        } else this.until[index] = 0
      }
      return stamp
    })
  }
}
