import { workspaceFetch } from './workspace-fetch.js'

/** Sign-in and identity fetches hide transport failures behind one sentence.
 * Only exact platform code tokens and a few error names select a class.
 * Cancellation, malformed values, and unknown codes keep the generic sentence.
 * The caught value is never copied into the message, cause, or a log.
 */

type Transport = 'dns' | 'tls' | 'proxy' | 'timeout' | 'connection' | 'redirect'
type Classified = Transport | 'unknown'
export type WorkspaceNetworkBoundary = 'sign-in' | 'identity'

const CODE = /^[A-Z][A-Z0-9_]{1,63}$/
const NET_CODE = /^net::(ERR_[A-Z0-9_]{1,60})$/
const NAME = /^[A-Za-z][A-Za-z0-9]{1,63}$/

const signInUnknown = 'The workspace could not confirm this sign-in request. Check the connection and sign in again.'
const identityUnknown = 'The workspace could not be reached. Check its address and your network or VPN. If an agent hosts it, use the host’s operator controls to check that its computer and network connection are running.'
const hosted = 'If an agent hosts it, use the host’s operator controls to check that its computer and network connection are running.'

const messages: Record<WorkspaceNetworkBoundary, Record<Classified, string>> = {
  'sign-in': {
    unknown: signInUnknown,
    dns: 'The workspace could not confirm this sign-in request. The address did not resolve. Check the address and sign in again.',
    tls: 'The workspace could not confirm this sign-in request. The secure connection was not accepted. Check the server certificate and the device clock, then sign in again.',
    proxy: 'The workspace could not confirm this sign-in request. The network proxy did not complete the connection. Check the proxy settings and sign in again.',
    timeout: 'The workspace could not confirm this sign-in request. The connection timed out before it could be confirmed. Check the network and sign in again.',
    connection: 'The workspace could not confirm this sign-in request. The connection was refused, reset, or closed before the workspace confirmed it. Check the connection and sign in again.',
    redirect: 'The workspace could not confirm this sign-in request. A redirect was refused, so the sign-in was not followed. Check the workspace address and sign in again.',
  },
  identity: {
    unknown: identityUnknown,
    dns: 'The workspace could not be reached. Its address did not resolve. Check the address, DNS, and VPN. ' + hosted,
    tls: 'The workspace could not be reached. The secure connection was not accepted. Check the server certificate and the device clock. ' + hosted,
    proxy: 'The workspace could not be reached. The network proxy did not complete the connection. Check the proxy settings. ' + hosted,
    timeout: 'The workspace could not be reached. The connection timed out. Check the network or VPN and try again. ' + hosted,
    connection: 'The workspace could not be reached. The connection was refused, reset, or closed. Check the address and that the workspace is running. ' + hosted,
    redirect: 'The workspace could not be reached. A redirect was refused and was not followed. Check the workspace address. ' + hosted,
  },
}

function assign(target: Record<string, Transport>, kind: Transport, codes: readonly string[]): void {
  for (const code of codes) target[code] = kind
}

