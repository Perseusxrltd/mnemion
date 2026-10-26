/** One bounded HTTPS attempt. The existing app owner supplies its lifetime. */
import { constants, X509Certificate } from 'node:crypto'
import { once } from 'node:events'
import { createRequire } from 'node:module'
import { isIP, Socket, type SocketConstructorOpts } from 'node:net'
import { Duplex } from 'node:stream'
import type { TLSSocket } from 'node:tls'
import { NativeTelemetryDelivery, PreparedTelemetryReport } from './telemetry-delivery.js'
import { validCertificateAuthorities } from './telemetry-route.js'

// The TLS ESM facade enumerates the lazy rootCertificates export. Select only
// the APIs used here so an explicit trust set never loads that general list.
const { connect, createSecureContext } = createRequire(import.meta.url)('node:tls') as typeof import('node:tls')

const MAX_TLS_BYTES = 32768, MAX_HEADERS = 2048, DEADLINE = 5000
type Outcome = 'delivered' | 'suppressed' | 'failed' | 'deadline' | 'wire_limit'
export type TelemetryAttemptResult = { outcome: Outcome; encrypted_bytes_charged: number }

/** Release-owned address; no resolver, proxy, alternate host or redirect. */
export class TelemetryEndpoint {
  readonly certificateAuthorities: readonly string[]
  constructor(readonly host: string, readonly address: string, readonly port = 443, certificateAuthorities: readonly string[] = []) {
    this.certificateAuthorities = Object.freeze(Array.isArray(certificateAuthorities) ? [...certificateAuthorities] : [])
    Object.freeze(this)
  }
  valid(destination: unknown): boolean {
    return typeof this.host === 'string' && this.host.length <= 253 &&
      /^[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$/.test(this.host) && !this.host.includes('..') &&
      typeof this.address === 'string' && !this.address.includes('%') && isIP(this.address) !== 0 &&
      Number.isInteger(this.port) && this.port >= 1 && this.port <= 65535 &&
      validCertificateAuthorities(this.certificateAuthorities) &&
      destination === `https://${this.authority()}/v1/report`
  }
  authority(): string { return this.port === 443 ? this.host : `${this.host}:${this.port}` }
  headers(): Buffer {
    return Buffer.from(`POST /v1/report HTTP/1.1\r\nHost: ${this.authority()}\r\n` +
      'Content-Type: application/octet-stream\r\nContent-Length: 4\r\nConnection: close\r\n\r\n', 'ascii')
  }
}

function emptyResponse(raw: Buffer): boolean {
  const delimiter = raw.indexOf('\r\n\r\n')
  if (delimiter < 0 || delimiter + 4 !== raw.length) return false
  const lines = raw.subarray(0, delimiter).toString('latin1').split('\r\n')
  if (!/^HTTP\/1\.1 204(?: [\x20-\x7e]*)?$/.test(lines.shift()!)) return false
  const names = new Set<string>()
  for (const line of lines) {
    const colon = line.indexOf(':'), name = line.slice(0, colon).toLowerCase(), value = line.slice(colon + 1).trim()
    if (colon < 1 || !/^[a-z0-9-]+$/.test(name) || names.has(name) || name === 'transfer-encoding' ||
      (name === 'content-length' && value !== '0')) return false
    names.add(name)
  }
  return true
}

/** Count the encrypted stream below TLS; TLSSocket byte counters are plaintext.
 * These are charged application transport bytes, not TCP/IP retransmissions. */
class Channel {
  readonly stopped = new AbortController()
  readonly raw = new Socket({ highWaterMark: 4096 } as SocketConstructorOpts & { highWaterMark: number })
  readonly bridge: Duplex
  secure?: TLSSocket
  charged = 0
  outcome: Outcome = 'failed'
  private phase: 'handshake' | 'capture' | 'sent' = 'handshake'
  private encrypted: Buffer[] = []
  private captured = 0
  private packet?: Buffer
  private original?: Uint8Array

