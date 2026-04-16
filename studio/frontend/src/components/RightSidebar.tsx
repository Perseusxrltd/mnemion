import { useQuery } from '@tanstack/react-query'
import { Tag, RefreshCw, X } from 'lucide-react'
import { api } from '../api/client'
import WingBadge from './WingBadge'
import TrustBadge, { ConfidenceBar } from './TrustBadge'

interface RightSidebarProps {
  drawerId?: string
  width?: number
  onClose?: () => void
}

function PropertyRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="property-row">
      <span className="property-key">{label}</span>
      <span className="property-value">{children}</span>
    </div>
  )
}

export default function RightSidebar({ drawerId, width = 240, onClose }: RightSidebarProps) {
  const { data, isLoading } = useQuery({
    queryKey: ['drawer', drawerId],
    queryFn: () => api.getDrawer(drawerId!),
    enabled: !!drawerId,
    staleTime: 30_000,
  })

  // Cast to any to access backend fields not in the strict type
  const drawer = data as any

  return (
    <div
      className="flex flex-col h-full overflow-hidden"
      style={{
        width,
        flexShrink: 0,
        background: 'var(--background-secondary)',
        borderLeft: '1px solid var(--background-modifier-border)',
      }}
    >
      {/* Header */}
      <div
        className="flex items-center justify-between px-3 py-2.5 border-b"
        style={{ borderColor: 'var(--background-modifier-border)' }}
      >
        <span className="text-[11px] font-semibold uppercase tracking-widest" style={{ color: 'var(--text-faint)' }}>
          Properties
        </span>
        {onClose && (
          <button
            onClick={onClose}
            className="transition-colors"
            style={{ color: 'var(--text-faint)' }}
          >
            <X size={13} />
          </button>
        )}
      </div>

      <div className="flex-1 overflow-y-auto px-3 py-2">
        {!drawerId && (
          <div className="mt-8 text-center" style={{ color: 'var(--text-faint)' }}>
            <Tag size={22} className="mx-auto mb-2 opacity-40" />
            <p className="text-[12px]">Select a drawer<br />to view its properties</p>
          </div>
        )}

        {drawerId && isLoading && (
          <div className="flex items-center gap-2 mt-4 text-[12px]" style={{ color: 'var(--text-muted)' }}>
            <RefreshCw size={11} className="animate-spin" /> Loading…
          </div>
        )}

        {drawer && (
          <div className="space-y-0 fade-in">
            {/* Metadata */}
            <section className="mb-4">
              <div className="text-[10px] font-semibold uppercase tracking-widest mb-2" style={{ color: 'var(--text-faint)' }}>
                Metadata
              </div>
              <PropertyRow label="Wing">
                <WingBadge wing={drawer.wing} room={drawer.room} />
              </PropertyRow>
              <PropertyRow label="Room">
                <span style={{ color: 'var(--text-muted)' }}>{drawer.room || '—'}</span>
              </PropertyRow>
              {(drawer.added_by || drawer.agent) && (
                <PropertyRow label="Agent">
                  <span className="font-mono text-[11px]" style={{ color: 'var(--text-accent)' }}>
                    {drawer.added_by || drawer.agent}
                  </span>
                </PropertyRow>
              )}
              {(drawer.timestamp || drawer.created_at) && (
                <PropertyRow label="Created">
                  <span style={{ color: 'var(--text-muted)' }}>
                    {new Date(drawer.timestamp || drawer.created_at).toLocaleDateString('en-GB', {
                      day: '2-digit', month: 'short', year: 'numeric',
                    })}
                  </span>
                </PropertyRow>
              )}
              {drawer.source && (
                <PropertyRow label="Source">
                  <span className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
                    {drawer.source}
                  </span>
                </PropertyRow>
              )}
            </section>

            {/* Trust */}
            <section className="mb-4">
              <div className="text-[10px] font-semibold uppercase tracking-widest mb-2" style={{ color: 'var(--text-faint)' }}>
                Trust
              </div>
              {drawer.trust ? (
                <>
                  <div className="py-1.5">
                    <TrustBadge trust={drawer.trust} showConfidence />
                  </div>
                  <div className="mt-2">
                    <ConfidenceBar confidence={drawer.trust.confidence ?? 1} />
                  </div>
                </>
              ) : (
                <div className="text-[12px]" style={{ color: 'var(--text-faint)' }}>No trust data</div>
              )}
            </section>

            {/* Char count */}
            {drawer.char_count > 0 && (
              <section className="mb-4">
                <div className="text-[10px] font-semibold uppercase tracking-widest mb-2" style={{ color: 'var(--text-faint)' }}>
                  Content
                </div>
                <PropertyRow label="Size">
                  <span style={{ color: 'var(--text-muted)' }}>{drawer.char_count.toLocaleString()} chars</span>
                </PropertyRow>
              </section>
            )}

            {/* Drawer ID */}
            <section>
              <div className="text-[10px] font-semibold uppercase tracking-widest mb-2" style={{ color: 'var(--text-faint)' }}>
                Identifier
              </div>
              <div
                className="font-mono text-[10px] px-2 py-1.5 rounded break-all"
                style={{ background: 'var(--interactive-normal)', color: 'var(--text-muted)', lineHeight: 1.5 }}
              >
                {drawer.id}
              </div>
            </section>
          </div>
        )}
      </div>
    </div>
  )
}
