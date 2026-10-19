/** Private OS-account selection controls. Never return native session handles or keys. */
import { createHash } from 'node:crypto'
import { WorkspaceConnections, type WorkspaceSession } from './workspace-connections.js'

const UUID = /^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/i
type Options = {
  connections: WorkspaceConnections
  localSelected: () => boolean
  deselectLocal: () => void
  openLocal: () => Promise<WorkspaceSession>
  beforeChange: () => Promise<void>
  changed: () => void
}

function identifier(value: unknown): string {
  if (typeof value !== 'string' || !UUID.test(value)) throw new Error('Use the identity returned by workspace.status or workspace.verify.')
  return value
}

export class DesktopWorkspaceActions {
  constructor(private readonly options: Options) {}

  async status() {
    const status = await this.options.connections.status()
    const local_selected = this.options.localSelected()
    // The private handle changes on every activation, including the same account.
    // Hash it into the observation but never expose it through the operator pipe.
    const revision = createHash('sha256').update(JSON.stringify({ status, local_selected })).digest('hex')
    const active = status.active ? {
      endpoint: status.active.endpoint, me: status.active.me,
      remembered: status.active.remembered, bookmarkId: status.active.bookmarkId,
      ...(status.active.authentication ? { authentication: status.active.authentication } : {}),
    } : null
    return { revision, local_selected, secureStorage: status.secureStorage,
      bookmarks: status.bookmarks, activeId: status.activeId, active }
  }

  private async mutate(input: Record<string, unknown>, signal: AbortSignal, operation: () => Promise<unknown>) {
    const before = await this.status()
    if (typeof input.expected_revision !== 'string' || input.expected_revision !== before.revision) throw new Error('The desktop connection changed. Read workspace.status and confirm its current revision before retrying.')
    signal.throwIfAborted()
    await this.options.beforeChange()
    try {
      signal.throwIfAborted()
      if ((await this.status()).revision !== before.revision) throw new Error('The desktop connection changed during review. Read workspace.status before retrying.')
      // Once accepted, the ordinary connection manager owns completion. A caller
      // disconnect cannot undo a completed login or safely replay a refresh token.
      await operation()
      return await this.status()
    } finally {
      const after = await this.status().catch(() => null)
      if (!after || after.revision !== before.revision) this.options.changed()
    }
  }

  async execute(action: string, input: Record<string, unknown>, signal: AbortSignal): Promise<unknown> {
    signal.throwIfAborted()
    const connections = this.options.connections
    if (action === 'workspace.status') return this.status()
    if (action === 'workspace.inspect') return connections.inspect(identifier(input.id))
    if (action === 'workspace.verify') {
      if (typeof input.endpoint !== 'string' || typeof input.credential !== 'string') throw new Error('Supply the workspace address and its private key.')
      return connections.identify(input.endpoint, input.credential)
    }
    if (action === 'workspace.connect' || action === 'workspace.sign-in') {
      if (typeof input.endpoint !== 'string' || typeof input.remember !== 'boolean') throw new Error('Supply a workspace address and choose whether to remember this connection.')
      const endpoint = input.endpoint, remember = input.remember
      if (action === 'workspace.connect') {
        if (typeof input.credential !== 'string') throw new Error('Supply the workspace key through private stdin.')
        const credential = input.credential
        const expected = { tenantId: identifier(input.expected_tenant_id), principalId: identifier(input.expected_principal_id) }
        return this.mutate(input, signal, async () => {
          await connections.connect(endpoint, credential, remember, expected)
          this.options.deselectLocal()
        })
      }
      return this.mutate(input, signal, async () => {
        await connections.signIn(endpoint, input.credentials, remember)
        this.options.deselectLocal()
      })
    }
    if (action === 'workspace.restore') {
      const id = identifier(input.id)
      return this.mutate(input, signal, async () => {
        await connections.restore(id)
        this.options.deselectLocal()
      })
    }
    if (action === 'workspace.disconnect') return this.mutate(input, signal, async () => {
      // A failed server logout can still complete the local disconnect. Do not
      // automatically reopen the local workspace after that deliberate choice.
      try { await connections.disconnect() } finally { this.options.deselectLocal() }
    })
    if (action === 'workspace.forget') {
      const id = identifier(input.id)
      return this.mutate(input, signal, async () => {
        const selected = (await connections.status()).active?.bookmarkId === id
        await connections.forget(id)
        if (selected) this.options.deselectLocal()
      })
    }
    if (action === 'local.open') return this.mutate(input, signal, () => this.options.openLocal())
    throw new Error('Choose a workspace operation from the desktop catalog.')
  }
}
