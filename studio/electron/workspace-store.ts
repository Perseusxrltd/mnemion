/** OS-encrypted workspace credentials. This module is never imported by the renderer. */
import { randomUUID } from 'node:crypto'
import { constants, type Stats } from 'node:fs'
import { chmod, lstat, mkdir, open, rename, rm } from 'node:fs/promises'
import { isAbsolute, join } from 'node:path'

export interface WorkspaceIdentity {
  principal_id: string
  tenant_id: string
  name: string
  tenant_name: string
  administrator: boolean
}

export interface WorkspaceBookmark {
  id: string
  endpoint: string
  label: string
  principalName: string
  principalId: string
  tenantId: string
  updatedAt: string
}

/** Historical information only; this never grants or restores a session. */
export interface WorkspaceInspection {
  bookmark: WorkspaceBookmark
  access: { identity: WorkspaceIdentity; verifiedAt: string } | null
  accessStatus: 'recorded' | 'not-recorded' | 'locked' | 'unavailable'
}

export interface CredentialCipher {
  available(): boolean
  encrypt(value: string): Buffer | Promise<Buffer>
  decrypt(value: Buffer): string | Promise<string>
}

type StoredWorkspace = WorkspaceBookmark & { sealed: string }
type StoredState = { activeId: string | null; connections: StoredWorkspace[] }
const LIMIT = 256 * 1024
const UUID = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i
const TOKEN = /^[A-Za-z0-9_.~+/=-]{16,1024}$/

export function workspaceEndpoint(value: unknown): string {
  if (typeof value !== 'string' || value.length > 4096) throw new Error('Enter the workspace address.')
  let url: URL
  try { url = new URL(value) } catch { throw new Error('Enter a valid workspace address.') }
  const loopback = ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname)
  if ((url.protocol !== 'https:' && !(url.protocol === 'http:' && loopback)) ||
      url.username || url.password || url.search || url.hash) {
    throw new Error('Use HTTPS for a remote workspace, without credentials or query parameters in the address.')
  }
  return url.href.replace(/\/+$/, '')
}

function privateFile(info: Stats, directory = false): void {
  if (info.isSymbolicLink() || (directory ? !info.isDirectory() : !info.isFile() || info.nlink !== 1) ||
      (process.platform !== 'win32' && ((info.mode & 0o077) !== 0 || info.uid !== process.getuid?.()))) {
    throw new Error('The saved-workspace location is not private. Reset saved connections or restore their private storage.')
  }
}

function label(value: unknown): value is string {
  return typeof value === 'string' && value.length > 0 && value.length <= 256 && !/[\u0000-\u001f]/.test(value)
}

export function workspaceIdentity(value: unknown): WorkspaceIdentity {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('Invalid workspace identity.')
  const me = value as WorkspaceIdentity
  if (typeof me.principal_id !== 'string' || !UUID.test(me.principal_id) ||
      typeof me.tenant_id !== 'string' || !UUID.test(me.tenant_id) ||
      !label(me.name) || !label(me.tenant_name) || typeof me.administrator !== 'boolean') {
    throw new Error('Invalid workspace identity.')
  }
  return { principal_id: me.principal_id, tenant_id: me.tenant_id, name: me.name, tenant_name: me.tenant_name, administrator: me.administrator }
}

function decode(value: unknown): StoredState {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('Invalid saved workspaces.')
  const document = value as { format?: unknown; activeId?: unknown; connections?: unknown }
  if (document.format !== 1 || !Array.isArray(document.connections) || document.connections.length > 32 ||
      !(document.activeId === null || typeof document.activeId === 'string' && UUID.test(document.activeId)) ||
      Object.keys(document).some(key => !['format', 'activeId', 'connections'].includes(key))) throw new Error('Invalid saved workspaces.')
  const identifiers = new Set<string>()
  const connections = document.connections.map((value: unknown) => {
    if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('Invalid saved workspace.')
    const item = value as StoredWorkspace
    if (Object.keys(item).sort().join(',') !== 'endpoint,id,label,principalId,principalName,sealed,tenantId,updatedAt' ||
        typeof item.id !== 'string' || !UUID.test(item.id) || identifiers.has(item.id) ||
        workspaceEndpoint(item.endpoint) !== item.endpoint || !label(item.label) || !label(item.principalName) ||
        typeof item.principalId !== 'string' || !UUID.test(item.principalId) ||
        typeof item.tenantId !== 'string' || !UUID.test(item.tenantId) ||
        typeof item.updatedAt !== 'string' || !Number.isFinite(Date.parse(item.updatedAt)) ||
        typeof item.sealed !== 'string' || !/^[A-Za-z0-9+/]+={0,2}$/.test(item.sealed) ||
        item.sealed.length > 16384 || Buffer.from(item.sealed, 'base64').toString('base64') !== item.sealed) {
      throw new Error('Invalid saved workspace. Reconnect before replacing its saved connection.')
    }
    identifiers.add(item.id)
    return item
  })
  if (document.activeId !== null && !identifiers.has(document.activeId as string)) throw new Error('Invalid saved workspace selection.')
  return { activeId: document.activeId as string | null, connections }
}

