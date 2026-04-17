import { useQuery } from '@tanstack/react-query'
import { Bot, Clock, Activity, Wifi, WifiOff, RefreshCw, Sparkles, Code2, MousePointer2, MessageSquare } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { api } from '../api/client'

function timeSince(isoStr: string): string {
  if (!isoStr) return 'never'
  const diff = Date.now() - new Date(isoStr).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

function isActive(isoStr: string): boolean {
  if (!isoStr) return false
  const diff = Date.now() - new Date(isoStr).getTime()
  return diff < 5 * 60 * 1000 // 5 minutes
}

const AGENT_ICON_MAP: [string, LucideIcon][] = [
  ['claude',  Bot],
  ['gemini',  Sparkles],
  ['gpt',     MessageSquare],
  ['codex',   Code2],
  ['cursor',  MousePointer2],
]

function AgentIcon({ name, size = 18, color }: { name: string; size?: number; color?: string }) {
  const n = name.toLowerCase()
  const match = AGENT_ICON_MAP.find(([k]) => n.includes(k))
  const Icon = match ? match[1] : Bot
  return <Icon size={size} color={color} />
}

export default function AgentsView() {
  const { data, isLoading, refetch, isFetching } = useQuery({
    queryKey: ['agents'],
    queryFn: api.agents,
    refetchInterval: 30_000,
  })

  const activity = data?.activity ?? []
  const heartbeats = data?.heartbeats ?? []

  return (
    <div className="flex-1 overflow-y-auto p-6 space-y-6">
      <div className="flex items-center justify-between fade-in">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Agents</h1>
          <p className="text-sm text-muted mt-0.5">Connected AI agents and their activity in the Anaktoron.</p>
        </div>
        <button
          onClick={() => refetch()}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs text-muted hover:text-white hover:bg-white/5 transition-colors border"
          style={{ borderColor: 'var(--border)' }}
        >
          <RefreshCw size={12} className={isFetching ? 'animate-spin' : ''} />
          Refresh
        </button>
      </div>

      {/* Live heartbeats */}
      {heartbeats.length > 0 && (
        <div className="fade-in">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-muted mb-3">Live Connections</h2>
          <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
            {heartbeats.map(b => {
              const active = isActive(b.last_call)
              return (
                <div key={b.agent_id} className="rounded-xl p-4" style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}>
                  <div className="flex items-center gap-2 mb-2">
                    <span className={`w-2 h-2 rounded-full ${active ? 'bg-emerald-400 pulse-slow' : 'bg-zinc-500'}`} />
                    <span className="text-sm font-medium">{b.agent_id}</span>
                  </div>
                  <div className="space-y-1 text-[10px] text-muted">
                    <div className="flex items-center gap-1">
                      <Clock size={9} /> Last call: {timeSince(b.last_call)}
                    </div>
                    <div className="flex items-center gap-1">
                      <Activity size={9} /> {b.call_count} calls
                    </div>
                    {b.last_tool && (
                      <div className="font-mono text-accent/70 truncate">{b.last_tool}</div>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Session activity */}
      <div className="fade-in">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-muted mb-3">
          Session Activity {activity.length > 0 && `· ${activity.length} agents`}
        </h2>

        {isLoading && <div className="text-sm text-muted">Loading…</div>}

        {!isLoading && activity.length === 0 && (
          <div className="flex flex-col items-center justify-center py-12 gap-3 rounded-xl" style={{ border: '1px dashed var(--border)' }}>
            <Bot size={28} className="text-faint" />
            <div className="text-sm text-muted">No agent activity recorded yet</div>
            <div className="text-xs text-faint">Agents write to the sessions wing after each conversation.</div>
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
          {activity.map(a => {
            const active = isActive(a.last_seen)
            return (
              <div
                key={a.agent}
                className="flex items-center gap-4 p-4 rounded-xl transition-all fade-in"
                style={{ background: 'var(--surface)', border: `1px solid ${active ? 'rgba(16,185,129,0.3)' : 'var(--border)'}` }}
              >
                <div className="relative flex-shrink-0">
                  <div className="w-10 h-10 rounded-full flex items-center justify-center"
                    style={{ background: active ? 'rgba(16,185,129,0.12)' : 'var(--raised)' }}>
                    <AgentIcon name={a.agent} size={18} color={active ? '#30d158' : '#666'} />
                  </div>
                  <span className={`absolute -bottom-0.5 -right-0.5 w-3 h-3 rounded-full border-2 ${active ? 'bg-emerald-400' : 'bg-zinc-600'}`}
                    style={{ borderColor: 'var(--surface)' }} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="font-medium text-sm">{a.agent}</div>
                  <div className="flex items-center gap-3 mt-0.5 text-[10px] text-muted">
                    <span className="flex items-center gap-1">
                      {active ? <Wifi size={9} className="text-emerald-400" /> : <WifiOff size={9} />}
                      {timeSince(a.last_seen)}
                    </span>
                    <span className="flex items-center gap-1">
                      <Activity size={9} /> {a.session_entries} entries
                    </span>
                  </div>
                </div>
                {active && (
                  <span className="text-[10px] font-medium px-2 py-0.5 rounded text-emerald-400 bg-emerald-400/10">Active</span>
                )}
              </div>
            )
          })}
        </div>
      </div>

      {/* How to connect */}
      <div className="rounded-xl p-5 fade-in" style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}>
        <h2 className="text-xs font-semibold uppercase tracking-wider text-muted mb-3">Connecting a new agent</h2>
        <div className="text-xs text-muted space-y-2">
          <p>Any MCP-compatible agent (Claude Code, Cursor, Windsurf…) can connect to Mnemion:</p>
          <pre className="bg-raised rounded-lg p-3 font-mono text-[11px] text-white/70 overflow-x-auto">{`# In your MCP config:
{
  "mnemion": {
    "command": "python",
    "args": ["-m", "mnemion.mcp_server"]
  }
}`}</pre>
          <p>Agents with <code className="bg-raised px-1 rounded text-accent/80">mnemion_diary_write</code> configured will appear here after their first session.</p>
        </div>
      </div>
    </div>
  )
}
