import { createContext, useContext, useState, useCallback, useRef } from 'react'
import { CheckCircle, AlertCircle, Info, X } from 'lucide-react'

// ── Types ─────────────────────────────────────────────────────────────────────

type ToastKind = 'success' | 'error' | 'info'

interface Toast {
  id: number
  kind: ToastKind
  message: string
}

interface ToastCtx {
  success: (msg: string) => void
  error:   (msg: string) => void
  info:    (msg: string) => void
}

// ── Context ───────────────────────────────────────────────────────────────────

export const ToastContext = createContext<ToastCtx>({
  success: () => {},
  error:   () => {},
  info:    () => {},
})

export const useToast = () => useContext(ToastContext)

// ── Icons / styling per kind ──────────────────────────────────────────────────

const TOAST_STYLE: Record<ToastKind, { icon: any; accent: string; border: string }> = {
  success: { icon: CheckCircle, accent: '#30d158', border: 'rgba(48,209,88,0.25)' },
  error:   { icon: AlertCircle, accent: '#ff453a', border: 'rgba(255,69,58,0.25)'  },
  info:    { icon: Info,        accent: '#7f6df2', border: 'rgba(127,109,242,0.25)' },
}

// ── Toast item ────────────────────────────────────────────────────────────────

function ToastItem({ toast, onDismiss }: { toast: Toast; onDismiss: () => void }) {
  const { icon: Icon, accent, border } = TOAST_STYLE[toast.kind]
  return (
    <div
      className="flex items-start gap-3 px-4 py-3 rounded-xl text-sm"
      style={{
        background: '#1e1e1e',
        border: `1px solid ${border}`,
        boxShadow: '0 8px 24px rgba(0,0,0,0.4), 0 0 0 1px rgba(255,255,255,0.04)',
        minWidth: 260,
        maxWidth: 380,
        animation: 'toastIn 120ms cubic-bezier(0, 0, 0.2, 1)',
      }}
    >
      <Icon size={15} style={{ color: accent, flexShrink: 0, marginTop: 1 }} />
      <span style={{ color: '#dcddde', flex: 1, lineHeight: 1.4 }}>{toast.message}</span>
      <button
        onClick={onDismiss}
        style={{ color: '#555', flexShrink: 0, marginTop: 1 }}
        onMouseEnter={e => (e.currentTarget.style.color = '#999')}
        onMouseLeave={e => (e.currentTarget.style.color = '#555')}
      >
        <X size={13} />
      </button>
    </div>
  )
}

// ── Provider ──────────────────────────────────────────────────────────────────

let nextId = 0

export default function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const timersRef = useRef<Map<number, ReturnType<typeof setTimeout>>>(new Map())

  const dismiss = useCallback((id: number) => {
    setToasts(prev => prev.filter(t => t.id !== id))
    const timer = timersRef.current.get(id)
    if (timer) { clearTimeout(timer); timersRef.current.delete(id) }
  }, [])

  const push = useCallback((kind: ToastKind, message: string) => {
    const id = ++nextId
    setToasts(prev => [...prev.slice(-4), { id, kind, message }])
    const timer = setTimeout(() => dismiss(id), kind === 'error' ? 5000 : 3000)
    timersRef.current.set(id, timer)
  }, [dismiss])

  const ctx: ToastCtx = {
    success: (msg) => push('success', msg),
    error:   (msg) => push('error', msg),
    info:    (msg) => push('info', msg),
  }

  return (
    <ToastContext.Provider value={ctx}>
      {children}

      {/* Toast stack — bottom-left, above status bar */}
      <div
        style={{
          position: 'fixed',
          bottom: 30, // above 22px status bar
          left: 16,
          zIndex: 9000,
          display: 'flex',
          flexDirection: 'column',
          gap: 8,
          pointerEvents: 'none',
        }}
      >
        {toasts.map(t => (
          <div key={t.id} style={{ pointerEvents: 'auto' }}>
            <ToastItem toast={t} onDismiss={() => dismiss(t.id)} />
          </div>
        ))}
      </div>

      <style>{`
        @keyframes toastIn {
          from { opacity: 0; transform: translateY(8px); }
          to   { opacity: 1; transform: translateY(0); }
        }
      `}</style>
    </ToastContext.Provider>
  )
}
