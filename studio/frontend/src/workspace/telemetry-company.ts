/** Fixed company restrictions; no account, identifier, measurement or cache. */
import contract from '../../../../mnemion/product_telemetry/disclosure.json'
import type { TelemetryCompanyPolicy } from '../../../shared/product-telemetry'

export const companyPolicyPath = '/studio/telemetry-policy'
const groups = contract.metric_groups
const denied = (): TelemetryCompanyPolicy => ({ state: 'unreadable', enabled: false, metric_groups: [] })

export function parseCompanyPolicy(value: unknown): TelemetryCompanyPolicy {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return denied()
  const policy = value as Record<string, unknown>
  if (Object.keys(policy).length !== 3 || !Object.keys(policy).every(key => ['state', 'enabled', 'metric_groups'].includes(key)) ||
      !['unmanaged', 'restricted', 'unreadable'].includes(policy.state as string) || typeof policy.enabled !== 'boolean' ||
      !Array.isArray(policy.metric_groups) || policy.metric_groups.length > groups.length ||
      policy.metric_groups.some(group => typeof group !== 'string' || !groups.includes(group)) ||
      new Set(policy.metric_groups).size !== policy.metric_groups.length ||
      (policy.state === 'unreadable' && (policy.enabled || policy.metric_groups.length))) return denied()
  // Keep only validated primitives; later response/caller mutations cannot
  // widen the restriction or turn private fields into local/outgoing data.
  return { state: policy.state as TelemetryCompanyPolicy['state'], enabled: policy.enabled,
    metric_groups: groups.filter(group => (policy.metric_groups as string[]).includes(group)) }
}

export function browserCompanyPolicy(): TelemetryCompanyPolicy {
  const value = document.querySelector('meta[name="mnemion-product-telemetry-policy"]')?.getAttribute('content')
  if (value === undefined || value === null) return { state: 'unmanaged', enabled: true, metric_groups: [...groups] }
  try { return value.length <= 8192 ? parseCompanyPolicy(JSON.parse(value)) : denied() }
  catch { return denied() }
}

/** A page reload is needed to relax an observed restriction. Fresh responses
 * never acknowledge disclosure or override the user's origin-local choice. */
export function restrictCompanyPolicy(left: TelemetryCompanyPolicy, right: TelemetryCompanyPolicy): TelemetryCompanyPolicy {
  const before = parseCompanyPolicy(left), next = parseCompanyPolicy(right)
  if (before.state === 'unreadable' || next.state === 'unreadable') return denied()
  return { state: before.state === 'restricted' || next.state === 'restricted' ? 'restricted' : 'unmanaged',
    enabled: before.enabled && next.enabled,
    metric_groups: before.metric_groups.filter(group => next.metric_groups.includes(group)) }
}

/** One credential-free read inside an already spent attempt. Its caller owns
 * cancellation, the five-second attempt deadline and the final privacy lock. */
export async function readBrowserCompanyPolicy(signal: AbortSignal,
  guard: (start: () => boolean) => Promise<boolean>, handedOff: () => void): Promise<TelemetryCompanyPolicy> {
  let reader: ReadableStreamDefaultReader<Uint8Array> | undefined
  const bytes = new Uint8Array(1024)
  try {
    const location = window.location
    if (location.protocol !== 'https:' && !(location.protocol === 'http:' &&
        ['localhost', '127.0.0.1', '[::1]'].includes(location.hostname))) return denied()
    const url = new URL(companyPolicyPath, location.origin).href
    let pending: Promise<Response | null> | undefined
    const started = await guard(() => {
      if (signal.aborted) return false
      pending = fetch(url, { method: 'GET', mode: 'same-origin', credentials: 'omit', cache: 'no-store',
        redirect: 'error', referrerPolicy: 'no-referrer', keepalive: false, signal,
      }).then(response => response, () => null)
      return true
    })
    handedOff()
    if (!started || !pending || signal.aborted) return denied()
    const response = await pending
    if (!response || signal.aborted || response.status !== 200 || response.redirected || response.url !== url ||
        response.headers.get('content-type')?.split(';')[0].trim().toLowerCase() !== 'application/json' ||
        !response.headers.get('cache-control')?.split(',').some(value => value.trim().toLowerCase() === 'no-store') ||
        ![null, '0'].includes(response.headers.get('age'))) return denied()
    const length = response.headers.get('content-length')
    if (length === null || !/^[1-9][0-9]{0,3}$/.test(length) || Number(length) > bytes.length || !response.body) return denied()
    reader = response.body.getReader()
    let used = 0
    for (let chunks = 0; chunks < 8; chunks++) {
      const part = await reader.read()
      if (signal.aborted) return denied()
      if (part.done) {
        if (used !== Number(length)) return denied()
        return parseCompanyPolicy(JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(bytes.subarray(0, used))))
      }
      if (!part.value?.byteLength || part.value.byteLength > Number(length) - used) return denied()
      bytes.set(part.value, used); used += part.value.byteLength
    }
    return denied()
  } catch { return denied() }
  finally {
    handedOff(); bytes.fill(0)
    // Never wait for cleanup of a malformed peer beyond the owned deadline.
    if (reader) void reader.cancel().catch(() => {})
  }
}
