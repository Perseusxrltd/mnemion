import contract from '../../../../mnemion/product_telemetry/disclosure.json'
import measurementCatalog from '../../../../mnemion/product_telemetry/catalog.json'
import type { TelemetryChoice, TelemetryCompanyPolicy, TelemetryConnectionMode, TelemetryPreview, TelemetryReview, TelemetryReviewAction, TelemetryReviewChoice, TelemetryStamp, TelemetryStatus } from '../../../shared/product-telemetry'
import { collect, pendingState, telemetryCatalog } from './telemetry-aggregate'
import type { WorkflowStore } from '../../../electron/telemetry-workflow'
import { budgetKey, budgetState, budgetView, freshBudget, serializeBudget, choiceKey, queueKey, DAY, COST, DAILY_BYTES, type BrowserBudget } from './telemetry-budget'
import { BrowserTelemetryDelivery, type BrowserDeliveryEnvironment } from './telemetry-delivery'
import { BrowserTelemetryActivity } from './telemetry-activity'
import { browserCompanyPolicy, parseCompanyPolicy, restrictCompanyPolicy } from './telemetry-company'
import { TelemetrySnapshotReader } from './telemetry-refusals'
import { clearReview, freshReview, type ReviewState } from '../../../electron/telemetry-review'
import { startReviewLifetime } from '../../../electron/telemetry-review-lifetime'
import { BrowserReviewClock } from './telemetry-review-clock'
import { browserReviewContext, reviewRequest } from './telemetry-review'
import { browserTransportAvailable } from './telemetry-capability'

export { choiceKey, queueKey } from './telemetry-budget'
export { browserCompanyPolicy } from './telemetry-company'
const connectionModes: TelemetryConnectionMode[] = ['auto', 'unmetered', 'metered']
const own = (value: object, keys: string[]) => Object.keys(value).every(key => keys.includes(key))
const validGeneration = (value: unknown): value is string => typeof value === 'string' && /^[0-9a-f]{32}$/.test(value)
function newGeneration(): string {
  // This compare-and-set nonce stays in local policy control, never analytics.
  const bytes = globalThis.crypto.getRandomValues(new Uint8Array(16))
  return Array.from(bytes, value => value.toString(16).padStart(2, '0')).join('')
}

/** The browser owns its origin-local choice; no account or device ID is made. */
export class BrowserTelemetry {
  protected storageFailed = false
  private observedCompany?: TelemetryCompanyPolicy
  readonly delivery: BrowserTelemetryDelivery
  private readonly reviewLocks: () => LockManager | null
  constructor(
    protected readonly storage: () => Storage = () => window.localStorage,
    private readonly company: () => TelemetryCompanyPolicy = browserCompanyPolicy,
    private readonly privacy: () => boolean = () => (navigator as Navigator & { globalPrivacyControl?: boolean }).globalPrivacyControl === true,
    private readonly coordinated: () => boolean = () => Boolean(navigator.locks),
    deliveryEnvironment: Partial<BrowserDeliveryEnvironment> = {},
    readonly reviewClock = new BrowserReviewClock(),
  ) {
    this.reviewLocks = deliveryEnvironment.locks ?? (() => typeof navigator === 'undefined' ? null : navigator.locks ?? null)
    this.delivery = new BrowserTelemetryDelivery({ storage: () => this.storage(), status: () => this.status(),
      reconcile: () => this.finishPendingClear(), fail: () => { this.storageFailed = true },
      reviewClock: () => this.reviewClock.read(), ensureReviewClock: epoch => this.reviewClock.ensure(epoch) }, deliveryEnvironment)
  }