const byCode: Record<string, Transport> = Object.create(null)
assign(byCode, 'dns', [
  'ENOTFOUND', 'EAI_NODATA', 'EAI_NONAME',
  'ERR_NAME_NOT_RESOLVED', 'ERR_NAME_RESOLUTION_FAILED', 'ERR_ICANN_NAME_COLLISION',
  'ERR_DNS_MALFORMED_RESPONSE', 'ERR_DNS_SERVER_REQUIRES_TCP', 'ERR_DNS_SERVER_FAILURE',
  'ERR_DNS_FORMAT_ERROR', 'ERR_DNS_SECURE_RESOLVER_HOSTNAME_RESOLUTION_FAILED',
  'ERR_DNS_OTHER_FAILURE', 'ERR_DNS_REFUSED',
])
assign(byCode, 'tls', [
  'ERR_TLS_CERT_ALTNAME_INVALID', 'ERR_TLS_CERT_ALTNAME_FORMAT', 'ERR_TLS_INVALID_PROTOCOL_METHOD',
  'ERR_TLS_INVALID_PROTOCOL_VERSION', 'ERR_TLS_PROTOCOL_VERSION_CONFLICT',
  'CERT_NOT_YET_VALID', 'CERT_HAS_EXPIRED', 'CRL_NOT_YET_VALID', 'CRL_HAS_EXPIRED', 'CERT_REVOKED',
  'UNABLE_TO_GET_ISSUER_CERT', 'UNABLE_TO_GET_ISSUER_CERT_LOCALLY', 'DEPTH_ZERO_SELF_SIGNED_CERT',
  'SELF_SIGNED_CERT_IN_CHAIN', 'CERT_CHAIN_TOO_LONG', 'UNABLE_TO_GET_CRL', 'UNABLE_TO_VERIFY_LEAF_SIGNATURE',
  'CERT_UNTRUSTED', 'INVALID_CA', 'PATH_LENGTH_EXCEEDED', 'HOSTNAME_MISMATCH', 'INVALID_PURPOSE',
  'CERT_REJECTED', 'CERT_SIGNATURE_FAILURE', 'CRL_SIGNATURE_FAILURE', 'ERROR_IN_CERT_NOT_BEFORE_FIELD',
  'ERROR_IN_CERT_NOT_AFTER_FIELD', 'ERROR_IN_CRL_LAST_UPDATE_FIELD', 'ERROR_IN_CRL_NEXT_UPDATE_FIELD',
  'UNABLE_TO_DECRYPT_CERT_SIGNATURE', 'UNABLE_TO_DECRYPT_CRL_SIGNATURE', 'UNABLE_TO_DECODE_ISSUER_PUBLIC_KEY',
  'ERR_CERT_COMMON_NAME_INVALID', 'ERR_CERT_DATE_INVALID', 'ERR_CERT_AUTHORITY_INVALID',
  'ERR_CERT_CONTAINS_ERRORS', 'ERR_CERT_NO_REVOCATION_MECHANISM', 'ERR_CERT_UNABLE_TO_CHECK_REVOCATION',
  'ERR_CERT_REVOKED', 'ERR_CERT_INVALID', 'ERR_CERT_WEAK_SIGNATURE_ALGORITHM', 'ERR_CERT_NON_UNIQUE_NAME',
  'ERR_CERT_WEAK_KEY', 'ERR_CERT_NAME_CONSTRAINT_VIOLATION', 'ERR_CERT_VALIDITY_TOO_LONG',
  'ERR_CERTIFICATE_TRANSPARENCY_REQUIRED', 'ERR_CERT_KNOWN_INTERCEPTION_BLOCKED', 'ERR_CERT_SELF_SIGNED_LOCAL_NETWORK',
  'ERR_SSL_PROTOCOL_ERROR', 'ERR_SSL_CLIENT_AUTH_CERT_NEEDED', 'ERR_SSL_VERSION_OR_CIPHER_MISMATCH',
  'ERR_SSL_RENEGOTIATION_REQUESTED', 'ERR_BAD_SSL_CLIENT_AUTH_CERT', 'ERR_SSL_NO_RENEGOTIATION',
  'ERR_SSL_DECOMPRESSION_FAILURE_ALERT', 'ERR_SSL_BAD_RECORD_MAC_ALERT',
  'ERR_SSL_CLIENT_AUTH_PRIVATE_KEY_ACCESS_DENIED', 'ERR_SSL_CLIENT_AUTH_CERT_NO_PRIVATE_KEY',
  'ERR_SSL_PINNED_KEY_NOT_IN_CERT_CHAIN', 'ERR_SSL_CLIENT_AUTH_SIGNATURE_FAILED', 'ERR_SSL_DECRYPT_ERROR_ALERT',
  'ERR_SSL_SERVER_CERT_CHANGED', 'ERR_SSL_UNRECOGNIZED_NAME_ALERT', 'ERR_SSL_CLIENT_AUTH_CERT_BAD_FORMAT',
  'ERR_SSL_SERVER_CERT_BAD_FORMAT', 'ERR_SSL_OBSOLETE_CIPHER', 'ERR_SSL_CLIENT_AUTH_NO_COMMON_ALGORITHMS',
  'ERR_TLS13_DOWNGRADE_DETECTED', 'ERR_SSL_KEY_USAGE_INCOMPATIBLE', 'ERR_INVALID_ECH_CONFIG_LIST',
  'ERR_ECH_NOT_NEGOTIATED', 'ERR_ECH_FALLBACK_CERTIFICATE_INVALID', 'ERR_STRICT_ECH_REQUIRED',
])
assign(byCode, 'proxy', [
  'ERR_TUNNEL_CONNECTION_FAILED', 'ERR_PROXY_AUTH_UNSUPPORTED', 'ERR_PROXY_AUTH_REQUESTED',
  'ERR_PROXY_CONNECTION_FAILED', 'ERR_MANDATORY_PROXY_CONFIGURATION_FAILED', 'ERR_SOCKS_CONNECTION_FAILED',
  'ERR_SOCKS_CONNECTION_HOST_UNREACHABLE', 'ERR_PROXY_CERTIFICATE_INVALID', 'ERR_PAC_SCRIPT_FAILED',
  'ERR_PAC_SCRIPT_TERMINATED', 'ERR_NO_SUPPORTED_PROXIES', 'ERR_PROXY_AUTH_REQUESTED_WITH_NO_CONNECTION',
  'ERR_PROXY_HTTP_1_1_REQUIRED', 'ERR_UNEXPECTED_PROXY_AUTH', 'ERR_PROXY_UNABLE_TO_CONNECT_TO_DESTINATION',
  'UND_ERR_PRX_CONN', 'UND_ERR_PRX_TLS', 'UND_ERR_SOCKS5', 'ERR_PROXY_TUNNEL', 'ERR_PROXY_INVALID_CONFIG',
])
assign(byCode, 'timeout', [
  'ETIMEDOUT', 'ERR_TIMED_OUT', 'ERR_CONNECTION_TIMED_OUT',
  // Chromium defines ERR_CONNECTION_ABORTED as an ACK timeout, not a reset.
  'ERR_CONNECTION_ABORTED', 'ERR_DNS_TIMED_OUT', 'UND_ERR_CONNECT_TIMEOUT', 'UND_ERR_HEADERS_TIMEOUT',
  'UND_ERR_BODY_TIMEOUT', 'ERR_HTTP_REQUEST_TIMEOUT', 'ERR_SOCKET_CONNECTION_TIMEOUT', 'ERR_TLS_HANDSHAKE_TIMEOUT',
])
assign(byCode, 'connection', [
  'ECONNREFUSED', 'ECONNRESET', 'EPIPE', 'ECONNABORTED',
  'ERR_CONNECTION_CLOSED', 'ERR_CONNECTION_RESET', 'ERR_CONNECTION_REFUSED', 'ERR_EMPTY_RESPONSE',
])
assign(byCode, 'redirect', [
  'ERR_TOO_MANY_REDIRECTS', 'ERR_INVALID_REDIRECT', 'ERR_UNSAFE_REDIRECT', 'UND_ERR_REDIRECT_MAX',
])

