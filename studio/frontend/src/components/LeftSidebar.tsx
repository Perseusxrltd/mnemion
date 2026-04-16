import { useState } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ChevronDown, ChevronRight, FileText, Folder, FolderOpen } from 'lucide-react'
import { api } from '../api/client'
import { wingColor } from '../types'

function WingEntry({
  wing, rooms, onNavigate,
}: {
  wing: string
  rooms: Record<string, number>
  onNavigate: (path: string) => void
}) {
  const [open, setOpen] = useState(false)
  const color = wingColor(wing)
  const total = Object.values(rooms).reduce((s, n) => s + n, 0)
  const roomList = Object.entries(rooms).sort((a, b) => b[1] - a[1])

  return (
    <div>
      <button
        className="flex items-center gap-1.5 w-full px-2 py-1 rounded text-[13px] transition-colors hover-row text-left group"
        style={{ color: open ? 'var(--text-normal)' : 'var(--text-muted)' }}
        onClick={() => { setOpen(v => !v); onNavigate(`/browse/${wing}`) }}
      >
        <span className="text-faint w-3 flex-shrink-0 flex items-center justify-center">
          {open ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
        </span>
        <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: color }} />
        <span className="flex-1 truncate font-medium" style={{ fontSize: 13 }}>{wing}</span>
        <span className="text-[10px] font-mono opacity-40 group-hover:opacity-70 transition-opacity">
          {total.toLocaleString()}
        </span>
      </button>

      {open && (
        <div className="tree-indent ml-3 mt-0.5 space-y-0.5">
          {roomList.map(([room, count]) => (
            <NavLink
              key={room}
              to={`/browse/${wing}/${room}`}
              className={({ isActive }) =>
                `flex items-center gap-1.5 px-2 py-0.5 rounded text-[12px] transition-colors
                ${isActive ? 'nav-item-active' : 'text-muted hover-row'}`
              }
            >
              <FileText size={10} className="flex-shrink-0 opacity-50" />
              <span className="flex-1 truncate">{room}</span>
              <span className="text-[10px] font-mono opacity-30">{count}</span>
            </NavLink>
          ))}
        </div>
      )}
    </div>
  )
}

export default function LeftSidebar({ width = 260 }: { width?: number }) {
  const navigate = useNavigate()
  const [vaultOpen, setVaultOpen] = useState(true)

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
      Object.values(b[1] as Record<string,number>).reduce((s, n) => s + n, 0) -
      Object.values(a[1] as Record<string,number>).reduce((s, n) => s + n, 0)
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
        <span style={{ fontSize: 14, lineHeight: 1 }}>🏛</span>
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
                onNavigate={navigate}
              />
            ))}
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
          style={{ background: status ? '#30d158' : '#666', boxShadow: status ? '0 0 6px #30d158' : 'none' }}
        />
        {status
          ? `${status.total_drawers.toLocaleString()} drawers · ${status.wing_count} wings`
          : 'Connecting…'}
      </div>
    </div>
  )
}