  status(): TelemetryStatus {
    let preference: { schema_version: number; revision: number; enabled: boolean; disclosure_version: number; store_generation: string | null; connection_mode: TelemetryConnectionMode } =
      { schema_version: 1, revision: 0, enabled: true, disclosure_version: 0, store_generation: null, connection_mode: 'auto' }
    let storage: TelemetryStatus['storage'] = 'new', pending = 0, clearing = false
    let delivery = budgetView(null)
    try {
      const local = this.storage(), raw = local.getItem(choiceKey), queue = local.getItem(queueKey)
      if (raw !== null) {
        if (raw.length > 2048) throw new Error()
        const parsed = JSON.parse(raw)
        const fields = ['schema_version', 'revision', 'enabled', 'disclosure_version']
        if (parsed?.schema_version >= 2) fields.push('store_generation')
        if (parsed?.schema_version >= 4) fields.push('connection_mode')
        if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed) ||
            !own(parsed, fields) || Object.keys(parsed).length !== fields.length ||
            ![1, 2, 3, 4, 5].includes(parsed.schema_version) || !Number.isInteger(parsed.revision) || parsed.revision < 0 || parsed.revision >= 2147483647 ||
            typeof parsed.enabled !== 'boolean' || !Number.isInteger(parsed.disclosure_version) ||
            parsed.disclosure_version < 0 || parsed.disclosure_version > contract.version ||
            (parsed.schema_version >= 2 && !validGeneration(parsed.store_generation)) ||
            (parsed.schema_version >= 4 && !connectionModes.includes(parsed.connection_mode))) throw new Error()
        preference = { ...parsed, store_generation: parsed.schema_version >= 2 ? parsed.store_generation : null,
          connection_mode: parsed.schema_version >= 4 ? parsed.connection_mode : 'auto' }
        storage = 'ready'
      }
      const savedBudget = local.getItem(budgetKey)
      const budget = savedBudget === null ? null : budgetState(savedBudget, preference.schema_version < 5)
      if (preference.schema_version >= 3 && (!budget || budget.generation !== preference.store_generation)) throw new Error()
      delivery = budgetView(budget, Date.now(), storage === 'ready' && preference.schema_version < 5 ? 'upgrade_required' : 'not_initialized')
      clearing = Boolean(budget && budget.clear !== 'none')
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
    if (storage === 'unreadable') delivery = { ...delivery, state: 'unavailable', attempts_in_rolling_week: null, reserved_wire_bytes_in_rolling_day: null }
    const initial = parseCompanyPolicy(this.company())
    const company = this.observedCompany ? restrictCompanyPolicy(initial, this.observedCompany) : initial
    const reason: TelemetryStatus['reason'] = storage === 'unreadable' ? 'storage_unavailable'
      : !preference.enabled ? 'user_disabled' : !this.coordinated() || clearing ? 'coordination_unavailable'
      : this.privacy() ? 'browser_privacy'
      : !company.enabled || !company.metric_groups.length ? 'company_policy'
      : preference.disclosure_version !== contract.version || preference.store_generation === null || preference.schema_version < 5 ? 'disclosure_required'
      : !contract.collection_available || !contract.destination ? 'collection_unavailable' : 'enabled'
    return {
      schema_version: 1, revision: preference.revision, store_generation: preference.store_generation, default_enabled: true,
      user_enabled: preference.enabled, effective_enabled: reason === 'enabled', reason, storage,
      connection_mode: preference.connection_mode,
      disclosure_version: preference.disclosure_version, required_disclosure_version: contract.version,
      company_policy: company, pending_records: storage === 'unreadable' ? null : pending,
      collection_available: contract.collection_available,
      disclosure: { ...contract, choice_scope: 'this browser and site' },
      delivery_budget: delivery,
    }
  }

  /** Only fixed restrictive state is retained, in this page's memory. */
  restrictCompany(policy: TelemetryCompanyPolicy): void {
    this.observedCompany = restrictCompanyPolicy(this.status().company_policy, policy)
    if (!this.observedCompany.enabled || !this.observedCompany.metric_groups.length) this.delivery.invalidate()
  }

  configure(input: TelemetryChoice): TelemetryStatus {
    if (!input || typeof input !== 'object' || Array.isArray(input) ||
        !own(input, ['enabled', 'expected_revision', 'expected_generation', 'disclosure_version', 'connection_mode']) ||
        typeof input.enabled !== 'boolean' || !Number.isInteger(input.expected_revision) ||
        input.expected_revision < 0 || input.expected_revision >= 2147483647 ||
        ![0, contract.version].includes(input.disclosure_version ?? 0) ||
        ('connection_mode' in input && !connectionModes.includes(input.connection_mode!)) ||
        (input.expected_generation != null && !validGeneration(input.expected_generation))) {
      throw new Error('Choose whether to share anonymous product statistics.')
    }
    this.delivery.invalidate()
    const current = this.status()
    if (current.storage === 'unreadable') throw new Error('Privacy storage is unavailable. Product telemetry stays off.')
    const stale = input.expected_revision !== current.revision || (input.expected_generation ?? null) !== current.store_generation
    if (input.enabled && stale) throw new Error('Your privacy choice changed in another tab. Refresh before enabling telemetry.')
    const acknowledged = input.disclosure_version ?? 0
    if (acknowledged && (!contract.collection_available || !contract.destination)) throw new Error('Collection is not available in this build. Your privacy choice can still be saved.')
    const disclosureVersion = input.enabled ? acknowledged : 0
    const connectionMode = stale ? current.connection_mode : input.connection_mode ?? current.connection_mode
    // Every explicit opt-out invalidates any earlier pending enable, including
    // another opt-out while the saved value was already false.
    const changed = !input.enabled || input.enabled !== current.user_enabled || disclosureVersion !== current.disclosure_version || connectionMode !== current.connection_mode
    try {
      const next = { schema_version: 5, revision: current.revision + (changed ? 1 : 0),
        store_generation: current.store_generation ?? newGeneration(), enabled: input.enabled, disclosure_version: disclosureVersion,
        connection_mode: connectionMode }
      const storage = this.storage()
      const rawBudget = storage.getItem(budgetKey)
      const budget = rawBudget === null ? freshBudget(next.store_generation) : budgetState(rawBudget, true)
      // Opt-out persists before cleanup. Enabling cannot become effective until
      // the durable clear intent and the empty queue both exist. Spending is
      // retained even when only the old choice key was removed/recreated.
      if (!input.enabled) storage.setItem(choiceKey, JSON.stringify(next))
      this.writeBudget({ ...budget, generation: next.store_generation, lease: null, clear: 'all', review: clearReview(budget.review) })
      this.finishPendingClear()
      if (input.enabled) storage.setItem(choiceKey, JSON.stringify(next))
    } catch {
      this.storageFailed = true
      // Quota failures can prevent saving a larger preference. Removing the
      // old acknowledgement also blocks other tabs and a later reload; never
      // erase the separate spent budget as an error recovery shortcut.
      try { this.storage().removeItem(choiceKey) } catch { /* Storage can be entirely inaccessible. */ }
      throw new Error('Privacy storage could not save the choice. Product telemetry stays off. Restore browser storage access and reload before changing this choice.')
    }
    return this.status()
  }

  protected writeBudget(value: BrowserBudget): void {
    this.storage().setItem(budgetKey, serializeBudget(value))
  }

  /** Caller owns the shared privacy Web Lock; read-only status never repairs. */
  protected finishPendingClear(): void {
    const raw = this.storage().getItem(budgetKey)
    if (raw === null) return
    const budget = budgetState(raw)
    if (budget.clear === 'none') return
    if (budget.clear === 'all') this.storage().removeItem(queueKey)
    else {
      const pending = pendingState(this.storage().getItem(queueKey))
      pending.entries = []
      this.storage().setItem(queueKey, JSON.stringify(pending))
    }
    // If this last write fails, the next owned mutation clears again before
    // admitting another observation. It cannot resurrect the consumed queue.
    this.writeBudget({ ...budget, clear: 'none' })
  }

  private reviewResult(state: ReviewState, message: string, reveal = false): TelemetryReview {
    return { schema_version: 1, status: this.status(), review: { mode: state.mode, token: state.token, outcome: state.outcome,
      report_available: state.report !== null, created_ms: state.report?.lifetime.created_ms ?? null,
      expires_ms: state.report?.lifetime.expires_ms ?? null },
      packet: reveal && state.report ? this.delivery.packetPreview(new Uint8Array(state.report.packet)) : null,
      message, interactive_privacy_qualified: false }
  }

  /** A stored, body-free snapshot. Inspect explicitly to verify its current age. */
  reviewStatus(): TelemetryReview {
    try {
      const status = this.status()
      if (status.storage === 'unreadable') throw new Error()
      const raw = this.storage().getItem(budgetKey), state = raw === null ? freshReview() : budgetState(raw, true).review
      return this.reviewResult(state, state.report ? 'stored_snapshot' : state.outcome)
    } catch { return { ...this.reviewResult(freshReview(), 'unavailable'), review: null } }
  }

  private reviewReady(budget: BrowserBudget, now: number): boolean {
    const view = budgetView(budget, now)
    return view.state === 'ready' && budget.clear === 'none' && view.attempts_in_rolling_week! < 7 &&
      view.reserved_wire_bytes_in_rolling_day! + COST <= DAILY_BYTES
  }

  async reviewAction(action: TelemetryReviewAction, input: TelemetryReviewChoice): Promise<TelemetryReview> {
    const expected = reviewRequest(action, input), locks = this.reviewLocks()
    if (!locks) throw new Error('telemetry_review_unavailable')
    // Resolve a live epoch before taking the short privacy lock. Recheck all
    // policy, token, queue and time data after that asynchronous boundary.
    if (action === 'inspect_report' || action === 'approve_report') {
      const status = this.status(), raw = this.storage().getItem(budgetKey)
      if (status.effective_enabled && status.revision === expected.expected_revision &&
          status.store_generation === expected.expected_generation && raw !== null) {
        const budget = budgetState(raw)
        if (budget.review.mode === 'review' && budget.review.token === expected.expected_review_token) {
          if (budget.review.report) await this.reviewClock.ensure(budget.review.report.lifetime.clock.epoch)
          else if (action === 'inspect_report' && this.reviewReady(budget, Date.now()) && browserTransportAvailable()) {
            const day = Math.floor(Date.now() / DAY)
            const pending = pendingState(this.storage().getItem(queueKey)).entries.some(row => row.window_day >= day - 1 && row.window_day <= day &&
              status.company_policy.metric_groups.includes(telemetryCatalog.describe(row.cell).group))
            if (pending) await this.reviewClock.ensure()
          }
        }
      }
    }
    return locks.request(choiceKey, { ifAvailable: true }, lock => {
      if (!lock) throw new Error('telemetry_busy')
      let changed = false
      try {
        const current = this.status()
        if (current.storage === 'unreadable') throw new Error('telemetry_review_unavailable')
        if (current.revision !== expected.expected_revision || current.store_generation !== expected.expected_generation)
          throw new Error('telemetry_choice_changed')
        const storage = this.storage(), raw = storage.getItem(budgetKey)
        if (raw === null && action !== 'review_mode') return this.reviewStatus()
        let budget = raw === null ? freshBudget(current.store_generation ?? newGeneration()) : budgetState(raw, action === 'review_mode')
        if (budget.review.token !== expected.expected_review_token) throw new Error('telemetry_review_changed')
        if (action === 'review_mode') {
          const generation = current.store_generation ?? newGeneration()
          const initialized = current.storage === 'new' || current.store_generation === null
          const state: ReviewState = budget.review.mode === expected.mode ? budget.review : {
            version: 1, mode: expected.mode!, token: newGeneration(),
            outcome: expected.mode === 'review' ? 'paused' : 'inactive', report: null }
          budget = { ...budget, generation, review: initialized && state.report ? clearReview(state) : state,
            lease: null, clear: initialized ? 'all' : budget.clear }
          changed = true
          this.delivery.invalidate()
          // Version two spending and version five choice jointly fence older
          // bundles. Persist the hold first; never erase spending to migrate.
          this.writeBudget(budget)
          this.finishPendingClear()
          storage.setItem(choiceKey, JSON.stringify({ schema_version: 5, revision: current.revision,
            store_generation: generation, enabled: current.user_enabled, disclosure_version: current.disclosure_version,
            connection_mode: current.connection_mode }))
          return this.reviewResult(budget.review, budget.review.outcome)
        }
        this.finishPendingClear()
        budget = budgetState(storage.getItem(budgetKey)!)
        if (budget.review.mode !== 'review') throw new Error('telemetry_review_not_paused')
        let state = budget.review, message: string = state.outcome, reveal = false
        const now = Date.now(), status = this.status()
        if (action === 'discard_report') {
          state = { ...clearReview(state, 'discarded'), token: newGeneration() }
          budget = { ...budget, lease: null }
          this.delivery.invalidate()
          message = 'discarded'
        } else if (state.report) {
          state = this.delivery.checkedReview(state, status, now)
          if (action === 'approve_report' && state.report) state = { ...state, outcome: 'approved' }
          message = state.outcome; reveal = action === 'inspect_report'
        } else if (action === 'approve_report') message = 'no_report'
        else if (!status.effective_enabled) message = 'collection_not_permitted'
        else if (!browserTransportAvailable()) message = 'transport_unavailable'
        else if (!this.reviewReady(budget, now)) message = 'delivery_not_ready'
        else {
          const day = Math.floor(now / DAY)
          const rows = pendingState(storage.getItem(queueKey)).entries.filter(row => row.window_day >= day - 1 && row.window_day <= day &&
            status.company_policy.metric_groups.includes(telemetryCatalog.describe(row.cell).group))
          if (!rows.length) message = 'no_observations'
          else {
            const lifetime = startReviewLifetime(now, this.reviewClock.read()!, (Math.min(...rows.map(row => row.window_day)) + 2) * DAY)
            const packet = this.delivery.prepareInspection(rows.map(row => [row.cell, row.count]), status.company_policy.metric_groups)
            state = { version: 1, mode: 'review', token: newGeneration(), outcome: 'held',
              report: { ...browserReviewContext(status), packet: [...packet], lifetime } }
            budget = { ...budget, clear: 'entries' }
            message = 'held'; reveal = true
          }
        }
        changed = true
        // One durable write stores the exact bytes and queue-clear intent. A
        // crash cannot leave both a stage and an independently reusable input.
        this.writeBudget({ ...budget, review: state })
        this.finishPendingClear()
        return this.reviewResult(state, message, reveal)
      } catch (error) {
        if (changed) {
          this.storageFailed = true
          try { this.storage().removeItem(choiceKey) } catch { /* No spending refund. */ }
          throw new Error('telemetry_review_unavailable')
        }
        const message = error instanceof Error ? error.message : ''
        throw new Error(['telemetry_choice_changed', 'telemetry_review_changed', 'telemetry_review_not_paused',
          'telemetry_review_clock_unavailable'].includes(message) ? message : 'telemetry_review_unavailable')
      }
    })
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
    return { schema_version: 1, status, outbound_body: null, outbound_bytes: 0, outbound_state: 'not_inspected',
      transport_available: status.delivery_budget!.transport_available,
      message: 'Synthetic report-format example. No actual outgoing packet was inspected.',
      illustrative_packet: this.delivery.formatExample(),
      measurement_catalog: measurementCatalog, local_aggregates: local }
  }

  /** Internal producer boundary; caller holds the origin-wide privacy lock. */
  record(input: unknown, stamp: TelemetryStamp, day = Math.floor(Date.now() / 86400000)): boolean {
    return this.recordMany([input], stamp, day)
  }

  recordMany(inputs: unknown[], stamp: TelemetryStamp, day = Math.floor(Date.now() / 86400000)): boolean {
    if (!contract.collection_available || !contract.destination || !stamp || !Number.isInteger(stamp.revision) || !validGeneration(stamp.store_generation)) return false
    try { this.finishPendingClear() } catch { this.storageFailed = true; return false }
    const current = this.status()
    if (!current.effective_enabled || current.revision !== stamp.revision || current.store_generation !== stamp.store_generation) return false
    try {
      const raw = this.storage().getItem(budgetKey)
      if (raw !== null) {
        const budget = budgetState(raw)
        if (budget.review.report) {
          // A tab without the live epoch only erases on known wall expiry;
          // it cannot recreate or approve that epoch as a producer.
          const now = Date.now(), lifetime = budget.review.report.lifetime
          const checked = this.reviewClock.read() ? this.delivery.checkedReview(budget.review, current, now)
            : now < lifetime.checked_ms || now >= lifetime.expires_ms ? clearReview(budget.review, 'expired') : budget.review
          if (!checked.report) this.writeBudget({ ...budget, review: checked })
        }
      }
    } catch { this.storageFailed = true; return false }
    let serialized: string, recorded: boolean
    try {
      if (!Array.isArray(inputs) || inputs.length < 1 || inputs.length > 2) return false
      for (const input of inputs) telemetryCatalog.observation(input)
      let state = pendingState(this.storage().getItem(queueKey))
      recorded = false
      for (const input of inputs) {
        const result = collect(state, input, day, current.company_policy.metric_groups)
        state = result.state; recorded ||= result.recorded
      }
      serialized = JSON.stringify(state)
      if (serialized.length > contract.limits.pending_bytes / 2 || new TextEncoder().encode(serialized).byteLength > contract.limits.pending_bytes) return false
    } catch { return false }
    try { this.storage().setItem(queueKey, serialized) }
    catch { this.storageFailed = true; return false }
    return recorded
  }
}

