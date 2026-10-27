/** Private, bounded lifetimes for the existing Studio service bridge. */
import { randomUUID } from 'node:crypto'

const token = (value: unknown): value is string => typeof value === 'string' &&
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(value)

type Owned = { owner: number; controller: AbortController }

export class ServiceRequests {
  private readonly pending = new Map<string, Owned>()
  private closed = false
  readonly maximum = 128

  async run<T>(owner: number, requestId: unknown, action: (signal: AbortSignal) => Promise<T>): Promise<T> {
    if (this.closed) throw new Error('Studio is shutting down')
    if (!Number.isSafeInteger(owner) || owner < 1 || (requestId !== undefined && !token(requestId))) {
      throw new Error('Invalid local service request')
    }
    // Old frontends may omit a token. They still receive a bounded native
    // lifetime and teardown cancellation, without inventing a remote key.
    const key = `${owner}:${requestId ?? randomUUID()}`
    if (this.pending.has(key)) throw new Error('This local service request is already active')
    if (this.pending.size >= this.maximum) throw new Error('Too many active service requests; wait for current work to finish')
    const item = { owner, controller: new AbortController() }
    this.pending.set(key, item)
    const timer = setTimeout(() => item.controller.abort(new Error('Service request timed out')), 60_000)
    timer.unref()
    try { return await action(item.controller.signal) }
    finally {
      clearTimeout(timer)
      if (this.pending.get(key) === item) this.pending.delete(key)
    }
  }

  cancel(owner: number, requestId: unknown): boolean {
    if (!token(requestId)) return false
    const item = this.pending.get(`${owner}:${requestId}`)
    if (!item) return false
    item.controller.abort(new Error('Service request cancelled'))
    // Abort requests cleanup; it is not evidence that native work has ended.
    // Retain the slot until its own finally, including a delayed auth lookup.
    return true
  }

  closeOwner(owner: number): void {
    for (const item of this.pending.values()) if (item.owner === owner) item.controller.abort(new Error('Studio page closed'))
  }

  close(): void {
    this.closed = true
    for (const item of this.pending.values()) item.controller.abort(new Error('Studio closed'))
  }
}
