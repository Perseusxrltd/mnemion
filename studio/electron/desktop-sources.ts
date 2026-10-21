/** One bounded source scan at a time, independent of the selected workspace. */
import { randomBytes, randomUUID } from 'node:crypto'
import type { CredentialCipher } from './workspace-store.js'
import { sourceMessages } from './desktop-source-process.js'
import { matchingCaptureHistory, readCaptureArchive, readCapturePreview, readCaptureRecoveries, readCaptureRestored, validCaptureCoverage, validCaptureStorage } from './capture-messages.js'
import type { CaptureArchiveInfo, CaptureBackupInput, CaptureInspectInput, CapturePreview, CaptureRecoveries, CaptureRestored, CaptureRestoreControl, CaptureRestoreInput, CaptureRestoreResult, DesktopSource, DesktopSourceView, SourceActivity, SourceConfigure, SourceControl, SourcePreviewSelection, SourceReason, SourceReport } from '../shared/desktop-sources.js'

type SavedSource = DesktopSource & { sealed_key?: string | null; sealed_provider?: string | null; sealed_inbox_key?: string | null; status_epoch?: string }
type Document = { format: 1; revision: string; sources: SavedSource[] }
export type SourceCall = (request: Record<string, unknown>, signal?: AbortSignal,
  resources?: (bytes: number) => void) => Promise<Record<string, unknown>>
type Options = { call: SourceCall; cipher: CredentialCipher; changed?: () => void; now?: () => number;
  retirementCredential?: (source: DesktopSource, supplied: string) => Promise<string> }
const UUID = /^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/
const messages: Partial<Record<SourceReason, string>> = { ...sourceMessages,
  history_reset: 'Scan history was reset after preserving its damaged record. Earlier outcomes are unknown; source settings and memories were retained.',
  partial: 'The scan was partial. Earlier good memories are retained; check Source status.',
  interrupted: 'An earlier scan did not record its outcome before Studio restarted. Completion and coverage are unknown; its next run will reconcile saved progress.',
  storage_locked: 'Unlock OS credential storage to resume this source.',
  source_credentials_unavailable: 'The source credential could not be unlocked. Check OS credential storage before retrying.',
}
const time = (value: unknown): value is string => typeof value === 'string' &&
  /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)$/.test(value) && Number.isFinite(Date.parse(value))
const reason = (value: unknown): value is SourceReason => typeof value === 'string' &&
  !value.startsWith('agent_') && Object.hasOwn(messages, value)
const continuing = (value: unknown) => value === 'capture_scan_pending' || value === 'capture_delivery_pending'
const object = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value)

function sealedBytes(value: unknown): Buffer {
  if (typeof value !== 'string' || value.length < 16 || value.length > 32768) throw new Error('The saved protected credential is unavailable.')
  const bytes = Buffer.from(value, 'base64')
  if (!bytes.length || bytes.toString('base64') !== value) throw new Error('The saved protected credential is unavailable.')
  return bytes
}

function readReport(value: unknown): SourceReport {
  if (!object(value) || Object.keys(value).some(key => !['completed', 'timestamp', 'duration_seconds',
    'changed', 'removed', 'unchanged', 'conflicts', 'remote_sync_available', 'capture'].includes(key)) ||
    typeof value.completed !== 'boolean' || !time(value.timestamp) || typeof value.remote_sync_available !== 'boolean' ||
    typeof value.duration_seconds !== 'number' || !Number.isFinite(value.duration_seconds) || value.duration_seconds < 0 || value.duration_seconds > 86400 ||
    ['changed', 'removed', 'unchanged', 'conflicts'].some(key => !Number.isSafeInteger(value[key]) || (value[key] as number) < 0 || (value[key] as number) > 1e12)) {
    throw Object.assign(new Error(messages.source_invalid_response), { code: 'source_invalid_response' })
  }
  if (value.capture !== undefined) {
    const capture = value.capture
    const counts = ['locally_accepted', 'pending_events', 'pending_bytes', 'remote_committed_events',
      'stored_events', 'forgotten_events', 'unknown_pages', 'database_bytes', 'device_pending_bytes', 'device_database_bytes']
    if (!object(capture) || Object.keys(capture).some(key => ![...counts, 'over_limit', 'capture_complete', 'delivery_complete', 'reason_code', 'coverage', 'storage', 'history'].includes(key)) ||
      counts.some(key => !Number.isSafeInteger(capture[key]) || (capture[key] as number) < 0 || (capture[key] as number) > 1e12) ||
      ['over_limit', 'capture_complete', 'delivery_complete'].some(key => typeof capture[key] !== 'boolean') ||
      (capture.reason_code != null && !reason(capture.reason_code)) ||
      (capture.coverage != null && !validCaptureCoverage(capture.coverage)) ||
      (capture.storage != null && (!validCaptureStorage(capture.storage) || capture.storage.database_bytes !== capture.database_bytes)) ||
      (capture.history != null && !matchingCaptureHistory(capture.history, capture)) ||
      (value.completed && (!capture.capture_complete || !capture.delivery_complete)) ||
      (capture.delivery_complete && capture.pending_events !== 0)) {
      throw Object.assign(new Error(messages.source_invalid_response), { code: 'source_invalid_response' })
    }
  }
  return value as SourceReport
}

