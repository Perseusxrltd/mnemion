import { useState, useEffect, useRef, createContext, useContext, useCallback } from 'react'
import { Outlet, useNavigate } from 'react-router-dom'
import Ribbon from './Ribbon'
import LeftSidebar from './LeftSidebar'
import StatusBar from './StatusBar'
import CommandPalette from './CommandPalette'
import ShortcutModal from './ShortcutModal'
import DrawerCreateModal from './DrawerCreateModal'
import ToastProvider from './ToastProvider'
import ErrorBoundary from './ErrorBoundary'

// ── Layout context ─────────────────────────────────────────────────────────────

interface LayoutCtx {
  openPalette: () => void
  openCreateDrawer: (defaultWing?: string) => void
}

export const LayoutContext = createContext<LayoutCtx>({
  openPalette: () => {},
  openCreateDrawer: () => {},
})
export const useLayoutCtx = () => useContext(LayoutContext)

// ── Helper ─────────────────────────────────────────────────────────────────────

function isTyping(): boolean {
  const el = document.activeElement
  if (!el) return false
  const tag = (el as HTMLElement).tagName
  return (
    tag === 'INPUT' ||
    tag === 'TEXTAREA' ||
    tag === 'SELECT' ||
    (el as HTMLElement).isContentEditable
  )
}

// ── Layout ─────────────────────────────────────────────────────────────────────

export default function Layout() {
  const navigate = useNavigate()
  const [paletteOpen, setPaletteOpen] = useState(false)
  const [shortcutsOpen, setShortcutsOpen] = useState(false)
  const [createOpen, setCreateOpen] = useState(false)
  const [createDefaultWing, setCreateDefaultWing] = useState('')

  // G-prefix sequence tracking
  const gActiveRef = useRef(false)
  const gTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const openCreateDrawer = useCallback((defaultWing = '') => {
    setCreateDefaultWing(defaultWing)
    setCreateOpen(true)
  }, [])

  const anyModalOpen = paletteOpen || shortcutsOpen || createOpen

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      // ── Ctrl+K: command palette (always) ──
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault()
        setPaletteOpen(v => !v)
        return
      }

      // ── Block single-key shortcuts when typing or modal open ──
      if (isTyping()) return

      // ── Escape closes any open modal ──
      if (e.key === 'Escape') {
        if (shortcutsOpen) { setShortcutsOpen(false); return }
        if (createOpen)    { setCreateOpen(false);    return }
        if (paletteOpen)   { setPaletteOpen(false);   return }
        return
      }

      // Don't fire shortcuts when any modal is open
      if (anyModalOpen) return

      // ── '?': keyboard shortcuts ──
      if (e.key === '?') {
        setShortcutsOpen(true)
        return
      }

      // ── 'C': new drawer ──
      if (e.key === 'c' || e.key === 'C') {
        openCreateDrawer()
        return
      }

      // ── 'G' prefix: navigation sequences ──
      if (e.key === 'g' || e.key === 'G') {
        if (gActiveRef.current) {
          // Double-G → graph
          if (gTimerRef.current) clearTimeout(gTimerRef.current)
          gActiveRef.current = false
          navigate('/graph')
          return
        }
        gActiveRef.current = true
        gTimerRef.current = setTimeout(() => { gActiveRef.current = false }, 800)
        return
      }

      if (gActiveRef.current) {
        if (gTimerRef.current) clearTimeout(gTimerRef.current)
        gActiveRef.current = false
        const k = e.key.toLowerCase()
        if (k === 'd') navigate('/')
        else if (k === 'b') navigate('/browse')
        else if (k === 's') navigate('/search')
        else if (k === 'a') navigate('/agents')
        else if (k === 'c') navigate('/connect')
        return
      }
    }

    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [navigate, anyModalOpen, paletteOpen, shortcutsOpen, createOpen, openCreateDrawer])

  const ctx: LayoutCtx = {
    openPalette: () => setPaletteOpen(true),
    openCreateDrawer,
  }

  return (
    <ToastProvider>
      <LayoutContext.Provider value={ctx}>
        <div
          className="flex h-screen overflow-hidden"
          style={{ background: 'var(--background-primary)' }}
        >
          {/* Ribbon — 44px leftmost icon strip */}
          <Ribbon />

          {/* Left sidebar — file explorer */}
          <LeftSidebar />

          {/* Main content column */}
          <div className="flex-1 flex flex-col overflow-hidden min-w-0">
            <main className="flex-1 overflow-hidden flex flex-col">
              <ErrorBoundary>
                <Outlet />
              </ErrorBoundary>
            </main>
            <StatusBar />
          </div>
        </div>

        {/* Global overlays */}
        <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
        <ShortcutModal open={shortcutsOpen} onClose={() => setShortcutsOpen(false)} />
        <DrawerCreateModal
          open={createOpen}
          defaultWing={createDefaultWing}
          onClose={() => setCreateOpen(false)}
          onCreated={id => { if (id) navigate(`/drawer/${encodeURIComponent(id)}`) }}
        />
      </LayoutContext.Provider>
    </ToastProvider>
  )
}