const byName: Record<string, Transport> = Object.create(null)
assign(byName, 'timeout', ['TimeoutError', 'ConnectTimeoutError', 'HeadersTimeoutError', 'BodyTimeoutError'])
assign(byName, 'redirect', ['MaxRedirectsError'])
assign(byName, 'proxy', ['ProxyConnectionError', 'SecureProxyConnectionError', 'Socks5ProxyError'])

type Read = { state: 'absent' | 'accessor' | 'failed' } | { state: 'value'; value: unknown }

/** Own data properties only. Getters are not called; descriptor traps are caught. */
function readData(value: object, key: string): Read {
  try {
    const descriptor = Object.getOwnPropertyDescriptor(value, key)
    if (!descriptor) return { state: 'absent' }
    if (descriptor.get !== undefined || descriptor.set !== undefined || !('value' in descriptor)) return { state: 'accessor' }
    return { state: 'value', value: descriptor.value }
  } catch {
    return { state: 'failed' }
  }
}

function listed(table: Record<string, Transport>, key: string): Transport | undefined {
  if (!Object.prototype.hasOwnProperty.call(table, key)) return undefined
  const kind = table[key]
  return kind === 'dns' || kind === 'tls' || kind === 'proxy' || kind === 'timeout' || kind === 'connection' || kind === 'redirect' ? kind : undefined
}

/** A string code, an exact `net::ERR_*` token, or nothing. Any other code is alien. */
function readToken(value: object): string | 'alien' | 'failed' | undefined {
  const code = readData(value, 'code')
  if (code.state === 'failed' || code.state === 'accessor') return 'failed'
  if (code.state === 'value' && code.value != null && code.value !== '') {
    const token = code.value
    if (typeof token === 'number' && Number.isFinite(token)) {
      // DOMException's legacy numeric code is not a Node or Electron token.
    } else if (typeof token !== 'string') {
      return 'alien'
    } else {
      const wrapped = NET_CODE.exec(token)
      if (wrapped) return wrapped[1]
      if (!CODE.test(token)) return 'alien'
      return token
    }
  }
  const message = readData(value, 'message')
  if (message.state === 'failed' || message.state === 'accessor') return 'failed'
  if (message.state === 'value' && typeof message.value === 'string') return NET_CODE.exec(message.value)?.[1]
  return undefined
}