function readActivity(value: unknown): SourceActivity {
  if (!object(value) || Object.keys(value).some(key => !['phase', 'durability', 'started_at', 'finished_at', 'next_scan_at',
    'reason_code', 'report', 'last_success_report', 'last_failure', 'repair_token'].includes(key))) throw new Error('Invalid saved source observation')
  if (value.durability === 'unavailable' && value.phase === 'attention' && value.reason_code === 'source_status_invalid') {
    if (Object.keys(value).some(key => !['phase', 'durability', 'reason_code', 'repair_token'].includes(key)) ||
      (value.repair_token !== undefined && (typeof value.repair_token !== 'string' || !/^[a-f0-9]{64}$/.test(value.repair_token)))) throw new Error('Invalid scan repair observation')
    return { ...value, message: messages.source_status_invalid } as SourceActivity
  }
  if (!['waiting', 'scanning', 'backfill', 'complete', 'attention'].includes(String(value.phase)) || value.durability !== 'saved' || value.repair_token !== undefined ||
    (value.phase !== 'waiting' && !time(value.started_at)) ||
    ['finished_at', 'next_scan_at'].some(key => value[key] !== undefined && !time(value[key])) ||
    (value.reason_code !== undefined && !reason(value.reason_code))) throw new Error('Invalid saved source observation')
  if (value.phase === 'waiting' && (value.reason_code !== 'history_reset' || !time(value.next_scan_at) ||
    ['started_at', 'finished_at', 'report', 'last_success_report', 'last_failure'].some(key => value[key] !== undefined))) throw new Error('Invalid history reset observation')
  if (value.report !== undefined) readReport(value.report)
  if (value.last_success_report !== undefined && !readReport(value.last_success_report).completed) throw new Error('Invalid successful observation')
  if (value.last_failure !== undefined && (!object(value.last_failure) || Object.keys(value.last_failure).some(key => !['observed_at', 'reason_code'].includes(key)) ||
    !time(value.last_failure.observed_at) || !reason(value.last_failure.reason_code) || continuing(value.last_failure.reason_code))) throw new Error('Invalid failed observation')
  if (value.phase === 'complete' && (!value.report || !(value.report as SourceReport).completed || !time(value.finished_at) || !time(value.next_scan_at) || value.reason_code !== undefined)) throw new Error('Unconfirmed source completion')
  if (value.phase === 'attention' && value.reason_code === undefined) throw new Error('Missing source failure reason')
  if (value.phase === 'backfill' || continuing(value.reason_code)) {
    const report = value.report as SourceReport | undefined
    const capture = report?.capture
    const pending = capture?.reason_code === 'capture_scan_pending' ? capture.capture_complete === false :
      capture?.reason_code === 'capture_delivery_pending' && capture.capture_complete === true && capture.delivery_complete === false
    if (value.phase !== 'backfill' || !time(value.finished_at) || !time(value.next_scan_at) ||
      !report || report.completed || !report.remote_sync_available || !capture || !pending ||
      capture.reason_code !== value.reason_code) throw new Error('Unconfirmed backfill progress')
  }
  return { ...value, ...(reason(value.reason_code) ? { message: messages[value.reason_code] } : {}) } as SourceActivity
}

function failureReason(error: unknown): SourceReason {
  const code = object(error) ? error.code : undefined
  return reason(code) && code !== 'history_reset' && !continuing(code) && !code.startsWith('source_status_') ? code : 'source_unavailable'
}

function publicSource(source: SavedSource): DesktopSource {
  const { sealed_key: _private, sealed_provider: _providerPrivate, sealed_inbox_key: _inboxPrivate, status_epoch: _statusPrivate, ...value } = source
  return value
}

export class DesktopSources {
  private document?: Document
  private loading?: Promise<void>
  private controlling = false
  private controlWork?: Promise<unknown>
  private recoveryReading?: Promise<CaptureRecoveries>
  private timer?: ReturnType<typeof setInterval>
  private startRequested = false
  private suspended = false
  private closed = false
  private active?: { id: string; abort: AbortController; work: Promise<void> }
  private pending = new Set<string>()
  private next = new Map<string, number>()
  private activities = new Map<string, SourceActivity>()
  private readonly owner = randomUUID()
  private rss = 0
  constructor(private readonly options: Options) {}
  get busy(): boolean { return this.controlling || !!this.active || !!this.loading }
  get memoryBytes(): number { return this.rss }
  private now(): number { return this.options.now?.() ?? Date.now() }
  private changed() { this.options.changed?.() }

