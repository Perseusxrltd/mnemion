import { useState, useEffect, useRef } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { X, Plus, AlertCircle } from 'lucide-react'
import { api } from '../api/client'
import { useToast } from './ToastProvider'

interface Props {
  open: boolean
  defaultWing?: string
  defaultRoom?: string
  onClose: () => void
  onCreated?: (id: string) => void
}

export default function DrawerCreateModal({ open, defaultWing = '', defaultRoom = '', onClose, onCreated }: Props) {
  const qc = useQueryClient()
  const toast = useToast()
  const [wing, setWing] = useState(defaultWing)
  const [room, setRoom] = useState(defaultRoom)
  const [content, setContent] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // Sync defaults when they change (e.g. opened from within a wing)
  useEffect(() => {
    if (open) {
      setWing(defaultWing)
      setRoom(defaultRoom)
      setContent('')
      setTimeout(() => textareaRef.current?.focus(), 60)
    }
  }, [open, defaultWing, defaultRoom])

  const mut = useMutation({
    mutationFn: () => api.createDrawer({ wing: wing.trim(), room: room.trim(), content: content.trim() }),
    onSuccess: (data: any) => {
      qc.invalidateQueries({ queryKey: ['drawers'] })
      qc.invalidateQueries({ queryKey: ['drawers-recent'] })
      qc.invalidateQueries({ queryKey: ['status'] })
      qc.invalidateQueries({ queryKey: ['taxonomy'] })
      const newId = data?.drawer_id ?? data?.id ?? ''
      toast.success(data?.reason === 'already_exists' ? 'Drawer already exists' : 'Drawer created')
      onCreated?.(newId)
      onClose()
    },
    onError: (err: any) => {
      toast.error(err?.message ?? 'Failed to create drawer')
    },
  })

  const canSubmit = wing.trim() && room.trim() && content.trim() && !mut.isPending

  // Keyboard: Ctrl+Enter to submit, Escape to close
  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { onClose(); return }
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter' && canSubmit) { mut.mutate() }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [open, canSubmit, mut, onClose])

  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: 'rgba(0,0,0,0.55)', backdropFilter: 'blur(4px)' }}
      onClick={onClose}
    >
      <div
        className="w-[560px] rounded-xl shadow-2xl fade-in flex flex-col"
        style={{
          background: 'var(--background-primary-alt)',
          border: '1px solid var(--background-modifier-border)',
          maxHeight: '80vh',
        }}
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div
          className="flex items-center justify-between px-5 py-4 border-b"
          style={{ borderColor: 'var(--background-modifier-border)' }}
        >
          <div className="flex items-center gap-2">
            <Plus size={15} style={{ color: 'var(--interactive-accent)' }} />
            <span className="font-semibold text-sm">New Drawer</span>
          </div>
          <button
            onClick={onClose}
            className="transition-colors rounded-md p-1 hover:bg-white/10"
            style={{ color: 'var(--text-muted)' }}
          >
            <X size={14} />
          </button>
        </div>

        {/* Form */}
        <div className="px-5 py-4 space-y-3 flex-1 overflow-y-auto">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-[11px] font-medium mb-1.5" style={{ color: 'var(--text-muted)' }}>
                Wing <span style={{ color: 'var(--interactive-accent)' }}>*</span>
              </label>
              <input
                value={wing}
                onChange={e => setWing(e.target.value)}
                placeholder="e.g. projects"
                className="w-full px-3 py-2 rounded-lg text-sm outline-none transition-colors font-mono"
                style={{
                  background: 'var(--background-modifier-form-field)',
                  border: `1px solid ${wing.trim() ? 'var(--background-modifier-border)' : 'var(--background-modifier-border)'}`,
                  color: 'var(--text-normal)',
                }}
                onFocus={e => e.target.style.borderColor = 'var(--interactive-accent)'}
                onBlur={e => e.target.style.borderColor = 'var(--background-modifier-border)'}
              />
            </div>
            <div>
              <label className="block text-[11px] font-medium mb-1.5" style={{ color: 'var(--text-muted)' }}>
                Room <span style={{ color: 'var(--interactive-accent)' }}>*</span>
              </label>
              <input
                value={room}
                onChange={e => setRoom(e.target.value)}
                placeholder="e.g. notes"
                className="w-full px-3 py-2 rounded-lg text-sm outline-none transition-colors font-mono"
                style={{
                  background: 'var(--background-modifier-form-field)',
                  border: '1px solid var(--background-modifier-border)',
                  color: 'var(--text-normal)',
                }}
                onFocus={e => e.target.style.borderColor = 'var(--interactive-accent)'}
                onBlur={e => e.target.style.borderColor = 'var(--background-modifier-border)'}
              />
            </div>
          </div>

          <div>
            <label className="block text-[11px] font-medium mb-1.5" style={{ color: 'var(--text-muted)' }}>
              Content <span style={{ color: 'var(--interactive-accent)' }}>*</span>
            </label>
            <textarea
              ref={textareaRef}
              value={content}
              onChange={e => setContent(e.target.value)}
              placeholder="Write your memory here…&#10;&#10;You can reference entities with [[wikilinks]]."
              rows={8}
              className="w-full px-3 py-2.5 rounded-lg text-sm outline-none transition-colors resize-none font-mono leading-relaxed"
              style={{
                background: 'var(--background-modifier-form-field)',
                border: '1px solid var(--background-modifier-border)',
                color: 'var(--text-normal)',
              }}
              onFocus={e => e.target.style.borderColor = 'var(--interactive-accent)'}
              onBlur={e => e.target.style.borderColor = 'var(--background-modifier-border)'}
            />
            <div className="flex justify-between mt-1">
              <span className="text-[10px]" style={{ color: 'var(--text-faint)' }}>
                Use <code style={{ background: 'rgba(127,109,242,0.15)', color: 'var(--text-accent)', borderRadius: 3, padding: '0 3px' }}>[[entity]]</code> syntax for wikilinks
              </span>
              <span className="text-[10px] font-mono" style={{ color: 'var(--text-faint)' }}>
                {content.length.toLocaleString()} chars
              </span>
            </div>
          </div>

          {mut.isError && (
            <div className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm" style={{ background: 'var(--background-modifier-error)', color: 'var(--text-error)' }}>
              <AlertCircle size={13} />
              {(mut.error as Error)?.message ?? 'Failed to create drawer'}
            </div>
          )}
        </div>

        {/* Footer */}
        <div
          className="flex items-center justify-between px-5 py-3 border-t"
          style={{ borderColor: 'var(--background-modifier-border)' }}
        >
          <span className="text-[11px]" style={{ color: 'var(--text-faint)' }}>
            <kbd className="font-mono">Ctrl</kbd>+<kbd className="font-mono">↵</kbd> to save
          </span>
          <div className="flex items-center gap-2">
            <button
              onClick={onClose}
              className="px-4 py-1.5 rounded-lg text-sm transition-colors"
              style={{ color: 'var(--text-muted)' }}
            >
              Cancel
            </button>
            <button
              onClick={() => mut.mutate()}
              disabled={!canSubmit}
              className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-sm font-medium transition-all disabled:opacity-40 disabled:cursor-not-allowed"
              style={{ background: 'var(--interactive-accent)', color: 'white' }}
            >
              {mut.isPending ? (
                <span className="flex items-center gap-1.5">
                  <span className="w-3 h-3 border border-white/40 border-t-white rounded-full animate-spin" />
                  Saving…
                </span>
              ) : (
                <>
                  <Plus size={13} /> Save Drawer
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
