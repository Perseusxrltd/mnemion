import { useState, useEffect, createContext, useContext } from 'react'
import { Outlet } from 'react-router-dom'
import Ribbon from './Ribbon'
import LeftSidebar from './LeftSidebar'
import StatusBar from './StatusBar'
import CommandPalette from './CommandPalette'

// ── Selected drawer context (for RightSidebar) ────────────────────────────────

interface LayoutCtx {
  selectedDrawerId: string | undefined
  setSelectedDrawerId: (id: string | undefined) => void
  openPalette: () => void
}

export const LayoutContext = createContext<LayoutCtx>({
  selectedDrawerId: undefined,
  setSelectedDrawerId: () => {},
  openPalette: () => {},
})

export function useLayoutCtx() {
  return useContext(LayoutContext)
}

// ── Layout ─────────────────────────────────────────────────────────────────────

export default function Layout() {
  const [paletteOpen, setPaletteOpen] = useState(false)
  const [selectedDrawerId, setSelectedDrawerId] = useState<string | undefined>(undefined)

  // Global Ctrl+K / Cmd+K
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault()
        setPaletteOpen(v => !v)
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])

  return (
    <LayoutContext.Provider value={{ selectedDrawerId, setSelectedDrawerId, openPalette: () => setPaletteOpen(true) }}>
      <div className="flex h-screen overflow-hidden" style={{ background: 'var(--background-primary)' }}>
        {/* Ribbon — leftmost 44px icon strip */}
        <Ribbon onSearch={() => setPaletteOpen(true)} />

        {/* Left sidebar — file explorer */}
        <LeftSidebar />

        {/* Center + optional right panel */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* Main content */}
          <main className="flex-1 overflow-hidden flex flex-col">
            <Outlet />
          </main>

          {/* Status bar */}
          <StatusBar />
        </div>
      </div>

      {/* Command palette overlay */}
      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
    </LayoutContext.Provider>
  )
}
