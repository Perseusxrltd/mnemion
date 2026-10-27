/** Installed-gate loopback checks through the real renderer/preload/main bridge. */
import { createServer } from 'node:http'
import type { BrowserWindow } from 'electron'

function deferred() {
  let resolve!: () => void
  return { promise: new Promise<void>(done => { resolve = done }), resolve: () => resolve() }
}

async function bounded<T>(work: Promise<T>): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined
  try {
    return await Promise.race([work, new Promise<never>((_, reject) => {
      timer = setTimeout(() => reject(new Error('Installed service cancellation did not complete')), 15_000)
    })])
  } finally { clearTimeout(timer) }
}

export async function verifyNativeServiceRequests(window: BrowserWindow): Promise<Record<string, boolean>> {
  const states = { headers: { entered: deferred(), closed: deferred() }, body: { entered: deferred(), closed: deferred() } }
  const observed: string[] = []
  const tokens: string[] = []
  const server = createServer((request, response) => {
    const phase = request.url === '/v1/service-request-probe/headers' ? 'headers'
      : request.url === '/v1/service-request-probe/body' ? 'body' : null
    if (!phase) { response.writeHead(404); response.end(); return }
    observed.push(JSON.stringify(request.headers))
    response.once('close', states[phase].closed.resolve)
    if (phase === 'body') { response.writeHead(200, { 'Content-Type': 'application/json' }); response.write('{"pending":') }
    states[phase].entered.resolve()
  })
  try {
    await bounded(new Promise<void>((resolve, reject) => {
      server.once('error', reject)
      server.listen(0, '127.0.0.1', resolve)
    }))
    const address = server.address()
    if (!address || typeof address === 'string') throw new Error('Missing native loopback listener')
    for (const phase of ['headers', 'body'] as const) {
      const url = `http://127.0.0.1:${address.port}/v1/service-request-probe/${phase}`
      const id = await bounded(window.webContents.executeJavaScript(`(() => {
        const id = crypto.randomUUID();
        const pending = window.mnemion.serviceRequest({ requestId: id, url: ${JSON.stringify(url)}, method: 'GET', headers: {} })
          .then(() => 'resolved', () => 'cancelled');
        window.__mnemionNativeRequestProbe = { id, pending };
        return id;
      })()`))
      if (typeof id !== 'string' || !/^[0-9a-f-]{36}$/.test(id)) throw new Error('Missing native cancellation token')
      tokens.push(id)
      await bounded(states[phase].entered.promise)
      const result = await bounded(window.webContents.executeJavaScript(`(async () => {
        const probe = window.__mnemionNativeRequestProbe;
        const accepted = await window.mnemion.serviceRequestCancel(probe.id);
        const result = await probe.pending;
        delete window.__mnemionNativeRequestProbe;
        return { accepted, result };
      })()`))
      if (result?.accepted !== true || result?.result !== 'cancelled') throw new Error('Installed native request ignored cancellation')
      await bounded(states[phase].closed.promise)
    }
    if (observed.length !== 2 || observed.some(headers => tokens.some(id => headers.includes(id)))) {
      throw new Error('A local cancellation token reached the loopback server')
    }
    return { nativeServiceCancelBeforeHeaders: true, nativeServiceCancelDuringBody: true, nativeServiceCancelTokenPrivate: true }
  } finally {
    if (!window.isDestroyed() && !window.webContents.isDestroyed()) {
      await bounded(window.webContents.executeJavaScript(`(async () => {
        const probe = window.__mnemionNativeRequestProbe;
        if (probe) { await window.mnemion.serviceRequestCancel(probe.id); delete window.__mnemionNativeRequestProbe; }
      })()`)).catch(() => {})
    }
    await new Promise<void>(resolve => { server.close(() => resolve()); server.closeAllConnections() })
  }
}
