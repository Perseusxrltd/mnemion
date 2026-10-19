/** Bounded, content-free progress from a completed live-conversation scan. */
export interface ConversationCapture {
  captured: number; observed: number; pending: number
  read: number; reused: number; rendered: number
}

export function supportsLiveConversations(version?: string | null): boolean {
  const parts = version?.match(/^(\d{1,5})\.(\d{1,5})\.(\d{1,5})$/)?.slice(1).map(Number)
  const major = parts?.[0] ?? 0, minor = parts?.[1] ?? 0
  return major > 4 || (major === 4 && minor >= 17)
}

export function conversationCapture(checkpoint?: string | null): ConversationCapture | null {
  if (!checkpoint?.startsWith('jsonl:v1:') || checkpoint.length > 1024) return null
  try {
    const value = JSON.parse(checkpoint.slice(9))
    if (!value || typeof value !== 'object' || Array.isArray(value) ||
        typeof value.id !== 'string' || !/^[a-f0-9]{32}$/.test(value.id)) return null
    const counters = ['captured', 'observed', 'read', 'reused', 'rendered'] as const
    if (!counters.every(key => Number.isSafeInteger(value[key]) && value[key] >= 0) ||
        value.observed < value.captured) return null
    return { captured: value.captured, observed: value.observed, pending: value.observed - value.captured,
      read: value.read, reused: value.reused, rendered: value.rendered }
  } catch { return null }
}
