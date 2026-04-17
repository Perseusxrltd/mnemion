import { useEffect, useState } from 'react'
import { NavLink, useNavigate, useLocation, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ChevronDown, ChevronRight, FileText, Plus } from 'lucide-react'
import { api } from '../api/client'
import { wingColor } from '../types'
import { useLayoutCtx } from './Layout'

function WingEntry({
  wing,
  rooms,
  isCurrentWing,
}: {
  wing: string
  rooms: Record<string, number>
  isCurrentWing: boolean
}) {
  const navigate = useNavigate()
  const location = useLocation()
  const [open, setOpen] = useState(isCurrentWing)
  // Auto-expand when the URL points to this wing (e.g. deep-link reload)
  useEffect(() => {
    if (isCurrentWing) setOpen(true)
  }, [isCurrentWing])
  const color = wingColor(wing)
  const total = Object.values(rooms).reduce((s, n) => s + n, 0)
  const roomList = Object.entries(rooms).sort((a, b) => b[1] - a[1])

  const isWingActive = location.pathname === `/browse/${wing}`

  return (
    <div>
      <button
        className="flex items-center gap-1.5 w-full px-2 py-1 rounded text-[13px] transition-colors text-left group hover-row"
        style={{ color: isWingActive ? 'var(--text-normal)' : 'var(--text-muted)' }}
        onClick={() => {
          setOpen(v => !v)
          navigate(`/browse/${wing}`)
        }}
      >
        <span className="w-3 flex-shrink-0 flex items-center justify-center" style={{ color: 'var(--text-faint)' }}>
          {open ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
        </span>
        <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: color }} />
        <span className="flex-1 truncate font-medium" style={{ color: open || isWingActive ? color : 'inherit' }}>
          {wing}
        </span>
        <span className="text-[10px] font-mono opacity-30 group-hover:opacity-60 transition-opacity">
          {total.toLocaleString()}
        </span>
      </button>

      {open && (
        <div className="tree-indent ml-3 mt-0.5 space-y-0.5" style={{ borderColor: color + '30' }}>
          {roomList.map(([room, count]) => {
            const roomPath = `/browse/${wing}/${room}`
            const isRoomActive = location.pathname === roomPath
            return (
              <NavLink
                key={room}
                to={roomPath}
                className={() =>
                  `flex items-center gap-1.5 px-2 py-0.5 rounded text-[12px] transition-colors ${
                    isRoomActive ? 'text-white' : 'text-muted hover-row'
                  }`
                }
                style={isRoomActive ? { background: 'rgba(127,109,242,0.15)' } : {}}
              >
                <FileText size={10} className="flex-shrink-0 opacity-40" />
                <span className="flex-1 truncate">{room}</span>
                <span className="text-[10px] font-mono opacity-25">{count}</span>
              </NavLink>
            )
          })}
        </div>
      )}
    </div>
  )
}

export default function LeftSidebar({ width = 260 }: { width?: number }) {
  const navigate = useNavigate()
  const { wing: currentWing } = useParams<{ wing?: string }>()
  const [vaultOpen, setVaultOpen] = useState(true)
  const { openCreateDrawer } = useLayoutCtx()

  const { data: taxonomy } = useQuery({
    queryKey: ['taxonomy'],
    queryFn: api.taxonomy,
    staleTime: 60_000,
  })

  const { data: status } = useQuery({
    queryKey: ['status'],
    queryFn: api.status,
    staleTime: 30_000,
  })

  const wings = taxonomy?.taxonomy ?? {}
  const wingsSorted = Object.entries(wings).sort(
    (a, b) =>
      Object.values(b[1] as Record<string, number>).reduce((s, n) => s + n, 0) -
      Object.values(a[1] as Record<string, number>).reduce((s, n) => s + n, 0)
  )

  return (
    <div
      className="flex flex-col h-full overflow-hidden"
      style={{
        width,
        flexShrink: 0,
        background: 'var(--background-secondary)',
        borderRight: '1px solid var(--background-modifier-border)',
      }}
    >
        {/* Vault header */}
        <div
          className="flex items-center gap-2 px-3 py-2.5 border-b"
          style={{ borderColor: 'var(--background-modifier-border)' }}
        >
          <span style={{ fontSize: 15, lineHeight: 1, flexShrink: 0 }}>🏛</span>
          <div className="flex-1 min-w-0">
            <div className="text-[13px] font-semibold truncate">Mnemion</div>
            <div className="text-[10px]" style={{ color: 'var(--text-faint)' }}>Memory Palace</div>
          </div>
          {status && (
            <span
              className="text-[10px] font-mono px-1.5 py-0.5 rounded flex-shrink-0"
              style={{ background: 'rgba(127,109,242,0.15)', color: '#9d8ff9' }}
            >
              v{status.version}
            </span>
          )}
        </div>

        {/* New Drawer button */}
        <div className="px-2 pt-2">
          <button
            onClick={() => openCreateDrawer(currentWing ?? '')}
            className="flex items-center gap-1.5 w-full px-3 py-1.5 rounded-lg text-[12px] font-medium transition-colors"
            style={{
              background: 'rgba(127,109,242,0.12)',
              color: 'var(--interactive-accent)',
              border: '1px solid rgba(127,109,242,0.2)',
            }}
            onMouseEnter={e => (e.currentTarget.style.background = 'rgba(127,109,242,0.2)')}
            onMouseLeave={e => (e.currentTarget.style.background = 'rgba(127,109,242,0.12)')}
          >
            <Plus size={13} />
            New Drawer
          </button>
        </div>

        {/* File explorer */}
        <div className="flex-1 overflow-y-auto px-1.5 py-2">
          {/* VAULT section */}
          <button
            className="flex items-center gap-1 w-full px-2 py-1 mb-1 text-[10px] font-semibold uppercase tracking-widest transition-colors"
            style={{ color: 'var(--text-faint)' }}
            onClick={() => setVaultOpen(v => !v)}
          >
            {vaultOpen ? <ChevronDown size={10} /> : <ChevronRight size={10} />}
            <span>Vault</span>
            {status && (
              <span className="ml-auto font-mono text-[10px]">
                {status.total_drawers.toLocaleString()}
              </span>
            )}
          </button>

          {vaultOpen && (
            <div className="space-y-0.5">
              {wingsSorted.map(([wing, rooms]) => (
                <WingEntry
                  key={wing}
                  wing={wing}
                  rooms={rooms as Record<string, number>}
                  isCurrentWing={wing === currentWing}
                />
              ))}

              {wingsSorted.length === 0 && (
                <div className="px-3 py-4 text-center text-[12px]" style={{ color: 'var(--text-faint)' }}>
                  No wings yet.<br />
                  <button
                    onClick={() => openCreateDrawer()}
                    className="mt-1 underline"
                    style={{ color: 'var(--interactive-accent)' }}
                  >
                    Create first drawer
                  </button>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Connection status */}
        <div
          className="px-3 py-2 border-t text-[11px] flex items-center gap-2"
          style={{ borderColor: 'var(--background-modifier-border)', color: 'var(--text-faint)' }}
        >
          <span
            className="w-1.5 h-1.5 rounded-full flex-shrink-0"
            style={{
              background: status ? '#30d158' : '#666',
              boxShadow: status ? '0 0 5px #30d15860' : 'none',
            }}
          />
          {status
            ? `${status.total_drawers.toLocaleString()} drawers · ${status.wing_count} wings`
            : 'Connecting…'}
        </div>
    </div>
  )
}
