/** System-browser OIDC with a temporary, bounded loopback code receiver. */
import { randomBytes } from 'node:crypto'
import { createServer } from 'node:http'
import { workspaceEndpoint } from './workspace-store.js'
import { passwordTokens, type PasswordTokens, type SignInRequest } from './workspace-auth.js'
import { companyConfiguration, companyCredentials, companyStart, companyUUID } from './company-sign-in-protocol.js'

export class WorkspaceCompanyAuth {
  private pending?: AbortController
  constructor(private readonly request: SignInRequest, private readonly openBrowser: (url: string) => Promise<void>) {}

  cancel(): void { this.pending?.abort() }

  async configuration(endpoint: string, workspaceId: unknown) {
    endpoint = workspaceEndpoint(endpoint)
    if (!companyUUID(workspaceId)) throw new Error('Use your administrator’s workspace sign-in link.')
    return companyConfiguration(await this.request(endpoint, 'company/configuration', { workspace_id: workspaceId }), endpoint)
  }

  async signIn(endpoint: string, input: unknown): Promise<PasswordTokens> {
    this.cancel()
    endpoint = workspaceEndpoint(endpoint)
    const credentials = companyCredentials(input), controller = new AbortController()
    this.pending = controller
    const path = '/mnemion-company/' + randomBytes(32).toString('base64url')
    let state = '', host = '', complete!: (value: string) => void, reject!: (error: Error) => void
    const callback = new Promise<string>((resolve, fail) => { complete = resolve; reject = fail })
    // Cancellation may arrive while the initial network request is still running.
    void callback.catch(() => {})
    const server = createServer((request, response) => {
      if (request.method !== 'GET' || request.headers.host !== host || request.headers.origin || !request.url || request.url.length > 8192) {
        response.writeHead(400).end(); return
      }
      const url = new URL(request.url, 'http://' + host)
      if (url.pathname !== path || !state || url.searchParams.getAll('state').length !== 1 || url.searchParams.get('state') !== state) {
        response.writeHead(400).end(); return
      }
      const code = url.searchParams.get('code'), error = url.searchParams.has('error')
      if (!error && (!code || code.length > 4096 || url.searchParams.getAll('code').length !== 1)) {
        response.writeHead(400).end(); return
      }
      const nonce = randomBytes(18).toString('base64url')
      response.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer',
        'Content-Security-Policy': `default-src 'none'; script-src 'nonce-${nonce}'; style-src 'nonce-${nonce}'; frame-ancestors 'none'; base-uri 'none'` })
      response.once('finish', () => error ? reject(new Error('Company sign-in was cancelled or declined. Try again.')) : complete(code!))
      response.end(`<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Mnemion · Company sign-in</title><style nonce="${nonce}">body{background:#080c12;color:#eae7df;font:17px system-ui;padding:4rem}h1{color:#c5a05d}</style><h1>Mnemion</h1><p>Return to the app to finish signing in. You can close this window.</p><script nonce="${nonce}">history.replaceState(null,'','/');</script></html>`)
    })
    server.maxConnections = 4
    server.headersTimeout = 3000
    server.requestTimeout = 5000
    server.keepAliveTimeout = 1000
    const abort = () => { reject(new Error('Company sign-in was cancelled.')); server.closeAllConnections(); server.close() }
    const timer = setTimeout(() => controller.abort(), 300_000)
    controller.signal.addEventListener('abort', abort, { once: true })
    try {
      await new Promise<void>((resolve, fail) => {
        server.once('error', fail)
        server.listen(0, '127.0.0.1', () => { server.off('error', fail); resolve() })
      })
      server.on('error', () => reject(new Error('The temporary company sign-in receiver stopped. Try again.')))
      const address = server.address()
      if (!address || typeof address === 'string' || controller.signal.aborted) throw new Error('Company sign-in was cancelled.')
      host = '127.0.0.1:' + address.port
      const flow = companyStart(await this.request(endpoint, 'company/start', {
        ...credentials, transport: 'native', callback_uri: 'http://' + host + path,
      }), credentials.provider_id)
      state = flow.state
      if (controller.signal.aborted) throw new Error('Company sign-in was cancelled.')
      await this.openBrowser(flow.authorization_url)
      const code = await callback
      const tokens = passwordTokens(await this.request(endpoint, 'company/finish', {
        state: flow.state, code_verifier: flow.code_verifier, code, transport: 'native',
      }))
      if (tokens.tenantId !== credentials.workspace_id || tokens.authentication !== 'company') throw new Error('The company login identified another workspace or sign-in method.')
      if (controller.signal.aborted) {
        await this.request(endpoint, 'logout', { workspace_id: tokens.tenantId, session_id: tokens.sessionId,
          refresh_token: tokens.refreshToken, transport: 'native' }).catch(() => {})
        throw new Error('Company sign-in was cancelled.')
      }
      return tokens
    } finally {
      clearTimeout(timer)
      controller.signal.removeEventListener('abort', abort)
      server.closeAllConnections()
      await new Promise<void>(resolve => server.close(() => resolve()))
      if (this.pending === controller) this.pending = undefined
    }
  }
}
