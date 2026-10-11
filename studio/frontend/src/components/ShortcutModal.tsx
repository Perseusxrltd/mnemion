import { useEffect } from 'react'
import { X, Keyboard } from 'lucide-react'

interface ShortcutModalProps {
  open: boolean
  onClose: () => void
}

const GROUPS = [
  {
    title: 'Global',
    shortcuts: [
      { keys: ['Ctrl', 'K'], label: 'Command palette' },
      { keys: ['?'],         label: 'Show keyboard shortcuts' },
      { keys: ['C'],         label: 'Save memory (when not typing)' },
      { keys: ['Esc'],       label: 'Close modal / go back' },
    ],
  },
  {
    title: 'Navigation',
    shortcuts: [
      { keys: ['G', 'D'], label: 'Go to Dashboard' },
      { keys: ['G', 'G'], label: 'Go to Graph' },
      { keys: ['G', 'B'], label: 'Go to Browse' },
      { keys: ['G', 'S'], label: 'Go to Search' },
      { keys: ['G', 'A'], label: 'Go to Agents' },
      { keys: ['G', 'M'], label: 'Go to Core Memory' },
      { keys: ['G', 'C'], label: 'Connect AI apps' },
    ],
  },
  {
    title: 'Command Palette',
    shortcuts: [
      { keys: ['Up', 'Down'], label: 'Navigate results' },
      { keys: ['Enter'],      label: 'Select / open' },
      { keys: ['Esc'],       label: 'Close' },
    ],
  },
  {
    title: 'Save Memory Form',
    shortcuts: [
      { keys: ['Ctrl', 'Enter'], label: 'Save memory' },
      { keys: ['Esc'],       label: 'Cancel' },
    ],
  },
]

function Key({ children }: { children: string }) {
  return (
    <kbd
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        minWidth: 22,
        height: 22,
        padding: '0 5px',
        borderRadius: 5,
        fontSize: 11,
        fontFamily: 'var(--font-monospace)',
        fontWeight: 500,
        background: 'var(--surface-overlay)',
        border: '1px solid var(--line)',
        borderBottom: '2px solid var(--line-soft)',
        color: 'var(--ivory)',
        lineHeight: 1,
        userSelect: 'none',
      }}
    >
      {children}
    </kbd>
  )
}

export default function ShortcutModal({ open, onClose }: ShortcutModalProps) {
  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [open, onClose])

  if (!open) return null

  return (
    <div
      style={{
        position: 'fixed', inset: 0, zIndex: 1000,
        background: 'rgba(0,0,0,0.6)',
        backdropFilter: 'blur(6px)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}
      onClick={onClose}
    >
      <div
        style={{
          width: 560,
          maxHeight: '80vh',
          borderRadius: 12,
          background: 'var(--surface-raised)',
          border: '1px solid var(--line-soft)',
          boxShadow: '0 20px 60px rgba(0,0,0,0.6)',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
          animation: 'slideDown 120ms cubic-bezier(0,0,0.2,1)',
        }}
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div
          style={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            padding: '16px 20px',
            borderBottom: '1px solid var(--surface-overlay)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Keyboard size={15} style={{ color: 'var(--gold)' }} />
            <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--ivory)' }}>Keyboard Shortcuts</span>
          </div>
          <button
            onClick={onClose}
            style={{ color: 'var(--text-faint)', padding: 4, borderRadius: 6 }}
            onMouseEnter={e => (e.currentTarget.style.color = 'var(--ivory-muted)')}
            onMouseLeave={e => (e.currentTarget.style.color = 'var(--text-faint)')}
          >
            <X size={14} />
          </button>
        </div>

        {/* Shortcut groups */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '12px 20px 20px' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
            {GROUPS.map(group => (
              <div key={group.title}>
                <div
                  style={{
                    fontSize: 10, fontWeight: 700, textTransform: 'uppercase',
                    letterSpacing: '0.08em', color: 'var(--text-faint)', marginBottom: 10,
                  }}
                >
                  {group.title}
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {group.shortcuts.map((s, i) => (
                    <div
                      key={i}
                      style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}
                    >
                      <span style={{ fontSize: 13, color: 'var(--ivory-muted)', flex: 1 }}>{s.label}</span>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 3, flexShrink: 0 }}>
                        {s.keys.map((k, ki) => <Key key={ki}>{k}</Key>)}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Footer */}
        <div
          style={{
            padding: '10px 20px',
            borderTop: '1px solid var(--surface-overlay)',
            fontSize: 11,
            color: 'var(--line)',
            display: 'flex',
            alignItems: 'center',
            gap: 16,
          }}
        >
          <span>Press <Key>?</Key> again or <Key>Esc</Key> to close</span>
          <span style={{ marginLeft: 'auto' }}>Mnemion Studio</span>
        </div>
      </div>
    </div>
  )
}