const browser: BrowserTelemetry = new BrowserTelemetry(undefined, undefined, undefined, undefined,
  { conditions: () => browserActivity.conditions.read() })
const browserActivity: BrowserTelemetryActivity = new BrowserTelemetryActivity(browser)
let desktopSnapshots: TelemetrySnapshotReader | undefined

export async function telemetryStatus(): Promise<TelemetryStatus> {
  if (window.mnemion?.productTelemetry) return window.mnemion.productTelemetry('telemetry.status')
  if (window.location.protocol === 'file:') throw new Error('This desktop does not provide product telemetry controls. Update the app to use them.')
  return browser.status()
}

export async function telemetryConfigure(input: TelemetryChoice): Promise<TelemetryStatus> {
  if (window.mnemion?.productTelemetry) {
    desktopSnapshots?.clear()
    try { return await window.mnemion.productTelemetry('telemetry.configure', input) }
    finally { desktopSnapshots?.clear() }
  }
  if (window.location.protocol === 'file:') throw new Error('This desktop does not provide product telemetry controls.')
  if (!navigator.locks) throw new Error('This browser cannot coordinate privacy settings between tabs. Product telemetry remains unavailable.')
  browserActivity.invalidate()
  return navigator.locks.request(choiceKey, () => browser.configure(input))
}