  constructor(private readonly endpoint: TelemetryEndpoint) {
    this.bridge = new Duplex({
      readableHighWaterMark: 4096, writableHighWaterMark: 4096,
      read: () => this.receive(),
      write: (chunk: Buffer, _encoding, callback) => {
        if (this.stopped.signal.aborted) { callback(new Error('telemetry_stopped')); return }
        if (this.phase === 'capture') {
          if (this.captured + chunk.length > MAX_HEADERS) {
            this.close('wire_limit'); callback(new Error('telemetry_wire_limit')); return
          }
          this.encrypted.push(Buffer.from(chunk)); this.captured += chunk.length
          callback(); return
        }
        if (this.phase !== 'handshake' || !this.charge(chunk.length)) {
          callback(new Error('telemetry_stopped')); return
        }
        this.raw.write(chunk, callback)
      },
      destroy: (_error, callback) => { this.raw.destroy(); callback() },
    })
    this.raw.on('readable', () => this.receive())
    this.raw.on('end', () => this.bridge.push(null))
    this.raw.on('error', () => this.close('failed'))
    this.bridge.on('error', () => this.close('failed'))
  }

  private charge(size: number): boolean {
    if (size > MAX_TLS_BYTES - this.charged) { this.close('wire_limit'); return false }
    this.charged += size
    return true
  }

  private receive(): void {
    while (!this.stopped.signal.aborted && this.raw.readableLength) {
      const remaining = MAX_TLS_BYTES - this.charged
      if (remaining <= 0) { this.close('wire_limit'); return }
      const chunk = this.raw.read(Math.min(4096, remaining, this.raw.readableLength)) as Buffer | null
      if (!chunk) return
      this.charged += chunk.length
      if (!this.bridge.push(chunk)) return
    }
  }

  close(outcome?: Outcome): void {
    if (!this.stopped.signal.aborted) {
      if (outcome) this.outcome = outcome
      this.stopped.abort()
    }
    // Destroy, never end(): no shutdown flush or TLS close-notify after opt-out.
    this.raw.destroy(); this.secure?.destroy(); this.bridge.destroy()
    this.original?.fill(0); this.packet?.fill(0)
    for (const chunk of this.encrypted) chunk.fill(0)
    this.encrypted = []
  }

  async handshake(): Promise<void> {
    if (this.stopped.signal.aborted) return
    // Validate the bounded public roots before any connection. An explicit CA
    // set avoids loading the general root store and never weakens TLS checks.
    for (const certificate of this.endpoint.certificateAuthorities) {
      if (!new X509Certificate(certificate).ca) throw new Error('telemetry_trust_unavailable')
    }
    const secureContext = createSecureContext({ ca: [...this.endpoint.certificateAuthorities],
      minVersion: 'TLSv1.3', secureOptions: constants.SSL_OP_NO_TICKET })
    const connected = once(this.raw, 'connect', { signal: this.stopped.signal })
    this.raw.setNoDelay(true)
    this.raw.connect({ host: this.endpoint.address, port: this.endpoint.port,
      family: isIP(this.endpoint.address), autoSelectFamily: false })
    this.raw.unref()
    await connected
    if (this.stopped.signal.aborted) return
    this.secure = connect({ socket: this.bridge, servername: this.endpoint.host, secureContext,
      rejectUnauthorized: true, minVersion: 'TLSv1.3', secureOptions: constants.SSL_OP_NO_TICKET,
      ALPNProtocols: ['http/1.1'] })
    this.secure.on('error', () => this.close('failed'))
    await once(this.secure, 'secureConnect', { signal: this.stopped.signal })
    if (!this.secure.authorized) this.close('failed')
  }

  async capture(body: Uint8Array): Promise<void> {
    if (!this.secure || this.stopped.signal.aborted || body.length !== 4) { body.fill(0); return }
    this.phase = 'capture'
    this.original = new Uint8Array(body)
    const request = Buffer.concat([this.endpoint.headers(), body])
    try {
      await new Promise<void>((resolve, reject) => this.secure!.write(request, error => error ? reject(error) : resolve()))
      this.packet = Buffer.concat(this.encrypted, this.captured)
      for (const chunk of this.encrypted) chunk.fill(0)
      this.encrypted = []
    } finally { request.fill(0); body.fill(0) }
  }

