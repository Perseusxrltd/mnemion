import type { AgentsResponse, ConnectorStatus, CoreMemory, DrawerDetail, DrawerSummary, KGGraph, ObsidianStatus, RecentDrawer, SearchHit, Status, StudioConfig, Taxonomy, TrustStats } from '../types'
import type { WorkspaceInspection, WorkspaceSession, WorkspaceStatus } from '../workspace/connection-types'
import type { LocalOptions, LocalStatus, MemoryWrite, PortChange, RemoteChange, RemoteCheck, BackupView, BackupSettingsInput, BackupReceipt, BackupInspectionData, BackupRestoreInput, RecoveryReceipt } from '../../../shared/local-workspace'
import type { SignInCredentials, InvitationCredentials, InvitationPreview } from '@mnemion/client'

declare global {
  interface Window {
    mnemion?: {
      version?: () => Promise<string>
      platform?: () => Promise<string>
      backendPort?: () => Promise<number>
      studioToken?: () => Promise<string | null>
      serviceRequest?: (request: { url: string; method: string; headers: Record<string, string>; body?: string }) => Promise<{ status: number; headers: Record<string, string>; body: Uint8Array }>
      workspaceStatus?: () => Promise<WorkspaceStatus>
      workspaceInspect?: (id: string) => Promise<WorkspaceInspection>
      workspaceResume?: () => Promise<WorkspaceSession | null>
      workspaceConnect?: (input: { endpoint: string; credential: string; remember: boolean }) => Promise<WorkspaceSession>
      workspaceSignIn?: (input: { endpoint: string; credentials: SignInCredentials; remember: boolean }) => Promise<WorkspaceSession>
      workspaceInvitationPreview?: (input: { endpoint: string; invitation: string }) => Promise<InvitationPreview>
      workspaceInvitationAccept?: (input: { endpoint: string; credentials: InvitationCredentials; remember: boolean }) => Promise<WorkspaceSession>
      workspaceRestore?: (id: string) => Promise<WorkspaceSession>
      workspaceForget?: (id: string) => Promise<void>
      workspaceDisconnect?: () => Promise<void>
      workspaceReset?: () => Promise<void>
      onWorkspaceClosed?: (callback: (sessionToken: string) => void) => () => void
      localStatus?: () => Promise<LocalStatus>
      localCreate?: (input: LocalOptions) => Promise<LocalStatus>
      localStart?: () => Promise<LocalStatus>
      localOpen?: () => Promise<WorkspaceSession>
      localStop?: () => Promise<boolean>
      localMemory?: (input: MemoryWrite) => Promise<LocalStatus>
      localPort?: (input: PortChange) => Promise<LocalStatus>
      localRemote?: (input: RemoteChange) => Promise<LocalStatus>
      localRemoteCheck?: (input: RemoteCheck) => Promise<LocalStatus>
      localBackupStatus?: () => Promise<BackupView>
      localBackupKey?: () => Promise<string>
      localBackupChoose?: (kind: 'folder' | 'file') => Promise<{ id: string; path: string } | null>
      localBackupConfigure?: (input: BackupSettingsInput) => Promise<BackupView>
      localBackupRun?: (input: { ledger_only?: boolean; recovery_key?: string }) => Promise<BackupReceipt>
      localBackupCancel?: () => Promise<LocalStatus>
      localBackupInspect?: (input: { selection_id: string; recovery_key: string }) => Promise<BackupInspectionData>
      localBackupRestore?: (input: BackupRestoreInput) => Promise<{ id: string; receipt: RecoveryReceipt }>
      localRecoveryCopies?: () => Promise<Array<{ id: string; receipt: RecoveryReceipt }>>
      localRecoveryUse?: (id: string | null) => Promise<LocalStatus>
      onBackupStatus?: (callback: () => void) => () => void
      onLocalStatus?: (callback: (status: LocalStatus) => void) => () => void
      onLocalSelection?: (callback: (phase: 'changing' | 'changed' | 'unchanged') => void) => () => void
      chooseVault?: () => Promise<{ id: string; path: string } | null>
      refreshVault?: (selection: string, bytes: Uint8Array) => Promise<{ completed: boolean; file_count: number; pruned_files: number; detached_annotations: string[]; conflicts: Array<{ path: string; proposal_path?: string }>; vault_path: string }>
      onNavigate?: (callback: (route: string) => void) => () => void
    }
  }
}

const isElectron = typeof window !== 'undefined' && window.location.protocol === 'file:'
let cachedStudioToken: string | null | undefined
let cachedElectronOrigin: string | undefined

async function electronOrigin(): Promise<string> {
  if (!cachedElectronOrigin) {
    let port = 7891
    try {
      port = (await window.mnemion?.backendPort?.()) || port
    } catch {
      port = 7891
    }
    cachedElectronOrigin = `http://127.0.0.1:${port}`
  }
  return cachedElectronOrigin
}

async function studioTokenHeader(): Promise<Record<string, string>> {
  if (cachedStudioToken === undefined) {
    cachedStudioToken = null
    try {
      cachedStudioToken = (await window.mnemion?.studioToken?.()) || null
    } catch {
      cachedStudioToken = null
    }
  }
  return cachedStudioToken ? { 'X-Mnemion-Studio-Token': cachedStudioToken } : {}
}

