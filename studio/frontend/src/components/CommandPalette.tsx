import { useState, useEffect, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  LayoutDashboard, Network, FolderOpen, Search,
  Bot, Plug, Settings, FileText, ArrowRight, Command,
} from 'lucide-react'
import { api } from '../api/client'

interface PaletteItem {
  id: string
  label: string
  sub?: string
  icon: React.ReactNode
  action: () => void
}

const NAV_ITEMS = (navigate: (p: string) => void): PaletteItem[] => [
  { id: 'nav-dashboard', label: 'Dashboard',       sub: 'Overview & stats',      icon: <LayoutDashboard size={14} />, action: () => navigate('/dashboard') },
  { id: 'nav-graph',     label: 'Graph',            sub: 'Wing Map & Knowledge Graph', icon: <Network size={14} />,         action: () => navigate('/graph') },
  { id: 'nav-browse',    label: 'Browse Drawers',   sub: 'All wings & rooms',     icon: <FolderOpen size={14} />,      action: () => navigate('/browse') },
  { id: 'nav-search',    label: 'Search',           sub: 'Full-text & semantic',  icon: <Search size={14} />,          action: () => navigate('/search') },
  { id: 'nav-agents',    label: 'Agents',           sub: 'Connected agents',      icon: <Bot size={14} />,             action: () => navigate('/agents') },
  { id: 'nav-connect',   label: 'Connect Agents',   sub: 'One-click MCP setup',   icon: <Plug size={14} />,            action: () => navigate('/connect') },
  { id: 'nav-settings',  label: 'Settings',         sub: 'LLM & backend config',  icon: <Settings size={14} />,        action: () => navigate('/settings') },
]

interface CommandPaletteProps {
  open: boolean
  onClose: () => void
}

export default function CommandPalette({ open, onClose }: CommandPaletteProps) {
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const [searchResults, setSearchResults] = useState<PaletteItem[]>([])
  const [selectedIndex, setSelectedIndex] = useState(0)
  const [searching, setSearching] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const searchTimer = useRef<ReturnType<typeof setTimeout>>()

  const navItems = NAV_ITEMS(navigate)

  // Reset state on open
  useEffect(() => {
    if (open) {
      setQuery('')
      setSearchResults([])
      setSelectedIndex(0)
      setTimeout(() => inputRef.current?.focus(), 50)
    }
  }, [open])

  // Semantic/text search
  useEffect(() => {
    clearTimeout(searchTimer.current)
    if (!query.trim()) {
      setSearchResults([])
      return
    }
    setSearching(true)
    searchTimer.current = setTimeout(async () => {
      try {
        const res = await api.search({ q: query, limit: 8 })
        const items: PaletteItem[] = (res.results ?? []).map((hit: any) => {
          const content = typeof hit.content === 'string' ? hit.content : ''
          const label = content
            ? content.slice(0, 60) + (content.length > 60 ? '…' : '')
            : hit.id
          return {
            id: `drawer-${hit.id}`,
            label,
            sub: `${hit.wing} / ${hit.room}`,
            icon: <FileText size={14} />,
            action: () => navigate(`/drawer/${encodeURIComponent(hit.id)}`),
          }
        })
        setSearchResults(items)
      } catch {
        setSearchResults([])
      } finally {
        setSearching(false)
      }
    }, 200)
  }, [query, navigate])

  const filteredNav = query.trim()
    ? navItems.filter(item =>
        item.label.toLowerCase().includes(query.toLowerCase()) ||
        (item.sub ?? '').toLowerCase().includes(query.toLowerCase())
      )
    : navItems

  const allItems = [...filteredNav, ...searchResults]

  const select = useCallback((item: PaletteItem) => {
    item.action()
    onClose()
  }, [onClose])

  // Keyboard navigation
  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { onClose(); return }
      if (e.key === 'ArrowDown') { e.preventDefault(); setSelectedIndex(i => Math.min(i + 1, allItems.length - 1)) }
      if (e.key === 'ArrowUp')   { e.preventDefault(); setSelectedIndex(i => Math.max(i - 1, 0)) }
      if (e.key === 'Enter' && allItems[selectedIndex]) { select(allItems[selectedIndex]) }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [open, allItems, selectedIndex, select, onClose])

  // Keep selection in range
  useEffect(() => {
    setSelectedIndex(0)
  }, [query])

  if (!open) return null

  return (
    <div className="prompt-overlay" onClick={onClose}>
      <div className="prompt-modal slide-down" onClick={e => e.stopPropagation()}>
        {/* Input */}
        <div className="prompt-input-wrap">
          <Command size={16} style={{ color: 'var(--text-faint)', flexShrink: 0 }} />
          <input
            ref={inputRef}
            className="prompt-input"
            placeholder="Type a command or search drawers…"
            value={query}
            onChange={e => setQuery(e.target.value)}
            spellCheck={false}
          />
          {searching && (
            <span className="text-[11px]" style={{ color: 'var(--text-faint)' }}>Searching…</span>
          )}
        </div>

        {/* Results */}
        <div className="prompt-results">
          {filteredNav.length > 0 && (
            <>
              <div className="prompt-section-header">Navigate</div>
              {filteredNav.map((item, i) => (
                <div
                  key={item.id}
                  className={`prompt-item ${i === selectedIndex ? 'selected' : ''}`}
                  onClick={() => select(item)}
                  onMouseEnter={() => setSelectedIndex(i)}
                >
                  <span className="prompt-item-icon">{item.icon}</span>
                  <span className="prompt-item-label">{item.label}</span>
                  {item.sub && <span className="prompt-item-sub">{item.sub}</span>}
                  <ArrowRight size={12} style={{ color: 'var(--text-faint)', opacity: i === selectedIndex ? 1 : 0 }} />
                </div>
              ))}
            </>
          )}

          {searchResults.length > 0 && (
            <>
              <div className="prompt-section-header">Drawers</div>
              {searchResults.map((item, i) => {
                const idx = filteredNav.length + i
                return (
                  <div
                    key={item.id}
                    className={`prompt-item ${idx === selectedIndex ? 'selected' : ''}`}
                    onClick={() => select(item)}
                    onMouseEnter={() => setSelectedIndex(idx)}
                  >
                    <span className="prompt-item-icon">{item.icon}</span>
                    <div className="prompt-item-label flex flex-col gap-0.5">
                      <span className="text-[13px]">{item.label}</span>
                      {item.sub && <span className="prompt-item-sub">{item.sub}</span>}
                    </div>
                    <ArrowRight size={12} style={{ color: 'var(--text-faint)', opacity: idx === selectedIndex ? 1 : 0 }} />
                  </div>
                )
              })}
            </>
          )}

          {query.trim() && !searching && filteredNav.length === 0 && searchResults.length === 0 && (
            <div className="px-3 py-6 text-center text-[13px]" style={{ color: 'var(--text-faint)' }}>
              No results for "{query}"
            </div>
          )}
        </div>

        {/* Footer hint */}
        <div
          className="px-4 py-2 border-t flex items-center gap-4 text-[11px]"
          style={{ borderColor: 'var(--background-modifier-border)', color: 'var(--text-faint)' }}
        >
          <span><kbd className="font-mono">↑↓</kbd> navigate</span>
          <span><kbd className="font-mono">↵</kbd> select</span>
          <span><kbd className="font-mono">Esc</kbd> close</span>
        </div>
      </div>
    </div>
  )
}