export async function telemetryPreview(): Promise<TelemetryPreview> {
  if (window.mnemion?.productTelemetry) return window.mnemion.productTelemetry('telemetry.preview')
  if (window.location.protocol === 'file:') throw new Error('This desktop does not provide product telemetry controls.')
  return browser.preview()
}

export async function telemetryReviewStatus(): Promise<TelemetryReview> {
  if (window.mnemion?.productTelemetry) return window.mnemion.productTelemetry('telemetry.review_status')
  if (window.location.protocol === 'file:') throw new Error('Update the desktop app to use report review.')
  return browser.reviewStatus()
}

export async function telemetryReviewAction(action: TelemetryReviewAction, input: TelemetryReviewChoice): Promise<TelemetryReview> {
  if (window.mnemion?.productTelemetry) return window.mnemion.productTelemetry(`telemetry.${action}`, input)
  if (window.location.protocol === 'file:') throw new Error('Update the desktop app to use report review.')
  try {
    const result = await browser.reviewAction(action, input)
    if (action === 'approve_report' && result.review?.outcome === 'approved' && result.status.effective_enabled)
      browserActivity.offer({ revision: result.status.revision, store_generation: result.status.store_generation })
    return result
  } catch (error) {
    const messages: Record<string, string> = {
      telemetry_choice_changed: 'Your privacy choice changed. Refresh before changing this report.',
      telemetry_review_changed: 'The report changed in another tab. Inspect its current state again.',
      telemetry_review_not_paused: 'Choose manual report review first.',
      telemetry_review_clock_unavailable: 'The report age could not be verified. No report was approved.',
      telemetry_busy: 'Another privacy action is finishing. Refresh and try again.',
    }
    throw new Error(messages[error instanceof Error ? error.message : ''] ?? 'Report review is unavailable. No report was approved; refresh its status.')
  }
}