export class WorkspaceStore {
  private queue: Promise<void> = Promise.resolve()
  private readonly path: string

  constructor(private readonly directory: string, private readonly cipher: CredentialCipher) {
    if (!isAbsolute(directory)) throw new Error('Use a private application directory.')
    this.path = join(directory, 'connections.json')
  }

  private async read(): Promise<StoredState> {
    try { privateFile(await lstat(this.directory), true) }
    catch (error) { if ((error as NodeJS.ErrnoException).code === 'ENOENT') return { activeId: null, connections: [] }; throw error }
    let file
    try {
      privateFile(await lstat(this.path))
      file = await open(this.path, constants.O_RDONLY | (constants.O_NOFOLLOW || 0) | constants.O_NONBLOCK)
    }
    catch (error) { if ((error as NodeJS.ErrnoException).code === 'ENOENT') return { activeId: null, connections: [] }; throw error }
    try {
      const info = await file.stat()
      privateFile(info)
      if (info.size > LIMIT) throw new Error('Saved workspace data exceeds its size limit.')
      const bytes = Buffer.alloc(LIMIT + 1)
      let length = 0
      while (length <= LIMIT) {
        const result = await file.read(bytes, length, bytes.length - length, null)
        if (!result.bytesRead) break
        length += result.bytesRead
      }
      if (length > LIMIT) throw new Error('Saved workspace data exceeds its size limit.')
      return decode(JSON.parse(bytes.subarray(0, length).toString('utf8')))
    } finally { await file.close() }
  }

  private async write(state: StoredState): Promise<void> {
    const document = JSON.stringify({ format: 1, ...state }) + '\n'
    if (Buffer.byteLength(document) > LIMIT) throw new Error('Too many saved workspaces.')
    await mkdir(this.directory, { mode: 0o700, recursive: true })
    privateFile(await lstat(this.directory), true)
    const temporary = join(this.directory, `.connections-${randomUUID()}.tmp`)
    const file = await open(temporary, 'wx', 0o600)
    try {
      await file.writeFile(document)
      await file.sync()
      await file.close()
      await rename(temporary, this.path)
      if (process.platform !== 'win32') {
        const directory = await open(this.directory, 'r')
        try { await directory.sync() } finally { await directory.close() }
      }
    } finally {
      await file.close().catch(() => {})
      await rm(temporary, { force: true })
    }
  }

  private serial<T>(operation: () => Promise<T>): Promise<T> {
    const pending = this.queue.then(operation)
    this.queue = pending.then(() => {}, () => {})
    return pending
  }

  available(): boolean { return this.cipher.available() }

  async status(): Promise<{ activeId: string | null; bookmarks: WorkspaceBookmark[] }> {
    const state = await this.read()
    return { activeId: state.activeId, bookmarks: state.connections.map(({ sealed: _sealed, ...bookmark }) => bookmark) }
  }

  async list(): Promise<WorkspaceBookmark[]> {
    return (await this.status()).bookmarks
  }

  save(endpoint: string, credential: string, identity: WorkspaceIdentity): Promise<WorkspaceBookmark> {
    return this.serial(async () => {
      if (!this.available()) throw new Error('Unlock the operating system password store, or connect without remembering this workspace.')
      endpoint = workspaceEndpoint(endpoint)
      identity = workspaceIdentity(identity)
      if (typeof credential !== 'string' || !TOKEN.test(credential) || JSON.stringify(identity).includes(credential)) throw new Error('Invalid workspace credential or identity.')
      const { connections: entries } = await this.read()
      const previous = entries.find(item => item.endpoint === endpoint && item.principalId === identity.principal_id && item.tenantId === identity.tenant_id)
      if (!previous && entries.length >= 32) throw new Error('Remove a saved connection before adding another workspace.')
      const bookmark: WorkspaceBookmark = {
        id: previous?.id ?? randomUUID(), endpoint, label: identity.tenant_name,
        principalName: identity.name, principalId: identity.principal_id,
        tenantId: identity.tenant_id, updatedAt: new Date().toISOString(),
      }
      // Bind the encrypted credential to its destination and identity. Changing
      // plaintext metadata cannot redirect the saved secret to another host.
      const sealed = (await this.cipher.encrypt(JSON.stringify({
        format: 1, endpoint, principalId: bookmark.principalId, tenantId: bookmark.tenantId, credential,
        // Older clients ignore additional encrypted fields. Keep the outer
        // bookmark format unchanged so rollback can still open the connection.
        identity, verifiedAt: bookmark.updatedAt,
      }))).toString('base64')
      await this.write({ activeId: bookmark.id, connections: [...entries.filter(item => item.id !== bookmark.id), { ...bookmark, sealed }] })
      return bookmark
    })
  }

