/** Independent host keys remain in the OS store; renderer receives public records only. */
import { randomUUID } from 'node:crypto'
import { constants, type Stats } from 'node:fs'
import { lstat, mkdir, open, readdir, rm } from 'node:fs/promises'
import { isAbsolute, join } from 'node:path'
import { replaceFile } from './atomic-file.js'
import type { CredentialCipher } from './workspace-store.js'
import type { SourceCall } from './desktop-sources.js'
import type { HostConnection, HostInspection, HostProfile, HostProfilesStatus, HostReceipt, HostRequest } from '../shared/host-control.js'
import { hostMessages } from './host-control-messages.js'

const UUID = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i
const FINGERPRINT = /^SHA256:[A-Za-z0-9+/]{43}$/
const LIMIT = 1024 * 1024
const ARCHIVE = /^[a-f0-9-]{36}_[a-f0-9-]{36}\.json$/
const reads = new Set(['host.status', 'operations.get', 'operations.list', 'operators.list'])
const finished = new Set(['succeeded', 'failed', 'cancelled', 'refused'])
type Saved = HostProfile & { sealed: string }
type Secret = { id: string; public_key: string; fingerprint: string; private_key: string; connection: HostConnection | null }

function privateLocation(info: Stats, directory = false) {
  if (info.isSymbolicLink() || (directory ? !info.isDirectory() : !info.isFile() || info.nlink !== 1) ||
      (process.platform !== 'win32' && (info.uid !== process.getuid?.() || (info.mode & 0o077) !== 0))) {
    throw new Error('Host logins must stay in private app storage. Existing files were retained.')
  }
}
function profile(value: unknown): Saved {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('Saved host logins need inspection.')
  const item = value as Saved
  if (Object.keys(item).sort().join(',') !== 'connection,created_at,fingerprint,id,last_operation,name,public_key,sealed' ||
      typeof item.id !== 'string' || !UUID.test(item.id) || typeof item.name !== 'string' ||
      !item.name.trim() || item.name.length > 80 || /[\x00-\x1f\x7f]/.test(item.name) ||
      typeof item.public_key !== 'string' || !/^ssh-ed25519 [A-Za-z0-9+/]{68}$/.test(item.public_key) ||
      typeof item.fingerprint !== 'string' || !FINGERPRINT.test(item.fingerprint) ||
      typeof item.created_at !== 'string' || !Number.isFinite(Date.parse(item.created_at)) ||
      typeof item.sealed !== 'string' || item.sealed.length > 16384 || !/^[A-Za-z0-9+/]+={0,2}$/.test(item.sealed) ||
      Buffer.from(item.sealed, 'base64').toString('base64') !== item.sealed) throw new Error('Saved host logins need inspection.')
  if (item.connection !== null && (!item.connection || typeof item.connection !== 'object' ||
      !UUID.test(item.connection.host_id) || !UUID.test(item.connection.operator_id) ||
      typeof item.connection.hostname !== 'string' || item.connection.hostname.length > 253 ||
      !FINGERPRINT.test(item.connection.host_key_fingerprint) || item.connection.operator_key_fingerprint !== item.fingerprint)) {
    throw new Error('The saved host connection needs inspection.')
  }
  if (item.last_operation !== null && (!item.last_operation || typeof item.last_operation !== 'object' ||
      !UUID.test(item.last_operation.request?.request_id ?? '') ||
      item.last_operation.request.host_id !== item.connection?.host_id ||
      typeof item.last_operation.request.action !== 'string' ||
      !['submitted', 'queued', 'running', 'inspection_required', ...finished].includes(item.last_operation.phase) ||
      Buffer.byteLength(JSON.stringify(item.last_operation.request)) > 16384)) throw new Error('The saved host operation needs inspection.')
  return item
}
function visible({ sealed: _sealed, ...value }: Saved): HostProfile { return value }
function publicReply(reply: HostReceipt): HostReceipt {
  if (!reply.ok && reply.error) reply.error = { code: reply.error.code, message: hostMessages[reply.error.code] ?? 'The host refused this operation. Read its current status and operation history.' }
  return reply
}