/** Best effort and no lock waiting. Only an accepted count can offer delivery. */
export async function recordBrowserTelemetry(input: unknown, stamp: TelemetryStamp): Promise<boolean> {
  return recordBrowserTelemetryMany([input], stamp)
}

export async function recordBrowserTelemetryMany(inputs: unknown[], stamp: TelemetryStamp): Promise<boolean> {
  if (!contract.collection_available || !contract.destination || window.location.protocol === 'file:' || !navigator.locks) return false
  try {
    // Freeze validated primitives and the original policy stamp before yielding
    // to another tab. Neither later argument mutation nor a newer choice can
    // relabel an observation that began under an older generation.
    if (!Array.isArray(inputs) || inputs.length < 1 || inputs.length > 2) return false
    for (const input of inputs) telemetryCatalog.observation(input)
    const values = inputs.map(input => ({ ...(input as Record<string, unknown>) }))
    const expected = { revision: stamp.revision, store_generation: stamp.store_generation }
    const recorded = await navigator.locks.request(choiceKey, { ifAvailable: true }, lock => lock ? browser.recordMany(values, expected) : false)
    // Wait for the actual Web Lock release before a reservation can compete.
    if (recorded) browserActivity.offer(expected)
    return recorded
  } catch { return false }
}

export function telemetrySurface(): 'desktop' | 'browser' {
  return window.location.protocol === 'file:' || Boolean(window.mnemion?.productTelemetrySnapshot) ? 'desktop' : 'browser'
}

/** The app uses its OS-account store; a web session uses its own origin store. */
export const productWorkflowStore: WorkflowStore = {
  get available() { return contract.collection_available && Boolean(contract.destination) },
  catalog: telemetryCatalog,
  snapshot(workflow, surface) {
    if (!this.available) return null
    if (window.mnemion?.productTelemetrySnapshot) {
      if (surface !== undefined && surface !== 'desktop') return null
      const invoke = window.mnemion.productTelemetrySnapshot
      if (desktopSnapshots?.invoke !== invoke) desktopSnapshots = new TelemetrySnapshotReader(invoke, telemetryCatalog.workflows)
      return desktopSnapshots.read(workflow)
    }
    if (window.location.protocol === 'file:') return null
    const status = browser.status()
    return status.effective_enabled ? Promise.resolve({ revision: status.revision, store_generation: status.store_generation }) : null
  },
  async recordMany(values, stamp) {
    if (!this.available) return false
    if (window.mnemion?.productTelemetryRecord) return window.mnemion.productTelemetryRecord(values, stamp)
    return recordBrowserTelemetryMany(values, stamp)
  },
}
