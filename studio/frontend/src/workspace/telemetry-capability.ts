/** Offline build capability, separate from consent, metering and a live send. */
import contract from '../../../../mnemion/product_telemetry/disclosure.json'

export function destinationValid(value: unknown): value is string {
  if (typeof value !== 'string' || value.length > 512) return false
  try {
    const url = new URL(value)
    return url.protocol === 'https:' && !url.username && !url.password && !url.search && !url.hash &&
      url.pathname === '/v3/report' && url.href === value
  } catch { return false }
}

export function browserTransportAvailable(): boolean {
  return contract.collection_available && destinationValid(contract.destination)
}