async function get<T>(path: string, params?: Record<string, string | number>): Promise<T> {
  const base = isElectron ? `${await electronOrigin()}/api${path}` : `/api${path}`
  const url = isElectron ? new URL(base) : new URL(base, window.location.origin)
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== null && v !== '') url.searchParams.set(k, String(v))
    }
  }
  const res = await fetch(url.toString(), { headers: await studioTokenHeader() })
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json()
}

async function getBlob(path: string, params?: Record<string, string | number>): Promise<Blob> {
  const base = isElectron ? `${await electronOrigin()}/api${path}` : `/api${path}`
  const url = isElectron ? new URL(base) : new URL(base, window.location.origin)
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== null && v !== '') url.searchParams.set(k, String(v))
    }
  }
  const res = await fetch(url.toString(), { headers: await studioTokenHeader() })
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.blob()
}

function saveBlob(blob: Blob, filename: string): void {
  const objectUrl = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = objectUrl
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 0)
}

async function apiUrl(path: string): Promise<string> {
  return isElectron ? `${await electronOrigin()}/api${path}` : `/api${path}`
}

async function del(path: string): Promise<void> {
  const res = await fetch(await apiUrl(path), {
    method: 'DELETE',
    headers: await studioTokenHeader(),
  })
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(await apiUrl(path), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(await studioTokenHeader()) },
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json()
}

async function put<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(await apiUrl(path), {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', ...(await studioTokenHeader()) },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json()
}

// API methods

export const api = {
  status: (): Promise<Status> => get('/status'),

  taxonomy: (): Promise<Taxonomy> => get('/taxonomy'),

  drawers: (params: {
    wing?: string
    room?: string
    limit?: number
    offset?: number
  }): Promise<{ drawers: DrawerSummary[]; wing: string | null; room: string | null; offset: number; limit: number }> =>
    get('/drawers', params as Record<string, string | number>),

  drawer: (id: string): Promise<DrawerDetail> => get(`/drawer/${encodeURIComponent(id)}`),

  deleteDrawer: (id: string): Promise<void> => del(`/drawer/${encodeURIComponent(id)}`),

  createDrawer: (body: { wing: string; room: string; content: string; source_file?: string }) =>
    post('/drawer', body),

  search: (params: {
    q: string
    wing?: string
    room?: string
    limit?: number
    min_similarity?: number
  }): Promise<{ query: string; count: number; results: SearchHit[] }> =>
    get('/search', params as Record<string, string | number>),

  kgGraph: (limitNodes?: number): Promise<KGGraph> =>
    get('/kg/graph', limitNodes ? { limit_nodes: limitNodes } : undefined),

  kgEntity: (name: string) => get(`/kg/entity/${encodeURIComponent(name)}`),

  kgEntities: (limit?: number) => get('/kg/entities', limit ? { limit } : undefined),

  trustStats: (): Promise<TrustStats> => get('/trust/stats'),

  contested: () => get('/trust/contested'),

  verifyDrawer: (id: string) => post(`/trust/${encodeURIComponent(id)}/verify`),

  challengeDrawer: (id: string, reason?: string) =>
    post(`/trust/${encodeURIComponent(id)}/challenge${reason ? `?reason=${encodeURIComponent(reason)}` : ''}`),

  recentDrawers: (limit?: number): Promise<{ drawers: RecentDrawer[] }> =>
    get('/drawers/recent', limit ? { limit } : undefined),

  agents: (): Promise<AgentsResponse> => get('/agents'),

  connectors: (): Promise<{ connectors: ConnectorStatus[]; python_cmd: string; python_args: string[] }> =>
    get('/connectors'),

  connector: (id: string): Promise<ConnectorStatus> =>
    get(`/connectors/${encodeURIComponent(id)}`),

  installConnector: (id: string): Promise<{ success: boolean; config_path: string; backup_path?: string; note?: string }> =>
    post(`/connectors/${encodeURIComponent(id)}/install`),

  uninstallConnector: (id: string): Promise<{ success: boolean; backup_path?: string }> =>
    post(`/connectors/${encodeURIComponent(id)}/uninstall`),

  config: (): Promise<StudioConfig> => get('/config'),

  updateLLM: (body: { backend: string; url?: string; model?: string; api_key?: string }) =>
    put('/config/llm', body),

  obsidianStatus: (): Promise<ObsidianStatus> => get('/obsidian/status'),

  syncObsidian: (): Promise<Record<string, unknown>> => post('/obsidian/sync'),

  openObsidian: (): Promise<Record<string, unknown>> => post('/obsidian/open'),

  getCoreMemories: (): Promise<CoreMemory[]> => get('/core-memory'),

  getCoreMemory: (key: string): Promise<CoreMemory> => get(`/core-memory/${encodeURIComponent(key)}`),

  updateCoreMemory: (key: string, content: string): Promise<{ success: boolean; key: string; content: string }> =>
    put(`/core-memory/${encodeURIComponent(key)}`, { content }),

  downloadVault: async (wing?: string) => {
    const blob = await getBlob('/export/vault', wing ? { wing } : undefined)
    saveBlob(blob, `mnemion_vault${wing ? `_${wing}` : ''}.zip`)
  },
}
