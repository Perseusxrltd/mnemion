import type { AgentsResponse, DrawerDetail, DrawerSummary, KGGraph, Status, Taxonomy, TrustStats } from '../types'

// In Electron (file:// origin) the backend runs on localhost:7891
const ELECTRON_ORIGIN = 'http://127.0.0.1:7891'
const isElectron = typeof window !== 'undefined' && window.location.protocol === 'file:'
async function get<T>(path: string, params?: Record<string, string | number>): Promise<T> {
  const base = isElectron ? `${ELECTRON_ORIGIN}/api${path}` : `/api${path}`
  const url = new URL(base, isElectron ? undefined : window.location.origin)
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== null && v !== '') url.searchParams.set(k, String(v))
    }
  }
  const res = await fetch(url.toString())
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json()
}

function apiUrl(path: string): string {
  return isElectron ? `${ELECTRON_ORIGIN}/api${path}` : `/api${path}`
}

async function del(path: string): Promise<void> {
  const res = await fetch(apiUrl(path), { method: 'DELETE' })
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(apiUrl(path), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json()
}

async function put<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(apiUrl(path), {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json()
}

// ── API methods ───────────────────────────────────────────────────────────────

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
  }): Promise<{ query: string; count: number; results: DrawerSummary[] }> =>
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

  agents: (): Promise<AgentsResponse> => get('/agents'),

  config: () => get('/config'),

  updateLLM: (body: { backend: string; url?: string; model?: string; api_key?: string }) =>
    put('/config/llm', body),

  // Alias for RightSidebar / drawer detail
  getDrawer: (id: string): Promise<DrawerDetail> => get(`/drawer/${encodeURIComponent(id)}`),

  // Vault export — download as zip
  exportVaultUrl: (wing?: string) => {
    const origin = isElectron ? ELECTRON_ORIGIN : window.location.origin
    const url = new URL('/api/export/vault', origin)
    if (wing) url.searchParams.set('wing', wing)
    return url.toString()
  },
}