export class HostProfiles {
  private queue: Promise<void> = Promise.resolve()
  private pending = 0
  private closed = false
  private suspended = false
  private controllers = new Set<AbortController>()
  constructor(private directory: string, private cipher: CredentialCipher, private call: SourceCall) {
    if (!isAbsolute(directory)) throw new Error('Use a private app directory for host logins.')
  }
  private async read(): Promise<Saved[]> {
    try { privateLocation(await lstat(this.directory), true) }
    catch (error) { if ((error as NodeJS.ErrnoException).code === 'ENOENT') return []; throw error }
    const path = join(this.directory, 'hosts.json')
    let file
    try {
      privateLocation(await lstat(path))
      file = await open(path, constants.O_RDONLY | (constants.O_NOFOLLOW || 0) | constants.O_NONBLOCK)
    } catch (error) { if ((error as NodeJS.ErrnoException).code === 'ENOENT') return []; throw error }
    try {
      const info = await file.stat(); privateLocation(info)
      if (info.size > LIMIT) throw new Error('Host logins exceed their storage allowance.')
      const bytes = Buffer.alloc(LIMIT + 1)
      let length = 0
      while (length <= LIMIT) {
        const result = await file.read(bytes, length, bytes.length - length, null)
        if (!result.bytesRead) break
        length += result.bytesRead
      }
      if (length > LIMIT) throw new Error('Host logins exceed their storage allowance.')
      const value = JSON.parse(bytes.subarray(0, length).toString('utf8'))
      if (!value || Object.keys(value).sort().join(',') !== 'format,profiles' || value.format !== 1 ||
          !Array.isArray(value.profiles) || value.profiles.length > 32) throw new Error('Saved host logins need inspection.')
      const items = value.profiles.map(profile) as Saved[]
      if (new Set(items.map(item => item.id)).size !== items.length) throw new Error('Duplicate saved host login.')
      return items
    } finally { await file.close() }
  }
  private async write(items: Saved[]) {
    const body = JSON.stringify({ format: 1, profiles: items.map(profile) }) + '\n'
    if (Buffer.byteLength(body) > LIMIT) throw new Error('Host logins exceed their storage allowance.')
    await mkdir(this.directory, { recursive: true, mode: 0o700 })
    privateLocation(await lstat(this.directory), true)
    const temporary = join(this.directory, '.hosts-' + randomUUID() + '.tmp')
    const file = await open(temporary, 'wx', 0o600)
    try { await file.writeFile(body); await file.sync() } finally { await file.close() }
    try {
      await replaceFile(temporary, join(this.directory, 'hosts.json'))
      if (process.platform !== 'win32') {
        const parent = await open(this.directory, constants.O_RDONLY)
        try { await parent.sync() } finally { await parent.close() }
      }
    } finally { await rm(temporary, { force: true }) }
  }
  private serial<T>(operation: () => Promise<T>): Promise<T> {
    if (this.closed || this.suspended || this.pending >= 8) return Promise.reject(new Error('Wait for the current host operation or app update to finish.'))
    this.pending++
    const work = this.queue.then(() => { if (this.closed || this.suspended) throw new Error('Host controls are closing. Inspect saved work after reopening.'); return operation() })
    this.queue = work.then(() => {}, () => {}).finally(() => { this.pending-- })
    return work
  }
  private async invoke(input: Record<string, unknown>, signal?: AbortSignal) {
    const controller = new AbortController(), abort = () => controller.abort()
    signal?.addEventListener('abort', abort, { once: true })
    if (signal?.aborted || this.closed) abort()
    this.controllers.add(controller)
    try { return await this.call(input, controller.signal) }
    finally { this.controllers.delete(controller); signal?.removeEventListener('abort', abort) }
  }
  private async unlock(item: Saved): Promise<Secret> {
    if (!await this.cipher.available()) throw new Error('Unlock this operating system’s secure store to use the host login.')
    const value = JSON.parse(await this.cipher.decrypt(Buffer.from(item.sealed, 'base64'))) as Secret
    if (!value || value.id !== item.id || value.public_key !== item.public_key || value.fingerprint !== item.fingerprint ||
        JSON.stringify(value.connection) !== JSON.stringify(item.connection) || typeof value.private_key !== 'string' || value.private_key.length > 8192) {
      throw new Error('The protected host identity no longer matches this saved connection. Existing data was retained.')
    }
    return value
  }
  private async seal(value: Secret) { return (await this.cipher.encrypt(JSON.stringify(value))).toString('base64') }
  private async archive(item: Saved) {
    if (!item.last_operation) return
    privateLocation(await lstat(this.directory), true)
    const directory = join(this.directory, 'recovery-requests')
    await mkdir(directory, { recursive: true, mode: 0o700 }); privateLocation(await lstat(directory), true)
    const id = item.id + '_' + item.last_operation.request.request_id + '.json'
    const names = await readdir(directory)
    if (names.includes(id)) {
      const existing = await this.recovery(id)
      if (JSON.stringify((existing.profile as HostProfile).last_operation?.request) !== JSON.stringify(item.last_operation.request)) throw new Error('The saved recovery request changed. Its original was retained.')
      return
    }
    if (names.length >= 128) throw new Error('Export and review the retained recovery requests before adding more; existing records were preserved.')
    const temporary = join(directory, '.request-' + randomUUID() + '.tmp')
    const file = await open(temporary, 'wx', 0o600)
    try { await file.writeFile(JSON.stringify({ format: 1, recorded_at: new Date().toISOString(), profile: visible(item), original_outcome: 'unconfirmed' }) + '\n'); await file.sync() }
    finally { await file.close() }
    try {
      await replaceFile(temporary, join(directory, id))
      if (process.platform !== 'win32') { const parent = await open(directory, constants.O_RDONLY); try { await parent.sync() } finally { await parent.close() } }
    } finally { await rm(temporary, { force: true }) }
  }
  async recovery(id: string): Promise<Record<string, unknown>> {
    if (typeof id !== 'string' || !ARCHIVE.test(id)) throw new Error('Choose a recorded recovery request.')
    privateLocation(await lstat(this.directory), true)
    const directory = join(this.directory, 'recovery-requests'), path = join(directory, id)
    privateLocation(await lstat(directory), true); privateLocation(await lstat(path))
    const file = await open(path, constants.O_RDONLY | (constants.O_NOFOLLOW || 0) | constants.O_NONBLOCK)
    try {
      const info = await file.stat(); privateLocation(info)
      if (info.size > 24576) throw new Error('The recorded recovery request exceeds its bound.')
      const bytes = Buffer.alloc(24577); let length = 0
      while (length < bytes.length) { const read = await file.read(bytes, length, bytes.length - length, null); if (!read.bytesRead) break; length += read.bytesRead }
      if (length > 24576) throw new Error('The recorded recovery request exceeds its bound.')
      const value = JSON.parse(bytes.subarray(0, length).toString('utf8'))
      if (value.format !== 1 || value.original_outcome !== 'unconfirmed' || !value.profile || Object.hasOwn(value.profile, 'sealed')) throw new Error('The recorded recovery request needs inspection.')
      const record = profile({ ...value.profile, sealed: 'QQ==' })
      if (id !== record.id + '_' + record.last_operation?.request.request_id + '.json') throw new Error('The recovery request identity changed.')
      return { format: 1, recorded_at: value.recorded_at, profile: visible(record), original_outcome: 'unconfirmed' }
    } finally { await file.close() }
  }
  async recoveries(): Promise<{ records: Record<string, unknown>[] }> {
    const directory = join(this.directory, 'recovery-requests')
    let names: string[]
    try { privateLocation(await lstat(this.directory), true); privateLocation(await lstat(directory), true); names = await readdir(directory) }
    catch (error) { if ((error as NodeJS.ErrnoException).code === 'ENOENT') return { records: [] }; throw error }
    if (names.length > 128) throw new Error('Retained host requests need a storage review.')
    const records = []
    for (const id of names.sort().filter(name => ARCHIVE.test(name))) {
      const value = await this.recovery(id), profile = value.profile as HostProfile
      records.push({ id, name: profile.name, recorded_at: value.recorded_at, hostname: profile.connection?.hostname,
        host_id: profile.connection?.host_id, operation_id: profile.last_operation?.request.request_id,
        action: profile.last_operation?.request.action, phase: profile.last_operation?.phase })
    }
    return { records }
  }
  async status(): Promise<HostProfilesStatus> {
    return { secure_storage: await this.cipher.available() === true, profiles: (await this.read()).map(visible) }
  }
  schema(signal?: AbortSignal) { return this.serial(() => this.invoke({ operation: 'schema' }, signal)) }
  inspect(id: string, signal?: AbortSignal): Promise<HostInspection> {
    return this.serial(async () => {
      const items = await this.read(), item = items.find(item => item.id === id)
      if (!item?.connection) throw new Error('Enroll this host login before connecting.')
      const secret = await this.unlock(item)
      const request = { protocol: 1, host_id: item.connection.host_id, request_id: randomUUID(),
        ...(item.last_operation ? { action: 'operations.get', operation_id: item.last_operation.request.request_id } : { action: 'host.status' }) }
      const result = await this.invoke({ operation: 'inspect', connection: item.connection, private_key: secret.private_key, request }, signal) as HostInspection
      publicReply(result.status)
      if (result.history) publicReply(result.history)
      if (result.operation) publicReply(result.operation)
      if (item.last_operation && result.operation?.ok) {
        item.last_operation.phase = String(result.operation.result?.phase)
        item.last_operation.at = new Date().toISOString()
        await this.write(items)
      }
      return result
    })
  }
  create(name: string, signal?: AbortSignal): Promise<HostProfile> {
    return this.serial(async () => {
      if (typeof name !== 'string' || !name.trim() || name.trim().length > 80 || /[\x00-\x1f\x7f]/.test(name)) throw new Error('Use a short name for this device or operator.')
      if (!await this.cipher.available()) throw new Error('Unlock this operating system’s secure store before creating a host login.')
      const items = await this.read()
      if (items.length >= 32) throw new Error('Remove an unused host login before creating another.')
      const value = await this.invoke({ operation: 'keygen' }, signal)
      if (typeof value.private_key !== 'string' || value.private_key.length > 8192 || typeof value.public_key !== 'string' || typeof value.fingerprint !== 'string') throw new Error('The native host helper did not create a valid identity.')
      const id = randomUUID()
      const secret = { id, public_key: value.public_key, fingerprint: value.fingerprint, private_key: value.private_key, connection: null }
      const item: Saved = { id, name: name.trim(), public_key: value.public_key, fingerprint: value.fingerprint,
        created_at: new Date().toISOString(), connection: null, last_operation: null, sealed: await this.seal(secret) }
      items.push(profile(item)); await this.write(items)
      return visible(item)
    })
  }
  enroll(id: string, connection: HostConnection, confirm: boolean, signal?: AbortSignal): Promise<HostProfile> {
    return this.serial(async () => {
      if (confirm !== true) throw new Error('Confirm the host identity and fingerprint before saving this enrollment.')
      const items = await this.read(), item = items.find(item => item.id === id)
      if (!item) throw new Error('Choose a saved host login.')
      if (item.connection && JSON.stringify(item.connection) !== JSON.stringify(connection)) throw new Error('This login is already enrolled. Create a separate login for a changed host identity.')
      const secret = await this.unlock(item)
      const result = await this.invoke({ operation: 'validate', private_key: secret.private_key, connection,
        request: { protocol: 1, host_id: connection?.host_id, request_id: randomUUID(), action: 'host.status' } }, signal)
      item.connection = result.connection as HostConnection
      item.sealed = await this.seal({ ...secret, connection: item.connection })
      await this.write(items)
      return visible(item)
    })
  }
  remove(id: string, confirm: boolean, acknowledgeOutstanding = false): Promise<void> {
    return this.serial(async () => {
      if (confirm !== true) throw new Error('Confirm removing this device’s host login. This does not revoke its host grant.')
      const items = await this.read(), item = items.find(item => item.id === id)
      if (!item) throw new Error('Choose a saved host login.')
      if (item.last_operation && !finished.has(item.last_operation.phase)) {
        if (acknowledgeOutstanding !== true) throw new Error('Inspect this login’s outstanding operation, or explicitly retain its public recovery request before removing the key.')
        await this.archive(item)
      }
      await this.write(items.filter(value => value.id !== id))
    })
  }
  archiveRequest(id: string, confirm: boolean): Promise<void> {
    return this.serial(async () => {
      if (confirm !== true) throw new Error('Confirm retaining the original recovery request. This does not cancel remote work.')
      const items = await this.read(), item = items.find(item => item.id === id)
      if (!item) throw new Error('Choose a saved host login.')
      if (item.last_operation && !finished.has(item.last_operation.phase)) await this.archive(item)
      item.last_operation = null
      await this.write(items)
    })
  }
  request(id: string, request: HostRequest, signal?: AbortSignal): Promise<HostReceipt> {
    return this.serial(async () => {
      const items = await this.read(), item = items.find(item => item.id === id)
      if (!item?.connection) throw new Error('Enroll this host login before connecting.')
      const secret = await this.unlock(item)
      const mutation = !reads.has(request.action)
      if (mutation) {
        const validated = await this.invoke({ operation: 'validate', connection: item.connection, private_key: secret.private_key, request }, signal)
        request = validated.request as HostRequest
        const last = item.last_operation
        if (last && !finished.has(last.phase) && last.request.request_id !== request.request_id &&
            !['upgrade.plan', 'upgrade.apply', 'backup.verify', 'operations.resolve'].includes(request.action)) throw new Error('Inspect or resolve the outstanding host operation before starting different work.')
        if (last?.request.request_id === request.request_id && JSON.stringify(last.request) !== JSON.stringify(request)) throw new Error('Use the exact saved request when retrying this operation.')
        signal?.throwIfAborted()
        if (last && !finished.has(last.phase) && last.request.request_id !== request.request_id) await this.archive(item)
        item.last_operation = { request, phase: last?.request.request_id === request.request_id ? last.phase : 'submitted', at: new Date().toISOString() }
        await this.write(items)
      }
      // No automatic replay: lost delivery keeps the durable original UUID.
      const reply = await this.invoke({ operation: 'call', connection: item.connection, private_key: secret.private_key, request }, signal) as HostReceipt
      publicReply(reply)
      if ((mutation && reply.ok) || (request.action === 'operations.get' && request.operation_id === item.last_operation?.request.request_id && reply.ok)) {
        if (item.last_operation) {
          item.last_operation.phase = String(reply.result?.phase ?? 'succeeded')
          item.last_operation.at = new Date().toISOString()
          await this.write(items)
        }
      }
      return reply
    })
  }
  get busy() { return this.pending > 0 }
  pauseForUpdate() { if (this.busy) return false; this.suspended = true; return true }
  resumeAfterUpdate() { this.suspended = false }
  async close() { this.closed = true; for (const controller of this.controllers) controller.abort(); await this.queue }
}