  private unconfirmed(id: string, error: unknown, observed?: SourceActivity): void {
    const code = object(error) && error.code === 'source_status_invalid' ? 'source_status_invalid' : 'source_status_unavailable'
    this.activities.set(id, { ...(observed ?? this.activities.get(id)), phase: 'attention',
      durability: 'unavailable', reason_code: code, message: messages[code] })
  }

  private remember(id: string, activity: SourceActivity) {
    this.activities.set(id, activity)
    if (activity.next_scan_at) this.next.set(id, Date.parse(activity.next_scan_at))
    else this.next.delete(id)
  }

  private async observations(document: Document, selected?: string): Promise<void> {
    try {
      const result = await this.options.call({ operation: 'status', owner: this.owner, expected_revision: document.revision })
      if (result.format !== 1 || !Array.isArray(result.sources) || result.sources.length > 16) throw new Error('Invalid source observations')
      const items = new Map<string, SourceActivity>()
      for (const entry of result.sources) {
        if (!object(entry) || Object.keys(entry).some(key => !['id', 'activity'].includes(key)) ||
          typeof entry.id !== 'string' || !document.sources.some(source => source.id === entry.id) || items.has(entry.id)) throw new Error('Invalid source observation identity')
        items.set(entry.id, readActivity(entry.activity))
      }
      for (const source of document.sources) {
        if (!selected || source.id === selected) this.remember(source.id, items.get(source.id) ?? { phase: 'waiting', durability: 'unknown' })
      }
    } catch (error) {
      for (const source of document.sources) {
        if (!selected || source.id === selected) this.unconfirmed(source.id, error)
      }
    }
  }

  private async ensure(): Promise<void> {
    if (this.document && !this.loading) return
    if (this.closed && !this.loading) throw new Error('Source controls are closing. Reopen the app before loading sources.')
    if (!this.loading) this.loading = (async () => {
      const result = await this.options.call({ operation: 'load' })
      if (result.format !== 1 || typeof result.revision !== 'string' || !Array.isArray(result.sources) || result.sources.length > 16) throw new Error('Saved source settings could not be read. The existing file has been retained.')
      // The native helper validates every field before returning its private file.
      await this.observations(result as Document)
      this.document = result as Document
    })().finally(() => { this.loading = undefined })
    return this.loading
  }

  async status(): Promise<DesktopSourceView> {
    await this.ensure()
    if (!this.busy && this.document!.sources.some(source => this.activities.get(source.id)?.reason_code === 'source_status_invalid' &&
      !this.activities.get(source.id)?.repair_token)) await this.observations(this.document!)
    return { revision: this.document!.revision, secure_storage: await this.options.cipher.available(),
      running: !!this.timer && !this.suspended && !this.closed, memory_bytes: this.rss,
      sources: this.document!.sources.map(source => ({ ...publicSource(source), activity: source.enabled ? {
        ...(this.activities.get(source.id) ?? { phase: 'waiting', durability: 'unknown' }),
        ...(this.next.has(source.id) ? { next_scan_at: new Date(this.next.get(source.id)!).toISOString() } : {}),
      } : { ...(this.activities.get(source.id) ?? { durability: 'unknown' }), phase: 'paused' } })) }
  }

  async start(): Promise<void> {
    this.startRequested = true
    if (this.closed) return
    await this.ensure()
    if (this.closed) return
    if (!this.timer) { this.timer = setInterval(() => { void this.tick() }, 2000); this.timer.unref() }
    void this.tick()
  }

  private async mutate<T>(expected: string, work: () => Promise<T>, schedule = true): Promise<T> {
    await this.ensure()
    if (this.closed || this.suspended || this.controlling) throw new Error('Source controls are busy. Wait for the current operation or app update to finish.')
    if (expected !== this.document!.revision) throw new Error('Source settings changed. Refresh before retrying.')
    this.controlling = true
    const pending = work()
    this.controlWork = pending
    try { return await pending } finally { this.controlWork = undefined; this.controlling = false; this.changed(); if (schedule) void this.tick() }
  }

  private async save(sources: SavedSource[]) {
    return this.updateDocument({ operation: 'store', expected_revision: this.document!.revision, sources })
  }

  private async updateDocument(request: Record<string, unknown>) {
    try {
      const result = await this.options.call(request)
      if (result.format !== 1 || typeof result.revision !== 'string' || !Array.isArray(result.sources)) throw new Error('Source settings could not be confirmed. Refresh before retrying.')
      this.document = result as Document
    } catch (error) {
      // A lost reply may follow a completed write. Reload before any retry;
      // never replay an ambiguous mutation against the previous revision.
      this.document = undefined
      throw error
    }
  }