  private async unseal(item: StoredWorkspace) {
    if (!this.available()) throw new Error('Unlock the operating system password store to reconnect.')
    const payload = await this.cipher.decrypt(Buffer.from(item.sealed, 'base64'))
    if (Buffer.byteLength(payload) > 16384) throw new Error('Invalid saved credential.')
    const decoded = JSON.parse(payload)
    if (!decoded || typeof decoded !== 'object' || decoded.format !== 1 ||
        decoded.endpoint !== item.endpoint || decoded.principalId !== item.principalId || decoded.tenantId !== item.tenantId ||
        typeof decoded.credential !== 'string' || !TOKEN.test(decoded.credential)) throw new Error('The saved credential does not match this workspace. Reconnect with your key.')
    return decoded
  }

  /** Only the main-process connection manager may receive the decrypted secret. */
  async credential(id: string): Promise<{ bookmark: WorkspaceBookmark; credential: string }> {
    const item = (await this.read()).connections.find(item => item.id === id)
    if (!item) throw new Error('That saved workspace is no longer available.')
    const decoded = await this.unseal(item)
    const { sealed: _sealed, ...bookmark } = item
    return { bookmark, credential: decoded.credential }
  }

  /** Read recovery context locally, without contacting or selecting a server. */
  async inspect(id: string): Promise<WorkspaceInspection> {
    const item = (await this.read()).connections.find(item => item.id === id)
    if (!item) throw new Error('That saved workspace is no longer available.')
    const { sealed: _sealed, ...bookmark } = item
    if (!this.available()) return { bookmark, access: null, accessStatus: 'locked' }
    try {
      const decoded = await this.unseal(item)
      if (decoded.identity === undefined && decoded.verifiedAt === undefined) {
        return { bookmark, access: null, accessStatus: 'not-recorded' }
      }
      const identity = workspaceIdentity(decoded.identity)
      if (identity.principal_id !== item.principalId || identity.tenant_id !== item.tenantId ||
          identity.name !== item.principalName || identity.tenant_name !== item.label ||
          decoded.verifiedAt !== item.updatedAt || JSON.stringify(identity).includes(decoded.credential)) {
        throw new Error('The stored access observation does not match this workspace.')
      }
      // Do not spread the decrypted payload into a renderer-facing result.
      return { bookmark, access: { identity, verifiedAt: decoded.verifiedAt }, accessStatus: 'recorded' }
    } catch {
      return { bookmark, access: null, accessStatus: 'unavailable' }
    }
  }

  remove(id: string): Promise<void> {
    return this.serial(async () => {
      const state = await this.read()
      if (!state.connections.some(item => item.id === id)) return
      await this.write({ activeId: state.activeId === id ? null : state.activeId, connections: state.connections.filter(item => item.id !== id) })
    })
  }

  select(id: string | null): Promise<void> {
    return this.serial(async () => {
      const state = await this.read()
      if (id !== null && !state.connections.some(item => item.id === id)) throw new Error('That saved workspace is no longer available.')
      if (state.activeId === id) return
      await this.write({ ...state, activeId: id })
    })
  }

  /** An explicit UI reset forgets device bookmarks; ordinary failures never do. */
  reset(): Promise<void> {
    return this.serial(async () => {
      await mkdir(this.directory, { mode: 0o700, recursive: true })
      const directory = await lstat(this.directory)
      if (directory.isSymbolicLink() || !directory.isDirectory() ||
          (process.platform !== 'win32' && directory.uid !== process.getuid?.())) throw new Error('The saved-workspace directory must belong to your operating-system account.')
      let file: Stats | undefined
      try { file = await lstat(this.path) } catch (error) { if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error }
      if (file && (file.isSymbolicLink() || !file.isFile() || file.nlink !== 1 ||
          (process.platform !== 'win32' && file.uid !== process.getuid?.()))) throw new Error('The saved-workspace file is linked elsewhere or belongs to another account. It was not changed.')
      if (process.platform !== 'win32') await chmod(this.directory, 0o700)
      await this.write({ activeId: null, connections: [] })
    })
  }
}
