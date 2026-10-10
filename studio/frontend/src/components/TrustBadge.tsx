import type { TrustSummary } from '../types'

const STATUS_STYLES: Record<string, { bg: string; text: string; dot: string; label: string }> = {
  current:    { bg: 'bg-emerald-500/10', text: 'text-emerald-400', dot: 'bg-emerald-400', label: 'Current' },
  superseded: { bg: 'bg-yellow-500/10',  text: 'text-yellow-400',  dot: 'bg-yellow-400',  label: 'Superseded' },
  contested:  { bg: 'bg-orange-500/10',  text: 'text-orange-400',  dot: 'bg-orange-400',  label: 'Contested' },
  historical: { bg: 'bg-zinc-500/10',    text: 'text-zinc-400',    dot: 'bg-zinc-500',    label: 'Historical' },
  unknown:    { bg: 'bg-zinc-500/10',    text: 'text-zinc-400',    dot: 'bg-zinc-500',    label: 'Unknown' },
}

interface Props {
  trust: TrustSummary | null
  showConfidence?: boolean
}

export default function TrustBadge({ trust, showConfidence = false }: Props) {
  if (!trust) return null
  const s = STATUS_STYLES[trust.status] ?? STATUS_STYLES.unknown
  const pct = Math.round((trust.confidence ?? 1) * 100)
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-xs font-medium ${s.bg} ${s.text}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${s.dot}`} />
      {s.label}
      {showConfidence && ` - ${pct}%`}
    </span>
  )
}

export function ConfidenceBar({ confidence }: { confidence: number }) {
  const pct = Math.round(confidence * 100)
  const color = pct >= 80 ? 'bg-emerald-400' : pct >= 50 ? 'bg-yellow-400' : 'bg-red-400'
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1 bg-white/10 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-muted w-8 text-right">{pct}%</span>
    </div>
  )
}
