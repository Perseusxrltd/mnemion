import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Plug, CheckCircle, AlertTriangle, RefreshCw, ExternalLink,
  Copy, Check, Terminal, Monitor, Code2, Trash2, Plus,
} from 'lucide-react'
import { api } from '../api/client'
import type { ConnectorStatus } from '../types'
import { useToast } from '../components/ToastProvider'

// ── Vendor → accent colour ────────────────────────────────────────────────────

const VENDOR_COLOR: Record<string, string> = {
  Anthropic: '#c96442',
  OpenAI:    '#10a37f',
  Google:    '#4285f4',
  Cursor:    '#7f6df2',
  Codeium:   '#09b6a2',
  'Zed Industries': '#ef4444',
}

function vendorColor(vendor: string): string {
  return VENDOR_COLOR[vendor] ?? '#7f6df2'
}

function CategoryIcon({ cat, size = 11 }: { cat: string; size?: number }) {
  if (cat === 'cli') return <Terminal size={size} />
  if (cat === 'app') return <Monitor size={size} />
  return <Code2 size={size} />
}

// ── Copy button ───────────────────────────────────────────────────────────────

function CopyButton({ text, label = 'Copy' }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <button
      onClick={() => {
        navigator.clipboard.writeText(text)
        setCopied(true)
        setTimeout(() => setCopied(false), 1500)
      }}
      className="flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-medium transition-colors"
      style={{
        background: copied ? 'rgba(48,209,88,0.15)' : 'rgba(255,255,255,0.04)',
        color: copied ? '#30d158' : 'var(--text-muted)',
        border: `1px solid ${copied ? 'rgba(48,209,88,0.3)' : 'var(--background-modifier-border)'}`,
      }}
    >
      {copied ? <Check size={11} /> : <Copy size={11} />}
      {copied ? 'Copied' : label}
    </button>
  )
}

// ── Connector card ────────────────────────────────────────────────────────────

function StatusBadge({ conn }: { conn: ConnectorStatus }) {
  if (!conn.installed) {
    return (
      <span className="flex items-center gap-1 text-[10px] font-medium px-1.5 py-0.5 rounded" style={{ color: 'var(--text-faint)', background: 'rgba(255,255,255,0.04)' }}>
        Not installed
      </span>
    )
  }
  if (conn.mnemion_configured) {
    return (
      <span className="flex items-center gap-1 text-[10px] font-medium px-1.5 py-0.5 rounded" style={{ color: '#30d158', background: 'rgba(48,209,88,0.12)' }}>
        <CheckCircle size={9} /> Connected
      </span>
    )
  }
  if (conn.legacy_detected) {
    return (
      <span className="flex items-center gap-1 text-[10px] font-medium px-1.5 py-0.5 rounded" style={{ color: '#f97316', background: 'rgba(249,115,22,0.12)' }}>
        <AlertTriangle size={9} /> Legacy (mempalace)
      </span>
    )
  }
  return (
    <span className="flex items-center gap-1 text-[10px] font-medium px-1.5 py-0.5 rounded" style={{ color: 'var(--text-muted)', background: 'rgba(255,255,255,0.04)' }}>
      Available
    </span>
  )
}