  /** Only this nonblocking raw-socket handoff runs under the privacy lock. */
  handoff(body: Uint8Array): boolean {
    if (this.stopped.signal.aborted || this.phase !== 'capture' || !this.packet?.length || !this.original ||
      body.length !== 4 || body.some((value, index) => value !== this.original![index]) ||
      this.raw.destroyed || this.raw.writableLength !== 0 || !this.charge(this.packet.length)) return false
    this.phase = 'sent'
    // The socket owns this buffer until its callback. Uncertain writes remain
    // charged; cancellation destroys the socket without making another write.
    const packet = this.packet
    this.packet = undefined
    this.raw.write(packet, () => packet.fill(0))
    this.original.fill(0)
    return true
  }

  response(): Promise<boolean> {
    return new Promise(resolve => {
      let headers = Buffer.alloc(0), done = false
      const finish = (valid: boolean) => {
        if (done) return
        done = true
        this.secure?.off('data', data); this.secure?.off('end', ended)
        this.stopped.signal.removeEventListener('abort', ended)
        headers.fill(0); resolve(valid)
      }
      const data = (chunk: Buffer) => {
        if (headers.length + chunk.length > MAX_HEADERS) { finish(false); return }
        headers = Buffer.concat([headers, chunk])
        if (headers.includes('\r\n\r\n')) finish(emptyResponse(headers))
      }
      const ended = () => finish(false)
      this.secure!.on('data', data); this.secure!.once('end', ended)
      this.stopped.signal.addEventListener('abort', ended, { once: true })
      if (this.stopped.signal.aborted) ended()
    })
  }
}

export async function sendNativeTelemetry(budget: NativeTelemetryDelivery, report: PreparedTelemetryReport,
  endpoint: TelemetryEndpoint, stop?: AbortSignal): Promise<TelemetryAttemptResult> {
  // A duplicate call has no network or cleanup ownership over the first call.
  if (!(report instanceof PreparedTelemetryReport) || !report.claimTransport()) return { outcome: 'suppressed', encrypted_bytes_charged: 0 }
  if (!budget.available || !(endpoint instanceof TelemetryEndpoint) || !endpoint.valid(budget.disclosure.destination) || stop?.aborted) {
    await budget.cancel(report)
    return { outcome: 'suppressed', encrypted_bytes_charged: 0 }
  }
  const channel = new Channel(endpoint)
  const aborted = () => channel.close('suppressed')
  let timer: ReturnType<typeof setTimeout> | undefined, watcher: Promise<void> | undefined
  let watching: AbortController | undefined
  const observe = () => {
    watching = new AbortController()
    watcher = budget.watch(report, aborted, watching.signal, false)
  }
  const drainObservation = async () => {
    watching?.abort()
    await watcher
    watcher = undefined; watching = undefined
  }
  let outcome: Outcome = 'failed'
  try {
    stop?.addEventListener('abort', aborted, { once: true })
    if (!await budget.current(report) || stop?.aborted) { outcome = 'suppressed'; return { outcome, encrypted_bytes_charged: 0 } }
    const remaining = Math.min(DEADLINE, report.monotonicDeadline - performance.now())
    if (remaining <= 0) { outcome = 'deadline'; return { outcome, encrypted_bytes_charged: 0 } }
    timer = setTimeout(() => channel.close('deadline'), remaining).unref()
    observe()
    await channel.handshake()
    await channel.capture(report.body())
    if (channel.stopped.signal.aborted || !channel.secure) outcome = channel.outcome
    else {
      const response = channel.response()
      // A Windows privacy probe yields while holding the single storage slot.
      // Finish that observation before the fresh, mandatory write fence. There
      // is no second connection, queued measurement or cached consent; the
      // original socket deadline and owner cancellation remain active.
      await drainObservation()
      if (channel.stopped.signal.aborted) outcome = channel.outcome
      else if (!await budget.guardedWrite(report, body => channel.handoff(body))) outcome = 'suppressed'
      else {
        observe()
        if (await response) outcome = 'delivered'
        else outcome = channel.outcome
      }
    }
  } catch { outcome = channel.outcome }
  finally {
    if (timer) clearTimeout(timer)
    stop?.removeEventListener('abort', aborted)
    channel.close()
    await drainObservation()
    await budget.cancel(report)
  }
  return { outcome, encrypted_bytes_charged: channel.charged }
}
