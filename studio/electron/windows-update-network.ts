import { Readable } from 'node:stream'
import type { UpdateFetch } from './windows-update-transfer.js'

/** Electron's net.fetch does not expose manual redirects like Node's fetch.
 * Convert net.request redirect events into responses for our strict URL policy.
 * The caller supplies a dedicated cookie-free session and manual redirect mode.
 */
export function createWindowsUpdateFetch(makeRequest: (url: string) => Electron.ClientRequest): UpdateFetch {
  return (url, options) => new Promise<Response>((resolve, reject) => {
    const request = makeRequest(url)
    let response: Readable | undefined
    let settled = false
    const signal = options.signal
    const cleanup = () => signal?.removeEventListener('abort', cancel)
    const fail = () => {
      cleanup()
      const error = new Error('Update network request failed')
      response?.destroy(error)
      if (!settled) { settled = true; reject(error) }
    }
    const cancel = () => { fail(); request.abort() }
    signal?.addEventListener('abort', cancel, { once: true })
    request.on('error', fail)
    request.once('redirect', (status, method, location) => {
      if (settled) return
      if (method !== 'GET' || ![301, 302, 303, 307, 308].includes(status)) { cancel(); return }
      settled = true
      cleanup()
      // Never follow inside Chromium. The bounded transfer validates the next URL.
      resolve(new Response(null, { status, headers: { location } }))
      request.abort()
    })
    request.once('response', incoming => {
      if (settled) return
      try {
        response = incoming as unknown as Readable
        const headers = new Headers()
        for (const [name, values] of Object.entries(incoming.headers)) {
          for (const value of Array.isArray(values) ? values : [values]) if (value !== undefined) headers.append(name, String(value))
        }
        response.once('end', cleanup)
        response.once('close', cleanup)
        response.once('error', () => { cleanup(); request.abort() })
        const body = [204, 205, 304].includes(incoming.statusCode) ? null : Readable.toWeb(response, {
          strategy: { highWaterMark: 256 * 1024, size: chunk => chunk.byteLength },
        }) as ReadableStream<Uint8Array>
        const result = new Response(body, { status: incoming.statusCode, headers })
        settled = true
        resolve(result)
      } catch { cancel() }
    })
    if (signal?.aborted) { cancel(); return }
    try {
      for (const [name, value] of new Headers(options.headers)) request.setHeader(name, value)
      request.end()
    } catch { cancel() }
  })
}
