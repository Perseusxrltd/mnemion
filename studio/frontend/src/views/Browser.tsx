import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useParams, useNavigate } from 'react-router-dom'
import { ChevronLeft, ChevronRight, FileText, Clock, User, ArrowRight } from 'lucide-react'
import { api } from '../api/client'
import { wingColor, type DrawerSummary } from '../types'
import TrustBadge from '../components/TrustBadge'
import WingBadge from '../components/WingBadge'

const PAGE = 50

// ── Skeleton row ──────────────────────────────────────────────────────────────

function SkeletonRow() {
  return (
    <div className="flex items-start gap-4 px-4 py-3 border-b" style={{ borderColor: 'var(--background-modifier-border)' }}>
      <div className="w-3.5 h-3.5 rounded mt-0.5 flex-shrink-0" style={{ background: 'var(--interactive-hover)' }} />
      <div className="flex-1 space-y-2 min-w-0">
        <div className="flex gap-2">
          <div className="h-4 w-20 rounded" style={{ background: 'var(--interactive-hover)' }} />
          <div className="h-4 w-14 rounded" style={{ background: 'var(--interactive-hover)' }} />
        </div>
        <div className="h-3 w-full rounded" style={{ background: 'var(--interactive-normal)' }} />
        <div className="h-3 w-3/4 rounded" style={{ background: 'var(--interactive-normal)' }} />
      </div>
    </div>
  )
}

// ── Drawer row ────────────────────────────────────────────────────────────────

function DrawerRow({ drawer, onClick }: { drawer: DrawerSummary; onClick: () => void }) {
  return (
    <button
      className="flex items-start gap-4 w-full px-4 py-3 border-b hover-row text-left transition-colors group"
      style={{ borderColor: 'var(--background-modifier-border)' }}
      onClick={onClick}
    >
      <FileText size={13} className="flex-shrink-0 mt-0.5" style={{ color: 'var(--text-faint)' }} />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1.5 flex-wrap">
          <WingBadge wing={drawer.wing} room={drawer.room} />
          {drawer.trust && <TrustBadge trust={drawer.trust} />}
        </div>
        <p className="text-sm leading-relaxed line-clamp-2" style={{ color: 'rgba(220,221,222,0.8)' }}>
          {drawer.preview}
        </p>
        <div className="flex items-center gap-3 mt-1.5 text-[10px]" style={{ color: 'var(--text-faint)' }}>
          {drawer.added_by && (
            <span className="flex items-center gap-1">
              <User size={9} />{drawer.added_by}
            </span>
          )}
          {drawer.timestamp && (
            <span className="flex items-center gap-1">
              <Clock size={9} />
              {drawer.timestamp.slice(0, 10)}
            </span>
          )}
          <span className="font-mono">{drawer.char_count.toLocaleString()} chars</span>
        </div>
      </div>
      <ArrowRight
        size={12}
        className="flex-shrink-0 mt-1 opacity-0 group-hover:opacity-100 transition-opacity"
        style={{ color: 'var(--text-faint)' }}
      />
    </button>
  )
}

// ── Wing grid (shown when no wing selected) ───────────────────────────────────

function WingGrid() {
  const navigate = useNavigate()
  const { data: taxonomy, isLoading } = useQuery({
    queryKey: ['taxonomy'],
    queryFn: api.taxonomy,
    staleTime: 60_000,
  })

  const wings = taxonomy?.taxonomy ?? {}
  const wingsSorted = Object.entries(wings).sort(
    (a, b) =>
      Object.values(b[1] as Record<string, number>).reduce((s, n) => s + n, 0) -
      Object.values(a[1] as Record<string, number>).reduce((s, n) => s + n, 0)
  )

  if (isLoading) {
    return (
      <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3 p-6">
        {Array.from({ length: 8 }).map((_, i) => (
          <div
            key={i}
            className="rounded-xl p-5"
            style={{ background: 'var(--surface)', border: '1px solid var(--background-modifier-border)', height: 88 }}
          />
        ))}
      </div>
    )
  }

  if (wingsSorted.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center flex-1 gap-3 py-16">
        <FileText size={36} style={{ color: 'var(--text-faint)' }} />
        <div className="text-sm" style={{ color: 'var(--text-muted)' }}>No drawers in the vault yet</div>
        <div className="text-xs" style={{ color: 'var(--text-faint)' }}>
          Connect an MCP agent to start storing memories.
        </div>
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <h2 className="text-xs font-semibold uppercase tracking-widest mb-4" style={{ color: 'var(--text-faint)' }}>
        All Wings — {wingsSorted.length}
      </h2>
      <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
        {wingsSorted.map(([wing, rooms]) => {
          const color = wingColor(wing)
          const total = Object.values(rooms as Record<string, number>).reduce((s, n) => s + n, 0)
          const roomCount = Object.keys(rooms).length
          return (
            <button
              key={wing}
              onClick={() => navigate(`/browse/${wing}`)}
              className="flex flex-col gap-3 p-5 rounded-xl text-left transition-all hover:scale-[1.02] fade-in"
              style={{
                background: 'var(--surface)',
                border: `1px solid var(--background-modifier-border)`,
              }}
              onMouseEnter={e => (e.currentTarget.style.borderColor = color + '60')}
              onMouseLeave={e => (e.currentTarget.style.borderColor = 'var(--background-modifier-border)')}
            >
              <div className="flex items-center justify-between">
                <span
                  className="w-3 h-3 rounded-full flex-shrink-0"
                  style={{ background: color, boxShadow: `0 0 8px ${color}60` }}
                />
                <span className="text-[10px] font-mono" style={{ color: 'var(--text-faint)' }}>
                  {total.toLocaleString()}
                </span>
              </div>
              <div>
                <div className="font-semibold text-sm mb-0.5" style={{ color }}>
                  {wing}
                </div>
                <div className="text-[11px]" style={{ color: 'var(--text-faint)' }}>
                  {roomCount} {roomCount === 1 ? 'room' : 'rooms'}
                </div>
              </div>
            </button>
          )
        })}
      </div>
    </div>
  )
}

