/** An origin-local review epoch shared only by live pages. No worker or storage. */
import { reviewClock, type ReviewClock } from '../../../electron/telemetry-review-lifetime'

const name = 'mnemion.product-telemetry.review-clock.v1'
const DISCOVERY_MS = 100, DEADLINE_MS = 250
const nonce = () => Array.from(crypto.getRandomValues(new Uint8Array(16)), byte => byte.toString(16).padStart(2, '0')).join('')
const token = (value: unknown): value is string => typeof value === 'string' && /^[0-9a-f]{32}$/.test(value) && !/^0+$/.test(value)
const object = (value: unknown): value is Record<string, unknown> => Boolean(value) && typeof value === 'object' && !Array.isArray(value)
type Environment = { now: () => number; locks: () => LockManager | null; channel: () => BroadcastChannel; nonce: () => string }
type Discovery = { token: string; expected: string | null; reply: ReviewClock | null; replies: number }

export class BrowserReviewClock {
  private value?: { clock: ReviewClock; at: number; checked: number }
  private channel?: BroadcastChannel
  private discovery?: Discovery
  private pending?: Promise<ReviewClock | null>
  private finishDiscovery?: () => void
  private generation = 0
  private readonly environment: Environment
  constructor(environment: Partial<Environment> = {}) {
    this.environment = { now: () => performance.now(), locks: () => typeof navigator === 'undefined' ? null : navigator.locks ?? null,
      channel: () => new BroadcastChannel(name), nonce, ...environment }
  }

  /** A read never initializes an epoch, posts messages, opens a channel or waits. */
  read(): ReviewClock | null {
    try {
      const current = this.value, now = this.environment.now()
      if (!current) return null
      if (!Number.isFinite(now) || now < current.checked) { this.close(); return null }
      const measured = reviewClock({ epoch: current.clock.epoch,
        elapsed_ms: current.clock.elapsed_ms + Math.floor(now - current.at) })
      current.checked = now
      return measured
    } catch { return null }
  }

  private receive = (event: MessageEvent): void => {
    try {
      const data: unknown = event.data
      if (!object(data) || !token(data.token)) return
      if (data.type === 'request' && Object.keys(data).sort().join() === 'expected,token,type' &&
          (data.expected === null || token(data.expected))) {
        const clock = this.read()
        if (clock && (data.expected === null || data.expected === clock.epoch))
          this.channel?.postMessage({ type: 'reply', token: data.token, ...clock })
      } else if (data.type === 'reply' && Object.keys(data).sort().join() === 'elapsed_ms,epoch,token,type') {
        const current = this.discovery
        if (!current || current.token !== data.token || current.replies >= 16) return
        const measured = reviewClock({ epoch: data.epoch, elapsed_ms: data.elapsed_ms })
        if (current.expected !== null && current.expected !== measured.epoch) return
        current.replies++
        // A new review can select an existing epoch deterministically. An
        // existing review can only join its own still-live epoch.
        if (!current.reply || measured.epoch < current.reply.epoch ||
            (measured.epoch === current.reply.epoch && current.reply.elapsed_ms < measured.elapsed_ms)) current.reply = measured
      }
    } catch { /* Unknown or malformed same-origin messages confer no authority. */ }
  }

  /** Explicit review or an already-eligible reviewed attempt may initialize.
   * The short Web Lock prevents simultaneous tabs from creating new epochs. */
  ensure(expected: string | null = null): Promise<ReviewClock | null> {
    if (expected !== null && !token(expected)) return Promise.resolve(null)
    const current = this.read()
    if (current && (expected === null || current.epoch === expected)) return Promise.resolve(current)
    if (this.pending) return this.pending.then(clock => clock && (expected === null || clock.epoch === expected) ? clock : null)
    if (current) this.close()
    const generation = this.generation
    const operation = (async () => {
      try {
        const locks = this.environment.locks()
        if (!locks) return null
        return await locks.request(name, { ifAvailable: true }, async lock => {
          if (!lock || generation !== this.generation) return null
          const started = this.environment.now(), ticket = this.environment.nonce()
          if (!Number.isFinite(started) || !token(ticket)) return null
          this.channel ??= this.environment.channel()
          this.channel.onmessage = this.receive
          const discovery: Discovery = { token: ticket, expected, reply: null, replies: 0 }
          this.discovery = discovery
          this.channel.postMessage({ type: 'request', token: ticket, expected })
          let timer: ReturnType<typeof setTimeout> | undefined
          try {
            await new Promise<void>(resolve => { this.finishDiscovery = resolve; timer = setTimeout(resolve, DISCOVERY_MS) })
          } finally {
            if (timer) clearTimeout(timer)
            this.finishDiscovery = undefined
            if (this.discovery === discovery) this.discovery = undefined
          }
          const now = this.environment.now()
          if (generation !== this.generation || (expected !== null && discovery.reply === null) || !Number.isFinite(now) ||
              now < started || now - started >= DEADLINE_MS) return null
          // Charge the whole discovery duration plus one rounding millisecond.
          // Joining another page can shorten validity, never renew its age.
          const clock = reviewClock(discovery.reply
            ? { epoch: discovery.reply.epoch, elapsed_ms: discovery.reply.elapsed_ms + Math.ceil(now - started) + 1 }
            : { epoch: this.environment.nonce(), elapsed_ms: 0 })
          this.value = { clock, at: now, checked: now }
          return { ...clock }
        })
      } catch { return null }
    })().finally(() => { if (this.pending === operation) this.pending = undefined })
    this.pending = operation
    return operation
  }

  /** Page exit loses its epoch. A later page must find a live peer or create a
   * new epoch, so a closed browser cannot revive an earlier review lifetime. */
  close(): void {
    this.generation++
    this.value = undefined
    this.discovery = undefined
    this.finishDiscovery?.()
    this.channel?.close()
    this.channel = undefined
  }
}
