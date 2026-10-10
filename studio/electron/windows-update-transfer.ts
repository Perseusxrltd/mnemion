import { open, rm } from 'node:fs/promises'
import { createHash, timingSafeEqual } from 'node:crypto'
import { allowedWindowsRedirect, type WindowsUpdate } from './windows-update-security.js'

export type UpdateFetch = (url: string, options: RequestInit) => Promise<Response>
const IDLE_TIMEOUT = 30_000

/** Consume streams incrementally, with independent total, idle and byte limits. */
export async function transferWindowsUpdate(fetcher: UpdateFetch, initial: string, options: {
  signal: AbortSignal
  limit: number
  timeout: number
  consume: (bytes: Uint8Array) => Promise<void>
  expectedSize?: number
  progress?: (bytes: number) => void
}): Promise<number> {
  const controller = new AbortController()
  const cancel = () => controller.abort()
  options.signal.addEventListener('abort', cancel, { once: true })
  if (options.signal.aborted) cancel()
  const deadline = setTimeout(cancel, options.timeout)
  let idle = setTimeout(cancel, IDLE_TIMEOUT)
  let reader: ReadableStreamDefaultReader<Uint8Array> | undefined
  const refreshIdle = () => { clearTimeout(idle); idle = setTimeout(cancel, IDLE_TIMEOUT) }
  try {
    let url = initial
    let response: Response | undefined
    for (let redirects = 0; redirects <= 3; redirects++) {
      controller.signal.throwIfAborted()
      response = await fetcher(url, { method: 'GET', signal: controller.signal,
        redirect: 'manual', credentials: 'omit', cache: 'no-store',
        headers: { 'Cache-Control': 'no-cache', Accept: 'application/octet-stream' } })
      refreshIdle()
      if ([301, 302, 303, 307, 308].includes(response.status)) {
        const location = response.headers.get('location')
        const next = location ? new URL(location, url).href : ''
        await response.body?.cancel()
        if (redirects === 3 || !allowedWindowsRedirect(url, next, initial)) throw new Error('Unsafe update redirect')
        url = next
        continue
      }
      break
    }
    if (!response || response.status !== 200 || !response.body) throw new Error('Update download is unavailable')
    const length = response.headers.get('content-length')
    if (length !== null && (!/^\d+$/.test(length) || !Number.isSafeInteger(Number(length))
      || Number(length) > options.limit || (options.expectedSize !== undefined && Number(length) !== options.expectedSize))) throw new Error('Invalid update content length')
    reader = response.body.getReader()
    let total = 0
    for (;;) {
      controller.signal.throwIfAborted()
      const { done, value } = await reader.read()
      controller.signal.throwIfAborted()
      if (done) break
      refreshIdle()
      total += value.byteLength
      if (total > options.limit) throw new Error('Update exceeds its download limit')
      await options.consume(value)
      options.progress?.(total)
    }
    if (options.expectedSize !== undefined && total !== options.expectedSize) throw new Error('Truncated update download')
    return total
  } finally {
    controller.abort()
    await reader?.cancel().catch(() => {})
    clearTimeout(deadline)
    clearTimeout(idle)
    options.signal.removeEventListener('abort', cancel)
  }
}

export async function fetchWindowsManifest(fetcher: UpdateFetch, url: string, limit: number, signal: AbortSignal): Promise<Buffer> {
  const chunks: Buffer[] = []
  await transferWindowsUpdate(fetcher, url, { signal, limit, timeout: 30_000,
    consume: async bytes => { chunks.push(Buffer.from(bytes)) } })
  return Buffer.concat(chunks)
}

export async function downloadWindowsInstaller(fetcher: UpdateFetch, path: string, update: WindowsUpdate,
  signal: AbortSignal, progress: (percent: number) => void): Promise<void> {
  // A stale or linked temporary file cannot be followed or overwritten.
  const file = await open(path, 'wx', 0o600)
  const hash = createHash('sha512')
  let lastProgress = -1
  let succeeded = false
  try {
    await transferWindowsUpdate(fetcher, update.url, { signal, limit: update.size,
      expectedSize: update.size, timeout: 20 * 60_000,
      consume: async bytes => {
        hash.update(bytes)
        let offset = 0
        while (offset < bytes.length) {
          const written = await file.write(bytes, offset, bytes.length - offset)
          if (!written.bytesWritten) throw new Error('Could not write the update')
          offset += written.bytesWritten
        }
      },
      progress: bytes => {
        const percent = Math.min(100, Math.floor(bytes / update.size * 100))
        if (percent !== lastProgress) { lastProgress = percent; progress(percent) }
      },
    })
    if (!timingSafeEqual(hash.digest(), Buffer.from(update.sha512, 'base64'))) throw new Error('Update download failed authentication')
    await file.sync()
    succeeded = true
  } finally {
    await file.close()
    if (!succeeded) await rm(path, { force: true })
  }
}
