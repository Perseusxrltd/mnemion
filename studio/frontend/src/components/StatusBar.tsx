import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'

export default function StatusBar() {
  const { data: status, isFetching } = useQuery({
    queryKey: ['status'],
    queryFn: api.status,
    staleTime: 30_000,
    refetchInterval: 60_000,
  })

  return (
    <div className="status-bar">
      {/* Left side */}
      <div className="flex items-center gap-3">
        <span className="flex items-center gap-1.5">
          <span
            className="w-1.5 h-1.5 rounded-full"
            style={{
              background: status ? '#30d158' : '#666',
              boxShadow: status ? '0 0 5px #30d158' : 'none',
            }}
          />
          {isFetching ? 'Syncing…' : status ? 'Connected' : 'Offline'}
        </span>

        {status && (
          <>
            <span style={{ color: 'var(--text-faint)' }}>·</span>
            <span>{status.total_drawers.toLocaleString()} drawers</span>
            <span style={{ color: 'var(--text-faint)' }}>·</span>
            <span>{status.wing_count} wings</span>
          </>
        )}
      </div>

      {/* Spacer */}
      <div className="flex-1" />

      {/* Right side */}
      <div className="flex items-center gap-3" style={{ color: 'var(--text-faint)' }}>
        {status?.version && (
          <span className="font-mono">v{status.version}</span>
        )}
        <span>Mnemion Studio</span>
        <span
          className="px-1.5 py-0.5 rounded text-[10px] font-mono"
          style={{ background: 'rgba(127,109,242,0.1)', color: 'var(--interactive-accent)' }}
        >
          Ctrl+K
        </span>
      </div>
    </div>
  )
}