function nativeTimeout(value: object): boolean | 'failed' {
  try {
    if (typeof DOMException !== 'function' || !(value instanceof DOMException)) return false
    const getter = Object.getOwnPropertyDescriptor(DOMException.prototype, 'name')?.get
    return getter?.call(value) === 'TimeoutError'
  } catch {
    return 'failed'
  }
}

function childErrors(value: object): unknown[] | 'unsafe' | undefined {
  const nested = readData(value, 'errors')
  if (nested.state === 'absent') return undefined
  if (nested.state !== 'value' || !Array.isArray(nested.value)) return 'unsafe'
  const length = readData(nested.value, 'length')
  if (length.state !== 'value' || typeof length.value !== 'number' || !Number.isInteger(length.value) || length.value < 0 || length.value > 4) return 'unsafe'
  const items: unknown[] = []
  for (let index = 0; index < length.value; index++) {
    const item = readData(nested.value, String(index))
    if (item.state !== 'value' || !item.value || typeof item.value !== 'object') return 'unsafe'
    items.push(item.value)
  }
  return items
}

function classify(error: unknown): Classified {
  const seen = new Set<object>()
  const pending: unknown[] = [error]
  const found = new Set<Transport>()
  let nodes = 0
  while (pending.length > 0) {
    if (nodes >= 8) return 'unknown'
    const current = pending.shift()
    if (!current || typeof current !== 'object') continue
    if (seen.has(current)) continue
    seen.add(current)
    nodes++
    const code = readToken(current)
    if (code === 'failed' || code === 'alien') return 'unknown'
    if (code) {
      const kind = listed(byCode, code)
      if (!kind) return 'unknown'
      found.add(kind)
    } else {
      const name = readData(current, 'name')
      if (name.state === 'failed' || name.state === 'accessor') return 'unknown'
      if (name.state === 'value' && name.value === 'AbortError') return 'unknown'
      if (name.state === 'value' && typeof name.value === 'string' && NAME.test(name.value)) {
        const kind = listed(byName, name.value)
        if (kind) found.add(kind)
      } else {
        const timeout = nativeTimeout(current)
        if (timeout === 'failed') return 'unknown'
        if (timeout) found.add('timeout')
      }
    }
    const cause = readData(current, 'cause')
    if (cause.state === 'failed' || cause.state === 'accessor') return 'unknown'
    if (cause.state === 'value' && cause.value && typeof cause.value === 'object') pending.push(cause.value)
    const nested = childErrors(current)
    if (nested === 'unsafe') return 'unknown'
    if (nested) pending.push(...nested)
  }
  if (found.size !== 1) return 'unknown'
  return found.values().next().value ?? 'unknown'
}

function transportClass(error: unknown): Classified {
  try { return classify(error) } catch { return 'unknown' }
}

function staticMessage(boundary: WorkspaceNetworkBoundary, kind: Classified): string {
  const fallback = boundary === 'identity' ? identityUnknown : signInUnknown
  const table = boundary === 'identity' ? messages.identity : messages['sign-in']
  if (!Object.prototype.hasOwnProperty.call(table, kind)) return fallback
  const text = table[kind]
  return typeof text === 'string' && text.length > 0 ? text : fallback
}

/** Password KDF deliveries need longer than refresh, logout, and the other sign-in calls. */
export function workspaceSignInDeadline(operation: unknown): number {
  return operation === 'login' || operation === 'invitations/accept' ? 60_000 : 20_000
}

export function workspaceNetworkFailure(error: unknown, boundary: WorkspaceNetworkBoundary): Error {
  const fallback = boundary === 'identity' ? identityUnknown : signInUnknown
  try { return new Error(staticMessage(boundary, transportClass(error))) } catch { return new Error(fallback) }
}

export async function workspaceBoundaryFetch(fetcher: (url: string, options: RequestInit) => Promise<Response>, url: string,
  options: RequestInit, boundary: WorkspaceNetworkBoundary): Promise<Response> {
  try {
    return await workspaceFetch(fetcher, url, options)
  } catch (error) {
    throw workspaceNetworkFailure(error, boundary)
  }
}