  async preview(selection: SourcePreviewSelection, signal?: AbortSignal): Promise<CapturePreview> {
    await this.ensure()
    if (this.busy || this.closed) throw new Error('Wait for the current source operation before previewing.')
    this.controlling = true
    const work = Promise.resolve().then(() => this.options.call({ operation: 'preview', selection }, signal))
    this.controlWork = work
    try { return readCapturePreview(await work) }
    finally { this.controlling = false; this.controlWork = undefined; this.changed() }
  }

  async backup(input: CaptureBackupInput, signal?: AbortSignal): Promise<CaptureArchiveInfo> {
    if (!object(input) || Object.keys(input).some(k => !['expected_revision', 'id', 'file', 'recovery_key', 'confirm'].includes(k)) || input.confirm !== true || !UUID.test(input.id)) throw new Error('Choose a paused source and confirm its encrypted backup.')
    return this.mutate(input.expected_revision, async () => {
      if (this.active) throw new Error('Wait for the current scan before creating a capture backup.')
      const source = this.document!.sources.find(item => item.id === input.id)
      if (!source?.custody || source.enabled || !source.sealed_inbox_key) throw new Error('Pause a retained conversation source before creating its backup.')
      if (!await this.options.cipher.available()) throw new Error('Unlock OS credential storage to back up this inbox.')
      const inbox_key = await this.options.cipher.decrypt(sealedBytes(source.sealed_inbox_key))
      signal?.throwIfAborted()
      const result = readCaptureArchive(await this.options.call({ ...input, operation: 'capture_export', inbox_key }, signal))
      if (result.binding.tenant_id !== source.tenant_id || result.binding.connector_id !== source.connector_id ||
        result.binding.source_id !== source.custody.source_id || result.binding.grant_id !== source.custody.grant_id) throw new Error('The backup report does not match the selected inbox. Inspect the saved archive before retrying.')
      return result
    }, false)
  }

  async inspectBackup(input: CaptureInspectInput, signal?: AbortSignal): Promise<CaptureArchiveInfo> {
    if (!object(input) || Object.keys(input).some(k => !['file', 'recovery_key'].includes(k))) throw new Error('Choose an archive and its separate recovery key.')
    // Inspection remains possible when source settings or OS-sealed keys are lost.
    if (this.busy || this.closed || this.suspended) throw new Error('Wait for the current source operation before inspecting an archive.')
    this.controlling = true
    const work = Promise.resolve().then(() => this.options.call({ ...input, operation: 'capture_inspect' }, signal))
    this.controlWork = work
    try { return readCaptureArchive(await work) }
    finally { this.controlling = false; this.controlWork = undefined; this.changed() }
  }

  async recoveries(signal?: AbortSignal): Promise<CaptureRecoveries> {
    if (this.closed || this.suspended) throw new Error('Wait for the app update before inspecting recoveries.')
    // This bounded read exposes only intent metadata, never a key or inbox.
    // Polling must not take the mutation slot and reject a user's backup or
    // restore. Share concurrent reads; actions revalidate the current intent
    // and settings rather than treating a possibly stale listing as authority.
    if (!this.recoveryReading) this.recoveryReading = Promise.resolve()
      .then(() => this.options.call({ operation: 'capture_restore_list' }, signal))
      .then(readCaptureRecoveries)
      .finally(() => { this.recoveryReading = undefined })
    return this.recoveryReading
  }

  private recovered(value: Record<string, unknown>, id: string, archive: string, grant: string): CaptureRestored {
    const result = readCaptureRestored(value.recovery), document = value.document
    if (result.id !== id || result.archive_sha256 !== archive || result.grant_id !== grant ||
      !object(document) || document.format !== 1 || typeof document.revision !== 'string' ||
      !Array.isArray(document.sources) || document.sources.length > 16) throw new Error('The recovered source could not be confirmed. Read source status and pending recoveries before retrying.')
    const source = document.sources.find(item => object(item) && item.id === id)
    if (!object(source) || !object(source.custody) || source.custody.grant_id !== grant || source.enabled !== result.source_enabled) throw new Error('Recovery changed the expected source identity. Inspect its saved status.')
    this.document = document as Document
    this.activities.set(id, { phase: 'waiting', durability: 'unknown' })
    return result
  }

