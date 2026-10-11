/** Authenticated workspace requests must observe the server's current state. */
export function workspaceFetch(fetcher: (url: string, options: RequestInit) => Promise<Response>, url: string, options: RequestInit): Promise<Response> {
  const headers = new Headers(options.headers)
  // Free ngrok endpoints otherwise serve their human browser interstitial to
  // Electron's Chromium user agent, even when the request accepts JSON.
  headers.set('ngrok-skip-browser-warning', 'mnemion')
  return fetcher(url, {
    ...options, headers, cache: 'no-store', redirect: 'error', credentials: 'omit',
  })
}
