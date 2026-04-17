import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Database, Network, Layers, Bot, AlertTriangle, CheckCircle, Clock, Plus, FileText } from 'lucide-react'
import { api } from '../api/client'
import { wingColor } from '../types'
import TrustBadge from '../components/TrustBadge'
import WingBadge from '../components/WingBadge'
import { useLayoutCtx } from '../components/Layout'

function timeSince(isoStr: string): string {
  if (!isoStr) return ''
  const diff = Date.now() - new Date(isoStr).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

// ── Skeleton ──────────────────────────────────────────────────────────────────

function Skeleton({ className = '' }: { className?: string }) {
  return (
    <div
      className={`rounded ${className}`}
      style={{
        background: 'linear-gradient(90deg, var(--interactive-normal) 25%, var(--interactive-hover) 50%, var(--interactive-normal) 75%)',
        backgroundSize: '200% 100%',
        animation: 'shimmer 1.4s infinite',
      }}
    />
  )
}

// ── StatCard ──────────────────────────────────────────────────────────────────

function StatCard({ icon: Icon, label, value, sub, color = '#7f6df2', onClick, loading }: {
  icon: any; label: string; value?: string | number; sub?: string
  color?: string; onClick?: () => void; loading?: boolean
}) {
  return (
    <button
      className="flex flex-col gap-3 p-5 rounded-xl text-left transition-all hover:scale-[1.02] fade-in"
      style={{ background: 'var(--surface)', border: '1px solid var(--background-modifier-border)' }}
      onClick={onClick}
      disabled={loading}
    >
      <div className="flex items-center justify-between">
        <span className="text-[11px] font-semibold uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
          {label}
        </span>
        <span className="p-1.5 rounded-lg" style={{ background: color + '20' }}>
          <Icon size={14} style={{ color }} />
        </span>
      </div>
      <div>
        {loading ? (
          <>
            <Skeleton className="h-7 w-20 mb-1" />
            <Skeleton className="h-3 w-28" />
          </>
        ) : (
          <>
            <div className="text-2xl font-semibold tracking-tight">
              {typeof value === 'number' ? value.toLocaleString() : (value ?? '—')}
            </div>
            {sub && <div className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>{sub}</div>}
          </>
        )}
      </div>
    </button>
  )
}

// ── Main ──────────────────────────────────────────────────────────────────────

export default function Dashboard() {
  const navigate = useNavigate()
  const { openCreateDrawer } = useLayoutCtx()
  const { data: status, isLoading: statusLoading } = useQuery({
    queryKey: ['status'],
    queryFn: api.status,
  })
  const { data: trust, isLoading: trustLoading } = useQuery({
    queryKey: ['trust-stats'],
    queryFn: api.trustStats,
  })
  const { data: agents } = useQuery({ queryKey: ['agents'], queryFn: api.agents })
  const { data: recent } = useQuery({
    queryKey: ['drawers-recent'],
    queryFn: () => api.recentDrawers(7),
  })

  const topWings = status
    ? Object.entries(status.wings).sort((a, b) => b[1] - a[1]).slice(0, 8)
    : []

  const topRooms = status
    ? Object.entries(status.rooms).sort((a, b) => b[1] - a[1]).slice(0, 6)
    : []

  const activeAgents = agents?.activity?.length ?? 0
  const contestedCount = trust?.contested_conflicts ?? 0
  const currentPct = trust?.by_status?.current
    ? Math.round((trust.by_status.current.count / (trust.total || 1)) * 100)
    : null

  return (
    <div className="flex-1 overflow-y-auto p-6 space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between fade-in">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Overview</h1>
          <p className="text-sm mt-0.5" style={{ color: 'var(--text-muted)' }}>
            Anaktoron status and memory health at a glance.
          </p>
        </div>
        <button
          onClick={() => openCreateDrawer()}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors"
          style={{ background: 'rgba(127,109,242,0.15)', color: '#9d8ff9', border: '1px solid rgba(127,109,242,0.25)' }}
          onMouseEnter={e => (e.currentTarget.style.background = 'rgba(127,109,242,0.25)')}
          onMouseLeave={e => (e.currentTarget.style.background = 'rgba(127,109,242,0.15)')}
          title="New drawer (C)"
        >
          <Plus size={12} /> New Drawer
        </button>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatCard
          icon={Database} label="Total Drawers" loading={statusLoading}
          value={status?.total_drawers} color="#7f6df2"
          onClick={() => navigate('/browse')}
        />
        <StatCard
          icon={Layers} label="Wings" loading={statusLoading}
          value={status?.wing_count}
          sub={status ? `${status.room_count} rooms` : undefined}
          color="#4A9EFF" onClick={() => navigate('/browse')}
        />
        <StatCard
          icon={Bot} label="Active Agents"
          value={activeAgents} sub="seen in sessions"
          color="#4ECDC4" onClick={() => navigate('/agents')}
        />
        <StatCard
          icon={Network} label="Trust Health" loading={trustLoading}
          value={currentPct !== null ? `${currentPct}%` : undefined}
          sub="drawers current"
          color="#30d158" onClick={() => navigate('/settings')}
        />
      </div>

      {/* Recently Added drawers */}
      {recent?.drawers && recent.drawers.length > 0 && (
        <div
          className="rounded-xl p-5 fade-in"
          style={{ background: 'var(--surface)', border: '1px solid var(--background-modifier-border)' }}
        >
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold">Recently Added</h2>
            <button
              onClick={() => navigate('/browse')}
              className="text-xs transition-colors"
              style={{ color: 'var(--text-muted)' }}
              onMouseEnter={e => (e.currentTarget.style.color = 'var(--interactive-accent)')}
              onMouseLeave={e => (e.currentTarget.style.color = 'var(--text-muted)')}
            >
              Browse all →
            </button>
          </div>
          <div className="space-y-1">
            {recent.drawers.map(d => (
              <button
                key={d.id}
                onClick={() => navigate(`/drawer/${encodeURIComponent(d.id)}`)}
                className="flex items-start gap-3 w-full px-2 py-2 rounded-lg transition-colors hover-row text-left"
              >
                <FileText size={12} className="flex-shrink-0 mt-0.5" style={{ color: 'var(--text-faint)' }} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-0.5">
                    <WingBadge wing={d.wing} room={d.room} />
                    <span className="text-[10px]" style={{ color: 'var(--text-faint)' }}>
                      {timeSince(d.timestamp)}
                    </span>
                  </div>
                  <p className="text-xs truncate" style={{ color: 'var(--text-muted)' }}>
                    {d.preview || '—'}
                  </p>
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Wings breakdown */}
        <div
          className="rounded-xl p-5 fade-in"
          style={{ background: 'var(--surface)', border: '1px solid var(--background-modifier-border)' }}
        >
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold">Wings</h2>
            <button
              onClick={() => navigate('/browse')}
              className="text-xs transition-colors"
              style={{ color: 'var(--text-muted)' }}
              onMouseEnter={e => (e.currentTarget.style.color = 'var(--interactive-accent)')}
              onMouseLeave={e => (e.currentTarget.style.color = 'var(--text-muted)')}
            >
              Browse all →
            </button>
          </div>

          {statusLoading ? (
            <div className="space-y-3">
              {Array.from({ length: 5 }).map((_, i) => (
                <div key={i} className="flex items-center gap-3">
                  <Skeleton className="w-2 h-2 rounded-full" />
                  <Skeleton className="flex-1 h-3" />
                  <Skeleton className="w-24 h-1.5 rounded-full" />
                  <Skeleton className="w-12 h-3" />
                </div>
              ))}
            </div>
          ) : (
            <div className="space-y-1.5">
              {topWings.map(([wing, count]) => {
                const color = wingColor(wing)
                const total = status!.total_drawers
                const pct = Math.round((count / total) * 100)
                return (
                  <button
                    key={wing}
                    className="flex items-center gap-3 w-full rounded px-2 py-1.5 transition-colors hover-row"
                    onClick={() => navigate(`/browse/${wing}`)}
                  >
                    <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: color }} />
                    <span className="flex-1 text-sm truncate text-left font-medium" style={{ color }}>
                      {wing}
                    </span>
                    <div className="w-24 h-1 rounded-full overflow-hidden" style={{ background: 'var(--interactive-normal)' }}>
                      <div className="h-full rounded-full transition-all" style={{ background: color, width: `${pct}%` }} />
                    </div>
                    <span className="text-xs font-mono w-16 text-right" style={{ color: 'var(--text-muted)' }}>
                      {count.toLocaleString()}
                    </span>
                  </button>
                )
              })}
            </div>
          )}
        </div>

        {/* Trust overview */}
        <div
          className="rounded-xl p-5 fade-in"
          style={{ background: 'var(--surface)', border: '1px solid var(--background-modifier-border)' }}
        >
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold">Memory Trust</h2>
            {contestedCount > 0 && (
              <span className="flex items-center gap-1 text-xs px-2 py-0.5 rounded" style={{ color: '#f97316', background: 'rgba(249,115,22,0.1)' }}>
                <AlertTriangle size={10} /> {contestedCount} contested
              </span>
            )}
          </div>

          {trustLoading ? (
            <div className="space-y-3">
              {Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="space-y-1.5">
                  <div className="flex justify-between">
                    <Skeleton className="w-20 h-3" />
                    <Skeleton className="w-16 h-3" />
                  </div>
                  <Skeleton className="w-full h-1.5 rounded-full" />
                </div>
              ))}
            </div>
          ) : trust ? (
            <div className="space-y-3">
              {Object.entries(trust.by_status ?? {}).map(([st, data]) => {
                const colors: Record<string, string> = {
                  current: '#30d158', superseded: '#f59e0b',
                  contested: '#f97316', historical: '#6b7280',
                }
                const color = colors[st] ?? '#6b7280'
                const pct = Math.round((data.count / trust.total) * 100)
                return (
                  <div key={st} className="space-y-1">
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-medium capitalize" style={{ color }}>{st}</span>
                      <span style={{ color: 'var(--text-muted)' }}>
                        {data.count.toLocaleString()} · {pct}%
                      </span>
                    </div>
                    <div className="h-1 rounded-full overflow-hidden" style={{ background: 'var(--interactive-normal)' }}>
                      <div
                        className="h-full rounded-full transition-all"
                        style={{ background: color, width: `${pct}%` }}
                      />
                    </div>
                  </div>
                )
              })}
              <div
                className="pt-2 border-t text-xs flex items-center gap-1.5"
                style={{ borderColor: 'var(--background-modifier-border)', color: 'var(--text-muted)' }}
              >
                <CheckCircle size={11} style={{ color: '#30d158' }} />
                avg confidence {Math.round((trust.by_status?.current?.avg_confidence ?? 1) * 100)}%
              </div>
            </div>
          ) : (
            <div className="text-sm" style={{ color: 'var(--text-muted)' }}>No trust data</div>
          )}
        </div>
      </div>

      {/* Recent Agent Activity */}
      {agents?.activity && agents.activity.length > 0 && (
        <div
          className="rounded-xl p-5 fade-in"
          style={{ background: 'var(--surface)', border: '1px solid var(--background-modifier-border)' }}
        >
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold">Recent Agent Activity</h2>
            <button
              onClick={() => navigate('/agents')}
              className="text-xs transition-colors"
              style={{ color: 'var(--text-muted)' }}
              onMouseEnter={e => (e.currentTarget.style.color = 'var(--interactive-accent)')}
              onMouseLeave={e => (e.currentTarget.style.color = 'var(--text-muted)')}
            >
              View all →
            </button>
          </div>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            {agents.activity.slice(0, 4).map(a => (
              <div
                key={a.agent}
                className="rounded-lg p-3"
                style={{ background: 'var(--raised)', border: '1px solid var(--background-modifier-border)' }}
              >
                <div className="flex items-center gap-1.5 mb-1">
                  <span className="w-1.5 h-1.5 rounded-full" style={{ background: '#30d158' }} />
                  <span className="text-xs font-medium truncate">{a.agent}</span>
                </div>
                <div className="text-[10px] flex items-center gap-1" style={{ color: 'var(--text-muted)' }}>
                  <Clock size={9} />
                  {a.last_seen ? new Date(a.last_seen).toLocaleDateString() : 'unknown'}
                </div>
                <div className="text-[10px] mt-0.5" style={{ color: 'var(--text-muted)' }}>
                  {a.session_entries} entries
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Busiest Rooms */}
      {topRooms.length > 0 && (
        <div
          className="rounded-xl p-5 fade-in"
          style={{ background: 'var(--surface)', border: '1px solid var(--background-modifier-border)' }}
        >
          <h2 className="text-sm font-semibold mb-4">Busiest Rooms</h2>
          <div className="flex flex-wrap gap-2">
            {topRooms.map(([room, count]) => (
              <button
                key={room}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs transition-colors"
                style={{ background: 'var(--raised)', border: '1px solid var(--background-modifier-border)' }}
                onClick={() => navigate('/search?q=' + encodeURIComponent(room))}
                onMouseEnter={e => (e.currentTarget.style.borderColor = 'var(--interactive-accent)')}
                onMouseLeave={e => (e.currentTarget.style.borderColor = 'var(--background-modifier-border)')}
              >
                <span style={{ color: 'var(--text-muted)' }}>{room}</span>
                <span className="font-mono text-[10px]" style={{ color: 'var(--interactive-accent)' }}>
                  {count.toLocaleString()}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