  async restore(input: CaptureRestoreInput, signal?: AbortSignal): Promise<CaptureRestoreResult> {
    if (!object(input) || Object.keys(input).some(key => !['expected_revision', 'file', 'recovery_key', 'archive_sha256', 'source', 'credential', 'retirement_credential', 'preview_hash', 'confirm'].includes(key)) ||
      input.confirm !== true || !object(input.source) || input.source.provider !== 'conversations' || input.source.enabled !== false || !input.source.custody ||
      typeof input.credential !== 'string' || typeof input.retirement_credential !== 'string') throw new Error('Review the archive, paused source, new device grant and previous-device retirement.')
    const recovery = await this.mutate(input.expected_revision, async () => {
      if (this.active) throw new Error('Wait for the active scan before recovering a capture source.')
      if (!await this.options.cipher.available()) throw new Error('Unlock OS credential storage before recovering this device.')
      const id = input.source.id ?? randomUUID(), source = { ...input.source, id }
      if (!UUID.test(id) || this.document!.sources.some(item => item.id === id || item.endpoint === source.endpoint && item.connector_id === source.connector_id)) throw new Error('This source already exists on this computer. Inspect its saved state before recovery.')
      const retirement_credential = this.options.retirementCredential
        ? await this.options.retirementCredential(source, input.retirement_credential) : input.retirement_credential
      const inboxKey = randomBytes(32).toString('base64')
      const sealed_key = (await this.options.cipher.encrypt(input.credential)).toString('base64')
      const sealed_inbox_key = (await this.options.cipher.encrypt(inboxKey)).toString('base64')
      signal?.throwIfAborted()
      try {
        const result = await this.options.call({ ...input, operation: 'capture_restore', retirement_credential,
          source: { ...source, sealed_key, sealed_inbox_key }, inbox_key: inboxKey }, signal)
        return this.recovered(result, id, input.archive_sha256, source.custody!.grant_id)
      } catch (error) { this.document = undefined; throw error }
    }, false)
    return { view: await this.status(), recovery }
  }

  async finishRecovery(input: CaptureRestoreControl, discard = false, signal?: AbortSignal): Promise<CaptureRestoreResult | { discarded: true; replacement_grant_revoked: true; archive_modified: false }> {
    if (!object(input) || !UUID.test(input.id) || input.confirm !== true || Object.keys(input).some(key =>
      !(discard ? ['id', 'expected_revision', 'confirm'] : ['id', 'expected_revision', 'confirm', 'file', 'recovery_key']).includes(key))) throw new Error('Confirm the selected unfinished capture recovery.')
    const result = await this.mutate(input.expected_revision, async () => {
      if (this.active) throw new Error('Wait for the active scan before finishing recovery.')
      if (!await this.options.cipher.available()) throw new Error('Unlock this device’s protected keys before finishing recovery.')
      const pending = await this.options.call({ operation: 'capture_restore_load', id: input.id, expected_revision: input.expected_revision }, signal)
      const source = pending.source
      if (!object(source) || source.id !== input.id || typeof source.sealed_key !== 'string' || typeof source.sealed_inbox_key !== 'string' ||
        !object(source.custody) || typeof source.custody.grant_id !== 'string' || !UUID.test(source.custody.grant_id) ||
        typeof pending.archive_sha256 !== 'string' || !/^[a-f0-9]{64}$/.test(pending.archive_sha256)) throw new Error('The protected recovery record could not be verified.')
      const credential = await this.options.cipher.decrypt(sealedBytes(source.sealed_key))
      const inbox_key = discard ? undefined : await this.options.cipher.decrypt(sealedBytes(source.sealed_inbox_key))
      signal?.throwIfAborted()
      try {
        const value = await this.options.call({ ...input, operation: discard ? 'capture_restore_discard' : 'capture_restore_finish', credential, ...(inbox_key ? { inbox_key } : {}) }, signal)
        if (discard) {
          if (Object.keys(value).length !== 3 || value.discarded !== true || value.replacement_grant_revoked !== true || value.archive_modified !== false) throw new Error('Discard could not be confirmed. Inspect the pending recovery before retrying.')
          return value as { discarded: true; replacement_grant_revoked: true; archive_modified: false }
        }
        return this.recovered(value, input.id, pending.archive_sha256, source.custody.grant_id)
      } catch (error) { this.document = undefined; throw error }
    }, false)
    return 'discarded' in result ? result : { view: await this.status(), recovery: result }
  }

