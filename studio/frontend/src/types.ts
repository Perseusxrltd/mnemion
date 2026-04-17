export interface Status {
  version: string
  total_drawers: number
  wing_count: number
  room_count: number
  wings: Record<string, number>
  rooms: Record<string, number>
  anaktoron_path: string
  collection_name: string
}

export interface TrustSummary {
  status: 'current' | 'superseded' | 'contested' | 'historical' | 'unknown'
  confidence: number
  verifications: number
  challenges: number
}

export interface DrawerSummary {
  id: string
  wing: string
  room: string
  source: string
  added_by: string
  timestamp: string
  preview: string
  char_count: number
  trust: TrustSummary | null
}

export interface DrawerDetail extends DrawerSummary {
  content: string
  trust_history: TrustHistoryEntry[]
  related: SearchHit[]
}

export interface TrustHistoryEntry {
  status: string
  changed_by: string
  reason: string
  changed_at: string
}

export interface SearchHit {
  id: string
  wing: string
  room: string
  content: string
  score?: number
  similarity?: number
  trust_status?: 'current' | 'superseded' | 'contested' | 'historical' | string
}

export interface Taxonomy {
  taxonomy: Record<string, Record<string, number>>
}

export interface KGNode {
  id: string
  label: string
  type: string
}

export interface KGEdge {
  id: string
  source: string
  target: string
  label: string
  valid_from?: string
  confidence?: number
}

export interface KGGraph {
  nodes: KGNode[]
  edges: KGEdge[]
}

export interface AgentActivity {
  agent: string
  last_seen: string
  session_entries: number
}

export interface AgentsResponse {
  heartbeats: HeartbeatEntry[]
  activity: AgentActivity[]
}

export interface HeartbeatEntry {
  agent_id: string
  pid: number
  started_at: string
  last_call: string
  last_tool: string
  call_count: number
}

export interface ConnectorStatus {
  id: string
  name: string
  vendor: string
  category: 'cli' | 'app' | 'ide' | string
  description: string
  doc_url: string
  install_note: string
  config_path: string
  format: 'json' | 'toml' | string
  installed: boolean
  mnemion_configured: boolean
  other_mcp_servers: string[]
  legacy_detected: boolean
  error: string | null
  snippet?: string
}

export interface LLMConfig {
  backend: string
  url?: string
  model?: string
  api_key?: string | null
}

export interface StudioConfig {
  anaktoron_path: string
  collection_name: string
  llm: LLMConfig
  topic_wings: string[]
}

export interface RecentDrawer {
  id: string
  wing: string
  room: string
  timestamp: string
  added_by: string
  preview: string
}

export interface TrustStats {
  total: number
  by_status: Record<string, { count: number; avg_confidence: number }>
  contested_conflicts: number
}

export type ViewName = 'dashboard' | 'graph' | 'browser' | 'search' | 'agents' | 'settings'

// Wing colors — consistent palette
export const WING_COLORS: Record<string, string> = {
  projects: '#4A9EFF',
  personal: '#4ECDC4',
  legal: '#FF6B6B',
  sessions: '#A78BFA',
  admin_law: '#F59E0B',
  gemini: '#EC4899',
  distilled: '#10B981',
  openclaw: '#FB923C',
  wing_claude: '#60A5FA',
  wing_stress: '#6B7280',
  live_test: '#34D399',
  cursor_scraped: '#FCD34D',
  unknown: '#6B7280',
}

export function wingColor(wing: string): string {
  // Exact match
  if (WING_COLORS[wing]) return WING_COLORS[wing]
  // Prefix match
  for (const [k, v] of Object.entries(WING_COLORS)) {
    if (wing.startsWith(k) || k.startsWith(wing)) return v
  }
  // Deterministic hash for unknown wings
  let hash = 0
  for (const c of wing) hash = (hash * 31 + c.charCodeAt(0)) & 0xffffff
  const palette = ['#818CF8', '#34D399', '#F472B6', '#FBBF24', '#60A5FA', '#A78BFA', '#FB923C']
  return palette[hash % palette.length]
}
