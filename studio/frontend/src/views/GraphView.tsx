import { useEffect, useRef, useState, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import { SigmaContainer, useLoadGraph, useRegisterEvents, useSigma } from '@react-sigma/core'
import Graph from 'graphology'
import forceAtlas2 from 'graphology-layout-forceatlas2'
import { Network, RefreshCw, X, Info, ZoomIn, ZoomOut, Maximize2, FolderOpen } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { wingColor } from '../types'

// ── Graph builders ─────────────────────────────────────────────────────────────

/** Log scale: compresses extreme values (5 → 29 608) into a usable range. */
function logSize(n: number, min: number, max: number): number {
  if (n <= 0) return min
  const scaled = Math.log1p(n) / Math.log1p(30000) // normalise to ~1
  return Math.max(min, Math.min(max, min + scaled * (max - min)))
}

function applyFA2(g: Graph, iterations: number) {
  try {
    forceAtlas2.assign(g, {
      iterations,
      settings: {
        gravity: 1,
        scalingRatio: 6,
        strongGravityMode: false,
        slowDown: 10,
        barnesHutOptimize: g.order > 80,
        barnesHutTheta: 0.5,
        linLogMode: false,
        outboundAttractionDistribution: false,
      },
    })
  } catch { /* keep random positions on error */ }
}

function buildWingGraph(taxonomy: Record<string, Record<string, number>>): Graph {
  const g = new Graph({ multi: false, type: 'undirected' })
  const wings = Object.entries(taxonomy)

  wings.forEach(([wing, rooms]) => {
    const total = Object.values(rooms as Record<string, number>).reduce((s, n) => s + n, 0)
    const color = wingColor(wing)
    const size = logSize(total, 14, 38)

    if (!g.hasNode(wing)) {
      g.addNode(wing, {
        label: wing,
        x: (Math.random() - 0.5) * 80,
        y: (Math.random() - 0.5) * 80,
        size,
        color,
        zIndex: 1,
        isWing: true,
      })
    }

    const roomList = Object.entries(rooms as Record<string, number>)
    roomList.forEach(([room, count]) => {
      const roomId = `${wing}/${room}`
      const rsize = logSize(count, 6, 18)

      if (!g.hasNode(roomId)) {
        g.addNode(roomId, {
          label: room,
          x: (Math.random() - 0.5) * 80,
          y: (Math.random() - 0.5) * 80,
          size: rsize,
          color: color + 'cc',
          zIndex: 0,
          isWing: false,
          wingName: wing,
        })
      }

      if (!g.hasEdge(wing, roomId)) {
        try { g.addEdge(wing, roomId, { size: 1.5, color: color + '50' }) } catch {}
      }
    })
  })

  return g
}

function buildKGGraph(nodes: any[], edges: any[]): Graph {
  const g = new Graph({ multi: false, type: 'mixed' })
  const TYPE_COLORS: Record<string, string> = {
    person: '#60A5FA', project: '#4ECDC4', tool: '#A78BFA',
    concept: '#10B981', place: '#F59E0B', event: '#EC4899',
  }

  for (const n of nodes) {
    if (!g.hasNode(n.id)) {
      g.addNode(n.id, {
        label: n.label,
        x: (Math.random() - 0.5) * 80,
        y: (Math.random() - 0.5) * 80,
        size: 5, // updated by degree below
        color: TYPE_COLORS[n.type] ?? '#9CA3AF',
        entityType: n.type, // renamed: 'type' is sigma-reserved for node renderer
      })
    }
  }
  for (const e of edges) {
    if (g.hasNode(e.source) && g.hasNode(e.target)) {
      try {
        g.addEdge(e.source, e.target, {
          label: e.label, size: 1, color: 'rgba(255,255,255,0.2)',
        })
      } catch {}
    }
  }

  // Degree-based node sizing
  g.forEachNode(node => {
    const deg = g.degree(node)
    const size = Math.max(5, Math.min(22, 5 + Math.sqrt(deg) * 2.5))
    g.setNodeAttribute(node, 'size', size)
  })

  return g
}

// ── Hover highlight (must live inside SigmaContainer) ────────────────────────

/** Dims all non-neighbour nodes/edges when hovering — Obsidian-style focus. */
function HoverHighlight() {
  const sigma = useSigma()
  const registerEvents = useRegisterEvents()

  useEffect(() => {
    registerEvents({
      enterNode: ({ node }) => {
        const graph = sigma.getGraph()
        const neighbors = new Set(graph.neighbors(node))
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        sigma.setSetting('nodeReducer', (n: string, data: any) => {
          if (n === node) return { ...data, highlighted: true, zIndex: 2 }
          if (neighbors.has(n)) return { ...data, zIndex: 1 }
          return { ...data, color: '#2a2a2a', label: undefined }
        })
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        sigma.setSetting('edgeReducer', (edge: string, data: any) => {
          const src = graph.source(edge)
          const tgt = graph.target(edge)
          if (src === node || tgt === node) {
            return { ...data, color: 'rgba(255,255,255,0.5)', size: (data.size ?? 1) * 2 }
          }
          return { ...data, color: 'rgba(100,100,100,0.04)' }
        })
      },
      leaveNode: () => {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        sigma.setSetting('nodeReducer', null as any)
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        sigma.setSetting('edgeReducer', null as any)
      },
    })
  }, [sigma, registerEvents])

  return null
}

// ── Camera connector (must live inside SigmaContainer) ────────────────────────

interface CameraAPI { zoomIn(): void; zoomOut(): void; fit(): void }

function CameraConnector({ apiRef }: { apiRef: React.MutableRefObject<CameraAPI | null> }) {
  const sigma = useSigma()
  useEffect(() => {
    apiRef.current = {
      zoomIn:  () => sigma.getCamera().animatedZoom({ duration: 180 }),
      zoomOut: () => sigma.getCamera().animatedUnzoom({ duration: 180 }),
      fit:     () => sigma.getCamera().animatedReset({ duration: 280 }),
    }
    return () => { apiRef.current = null }
  }, [sigma, apiRef])
  return null
}

// ── Wing info panel ────────────────────────────────────────────────────────────

interface WingSelection {
  id: string
  label: string
  isWing: boolean
  color: string
  total?: number
  rooms?: { name: string; count: number }[]
  wingName?: string
  roomCount?: number
}

// ── Wing graph loader ──────────────────────────────────────────────────────────

function WingMapLoader({
  graph,
  taxonomy,
  onSelect,
}: {
  graph: Graph
  taxonomy: Record<string, Record<string, number>>
  onSelect: (s: WingSelection | null) => void
}) {
  const loadGraph  = useLoadGraph()
  const registerEvents = useRegisterEvents()
  const sigma = useSigma()

  useEffect(() => { loadGraph(graph) }, [graph, loadGraph])

  useEffect(() => {
    registerEvents({
      clickNode: ({ node }) => {
        const attrs = sigma.getGraph().getNodeAttributes(node)
        const color = attrs.color?.replace(/cc$/, '') ?? '#7f6df2'
        if (attrs.isWing) {
          const rooms = taxonomy[attrs.label] ?? {}
          const sorted = Object.entries(rooms)
            .sort((a, b) => (b[1] as number) - (a[1] as number))
          onSelect({
            id: node,
            label: attrs.label,
            isWing: true,
            color,
            total: Object.values(rooms).reduce((s, n) => s + (n as number), 0),
            rooms: sorted.map(([name, count]) => ({ name, count: count as number })),
          })
        } else {
          const [wing, room] = node.split('/')
          const count = (taxonomy[wing] ?? {})[room] ?? 0
          onSelect({
            id: node,
            label: attrs.label,
            isWing: false,
            color,
            wingName: wing,
            roomCount: count,
          })
        }
      },
      clickStage: () => onSelect(null),
    })
  }, [registerEvents, sigma, taxonomy, onSelect])

  return null
}

// ── KG loader ─────────────────────────────────────────────────────────────────

interface KGSelection {
  id: string; label: string; type: string
  edges: { label: string; neighbor: string; direction: 'in' | 'out' }[]
}

function KGLoader({
  onSelect,
  onReady,
  onNodeCount,
}: {
  onSelect: (s: KGSelection | null) => void
  onReady: () => void
  onNodeCount: (n: number) => void
}) {
  const loadGraph      = useLoadGraph()
  const registerEvents = useRegisterEvents()
  const sigma = useSigma()

  const { data: kgData } = useQuery({
    queryKey: ['kg-graph'],
    queryFn:  () => api.kgGraph(1500),
    staleTime: 120_000,
  })

  useEffect(() => {
    if (!kgData) return
    try {
      const g = buildKGGraph(kgData.nodes ?? [], kgData.edges ?? [])
      onNodeCount(g.order)
      if (g.order > 1) applyFA2(g, 150)
      loadGraph(g)
    } catch (err) {
      console.error('[KGLoader] graph build error:', err)
      // Load empty graph so sigma doesn't stay blank
      try { loadGraph(new Graph({ type: 'mixed' })) } catch {}
    } finally {
      onReady()
    }
  }, [kgData, loadGraph, onReady, onNodeCount])

  useEffect(() => {
    registerEvents({
      clickNode: ({ node }) => {
        const g = sigma.getGraph()
        const attrs = g.getNodeAttributes(node)
        const edges = g.edges(node).map(e => {
          const src = g.source(e), tgt = g.target(e)
          const dir = src === node ? 'out' : 'in'
          const nb  = dir === 'out' ? tgt : src
          return {
            label: g.getEdgeAttribute(e, 'label') ?? '',
            neighbor: g.getNodeAttribute(nb, 'label') ?? nb,
            direction: dir as 'in' | 'out',
          }
        })
        onSelect({ id: node, label: attrs.label, type: attrs.entityType ?? 'entity', edges })
      },
      clickStage: () => onSelect(null),
    })
  }, [registerEvents, sigma, onSelect])

  return null
}

// ── Sigma settings ─────────────────────────────────────────────────────────────

const SIGMA_SETTINGS = {
  renderEdgeLabels: false,
  labelFont: 'Inter, -apple-system, sans-serif',
  labelSize: 12,
  labelWeight: '500',
  labelColor: { color: '#aaaaaa' },
  defaultNodeColor: '#7f6df2',
  defaultEdgeColor: 'rgba(255,255,255,0.15)',
  minCameraRatio: 0.008,
  maxCameraRatio: 20,
  enableEdgeEvents: false,
  labelRenderedSizeThreshold: 10,
}

// ── Camera controls (floating) ─────────────────────────────────────────────────

function CamBtn({ onClick, title, children }: { onClick(): void; title: string; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      title={title}
      style={{
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        width: 28, height: 28, borderRadius: 6,
        background: 'rgba(26,26,26,0.9)',
        border: '1px solid rgba(255,255,255,0.08)',
        color: '#888',
        cursor: 'pointer',
        transition: 'color 50ms, background 50ms',
      }}
      onMouseEnter={e => { e.currentTarget.style.color = '#ddd'; e.currentTarget.style.background = 'rgba(40,40,40,0.95)' }}
      onMouseLeave={e => { e.currentTarget.style.color = '#888'; e.currentTarget.style.background = 'rgba(26,26,26,0.9)' }}
    >
      {children}
    </button>
  )
}

// ── Main component ─────────────────────────────────────────────────────────────

export default function GraphView() {
  const navigate = useNavigate()
  const [mode, setMode] = useState<'wings' | 'kg'>('wings')
  const [wingSelection, setWingSelection] = useState<WingSelection | null>(null)
  const [kgSelection, setKgSelection] = useState<KGSelection | null>(null)
  const [kgReady, setKgReady]       = useState(false)
  const [kgNodeCount, setKgNodeCount] = useState(0)
  const [wingReady, setWingReady]   = useState(false)
  const cameraRef = useRef<CameraAPI | null>(null)

  const { data: taxonomy } = useQuery({ queryKey: ['taxonomy'], queryFn: api.taxonomy })

  const taxonomyMap = taxonomy?.taxonomy ?? {} as Record<string, Record<string, number>>

  const [resolvedWingGraph, setResolvedWingGraph] = useState<Graph | null>(null)

  useEffect(() => {
    if (!taxonomy?.taxonomy) return
    setWingReady(false)
    const g = buildWingGraph(taxonomy.taxonomy)
    applyFA2(g, 150)
    setResolvedWingGraph(g)
    setWingReady(true)
  }, [taxonomy])

  const handleKgReady     = useCallback(() => setKgReady(true), [])
  const handleKgNodeCount = useCallback((n: number) => setKgNodeCount(n), [])
  const handleWingSelect  = useCallback((s: WingSelection | null) => setWingSelection(s), [])
  const handleKgSelect    = useCallback((s: KGSelection | null) => setKgSelection(s), [])

  const wingCount = Object.keys(taxonomyMap).length
  const roomCount = Object.values(taxonomyMap).reduce((s, r) => s + Object.keys(r as any).length, 0)

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* Toolbar */}
      <div
        className="flex items-center gap-3 px-4 py-2.5 border-b flex-shrink-0"
        style={{ borderColor: 'var(--background-modifier-border)', background: 'var(--background-secondary)', minHeight: 44 }}
      >
        <Network size={14} style={{ color: 'var(--interactive-accent)', flexShrink: 0 }} />
        <span className="font-medium text-sm">Memory Graph</span>

        {/* Mode switcher */}
        <div className="flex gap-0.5 ml-3 p-0.5 rounded-lg" style={{ background: 'var(--interactive-normal)' }}>
          {(['wings', 'kg'] as const).map(m => (
            <button
              key={m}
              onClick={() => {
              setMode(m)
              setWingSelection(null)
              setKgSelection(null)
              if (m === 'kg') { setKgReady(false); setKgNodeCount(0) }
            }}
              className="px-3 py-1 rounded text-xs font-medium transition-colors"
              style={
                mode === m
                  ? { background: 'var(--interactive-accent)', color: 'white' }
                  : { color: 'var(--text-muted)' }
              }
              onMouseEnter={e => { if (mode !== m) e.currentTarget.style.color = 'var(--text-normal)' }}
              onMouseLeave={e => { if (mode !== m) e.currentTarget.style.color = 'var(--text-muted)' }}
            >
              {m === 'wings' ? 'Wing Map' : 'Knowledge Graph'}
            </button>
          ))}
        </div>

        {/* Loading indicator */}
        {((mode === 'wings' && !wingReady) || (mode === 'kg' && !kgReady)) && (
          <span className="flex items-center gap-1.5 text-xs ml-2" style={{ color: 'var(--text-muted)' }}>
            <RefreshCw size={11} className="animate-spin" />
            {mode === 'wings' ? 'Computing layout…' : 'Building graph…'}
          </span>
        )}

        <div className="ml-auto text-xs font-mono" style={{ color: 'var(--text-faint)' }}>
          {mode === 'wings'
            ? wingReady ? `${wingCount} wings · ${roomCount} rooms` : '—'
            : kgNodeCount > 0 ? `${kgNodeCount} entities` : 'KG empty'
          }
        </div>
      </div>

      {/* Graph area */}
      <div className="flex-1 relative overflow-hidden">

        {/* Wing Map */}
        {mode === 'wings' && resolvedWingGraph && (
          <SigmaContainer
            key="wings"
            style={{ position: 'absolute', inset: 0, background: '#111111' }}
            settings={SIGMA_SETTINGS}
          >
            <WingMapLoader
              graph={resolvedWingGraph}
              taxonomy={taxonomyMap}
              onSelect={handleWingSelect}
            />
            <HoverHighlight />
            <CameraConnector apiRef={cameraRef} />
          </SigmaContainer>
        )}

        {/* KG */}
        {mode === 'kg' && (
          <SigmaContainer
            key="kg"
            style={{ position: 'absolute', inset: 0, background: '#111111' }}
            settings={SIGMA_SETTINGS}
          >
            <KGLoader onSelect={handleKgSelect} onReady={handleKgReady} onNodeCount={handleKgNodeCount} />
            <HoverHighlight />
            <CameraConnector apiRef={cameraRef} />
          </SigmaContainer>
        )}

        {/* Building skeleton while FA2 runs */}
        {mode === 'wings' && !resolvedWingGraph && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-3" style={{ background: '#111' }}>
            <RefreshCw size={22} className="animate-spin" style={{ color: '#7f6df2' }} />
            <span className="text-sm" style={{ color: 'var(--text-muted)' }}>Computing force layout…</span>
          </div>
        )}

        {/* Empty KG state */}
        {mode === 'kg' && kgReady && kgNodeCount === 0 && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 pointer-events-none"
            style={{ background: '#111' }}>
            <Info size={28} style={{ color: 'var(--text-faint)' }} />
            <div className="text-sm" style={{ color: 'var(--text-muted)' }}>Knowledge Graph is empty</div>
            <div className="text-xs text-center max-w-xs" style={{ color: 'var(--text-faint)', lineHeight: 1.6 }}>
              Run <code style={{ background: 'rgba(127,109,242,0.15)', color: '#9d8ff9', borderRadius: 3, padding: '1px 5px' }}>mnemion librarian</code> to extract
              entity relationships from your drawers. Entities, people, projects and concepts will appear here as a connected graph.
            </div>
          </div>
        )}

        {/* ── Camera controls ── */}
        <div
          className="absolute flex flex-col gap-1"
          style={{ bottom: 16, right: 16, zIndex: 10 }}
        >
          <CamBtn onClick={() => cameraRef.current?.zoomIn()} title="Zoom in">
            <ZoomIn size={13} />
          </CamBtn>
          <CamBtn onClick={() => cameraRef.current?.zoomOut()} title="Zoom out">
            <ZoomOut size={13} />
          </CamBtn>
          <CamBtn onClick={() => cameraRef.current?.fit()} title="Fit to screen">
            <Maximize2 size={13} />
          </CamBtn>
        </div>

        {/* ── Wing Map legend ── */}
        {mode === 'wings' && resolvedWingGraph && (
          <div
            className="absolute bottom-4 left-4 p-3 rounded-xl"
            style={{
              background: 'rgba(17,17,17,0.88)',
              border: '1px solid rgba(255,255,255,0.07)',
              backdropFilter: 'blur(10px)',
              maxWidth: 220,
              zIndex: 10,
            }}
          >
            <div className="text-[10px] font-semibold uppercase tracking-wider mb-2" style={{ color: 'var(--text-faint)' }}>
              Wings
            </div>
            <div className="flex flex-wrap gap-x-3 gap-y-1.5">
              {Object.entries(taxonomyMap)
                .sort((a, b) => Object.values(b[1] as any).reduce((s:any,n:any)=>s+n,0) as number - (Object.values(a[1] as any).reduce((s:any,n:any)=>s+n,0) as number))
                .slice(0, 10)
                .map(([wing]) => (
                  <span key={wing} className="flex items-center gap-1 text-[10px]">
                    <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: wingColor(wing) }} />
                    <span style={{ color: wingColor(wing) }}>{wing}</span>
                  </span>
                ))}
            </div>
            <div className="mt-2 text-[10px]" style={{ color: 'var(--text-faint)', borderTop: '1px solid rgba(255,255,255,0.05)', paddingTop: 6 }}>
              Node size = drawer count · Click to inspect
            </div>
          </div>
        )}

        {/* ── KG legend ── */}
        {mode === 'kg' && kgReady && kgNodeCount > 0 && (
          <div
            className="absolute bottom-4 left-4 p-3 rounded-xl"
            style={{
              background: 'rgba(17,17,17,0.88)',
              border: '1px solid rgba(255,255,255,0.07)',
              backdropFilter: 'blur(10px)',
              maxWidth: 200,
              zIndex: 10,
            }}
          >
            <div className="text-[10px] font-semibold uppercase tracking-wider mb-2" style={{ color: 'var(--text-faint)' }}>
              Entity types
            </div>
            <div className="flex flex-wrap gap-x-3 gap-y-1.5">
              {[['person','#60A5FA'],['project','#4ECDC4'],['tool','#A78BFA'],['concept','#10B981'],['place','#F59E0B'],['event','#EC4899']].map(([t,c]) => (
                <span key={t} className="flex items-center gap-1 text-[10px]">
                  <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: c }} />
                  <span style={{ color: 'var(--text-muted)' }} className="capitalize">{t}</span>
                </span>
              ))}
            </div>
            <div className="mt-2 text-[10px]" style={{ color: 'var(--text-faint)', borderTop: '1px solid rgba(255,255,255,0.05)', paddingTop: 6 }}>
              Node size = connection count
            </div>
          </div>
        )}

        {/* ── Wing selection panel ── */}
        {wingSelection && (
          <div
            className="absolute top-4 right-4 rounded-xl fade-in"
            style={{
              width: 240,
              background: 'rgba(22,22,22,0.97)',
              border: '1px solid rgba(255,255,255,0.08)',
              backdropFilter: 'blur(16px)',
              boxShadow: '0 16px 40px rgba(0,0,0,0.5)',
              zIndex: 20,
              overflow: 'hidden',
            }}
          >
            {/* Header */}
            <div className="flex items-start justify-between p-4 pb-3"
              style={{ borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
              <div>
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                    style={{ background: wingSelection.color }} />
                  <span className="font-semibold text-sm">{wingSelection.label}</span>
                </div>
                <div className="text-[11px] mt-1" style={{ color: 'var(--text-muted)' }}>
                  {wingSelection.isWing
                    ? `${wingSelection.total?.toLocaleString()} drawers · ${wingSelection.rooms?.length} rooms`
                    : `${wingSelection.roomCount?.toLocaleString()} drawers in ${wingSelection.wingName}`
                  }
                </div>
              </div>
              <button
                onClick={() => setWingSelection(null)}
                style={{ color: 'var(--text-faint)', padding: 2, borderRadius: 4 }}
                onMouseEnter={e => (e.currentTarget.style.color = 'var(--text-normal)')}
                onMouseLeave={e => (e.currentTarget.style.color = 'var(--text-faint)')}
              >
                <X size={13} />
              </button>
            </div>

            {/* Room list */}
            {wingSelection.isWing && wingSelection.rooms && (
              <div style={{ maxHeight: 220, overflowY: 'auto' }}>
                {wingSelection.rooms.map(r => (
                  <button
                    key={r.name}
                    onClick={() => navigate(`/browse/${wingSelection.label}/${r.name}`)}
                    className="flex items-center justify-between w-full px-4 py-2 text-left text-[12px] transition-colors"
                    style={{ color: 'var(--text-muted)' }}
                    onMouseEnter={e => {
                      e.currentTarget.style.background = 'rgba(255,255,255,0.04)'
                      e.currentTarget.style.color = 'var(--text-normal)'
                    }}
                    onMouseLeave={e => {
                      e.currentTarget.style.background = 'transparent'
                      e.currentTarget.style.color = 'var(--text-muted)'
                    }}
                  >
                    <span className="flex items-center gap-2">
                      <FolderOpen size={11} style={{ color: wingSelection.color, opacity: 0.7, flexShrink: 0 }} />
                      {r.name}
                    </span>
                    <span className="font-mono text-[10px]" style={{ color: 'var(--text-faint)' }}>
                      {r.count.toLocaleString()}
                    </span>
                  </button>
                ))}
              </div>
            )}

            {/* Browse link */}
            <div className="p-3 pt-2" style={{ borderTop: '1px solid rgba(255,255,255,0.06)' }}>
              <button
                onClick={() => navigate(
                  wingSelection.isWing
                    ? `/browse/${wingSelection.label}`
                    : `/browse/${wingSelection.wingName}/${wingSelection.label}`
                )}
                className="flex items-center gap-1.5 w-full px-3 py-1.5 rounded-lg text-[11px] font-medium justify-center transition-colors"
                style={{ background: 'rgba(127,109,242,0.15)', color: '#9d8ff9' }}
                onMouseEnter={e => (e.currentTarget.style.background = 'rgba(127,109,242,0.25)')}
                onMouseLeave={e => (e.currentTarget.style.background = 'rgba(127,109,242,0.15)')}
              >
                <FolderOpen size={11} /> Browse drawers
              </button>
            </div>
          </div>
        )}

        {/* ── KG selection panel ── */}
        {kgSelection && (
          <div
            className="absolute top-4 right-4 w-60 rounded-xl p-4 fade-in"
            style={{
              background: 'rgba(22,22,22,0.97)',
              border: '1px solid rgba(255,255,255,0.08)',
              backdropFilter: 'blur(16px)',
              boxShadow: '0 16px 40px rgba(0,0,0,0.5)',
              zIndex: 20,
            }}
          >
            <div className="flex items-start justify-between mb-3">
              <div>
                <div className="font-semibold text-sm">{kgSelection.label}</div>
                <div className="text-xs mt-0.5" style={{ color: 'var(--interactive-accent)' }}>{kgSelection.type}</div>
              </div>
              <button
                onClick={() => setKgSelection(null)}
                style={{ color: 'var(--text-faint)', padding: 2, borderRadius: 4 }}
                onMouseEnter={e => (e.currentTarget.style.color = 'var(--text-normal)')}
                onMouseLeave={e => (e.currentTarget.style.color = 'var(--text-faint)')}
              >
                <X size={13} />
              </button>
            </div>
            <div style={{ maxHeight: 200, overflowY: 'auto' }} className="space-y-1.5">
              {kgSelection.edges.slice(0, 15).map((e, i) => (
                <div key={i} className="flex items-start gap-2 text-[12px]">
                  <span className="flex-shrink-0 font-mono w-3" style={{ color: 'var(--text-faint)' }}>
                    {e.direction === 'out' ? '→' : '←'}
                  </span>
                  <span className="italic flex-shrink-0" style={{ color: 'var(--interactive-accent)', opacity: 0.8 }}>
                    {e.label}
                  </span>
                  <span className="break-words" style={{ color: 'rgba(220,221,222,0.75)' }}>{e.neighbor}</span>
                </div>
              ))}
              {kgSelection.edges.length === 0 && (
                <div className="text-xs" style={{ color: 'var(--text-muted)' }}>No relations found</div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