  async configure(input: SourceConfigure, signal?: AbortSignal): Promise<DesktopSourceView> {
    if (!input || !input.source || Object.keys(input).some(k => !['expected_revision', 'source', 'credential', 'provider_credential', 'preview_hash'].includes(k))) throw new Error('Review the source settings and its dedicated application key.')
    if (input.source.capture_policy && (typeof input.preview_hash !== 'string' || !/^[a-f0-9]{64}$/.test(input.preview_hash))) throw new Error('Preview the current capture settings before saving.')
    await this.mutate(input.expected_revision, async () => {
      signal?.throwIfAborted()
      if (!await this.options.cipher.available()) throw new Error('Unlock OS credential storage before remembering a background source.')
      const id = input.source.id ?? randomUUID()
      if (!UUID.test(id)) throw new Error('Choose a source from current desktop status.')
      const before = this.document!.sources.find(item => item.id === id)
      if (!before && this.document!.sources.length >= 16) throw new Error('This app can host up to 16 sources. Pause or remove an unused source first.')
      if (this.active?.id === id) throw new Error('Pause this source before changing its settings.')
      const source = { ...input.source, id }
      if (before && !!before.custody !== !!source.custody) throw new Error('Changing an existing source’s retention policy needs a reviewed migration. Its current policy is retained.')
      if (before?.custody && (['source_id', 'grant_id', 'keep_accepted'] as const).some(key => before.custody![key] !== source.custody?.[key])) throw new Error('Retain the existing source and device capture authorization.')
      if (before?.custody && ((before.capture_mode ?? 'complete') !== (source.capture_mode ?? 'complete') || input.credential !== undefined)) throw new Error('Drain and migrate this inbox before changing its capture selection or dedicated key.')
      if (before && ['endpoint', 'tenant_id', 'connector_id', 'principal_id', 'provider', 'path'].some(key => source[key as keyof DesktopSource] !== before[key as keyof DesktopSource])) throw new Error('Use a new connection for a different source folder or workspace.')
      if (before?.slack?.team_id !== undefined && before.slack.team_id !== source.slack?.team_id) throw new Error('Use a new connection for a different Slack workspace.')
      if (this.document!.sources.some(item => item.id !== id && item.endpoint === source.endpoint && item.connector_id === source.connector_id)) throw new Error('This connection already runs on this computer.')
      const credential = input.credential ?? (before ? await this.options.cipher.decrypt(sealedBytes(before.sealed_key)) : '')
      const cloud = ['slack', 'gdrive'].includes(source.provider)
      if (!cloud && input.provider_credential !== undefined) throw new Error('Only a cloud source accepts provider credentials.')
      const provider = input.provider_credential ?? (before?.sealed_provider ? await this.options.cipher.decrypt(sealedBytes(before.sealed_provider)) : undefined)
      if (cloud && (typeof provider !== 'string' || !provider || Buffer.byteLength(provider, 'utf8') > 8192)) throw new Error('Supply the selected cloud provider’s credential, up to 8 KiB.')
      const verified = await this.options.call({ operation: 'verify', source, credential,
        ...(input.preview_hash ? { preview_hash: input.preview_hash } : {}),
        ...(cloud ? { provider_credential: provider } : {}) }, signal) as DesktopSource
      signal?.throwIfAborted()
      if (before && (before.scope_id !== undefined || before.provider === 'conversations') && (before.scope_id ?? 'selected-source') !== (verified.scope_id ?? 'selected-source')) throw new Error('The existing folder identity changed. Retain its original connection settings before scanning.')
      const sealed_key = (await this.options.cipher.encrypt(credential)).toString('base64')
      const sealed_provider = cloud ? (await this.options.cipher.encrypt(provider!)).toString('base64') : undefined
      const sealed_inbox_key = source.custody ? before?.sealed_inbox_key ??
        (await this.options.cipher.encrypt(randomBytes(32).toString('base64'))).toString('base64') : undefined
      signal?.throwIfAborted()
      await this.save([...this.document!.sources.filter(item => item.id !== id), { ...verified, sealed_key,
        ...(sealed_provider ? { sealed_provider } : {}), ...(sealed_inbox_key ? { sealed_inbox_key } : {}) }])
      this.activities.set(id, { phase: 'waiting', durability: 'unknown' })
      this.next.set(id, this.now())
    })
    if (this.startRequested && !this.timer) await this.start()
    return this.status()
  }

