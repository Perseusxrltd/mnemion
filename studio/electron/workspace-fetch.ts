/** Authenticated workspace requests must observe the server's current state. */
async function authorizationBeforeDeadline(current: () => Promise<string>, signal?: AbortSignal | null): Promise<string> {
  signal?.throwIfAborted()
  if (!signal) return current()
  let remove = () => {}
  try {
    return await Promise.race([Promise.resolve().then(current), new Promise<string>((_, reject) => {
      const abort = () => reject(signal.reason ?? new Error('Workspace authorization was cancelled'))
      signal.addEventListener('abort', abort, { once: true })
      remove = () => signal.removeEventListener('abort', abort)
    })])
  } finally { remove() }
}

export async function workspaceFetch(fetcher: (url: string, options: RequestInit) => Promise<Response>, url: string, options: RequestInit,
  currentAuthorization?: () => Promise<string>): Promise<Response> {
  const headers = new Headers(options.headers)
  // Free ngrok endpoints otherwise serve their human browser interstitial to
  // Electron's Chromium user agent, even when the request accepts JSON.
  headers.set('ngrok-skip-browser-warning', 'mnemion')
  const request = () => fetcher(url, { ...options, headers, cache: 'no-store', redirect: 'error', credentials: 'omit' })
  const response = await request()
  const retryable = !options.method || options.method === 'GET' || headers.has('idempotency-key') ||
    (options.method === 'POST' && /\/v1\/(recall|context|knowledge)$/.test(new URL(url).pathname))
  if (response.status === 401 && retryable && currentAuthorization && headers.has('authorization')) {
    try {
      options.signal?.throwIfAborted()
      const current = await authorizationBeforeDeadline(currentAuthorization, options.signal)
      options.signal?.throwIfAborted()
      if (current !== headers.get('authorization')) {
        await response.body?.cancel()
        headers.set('authorization', current)
        return request()
      }
    } catch (error) { await response.body?.cancel(); throw error }
  }
  return response
}
