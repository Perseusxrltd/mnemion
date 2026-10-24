import contract from '../../../../mnemion/product_telemetry/disclosure.json'
import measurementCatalog from '../../../../mnemion/product_telemetry/catalog.json'
import type { TelemetryChoice, TelemetryCompanyPolicy, TelemetryPreview, TelemetryStatus } from '../../../shared/product-telemetry'
import { collect, pendingState, telemetryCatalog } from './telemetry-aggregate'

export const choiceKey = 'mnemion.product-telemetry.choice.v1'
export const queueKey = 'mnemion.product-telemetry.pending.v1'
const groups = contract.metric_groups
const own = (value: object, keys: string[]) => Object.keys(value).every(key => keys.includes(key))

export function browserCompanyPolicy(): TelemetryCompanyPolicy {
  const value = document.querySelector('meta[name="mnemion-product-telemetry-policy"]')?.getAttribute('content')
  if (value === undefined || value === null) return { state: 'unmanaged', enabled: true, metric_groups: [...groups] }
  try {
    if (value.length > 8192) throw new Error()
    const policy = JSON.parse(value)
    if (!policy || typeof policy !== 'object' || Array.isArray(policy) ||
        !own(policy, ['state', 'enabled', 'metric_groups']) || Object.keys(policy).length !== 3 ||
        !['unmanaged', 'restricted', 'unreadable'].includes(policy.state) || typeof policy.enabled !== 'boolean' ||
        !Array.isArray(policy.metric_groups) || policy.metric_groups.length > groups.length ||
        policy.metric_groups.some((group: unknown) => typeof group !== 'string' || !groups.includes(group)) ||
        new Set(policy.metric_groups).size !== policy.metric_groups.length ||
        (policy.state === 'unreadable' && policy.enabled)) throw new Error()
    return policy
  } catch { return { state: 'unreadable', enabled: false, metric_groups: [] } }
}

/** The browser owns its origin-local choice; no account or device ID is made. */
export class BrowserTelemetry {
  private storageFailed = false
  constructor(
    private readonly storage: () => Storage = () => window.localStorage,
    private readonly company: () => TelemetryCompanyPolicy = browserCompanyPolicy,
    private readonly privacy: () => boolean = () => (navigator as Navigator & { globalPrivacyControl?: boolean }).globalPrivacyControl === true,
    private readonly coordinated: () => boolean = () => Boolean(navigator.locks),
  ) {}