  async control(action: 'pause' | 'sync' | 'remove' | 'repair', input: SourceControl): Promise<DesktopSourceView> {
    const fields = action === 'repair' ? ['expected_revision', 'id', 'confirm', 'repair_token'] : ['expected_revision', 'id', 'enabled', 'confirm', ...(action === 'remove' ? ['discard_local_inbox', 'retirement_credential'] : [])]
    if (!input || !UUID.test(input.id) || Object.keys(input).some(k => !fields.includes(k))) throw new Error('Choose a source from current desktop status.')
    await this.mutate(input.expected_revision, async () => {
      const source = this.document!.sources.find(item => item.id === input.id)
      if (!source) throw new Error('This source is no longer configured on this computer.')
      if (action === 'repair') {
        if (this.active) throw new Error('Wait for the active source scan to finish or pause it before repairing device scan history.')
        if (input.confirm !== true || typeof input.repair_token !== 'string' || !/^[a-f0-9]{64}$/.test(input.repair_token)) throw new Error('Read source status and confirm repair of scan history for every source on this computer.')
        // Do not turn history repair (including a lost reply) into an immediate
        // scan. The saved repair record also defers normal work until next poll.
        for (const item of this.document!.sources) {
          this.next.set(item.id, Math.max(this.next.get(item.id) ?? 0, this.now() + item.poll_seconds * 1000))
          this.pending.delete(item.id)
        }
        try {
          const result = await this.options.call({ operation: 'status_repair', owner: this.owner,
            expected_revision: input.expected_revision, id: input.id, repair_token: input.repair_token, confirm: true })
          if (result.format !== 1 || result.repaired !== true || result.history_restored !== false || result.original_preserved !== true) throw new Error('Repair could not be confirmed. Read source status before retrying.')
        } finally { await this.observations(this.document!) }
        return
      }
      if (action === 'sync') {
        if (!source.enabled) throw new Error('Resume this source before requesting a scan.')
        this.pending.add(source.id)
        return
      }
      if (action === 'pause' && typeof input.enabled !== 'boolean') throw new Error('Choose whether to run this source.')
      if (action === 'remove' && input.confirm !== true) throw new Error('Confirm removal of this computer’s source settings. Existing memories are retained.')
      if (input.retirement_credential !== undefined && (!source.custody || typeof input.retirement_credential !== 'string' || !/^[A-Za-z0-9_.~+/=-]{16,1024}$/.test(input.retirement_credential))) throw new Error('Use a current workspace administrator credential only for retained inbox removal.')
      if (action === 'remove' && source.custody) {
        if (source.enabled || this.active?.id === source.id) throw new Error('Pause this source before removing its retained inbox.')
        if (input.discard_local_inbox !== true) throw new Error('Confirm discarding every locally pending memory. Server memories are retained; this device’s capture grant will be revoked.')
        let credential: string | null = null
        if (input.retirement_credential !== undefined) {
          credential = this.options.retirementCredential ? await this.options.retirementCredential(publicSource(source), input.retirement_credential) : input.retirement_credential
        } else {
          // Confirmed retirement can resume local cleanup without a surviving
          // key. The native helper refuses first-time removal without current
          // server authority; an unavailable key never grants offline consent.
          try { if (await this.options.cipher.available()) credential = await this.options.cipher.decrypt(sealedBytes(source.sealed_key)) } catch { /* The helper returns a bounded recovery instruction. */ }
        }
        const retired = await this.options.call({ operation: 'capture_retire', id: source.id,
          expected_revision: this.document!.revision, credential, discard_local_inbox: true })
        if (retired.retired !== true || retired.remote_grant_revoked !== true || retired.local_inbox_discarded !== true) throw new Error('Removal is unconfirmed. Read source status before retrying.')
      }
      const next = action === 'remove' ? this.document!.sources.filter(item => item.id !== input.id) :
        this.document!.sources.map(item => item.id === input.id ? { ...item, enabled: input.enabled! } : item)
      // Persist a pause before stopping work. A failed settings save must not
      // misleadingly claim that a source will stay paused after restart.
      if (action === 'pause' && input.enabled === false) {
        // Only the selected flag is written. A stale in-memory credential must
        // never replace a lost/damaged disk key while the user is stopping work.
        await this.updateDocument({ operation: 'pause', expected_revision: this.document!.revision, id: input.id })
      } else await this.save(next)
      if (action === 'remove' || !input.enabled) {
        this.pending.delete(input.id)
        if (this.active?.id === input.id) { this.active.abort.abort(); await this.active.work }
      } else this.next.set(input.id, this.now())
      if (action === 'pause' && input.enabled === false) {
        const saved = this.document!.sources.find(item => item.id === source.id)
        if (saved && (source.sealed_key !== saved.sealed_key || source.sealed_provider !== saved.sealed_provider ||
          source.sealed_inbox_key !== saved.sealed_inbox_key || source.status_epoch !== saved.status_epoch)) {
          // Only matching persisted observations may return after exact-key
          // recovery. Do not reset another source's live activity or scan again.
          await this.observations(this.document!, source.id)
        }
      }
      if (action === 'remove') { this.activities.delete(input.id); this.next.delete(input.id) }
    }, action !== 'repair')
    return this.status()
  }

