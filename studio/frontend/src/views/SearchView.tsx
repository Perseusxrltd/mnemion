import { useState, useEffect, useRef } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Search, X, SlidersHorizontal, Clock, FileText, AlertTriangle } from 'lucide-react'
import { api } from '../api/client'
import type { SearchHit } from '../types'
import WingBadge from '../components/WingBadge'

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function highlight(text: string, query: string): string {
  const safe = escapeHtml(text)
  if (!query.trim()) return safe
  const escapedQ = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  return safe.replace(new RegExp(`(${escapeHtml(escapedQ)})`, 'gi'), '<mark>$1</mark>')
}

/** Parse inline operators from the raw query string. */
function parseQuery(raw: string): { q: string; parsedWing: string; parsedRoom: string } {
  let q = raw
  let parsedWing = ''
  let parsedRoom = ''
  q = q.replace(/\bwing:(\S+)/gi, (_, w) => { parsedWing = w; return '' })
  q = q.replace(/\broom:(\S+)/gi, (_, r) => { parsedRoom = r; return '' })
  return { q: q.trim(), parsedWing, parsedRoom }
}

export default function SearchView() {
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()
  const [q, setQ] = useState(params.get('q') ?? '')
  const [results, setResults] = useState<SearchHit[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [showFilters, setShowFilters] = useState(false)
  const [wingFilter, setWingFilter] = useState('')
  const [history, setHistory] = useState<string[]>(() => {
    try { return JSON.parse(localStorage.getItem('mnemion_search_history') ?? '[]') } catch { return [] }
  })
  const timerRef = useRef<ReturnType<typeof setTimeout>>()

  useEffect(() => {
    const initial = params.get('q')
    if (initial) { setQ(initial); doSearch(initial) }
  }, [])

  async function doSearch(query: string) {
    const { q: parsedQ, parsedWing, parsedRoom } = parseQuery(query)
    const effectiveWing = parsedWing || wingFilter
    // Auto-surface the parsed wing filter in the UI
    if (parsedWing) { setWingFilter(parsedWing); setShowFilters(true) }

    if (!parsedQ) { setResults([]); return }
    setLoading(true); setError('')
    try {
      const res = await api.search({
        q: parsedQ,
        wing: effectiveWing || undefined,
        room: parsedRoom || undefined,
        limit: 30,
      })
      setResults(res.results)
      const updated = [query, ...history.filter(h => h !== query)].slice(0, 10)
      setHistory(updated)
      localStorage.setItem('mnemion_search_history', JSON.stringify(updated))
      setParams({ q: query }, { replace: true })
    } catch (e: any) {
      setError(e.message ?? 'Search failed')
    } finally {
      setLoading(false)
    }
  }

  function onChange(v: string) {
    setQ(v)
    clearTimeout(timerRef.current)
    timerRef.current = setTimeout(() => doSearch(v), 300)
  }

  function clearHistory() {
    setHistory([])
    localStorage.removeItem('mnemion_search_history')
  }

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* Search bar */}
      <div
        className="px-6 pt-5 pb-4 border-b"
        style={{ borderColor: 'var(--background-modifier-border)', background: 'var(--background-secondary)' }}
      >
        <div className="flex items-center gap-3 max-w-2xl">
          <div className="flex-1 relative">
            <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" style={{ color: 'var(--text-faint)' }} />
            <input
              autoFocus
              value={q}
              onChange={e => onChange(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && doSearch(q)}
              placeholder="Search across all drawers…"
              className="w-full rounded-lg py-2.5 pl-9 pr-10 text-sm outline-none transition-colors"
              style={{
                background: 'var(--background-modifier-form-field)',
                border: '1px solid var(--background-modifier-border)',
                color: 'var(--text-normal)',
              }}
              onFocus={e => (e.target.style.borderColor = 'var(--interactive-accent)')}
              onBlur={e => (e.target.style.borderColor = 'var(--background-modifier-border)')}
            />
            {q && (
              <button
                onClick={() => { setQ(''); setResults([]) }}
                className="absolute right-3 top-1/2 -translate-y-1/2 transition-colors"
                style={{ color: 'var(--text-faint)' }}
                onMouseEnter={e => (e.currentTarget.style.color = 'var(--text-normal)')}
                onMouseLeave={e => (e.currentTarget.style.color = 'var(--text-faint)')}
              >
                <X size={13} />
              </button>
            )}
          </div>
          <button
            onClick={() => setShowFilters(v => !v)}
            className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm transition-colors"
            style={{
              color: showFilters ? 'var(--interactive-accent)' : 'var(--text-muted)',
              background: showFilters ? 'rgba(127,109,242,0.1)' : 'transparent',
              border: `1px solid ${showFilters ? 'rgba(127,109,242,0.3)' : 'var(--background-modifier-border)'}`,
            }}
          >
            <SlidersHorizontal size={13} /> Filters
          </button>
        </div>

        {showFilters && (
          <div className="flex items-center gap-3 mt-3 max-w-2xl">
            <input
              value={wingFilter}
              onChange={e => setWingFilter(e.target.value)}
              placeholder="Filter by wing (e.g. legal)"
              className="px-3 py-1.5 rounded-lg text-xs outline-none transition-colors"
              style={{
                background: 'var(--background-modifier-form-field)',
                border: '1px solid var(--background-modifier-border)',
                color: 'var(--text-normal)',
                width: 220,
              }}
              onFocus={e => (e.target.style.borderColor = 'var(--interactive-accent)')}
              onBlur={e => (e.target.style.borderColor = 'var(--background-modifier-border)')}
            />
            {wingFilter && (
              <button
                onClick={() => setWingFilter('')}
                className="text-xs transition-colors"
                style={{ color: 'var(--text-muted)' }}
                onMouseEnter={e => (e.currentTarget.style.color = 'var(--text-normal)')}
                onMouseLeave={e => (e.currentTarget.style.color = 'var(--text-muted)')}
              >
                Clear
              </button>
            )}
          </div>
        )}
      </div>

      <div className="flex-1 overflow-y-auto">
        {/* No query — show history */}
        {!q && history.length > 0 && (
          <div className="px-6 py-4">
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs font-medium text-muted uppercase tracking-wider">Recent searches</span>
              <button onClick={clearHistory} className="text-xs text-muted hover:text-white transition-colors">Clear</button>
            </div>
            <div className="space-y-1">
              {history.map(h => (
                <button key={h} onClick={() => { setQ(h); doSearch(h) }}
                  className="flex items-center gap-2 w-full px-3 py-2 rounded-lg text-sm text-muted hover:text-white hover:bg-white/5 transition-colors text-left">
                  <Clock size={12} className="flex-shrink-0" />
                  {h}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Loading */}
        {loading && (
          <div className="flex items-center justify-center py-12 text-sm text-muted">Searching…</div>
        )}

        {/* Error */}
        {error && (
          <div className="mx-6 mt-4 px-4 py-3 rounded-lg text-sm text-red-400 bg-red-400/10 border border-red-400/20">
            {error}
          </div>
        )}

        {/* Results */}
        {!loading && results.length > 0 && (
          <div>
            <div className="px-6 py-2 text-xs text-muted border-b" style={{ borderColor: 'var(--border)' }}>
              {results.length} results for <span className="text-white font-medium">"{q}"</span>
            </div>
            {results.map(hit => {
              const sim = hit.similarity ?? hit.score ?? 0
              const simPct = Math.round(sim * 100)
              const preview = (hit.content ?? '').slice(0, 400)
              const { q: parsedQ } = parseQuery(q)
              const contested = hit.trust_status === 'contested'
              return (
                <button
                  key={hit.id}
                  className="flex items-start gap-4 w-full px-6 py-4 border-b hover-row text-left transition-colors"
                  style={{ borderColor: 'var(--border)' }}
                  onClick={() => navigate(`/drawer/${encodeURIComponent(hit.id)}`)}
                >
                  <FileText size={14} className="text-muted flex-shrink-0 mt-1" />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1.5 flex-wrap">
                      <WingBadge wing={hit.wing} room={hit.room} />
                      {simPct > 0 && (
                        <span className="text-[10px] font-mono px-1.5 py-0.5 rounded"
                          style={{ background: 'rgba(124,106,247,0.12)', color: '#9d8ff9' }}>
                          {simPct}%
                        </span>
                      )}
                      {contested && (
                        <span className="flex items-center gap-0.5 text-[10px] px-1.5 py-0.5 rounded"
                          style={{ background: 'rgba(249,115,22,0.12)', color: '#f97316' }}>
                          <AlertTriangle size={9} /> contested
                        </span>
                      )}
                    </div>
                    <p
                      className="text-sm text-white/75 leading-relaxed line-clamp-3"
                      dangerouslySetInnerHTML={{ __html: highlight(preview, parsedQ) }}
                    />
                  </div>
                </button>
              )
            })}
          </div>
        )}

        {/* Empty */}
        {!loading && q && results.length === 0 && !error && (
          <div className="flex flex-col items-center justify-center py-16 gap-3">
            <Search size={28} style={{ color: 'var(--text-faint)' }} />
            <div className="text-sm" style={{ color: 'var(--text-muted)' }}>No results for "{q}"</div>
            <div className="text-xs" style={{ color: 'var(--text-faint)' }}>Try a different query or clear wing filters</div>
          </div>
        )}

        {/* No query, no history */}
        {!q && history.length === 0 && (
          <div className="flex flex-col items-center justify-center py-16 gap-3">
            <Search size={28} style={{ color: 'var(--text-faint)' }} />
            <div className="text-sm" style={{ color: 'var(--text-muted)' }}>Search across all drawers</div>
            <div className="text-xs" style={{ color: 'var(--text-faint)' }}>
              Hybrid semantic + keyword — try a concept, phrase, or topic
            </div>
          </div>
        )}
      </div>

    </div>
  )
}
