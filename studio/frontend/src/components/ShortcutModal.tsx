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
      { keys: ['C'],         label: 'New drawer (when not typing)' },
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
      { keys: ['G', 'C'], label: 'Connect agents (MCP setup)' },
    ],
  },
  {
    title: 'Command Palette',
    shortcuts: [
      { keys: ['↑', '↓'],   label: 'Navigate results' },
      { keys: ['↵'],         label: 'Select / open' },
      { keys: ['Esc'],       label: 'Close' },
    ],
  },
  {
    title: 'New Drawer Form',
    shortcuts: [
      { keys: ['Ctrl', '↵'], label: 'Save drawer' },
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
        background: '#2a2a2a',
        border: '1px solid #3d3d3d',
        borderBottom: '2px solid #333',
        color: '#dcddde',
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
          background: '#1a1a1a',
          border: '1px solid #333',
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
            borderBottom: '1px solid #2a2a2a',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Keyboard size={15} style={{ color: '#7f6df2' }} />
            <span style={{ fontSize: 14, fontWeight: 600, color: '#dcddde' }}>Keyboard Shortcuts</span>
          </div>
          <button
            onClick={onClose}
            style={{ color: '#555', padding: 4, borderRadius: 6 }}
            onMouseEnter={e => (e.currentTarget.style.color = '#999')}
            onMouseLeave={e => (e.currentTarget.style.color = '#555')}
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
                    letterSpacing: '0.08em', color: '#555', marginBottom: 10,
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
                      <span style={{ fontSize: 13, color: '#999', flex: 1 }}>{s.label}</span>
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
            borderTop: '1px solid #2a2a2a',
            fontSize: 11,
            color: '#444',
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