  async tick(): Promise<void> {
    if (!this.document || this.busy || this.suspended || this.closed || !this.timer) return
    // Serve older due work first so repeated requests for one connector cannot
    // starve other workspaces' sources on this device.
    const source = this.document.sources.filter(item => item.enabled && (this.pending.has(item.id) || (this.next.get(item.id) ?? 0) <= this.now()))
      .sort((a, b) => (this.next.get(a.id) ?? 0) - (this.next.get(b.id) ?? 0))[0]
    if (!source) return
    this.pending.delete(source.id)
    const abort = new AbortController()
    const run = randomUUID()
    const activity = { id: source.id, abort, work: Promise.resolve() }
    this.active = activity
    this.changed()
    activity.work = (async () => {
      let began = false
      let observation: SourceActivity | undefined
      try {
        const opened = await this.options.call({ operation: 'status_begin', owner: this.owner, run,
          id: source.id, expected_revision: this.document!.revision })
        if (opened.format !== 1 || opened.id !== source.id) throw new Error('Unconfirmed scan start')
        const started = readActivity(opened.activity)
        if (started.phase !== 'scanning') throw new Error('Unconfirmed scan start')
        this.remember(source.id, started)
        began = true
        this.changed()
        if (!await this.options.cipher.available()) throw Object.assign(new Error(messages.storage_locked), { code: 'storage_locked' })
        let credential: string, provider: string | undefined, inboxKey: string | undefined
        try {
          credential = await this.options.cipher.decrypt(sealedBytes(source.sealed_key))
          provider = source.sealed_provider ? await this.options.cipher.decrypt(sealedBytes(source.sealed_provider)) : undefined
          if (['slack', 'gdrive'].includes(source.provider) !== !!source.sealed_provider) throw new Error('The saved provider credential is unavailable.')
        } catch { throw Object.assign(new Error(messages.source_credentials_unavailable), { code: 'source_credentials_unavailable' }) }
        if (source.custody) {
          try {
            if (!source.sealed_inbox_key) throw new Error('Missing inbox key')
            inboxKey = await this.options.cipher.decrypt(sealedBytes(source.sealed_inbox_key))
          } catch { throw Object.assign(new Error(messages.capture_key_unavailable), { code: 'capture_key_unavailable' }) }
        }
        abort.signal.throwIfAborted()
        const report = readReport(await this.options.call({ operation: 'scan', source: publicSource(source), credential,
          ...(provider ? { provider_credential: provider } : {}), ...(inboxKey ? { inbox_key: inboxKey } : {}) }, abort.signal,
          bytes => { this.rss = bytes }))
        observation = { ...this.activities.get(source.id), phase: report.completed ? 'complete' : 'attention', report,
          ...(report.completed ? {} : { reason_code: 'partial', message: messages.partial }) }
        const completed = await this.options.call({ operation: 'status_finish', owner: this.owner, id: source.id, run, report })
        if (completed.ignored === true && !this.document?.sources.some(item => item.id === source.id)) return
        if (completed.format !== 1 || completed.id !== source.id) throw new Error('Unconfirmed scan outcome')
        const finished = readActivity(completed.activity)
        if (finished.phase === 'scanning') throw new Error('Unconfirmed scan outcome')
        this.remember(source.id, finished)
      } catch (error) {
        if (!began || observation) this.unconfirmed(source.id, error, observation)
        else {
          const code = abort.signal.aborted ? 'source_cancelled' : failureReason(error)
          observation = { ...this.activities.get(source.id), phase: 'attention', reason_code: code, message: messages[code],
            last_failure: { observed_at: new Date(this.now()).toISOString(), reason_code: code } }
          try {
            const failed = await this.options.call({ operation: 'status_finish', owner: this.owner, id: source.id, run, reason_code: code })
            if (failed.ignored === true && !this.document?.sources.some(item => item.id === source.id)) return
            if (failed.format !== 1 || failed.id !== source.id) throw new Error('Unconfirmed scan failure')
            const finished = readActivity(failed.activity)
            if (finished.phase === 'scanning') throw new Error('Unconfirmed scan failure')
            this.remember(source.id, finished)
          } catch (failure) { this.unconfirmed(source.id, failure, observation) }
        }
      } finally {
        if (this.activities.get(source.id)?.durability !== 'saved' || !this.next.has(source.id)) this.next.set(source.id, this.now() + source.poll_seconds * 1000)
        this.rss = 0
        if (this.active === activity) this.active = undefined
        this.changed()
      }
    })()
    await activity.work
  }

  pauseForUpdate(): boolean {
    if (this.busy) return false
    this.suspended = true
    return true
  }
  resumeAfterUpdate(): void { this.suspended = false; void this.tick() }
  async close(): Promise<void> {
    this.closed = true
    if (this.timer) clearInterval(this.timer)
    this.timer = undefined
    this.active?.abort.abort()
    // App quit retries only after all work counted by busy has drained. A
    // startup read otherwise keeps busy true while repeated quit promises
    // starve the event loop that needs to receive its helper's completion.
    if (this.loading) await this.loading.catch(() => {})
    if (this.active) await this.active.work
    if (this.controlWork) await this.controlWork.catch(() => {})
    if (this.recoveryReading) await this.recoveryReading.catch(() => {})
  }
}
