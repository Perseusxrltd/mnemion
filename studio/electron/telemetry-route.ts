/** Immutable release trust only. No TLS loading, sockets or user credentials. */
import { openSync, readSync, closeSync } from 'node:fs'

export type TelemetryRoute = { address: string; certificate_authorities: readonly string[] }

export function validCertificateAuthorities(value: unknown): value is readonly string[] {
  if (!Array.isArray(value) || value.length < 1 || value.length > 2) return false
  const seen = new Set<string>()
  for (const certificate of value) {
    if (typeof certificate !== 'string' || certificate.length > 4096) return false
    const lines = certificate.replace(/\r\n/g, '\n').replace(/\n$/, '').split('\n')
    if (lines.length < 3 || lines[0] !== '-----BEGIN CERTIFICATE-----' || lines.at(-1) !== '-----END CERTIFICATE-----' ||
        lines.slice(1, -1).some(line => !/^[A-Za-z0-9+/=]{1,64}$/.test(line))) return false
    const encoded = lines.slice(1, -1).join('')
    if (!encoded || Buffer.from(encoded, 'base64').toString('base64') !== encoded || seen.has(encoded)) return false
    seen.add(encoded)
  }
  return true
}

export function parseTelemetryRoute(value: unknown): Readonly<TelemetryRoute> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value) ||
      Object.keys(value).sort().join() !== 'address,certificate_authorities,version') return null
  const route = value as Record<string, unknown>
  return route.version === 2 && typeof route.address === 'string' && route.address.length <= 45 &&
    validCertificateAuthorities(route.certificate_authorities)
    ? Object.freeze({ address: route.address, certificate_authorities: Object.freeze([...route.certificate_authorities]) }) : null
}

let cached: Readonly<TelemetryRoute> | null | undefined
export function nativeTelemetryRoute(): Readonly<TelemetryRoute> | null {
  if (cached !== undefined) return cached
  let file: number | undefined
  try {
    file = openSync(new URL('./telemetry-transport-route.json', import.meta.url), 'r')
    const bytes = Buffer.alloc(16385), size = readSync(file, bytes, 0, bytes.length, 0)
    cached = size <= 16384 ? parseTelemetryRoute(JSON.parse(bytes.subarray(0, size).toString('utf8'))) : null
  } catch { cached = null }
  finally { if (file !== undefined) { try { closeSync(file) } catch { cached = null } } }
  return cached
}
