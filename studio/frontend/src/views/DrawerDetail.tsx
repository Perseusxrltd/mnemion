import { useState, useCallback } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  ArrowLeft, Copy, Trash2, CheckCircle, XCircle, Clock,
  FileText, User, Hash, Link2, Shield, ChevronRight,
} from 'lucide-react'
import { api } from '../api/client'
import { wingColor } from '../types'
import WingBadge from '../components/WingBadge'
import TrustBadge, { ConfidenceBar } from '../components/TrustBadge'

// ── Wikilink renderer ─────────────────────────────────────────────────────────

function WikiContent({ text }: { text: string }) {
  // Split on [[...]] tokens, render each as clickable span or plain text
  const parts = text.split(/(\[\[[^\]]+\]\])/g)
  return (
    <pre className="drawer-content" style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
      {parts.map((part, i) => {
        const m = part.match(/^\[\[([^\]]+)\]\]$/)
        if (m) {
          return (
            <span key={i} className="wikilink" title={`Entity: ${m[1]}`}>
              {m[1]}
            </span>
          )
        }
        return <span key={i}>{part}</span>
      })}
    </pre>
  )
}

// ── Section header ────────────────────────────────────────────────────────────

function SectionHeader({ children }: { children: React.ReactNode }) {
  return (
    <h3
      className="text-[10px] font-semibold uppercase tracking-widest mb-3 flex items-center gap-1.5"
      style={{ color: 'var(--text-faint)' }}
    >
      {children}
    </h3>
  )
}

function MetaRow({ icon: Icon, label, value, mono = false, truncate = false }: {
  icon: any; label: string; value: string; mono?: boolean; truncate?: boolean
}) {
  return (
    <div className="flex items-start gap-2.5 py-1.5">
      <Icon size={11} className="flex-shrink-0 mt-0.5" style={{ color: 'var(--text-faint)' }} />
      <div className="min-w-0 flex-1">
        <div className="text-[10px] mb-0.5" style={{ color: 'var(--text-faint)' }}>{label}</div>
        <div
          className={`text-[12px] ${mono ? 'font-mono' : ''} ${truncate ? 'truncate' : 'break-words'}`}
          style={{ color: 'var(--text-muted)' }}
        >
          {value || '-'}
        </div>
      </div>
    </div>
  )
}

// ── Main ──────────────────────────────────────────────────────────────────────