// ── Main ──────────────────────────────────────────────────────────────────────

export default function Browser() {
  const { wing, room } = useParams<{ wing?: string; room?: string }>()
  const navigate = useNavigate()
  const [offset, setOffset] = useState(0)

  const { data, isLoading } = useQuery({
    queryKey: ['drawers', wing, room, offset],
    queryFn: () => api.drawers({ wing, room, limit: PAGE, offset }),
    placeholderData: prev => prev,
    enabled: !!wing, // only fetch when a wing is selected
  })

  const drawers: DrawerSummary[] = data?.drawers ?? []
  const hasMore = drawers.length === PAGE
  const color = wing ? wingColor(wing) : '#7f6df2'

  // No wing selected — show wing grid
  if (!wing) {
    return (
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Header */}
        <div
          className="flex items-center gap-2 px-4 py-3 border-b text-sm"
          style={{ borderColor: 'var(--background-modifier-border)', background: 'var(--background-secondary)' }}
        >
          <span className="font-medium">Browse</span>
          <div className="ml-auto text-[11px]" style={{ color: 'var(--text-faint)' }}>
            Select a wing to explore
          </div>
        </div>
        <WingGrid />
      </div>
    )
  }

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* Breadcrumb header */}
      <div
        className="flex items-center gap-2 px-4 py-3 border-b text-sm"
        style={{ borderColor: 'var(--background-modifier-border)', background: 'var(--background-secondary)' }}
      >
        <button
          onClick={() => navigate('/browse')}
          className="transition-colors"
          style={{ color: 'var(--text-faint)' }}
          onMouseEnter={e => (e.currentTarget.style.color = 'var(--text-normal)')}
          onMouseLeave={e => (e.currentTarget.style.color = 'var(--text-faint)')}
        >
          Browse
        </button>
        {wing && (
          <>
            <ChevronRight size={12} style={{ color: 'var(--text-faint)' }} />
            <button
              onClick={() => navigate(`/browse/${wing}`)}
              className="font-medium transition-colors"
              style={{ color }}
            >
              {wing}
            </button>
          </>
        )}
        {room && (
          <>
            <ChevronRight size={12} style={{ color: 'var(--text-faint)' }} />
            <span style={{ color: 'var(--text-normal)' }}>{room}</span>
          </>
        )}
        <span className="ml-auto text-xs font-mono" style={{ color: 'var(--text-faint)' }}>
          {isLoading ? '…' : drawers.length > 0 ? `${offset + 1}–${offset + drawers.length}` : '0 drawers'}
        </span>
      </div>

      {/* Loading skeletons */}
      {isLoading && (
        <div className="flex-1 overflow-hidden">
          {Array.from({ length: 8 }).map((_, i) => <SkeletonRow key={i} />)}
        </div>
      )}

      {/* Empty */}
      {!isLoading && drawers.length === 0 && (
        <div className="flex-1 flex flex-col items-center justify-center gap-3">
          <FileText size={32} style={{ color: 'var(--text-faint)' }} />
          <div className="text-sm" style={{ color: 'var(--text-muted)' }}>No drawers in this {room ? 'room' : 'wing'}</div>
        </div>
      )}

      {/* Drawer list */}
      {!isLoading && drawers.length > 0 && (
        <div className="flex-1 overflow-y-auto">
          {drawers.map(d => (
            <DrawerRow
              key={d.id}
              drawer={d}
              onClick={() => navigate(`/drawer/${encodeURIComponent(d.id)}`)}
            />
          ))}
        </div>
      )}

      {/* Pagination */}
      {(offset > 0 || hasMore) && !isLoading && (
        <div
          className="flex items-center justify-between px-4 py-2 border-t text-xs"
          style={{ borderColor: 'var(--background-modifier-border)', background: 'var(--background-secondary)' }}
        >
          <button
            disabled={offset === 0}
            onClick={() => setOffset(Math.max(0, offset - PAGE))}
            className="flex items-center gap-1 px-3 py-1.5 rounded-lg transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
            style={{ color: 'var(--text-muted)', border: '1px solid var(--background-modifier-border)' }}
            onMouseEnter={e => !e.currentTarget.disabled && (e.currentTarget.style.color = 'var(--text-normal)')}
            onMouseLeave={e => (e.currentTarget.style.color = 'var(--text-muted)')}
          >
            <ChevronLeft size={12} /> Prev
          </button>
          <span style={{ color: 'var(--text-faint)' }}>
            Page {Math.floor(offset / PAGE) + 1}
          </span>
          <button
            disabled={!hasMore}
            onClick={() => setOffset(offset + PAGE)}
            className="flex items-center gap-1 px-3 py-1.5 rounded-lg transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
            style={{ color: 'var(--text-muted)', border: '1px solid var(--background-modifier-border)' }}
            onMouseEnter={e => !e.currentTarget.disabled && (e.currentTarget.style.color = 'var(--text-normal)')}
            onMouseLeave={e => (e.currentTarget.style.color = 'var(--text-muted)')}
          >
            Next <ChevronRight size={12} />
          </button>
        </div>
      )}
    </div>
  )
}
