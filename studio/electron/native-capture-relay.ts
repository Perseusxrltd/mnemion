/** Loopback-only fault injection for the disposable installed capture gate.
 * No control endpoint, external destination, credential log or product hook.
 */
import { createServer, request, type Server } from 'node:http'
import type { AddressInfo } from 'node:net'

const limit = 2 * 1024 * 1024
type Page = { page_id: string; events: Array<{ event_id: string; producer_scope: string; item: any }> }
type Receipt = { page_id: string; grant_id: string; source_id: string; durable: boolean;
  items: Array<{ event_id: string; lineage_id: string; memory_id: string | null; operation_id: string | null; outcome: string }> }

export class NativeCaptureRelay {
  private server: Server
  private grant = ''
  private mode: 'pass' | 'offline' | 'drop' = 'pass'
  private failure?: Error
  private retirementGrant = ''
  private dropRetirement = false
  readonly pages: Array<{ page: Page; receipt: Receipt }> = []
  readonly reconciled: string[] = []
  dropped = 0
  retirementRequests = 0
  retirementRepliesDropped = 0
  endpoint = ''

  constructor(target: string) {
    const address = new URL(target)
    if (address.protocol !== 'http:' || address.hostname !== '127.0.0.1' || !address.port ||
        !['', '/'].includes(address.pathname) || address.username || address.password || address.search || address.hash) {
      throw new Error('The capture gate relay requires its disposable loopback workspace.')
    }
    this.server = createServer(async (incoming, outgoing) => {
      try {
        // Never resolve an absolute/protocol-relative request target supplied by
        // a client. Forward only paths to the fixed local service above.
        const path = incoming.url ?? ''
        if (!path.startsWith('/') || path.startsWith('//') || /[\r\n]/.test(path)) throw new Error('Invalid capture gate request path.')
        const route = '/v1/capture-grants/' + this.grant
        const capture = !!this.grant && (path === route || path.startsWith(route + '/'))
        if (capture && this.mode === 'offline') {
          incoming.resume(); outgoing.writeHead(503, { 'Content-Type': 'application/json' })
          outgoing.end('{"detail":"Disposable capture connection unavailable"}')
          return
        }
        const chunks: Buffer[] = []
        let size = 0
        for await (const bytes of incoming) {
          size += bytes.length
          if (size > limit) throw new Error('The capture gate request exceeded its fixed bound.')
          chunks.push(bytes)
        }
        const body = Buffer.concat(chunks)
        const retirement = !!this.retirementGrant && incoming.method === 'DELETE' && path === '/v1/capture-grants/' + this.retirementGrant
        if (retirement) this.retirementRequests++
        const response = await new Promise<{ status: number; headers: Record<string, any>; body: Buffer }>((resolve, reject) => {
          const upstream = request({ hostname: address.hostname, port: address.port, path,
            method: incoming.method, headers: { ...incoming.headers, host: address.host, connection: 'close' },
            agent: false, timeout: 30000 }, reply => {
            const buffers: Buffer[] = []
            let bytes = 0
            reply.on('data', chunk => {
              bytes += chunk.length
              if (bytes > limit) { reply.destroy(); reject(new Error('The capture gate reply exceeded its fixed bound.')); return }
              buffers.push(chunk)
            })
            reply.on('error', reject)
            reply.on('end', () => resolve({ status: reply.statusCode ?? 502, headers: reply.headers, body: Buffer.concat(buffers) }))
          })
          upstream.on('timeout', () => upstream.destroy(new Error('The capture gate upstream timed out.')))
          upstream.on('error', reject)
          upstream.end(body)
        })
        if (retirement && this.dropRetirement) {
          const grant = JSON.parse(response.body.toString('utf8'))
          if (response.status !== 200 || grant.grant_id !== this.retirementGrant || !grant.revoked_at || grant.active) throw new Error('The capture gate did not receive a confirmed retirement.')
          this.dropRetirement = false; this.retirementRepliesDropped++
          outgoing.destroy()
          return
        }
        if (capture && incoming.method === 'POST' && path === route + '/pages') {
          if (this.pages.length >= 16 || response.status !== 200) throw new Error('The capture gate did not receive a bounded successful page commit.')
          const page: Page = JSON.parse(body.toString('utf8')), receipt: Receipt = JSON.parse(response.body.toString('utf8'))
          if (!receipt.durable || receipt.page_id !== page.page_id || receipt.grant_id !== this.grant || !receipt.items.length) {
            throw new Error('The capture gate received an unmatched commit receipt.')
          }
          this.pages.push({ page, receipt })
          if (this.mode === 'drop') {
            // The real service has completed its response, including commit.
            // Destroy the client socket before sending any response byte, and
            // hold later capture requests until the next app launch.
            this.mode = 'offline'; this.dropped++
            outgoing.destroy()
            return
          }
        } else if (capture && incoming.method === 'GET' && path.startsWith(route + '/pages/')) {
          if (response.status !== 200 || this.reconciled.length >= 16) throw new Error('The capture gate did not reconcile an existing receipt.')
          this.reconciled.push(path.slice((route + '/pages/').length))
        }
        const { connection: _connection, 'transfer-encoding': _transfer, ...headers } = response.headers
        outgoing.writeHead(response.status, { ...headers, 'Content-Length': response.body.length, Connection: 'close' })
        outgoing.end(response.body)
      } catch (error) {
        this.failure ??= error instanceof Error ? error : new Error('The capture gate relay failed.')
        outgoing.destroy()
      }
    })
    this.server.requestTimeout = 30000
  }

  async start(port = 0): Promise<string> {
    await new Promise<void>((resolve, reject) => {
      this.server.once('error', reject)
      this.server.listen(port, '127.0.0.1', () => { this.server.off('error', reject); resolve() })
    })
    this.endpoint = 'http://127.0.0.1:' + (this.server.address() as AddressInfo).port
    return this.endpoint
  }

  capture(grant: string, mode: 'pass' | 'offline' | 'drop') {
    if (!/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/.test(grant)) throw new Error('Choose the disposable capture grant.')
    this.grant = grant; this.mode = mode
    this.check()
  }

  interruptRetirement(grant: string) {
    if (this.retirementGrant || !/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/.test(grant)) throw new Error('Choose one disposable grant retirement to interrupt.')
    this.retirementGrant = grant; this.dropRetirement = true
  }

  check() { if (this.failure) throw this.failure }

  async close() {
    this.server.closeAllConnections()
    await new Promise<void>((resolve, reject) => this.server.close(error => error ? reject(error) : resolve()))
  }
}