function ConnectorCard({
  conn,
  snippet,
  onInstall,
  onUninstall,
  busy,
}: {
  conn: ConnectorStatus
  snippet?: string
  onInstall: () => void
  onUninstall: () => void
  busy: boolean
}) {
  const [expanded, setExpanded] = useState(false)
  const color = vendorColor(conn.vendor)

  return (
    <div
      className="rounded-xl overflow-hidden fade-in transition-all"
      style={{
        background: 'var(--surface)',
        border: `1px solid ${conn.mnemion_configured ? 'rgba(48,209,88,0.2)' : 'var(--background-modifier-border)'}`,
      }}
    >
      {/* Header */}
      <div className="flex items-start gap-3 p-4">
        <div
          className="w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0"
          style={{ background: color + '20', color }}
        >
          <CategoryIcon cat={conn.category} size={16} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-semibold text-sm">{conn.name}</span>
            <span className="text-[10px] uppercase tracking-wider font-mono" style={{ color: 'var(--text-faint)' }}>
              {conn.vendor}
            </span>
            <StatusBadge conn={conn} />
          </div>
          <p className="text-xs mt-0.5 leading-snug" style={{ color: 'var(--text-muted)' }}>
            {conn.description}
          </p>
          {conn.other_mcp_servers.length > 0 && (
            <div className="text-[10px] mt-1" style={{ color: 'var(--text-faint)' }}>
              Alongside: <span className="font-mono">{conn.other_mcp_servers.join(', ')}</span>
            </div>
          )}
        </div>
      </div>

      {/* Actions */}
      <div
        className="flex items-center justify-between px-4 py-2.5 gap-2 flex-wrap"
        style={{ borderTop: '1px solid var(--background-modifier-border)', background: 'var(--raised)' }}
      >
        <div className="flex items-center gap-2">
          {conn.mnemion_configured ? (
            <button
              onClick={onUninstall}
              disabled={busy}
              className="flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-medium transition-colors disabled:opacity-40"
              style={{ background: 'rgba(255,69,58,0.1)', color: '#ff6b6b', border: '1px solid rgba(255,69,58,0.2)' }}
            >
              <Trash2 size={11} /> Remove
            </button>
          ) : (
            <button
              onClick={onInstall}
              disabled={busy}
              className="flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-medium transition-colors disabled:opacity-40"
              style={{ background: 'rgba(127,109,242,0.15)', color: '#9d8ff9', border: '1px solid rgba(127,109,242,0.3)' }}
            >
              {busy ? <RefreshCw size={11} className="animate-spin" /> : <Plus size={11} />}
              {conn.legacy_detected ? 'Fix & Install' : 'Install'}
            </button>
          )}
          <button
            onClick={() => setExpanded(v => !v)}
            className="text-[11px] transition-colors"
            style={{ color: 'var(--text-muted)' }}
          >
            {expanded ? 'Hide details' : 'Show details'}
          </button>
        </div>
        {conn.doc_url && (
          <a
            href={conn.doc_url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1 text-[11px] hover:underline"
            style={{ color: 'var(--interactive-accent)' }}
          >
            <ExternalLink size={10} /> Docs
          </a>
        )}
      </div>

      {/* Details */}
      {expanded && (
        <div className="px-4 py-3 space-y-3 text-xs" style={{ borderTop: '1px solid var(--background-modifier-border)' }}>
          <div>
            <div className="text-[10px] font-semibold uppercase tracking-wider mb-1" style={{ color: 'var(--text-faint)' }}>
              Config path
            </div>
            <div className="flex items-center gap-2 font-mono text-[11px] break-all" style={{ color: 'var(--text-muted)' }}>
              {conn.config_path}
              <CopyButton text={conn.config_path} label="Path" />
            </div>
          </div>
          {conn.install_note && (
            <div className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
              ⓘ {conn.install_note}
            </div>
          )}
          {conn.error && (
            <div className="flex items-start gap-1.5 text-[11px] px-2.5 py-1.5 rounded" style={{ color: '#ff6b6b', background: 'rgba(255,69,58,0.1)' }}>
              <AlertTriangle size={11} className="flex-shrink-0 mt-0.5" />
              {conn.error}
            </div>
          )}
          {snippet && (
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-[10px] font-semibold uppercase tracking-wider" style={{ color: 'var(--text-faint)' }}>
                  Manual setup — {conn.format.toUpperCase()}
                </span>
                <CopyButton text={snippet} />
              </div>
              <pre
                className="font-mono text-[10.5px] p-2.5 rounded-md overflow-x-auto"
                style={{
                  background: 'var(--background-primary)',
                  border: '1px solid var(--background-modifier-border)',
                  color: 'var(--text-muted)',
                  lineHeight: 1.5,
                }}
              >{snippet}</pre>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Main view ────────────────────────────────────────────────────────────────

export default function ConnectorsView() {
  const qc = useQueryClient()
  const toast = useToast()
  const { data, isLoading, refetch, isFetching } = useQuery({
    queryKey: ['connectors'],
    queryFn: api.connectors,
    refetchInterval: 15_000,
  })
  const [busyId, setBusyId] = useState<string | null>(null)

  // Per-card detail fetches (for snippet); only loads when expanded
  const [details, setDetails] = useState<Record<string, string>>({})

  const installMut = useMutation({
    mutationFn: (id: string) => api.installConnector(id),
    onMutate: (id) => setBusyId(id),
    onSuccess: (r, id) => {
      const name = data?.connectors.find(c => c.id === id)?.name ?? id
      toast.success(`Mnemion installed in ${name}${r.note ? ' — ' + r.note : ''}`)
      qc.invalidateQueries({ queryKey: ['connectors'] })
    },
    onError: (err: any) => toast.error(err?.message ?? 'Install failed'),
    onSettled: () => setBusyId(null),
  })

  const uninstallMut = useMutation({
    mutationFn: (id: string) => api.uninstallConnector(id),
    onMutate: (id) => setBusyId(id),
    onSuccess: (_, id) => {
      const name = data?.connectors.find(c => c.id === id)?.name ?? id
      toast.success(`Removed from ${name}`)
      qc.invalidateQueries({ queryKey: ['connectors'] })
    },
    onError: (err: any) => toast.error(err?.message ?? 'Remove failed'),
    onSettled: () => setBusyId(null),
  })

  // Simple pre-fetch of all snippets (they're tiny)
  async function ensureSnippets() {
    if (!data) return
    const missing = data.connectors.filter(c => !(c.id in details))
    if (!missing.length) return
    const fetched = await Promise.all(
      missing.map(async c => {
        try {
          const full = await api.connector(c.id)
          return [c.id, full.snippet ?? ''] as const
        } catch {
          return [c.id, ''] as const
        }
      })
    )
    setDetails(prev => ({ ...prev, ...Object.fromEntries(fetched) }))
  }

  // Lazy: when data loads, fetch snippets in the background
  if (data && Object.keys(details).length === 0) {
    void ensureSnippets()
  }

  const groups: Array<[string, ConnectorStatus[]]> = [
    ['CLI', (data?.connectors ?? []).filter(c => c.category === 'cli')],
    ['Desktop App', (data?.connectors ?? []).filter(c => c.category === 'app')],
    ['IDE / Editor', (data?.connectors ?? []).filter(c => c.category === 'ide')],
  ]

  const connectedCount = data?.connectors.filter(c => c.mnemion_configured).length ?? 0
  const totalInstalled = data?.connectors.filter(c => c.installed).length ?? 0

  return (
    <div className="flex-1 overflow-y-auto p-6 space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between fade-in">
        <div>
          <h1 className="text-xl font-semibold tracking-tight flex items-center gap-2">
            <Plug size={18} style={{ color: 'var(--interactive-accent)' }} />
            Connect Agents
          </h1>
          <p className="text-sm mt-0.5" style={{ color: 'var(--text-muted)' }}>
            One-click setup for AI tools that speak the Model Context Protocol.
            {!isLoading && data && (
              <span>
                {' '}
                <span style={{ color: '#30d158' }}>{connectedCount} connected</span> ·{' '}
                {totalInstalled} detected · {data.connectors.length} known
              </span>
            )}
          </p>
        </div>
        <button
          onClick={() => refetch()}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs transition-colors"
          style={{ color: 'var(--text-muted)', border: '1px solid var(--background-modifier-border)' }}
        >
          <RefreshCw size={11} className={isFetching ? 'animate-spin' : ''} /> Rescan
        </button>
      </div>

      {/* Loading skeleton */}
      {isLoading && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="rounded-xl p-4 animate-pulse" style={{ background: 'var(--surface)', border: '1px solid var(--background-modifier-border)', height: 110 }} />
          ))}
        </div>
      )}

      {/* Launch command reminder */}
      {data && (
        <div
          className="rounded-xl p-4 flex items-center gap-3 fade-in"
          style={{ background: 'var(--surface)', border: '1px solid var(--background-modifier-border)' }}
        >
          <Terminal size={14} style={{ color: 'var(--interactive-accent)' }} />
          <div className="flex-1 min-w-0">
            <div className="text-[11px] font-semibold uppercase tracking-wider" style={{ color: 'var(--text-faint)' }}>
              Mnemion MCP command
            </div>
            <div className="font-mono text-[12px] mt-0.5 break-all" style={{ color: 'var(--text-muted)' }}>
              {data.python_cmd} {data.python_args.join(' ')}
            </div>
          </div>
          <CopyButton text={`${data.python_cmd} ${data.python_args.join(' ')}`} />
        </div>
      )}

      {/* Groups */}
      {groups.map(([title, conns]) =>
        conns.length > 0 && (
          <section key={title} className="fade-in">
            <h2 className="text-xs font-semibold uppercase tracking-wider mb-3" style={{ color: 'var(--text-faint)' }}>
              {title}
            </h2>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
              {conns.map(c => (
                <ConnectorCard
                  key={c.id}
                  conn={c}
                  snippet={details[c.id]}
                  busy={busyId === c.id}
                  onInstall={() => installMut.mutate(c.id)}
                  onUninstall={() => uninstallMut.mutate(c.id)}
                />
              ))}
            </div>
          </section>
        )
      )}

      {/* Manual / unlisted */}
      <section
        className="rounded-xl p-5 fade-in"
        style={{ background: 'var(--surface)', border: '1px dashed var(--background-modifier-border)' }}
      >
        <h2 className="text-sm font-semibold mb-2">Other MCP clients</h2>
        <p className="text-xs mb-3" style={{ color: 'var(--text-muted)' }}>
          Don't see your tool? Any MCP-compatible client (OpenClaw, Nemoclaw, Hermes, Cline,
          custom agents…) can connect using this command:
        </p>
        {data && (
          <pre
            className="font-mono text-[11px] p-3 rounded-md overflow-x-auto"
            style={{
              background: 'var(--background-primary)',
              border: '1px solid var(--background-modifier-border)',
              color: 'var(--text-muted)',
              lineHeight: 1.5,
            }}
          >{JSON.stringify({
            mcpServers: {
              mnemion: { command: data.python_cmd, args: data.python_args },
            },
          }, null, 2)}</pre>
        )}
      </section>
    </div>
  )
}