  status(): TelemetryStatus {
    let preference = { schema_version: 1, revision: 0, enabled: true, disclosure_version: 0 }
    let storage: TelemetryStatus['storage'] = 'new', pending = 0
    try {
      const local = this.storage(), raw = local.getItem(choiceKey), queue = local.getItem(queueKey)
      if (raw !== null) {
        if (raw.length > 2048) throw new Error()
        const parsed = JSON.parse(raw)
        if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed) ||
            !own(parsed, ['schema_version', 'revision', 'enabled', 'disclosure_version']) || Object.keys(parsed).length !== 4 ||
            parsed.schema_version !== 1 || !Number.isInteger(parsed.revision) || parsed.revision < 0 || parsed.revision >= 2147483647 ||
            typeof parsed.enabled !== 'boolean' || !Number.isInteger(parsed.disclosure_version) ||
            parsed.disclosure_version < 0 || parsed.disclosure_version > contract.version) throw new Error()
        preference = parsed
        storage = 'ready'
      }
      if (queue !== null) {
        if (queue.length > contract.limits.pending_bytes / 2) throw new Error()
        if (new TextEncoder().encode(queue).byteLength > contract.limits.pending_bytes) throw new Error()
        const entries = JSON.parse(queue)
        if (!Array.isArray(entries)) pending = pendingState(queue).entries.length
        else {
          // Older source-only controls used an array. It can be cleared by an
          // explicit choice, but is never admitted by a producer or sender.
          if (entries.length > contract.limits.pending_records || entries.some(entry =>
            !entry || typeof entry !== 'object' || Array.isArray(entry) ||
            !own(entry, ['cell', 'count', 'window_day']) || Object.keys(entry).length !== 3 ||
            !Number.isInteger(entry.cell) || entry.cell < 0 || entry.cell > 65535 ||
            !Number.isInteger(entry.count) || entry.count < 1 || entry.count > 65535 ||
            !Number.isInteger(entry.window_day) || entry.window_day < 0 || entry.window_day > 1000000)) throw new Error()
          pending = entries.length
        }
      }
    } catch { storage = 'unreadable' }
    if (this.storageFailed) storage = 'unreadable'
    const company = this.company()
    const reason: TelemetryStatus['reason'] = storage === 'unreadable' ? 'storage_unavailable'
      : !preference.enabled ? 'user_disabled' : !this.coordinated() ? 'coordination_unavailable'
      : this.privacy() ? 'browser_privacy'
      : !company.enabled || !company.metric_groups.length ? 'company_policy'
      : preference.disclosure_version !== contract.version ? 'disclosure_required'
      : !contract.collection_available || !contract.destination ? 'collection_unavailable' : 'enabled'
    return {
      schema_version: 1, revision: preference.revision, default_enabled: true,
      user_enabled: preference.enabled, effective_enabled: reason === 'enabled', reason, storage,
      disclosure_version: preference.disclosure_version, required_disclosure_version: contract.version,
      company_policy: company, pending_records: storage === 'unreadable' ? null : pending,
      collection_available: contract.collection_available,
      disclosure: { ...contract, choice_scope: 'this browser and site' },
    }
  }

  configure(input: TelemetryChoice): TelemetryStatus {
    if (!input || typeof input !== 'object' || Array.isArray(input) ||
        !own(input, ['enabled', 'expected_revision', 'disclosure_version']) ||
        typeof input.enabled !== 'boolean' || !Number.isInteger(input.expected_revision) ||
        input.expected_revision < 0 || input.expected_revision >= 2147483647 ||
        ![0, contract.version].includes(input.disclosure_version ?? 0)) {
      throw new Error('Choose whether to share anonymous product statistics.')
    }
    const current = this.status()
    if (current.storage === 'unreadable') throw new Error('Privacy storage is unavailable. Product telemetry stays off.')
    if (input.enabled && input.expected_revision !== current.revision) throw new Error('Your privacy choice changed in another tab. Refresh before enabling telemetry.')
    const acknowledged = input.disclosure_version ?? 0
    if (acknowledged && (!contract.collection_available || !contract.destination)) throw new Error('Collection is not available in this build. Your privacy choice can still be saved.')
    const disclosureVersion = input.enabled ? acknowledged : 0
    // Every explicit opt-out invalidates any earlier pending enable, including
    // another opt-out while the saved value was already false.
    const changed = !input.enabled || input.enabled !== current.user_enabled || disclosureVersion !== current.disclosure_version
    const next = { schema_version: 1, revision: current.revision + (changed ? 1 : 0), enabled: input.enabled, disclosure_version: disclosureVersion }
    try {
      const storage = this.storage()
      // Enabling starts empty; disabling first persists the restrictive choice.
      if (input.enabled) storage.removeItem(queueKey)
      storage.setItem(choiceKey, JSON.stringify(next))
      if (!input.enabled) storage.removeItem(queueKey)
    } catch {
      this.storageFailed = true
      throw new Error('Privacy storage could not save the choice. Product telemetry stays off. Restore browser storage access and reload before changing this choice.')
    }
    return this.status()
  }

  preview(): TelemetryPreview {
    const status = this.status()
    let local: NonNullable<TelemetryPreview['local_aggregates']> = []
    if (status.effective_enabled) {
      try {
        const day = Math.floor(Date.now() / 86400000)
        local = pendingState(this.storage().getItem(queueKey)).entries.filter(row => row.window_day >= day - 1 && row.window_day <= day)
          .filter(row => status.company_policy.metric_groups.includes(telemetryCatalog.describe(row.cell).group))
          .sort((left, right) => left.cell - right.cell).map(row => ({ cell: row.cell, ...telemetryCatalog.describe(row.cell), count: row.count }))
      } catch { /* Invalid queues never become raw diagnostic output. */ }
    }
    return { schema_version: 1, status, outbound_body: null, outbound_bytes: 0,
      transport_available: false, message: 'No product-telemetry sender is active in this build.',
      measurement_catalog: measurementCatalog, local_aggregates: local }
  }

  /** Internal producer boundary; caller holds the origin-wide privacy lock. */
  record(input: unknown, expectedRevision: number, day = Math.floor(Date.now() / 86400000)): boolean {
    if (!contract.collection_available || !contract.destination || !Number.isInteger(expectedRevision)) return false
    const current = this.status()
    if (!current.effective_enabled || current.revision !== expectedRevision) return false
    let serialized: string, recorded: boolean
    try {
      const result = collect(pendingState(this.storage().getItem(queueKey)), input, day, current.company_policy.metric_groups)
      serialized = JSON.stringify(result.state)
      if (serialized.length > contract.limits.pending_bytes / 2 || new TextEncoder().encode(serialized).byteLength > contract.limits.pending_bytes) return false
      recorded = result.recorded
    } catch { return false }
    try { this.storage().setItem(queueKey, serialized) }
    catch { this.storageFailed = true; return false }
    return recorded
  }
}

const browser = new BrowserTelemetry()

export async function telemetryStatus(): Promise<TelemetryStatus> {
  if (window.mnemion?.productTelemetry) return window.mnemion.productTelemetry('telemetry.status')
  if (window.location.protocol === 'file:') throw new Error('This desktop does not provide product telemetry controls. Update the app to use them.')
  return browser.status()
}

export async function telemetryConfigure(input: TelemetryChoice): Promise<TelemetryStatus> {
  if (window.mnemion?.productTelemetry) return window.mnemion.productTelemetry('telemetry.configure', input)
  if (window.location.protocol === 'file:') throw new Error('This desktop does not provide product telemetry controls.')
  if (!navigator.locks) throw new Error('This browser cannot coordinate privacy settings between tabs. Product telemetry remains unavailable.')
  return navigator.locks.request(choiceKey, () => browser.configure(input))
}

export async function telemetryPreview(): Promise<TelemetryPreview> {
  if (window.mnemion?.productTelemetry) return window.mnemion.productTelemetry('telemetry.preview')
  if (window.location.protocol === 'file:') throw new Error('This desktop does not provide product telemetry controls.')
  return browser.preview()
}

/** Best effort and no lock waiting. No networking or queue of raw input objects. */
export async function recordBrowserTelemetry(input: unknown, expectedRevision: number): Promise<boolean> {
  if (!contract.collection_available || !contract.destination || window.location.protocol === 'file:' || !navigator.locks) return false
  try {
    return await navigator.locks.request(choiceKey, { ifAvailable: true }, lock => lock ? browser.record(input, expectedRevision) : false)
  } catch { return false }
}