export default function DrawerDetail() {
  const location = useLocation()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [copied, setCopied] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)

  const drawerId = decodeURIComponent(location.pathname.replace(/^\/drawer\//, ''))

  const { data, isLoading, error } = useQuery({
    queryKey: ['drawer', drawerId],
    queryFn: () => api.drawer(drawerId),
    enabled: !!drawerId,
  })

  const verifyMut = useMutation({
    mutationFn: () => api.verifyDrawer(drawerId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['drawer', drawerId] }),
  })

  const challengeMut = useMutation({
    mutationFn: () => api.challengeDrawer(drawerId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['drawer', drawerId] }),
  })

  const deleteMut = useMutation({
    mutationFn: () => api.deleteDrawer(drawerId),
    onSuccess: () => navigate(-1),
  })

  const copyId = useCallback(() => {
    navigator.clipboard.writeText(drawerId)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }, [drawerId])

  if (isLoading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 border-2 rounded-full animate-spin" style={{ borderColor: 'var(--background-modifier-border)', borderTopColor: 'var(--interactive-accent)' }} />
          <div className="text-sm" style={{ color: 'var(--text-muted)' }}>Loading memory...</div>
        </div>
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center gap-3">
        <FileText size={32} style={{ color: 'var(--text-faint)' }} />
        <div className="text-sm" style={{ color: 'var(--text-muted)' }}>Memory not found</div>
        <button
          onClick={() => navigate(-1)}
          className="text-xs hover:underline"
          style={{ color: 'var(--interactive-accent)' }}
        >
          Go back
        </button>
      </div>
    )
  }

  const wingCol = wingColor(data.wing)
  const wikilinkCount = (data.content.match(/\[\[[^\]]+\]\]/g) ?? []).length

  return (
    <div className="flex-1 flex overflow-hidden">
      {/* ── Main content ── */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Toolbar + breadcrumb */}
        <div
          className="flex items-center gap-2 px-4 py-2.5 border-b flex-shrink-0"
          style={{ borderColor: 'var(--background-modifier-border)', background: 'var(--background-secondary)', minHeight: 44 }}
        >
          {/* Back */}
          <button
            onClick={() => navigate(-1)}
            className="p-1.5 rounded-md transition-colors hover:bg-white/10"
            style={{ color: 'var(--text-muted)' }}
            title="Go back"
          >
            <ArrowLeft size={14} />
          </button>

          {/* Breadcrumb */}
          <div className="flex items-center gap-1 text-[12px] min-w-0">
            <button
              onClick={() => navigate('/browse')}
              className="transition-colors hover:underline flex-shrink-0"
              style={{ color: 'var(--text-faint)' }}
            >
              Browse
            </button>
            <ChevronRight size={11} style={{ color: 'var(--text-faint)', flexShrink: 0 }} />
            <button
              onClick={() => navigate(`/browse/${data.wing}`)}
              className="transition-colors hover:underline font-medium flex-shrink-0"
              style={{ color: wingCol }}
            >
              {data.wing}
            </button>
            {data.room && (
              <>
                <ChevronRight size={11} style={{ color: 'var(--text-faint)', flexShrink: 0 }} />
                <button
                  onClick={() => navigate(`/browse/${data.wing}/${data.room}`)}
                  className="transition-colors hover:underline flex-shrink-0"
                  style={{ color: 'var(--text-muted)' }}
                >
                  {data.room}
                </button>
              </>
            )}
            <ChevronRight size={11} style={{ color: 'var(--text-faint)', flexShrink: 0 }} />
            <span
              className="truncate font-mono text-[11px]"
              style={{ color: 'var(--text-faint)' }}
            >
              {drawerId.slice(-20)}
            </span>
          </div>

          <div className="flex-1" />

          {/* Wikilink badge */}
          {wikilinkCount > 0 && (
            <span
              className="text-[10px] px-2 py-0.5 rounded font-medium flex-shrink-0"
              style={{ background: 'rgba(196,154,85,0.12)', color: 'var(--interactive-accent)' }}
              title={`${wikilinkCount} links`}
            >
              {wikilinkCount} links
            </span>
          )}

          {/* Copy ID */}
          <button
            onClick={copyId}
            className="flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-lg transition-colors flex-shrink-0"
            style={{ color: 'var(--text-muted)', border: '1px solid var(--background-modifier-border)' }}
            onMouseEnter={e => (e.currentTarget.style.color = 'var(--text-normal)')}
            onMouseLeave={e => (e.currentTarget.style.color = 'var(--text-muted)')}
          >
            {copied
              ? <><CheckCircle size={11} style={{ color: 'var(--success)' }} /> Copied</>
              : <><Copy size={11} /> Copy ID</>
            }
          </button>

          {/* Delete */}
          {!confirmDelete ? (
            <button
              onClick={() => setConfirmDelete(true)}
              className="flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-lg transition-colors flex-shrink-0"
              style={{ color: 'var(--text-error)', border: '1px solid transparent' }}
              onMouseEnter={e => (e.currentTarget.style.background = 'rgba(229,121,114,0.08)')}
              onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
            >
              <Trash2 size={11} /> Delete
            </button>
          ) : (
            <div className="flex items-center gap-1.5 flex-shrink-0">
              <span className="text-xs" style={{ color: 'var(--text-error)' }}>Delete?</span>
              <button
                onClick={() => deleteMut.mutate()}
                className="px-2.5 py-1 rounded text-xs font-medium"
                style={{ background: 'rgba(229,121,114,0.15)', color: 'var(--text-error)' }}
              >
                Yes
              </button>
              <button
                onClick={() => setConfirmDelete(false)}
                className="px-2.5 py-1 rounded text-xs"
                style={{ color: 'var(--text-muted)' }}
              >
                No
              </button>
            </div>
          )}
        </div>

        {/* Content area */}
        <div className="flex-1 overflow-y-auto">
          <div className="max-w-3xl mx-auto px-8 py-7">
            {/* Wing badge */}
            <div className="mb-5">
              <WingBadge wing={data.wing} room={data.room} size="md" />
            </div>

            {/* Content — renders wikilinks */}
            <WikiContent text={data.content} />
          </div>
        </div>
      </div>

      {/* ── Right metadata panel ── */}
      <div
        className="w-64 flex-shrink-0 flex flex-col overflow-hidden"
        style={{
          background: 'var(--background-secondary)',
          borderLeft: '1px solid var(--background-modifier-border)',
        }}
      >
        <div
          className="px-4 py-3 border-b"
          style={{ borderColor: 'var(--background-modifier-border)' }}
        >
          <span className="text-[10px] font-semibold uppercase tracking-widest" style={{ color: 'var(--text-faint)' }}>
            Properties
          </span>
        </div>

        <div className="flex-1 overflow-y-auto px-4 py-3 space-y-5">
          {/* Metadata */}
          <section>
            <SectionHeader><Hash size={10} /> Details</SectionHeader>
            <MetaRow icon={User}     label="Added by"  value={data.added_by} />
            <MetaRow icon={Clock}    label="Timestamp" value={data.timestamp ? data.timestamp.slice(0, 16).replace('T', ' ') : ''} />
            <MetaRow icon={FileText} label="Size"      value={`${data.char_count.toLocaleString()} characters`} />
            {data.source && (
              <MetaRow icon={Link2} label="Source" value={data.source} truncate />
            )}
            <MetaRow icon={Hash} label="ID" value={drawerId.slice(-24)} mono truncate />
          </section>

          {/* Trust */}
          <section>
            <SectionHeader><Shield size={10} /> Trust</SectionHeader>
            {data.trust ? (
              <div className="space-y-2.5">
                <TrustBadge trust={data.trust} showConfidence />
                <ConfidenceBar confidence={data.trust.confidence ?? 1} />
                <div className="flex gap-3 text-[11px]" style={{ color: 'var(--text-muted)' }}>
                  <span className="flex items-center gap-1">
                    <CheckCircle size={9} style={{ color: 'var(--success)' }} />
                    {data.trust.verifications}
                  </span>
                  <span className="flex items-center gap-1">
                    <XCircle size={9} style={{ color: '#f97316' }} />
                    {data.trust.challenges}
                  </span>
                </div>
                <div className="flex gap-1.5">
                  <button
                    onClick={() => verifyMut.mutate()}
                    disabled={verifyMut.isPending}
                    className="flex-1 py-1.5 rounded-lg text-[12px] font-medium transition-colors disabled:opacity-40"
                    style={{ background: 'rgba(106,178,140,0.12)', color: 'var(--success)', border: '1px solid rgba(106,178,140,0.2)' }}
                    onMouseEnter={e => (e.currentTarget.style.background = 'rgba(106,178,140,0.2)')}
                    onMouseLeave={e => (e.currentTarget.style.background = 'rgba(106,178,140,0.12)')}
                  >
                    Confirm
                  </button>
                  <button
                    onClick={() => challengeMut.mutate()}
                    disabled={challengeMut.isPending}
                    className="flex-1 py-1.5 rounded-lg text-[12px] font-medium transition-colors disabled:opacity-40"
                    style={{ background: 'rgba(249,115,22,0.12)', color: '#f97316', border: '1px solid rgba(249,115,22,0.2)' }}
                    onMouseEnter={e => (e.currentTarget.style.background = 'rgba(249,115,22,0.2)')}
                    onMouseLeave={e => (e.currentTarget.style.background = 'rgba(249,115,22,0.12)')}
                  >
                    Flag
                  </button>
                </div>
              </div>
            ) : (
              <div className="text-[12px]" style={{ color: 'var(--text-faint)' }}>No verification history</div>
            )}
          </section>

          {/* Trust history */}
          {data.trust_history?.length > 0 && (
            <section>
              <SectionHeader>History</SectionHeader>
              <div className="space-y-2">
                {data.trust_history.map((h, i) => {
                  const colors: Record<string, string> = {
                    current: 'var(--success)', superseded: '#f59e0b',
                    contested: '#f97316', historical: '#6b7280',
                  }
                  return (
                    <div key={i} className="text-[11px]">
                      <div className="flex items-center justify-between">
                        <span className="font-medium capitalize" style={{ color: colors[h.status] ?? '#9ca3af' }}>
                          {h.status}
                        </span>
                        <span style={{ color: 'var(--text-faint)' }}>{h.changed_at?.slice(0, 10)}</span>
                      </div>
                      {h.reason && (
                        <div className="truncate mt-0.5" style={{ color: 'var(--text-muted)' }}>{h.reason}</div>
                      )}
                    </div>
                  )
                })}
              </div>
            </section>
          )}

          {/* Related memories */}
          {data.related?.length > 0 && (
            <section>
              <SectionHeader>Related Memories</SectionHeader>
              <div className="space-y-1.5">
                {data.related.map(r => (
                  <button
                    key={r.id}
                    onClick={() => navigate(`/drawer/${encodeURIComponent(r.id)}`)}
                    className="w-full text-left p-2.5 rounded-lg text-[12px] transition-colors"
                    style={{ background: 'var(--interactive-normal)', border: '1px solid var(--background-modifier-border)' }}
                    onMouseEnter={e => (e.currentTarget.style.background = 'var(--interactive-hover)')}
                    onMouseLeave={e => (e.currentTarget.style.background = 'var(--interactive-normal)')}
                  >
                    <WingBadge wing={r.wing} room={r.room} />
                    <p className="mt-1.5 line-clamp-2 leading-relaxed" style={{ color: 'var(--text-muted)' }}>
                      {(r.content ?? '').slice(0, 90)}
                    </p>
                  </button>
                ))}
              </div>
            </section>
          )}
        </div>
      </div>
    </div>
  )
}
