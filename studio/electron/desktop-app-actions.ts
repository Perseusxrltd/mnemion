/** Local OS-account controls reuse the ordinary update and preference controller. */
import type { DesktopUpdates } from './updates.js'

export function desktopAppAction(updates: DesktopUpdates | null, action: string,
  input: Record<string, unknown>, signal: AbortSignal) {
  signal.throwIfAborted()
  if (!updates) throw new Error('The desktop update controller is still starting. Retry shortly.')
  switch (action) {
    case 'app.status': return updates.inspect()
    case 'app.preferences': {
      const key = input.key
      if (key !== 'automaticUpdates' && key !== 'startAtLogin' && key !== 'background') throw new Error('Choose automaticUpdates, startAtLogin or background.')
      if (typeof input.enabled !== 'boolean' || typeof input.expected_value !== 'boolean') throw new Error('Supply boolean enabled and the observed expected_value.')
      if (updates.preferences[key] !== input.expected_value) throw new Error('That app preference changed. Read app.status before retrying.')
      if (key === 'automaticUpdates' && updates.policyManaged) throw new Error('Automatic updates are controlled by this computer’s administrator.')
      updates.setPreference(key, input.enabled)
      return { ...updates.inspect(), applied: updates.preferences[key] === input.enabled }
    }
    case 'app.update-check':
      if (!updates.enabled) throw new Error('Automatic updates are paused, managed by the administrator, or unavailable for this distribution. Read app.status.')
      // The app owns this ordinary check/download after accepting the request;
      // disconnecting the operator does not cancel the app's automatic updater.
      void updates.check()
      return { requested: true, ...updates.inspect() }
    case 'app.update-restart':
      if (input.confirm !== true || typeof input.expected_version !== 'string' ||
          !/^\d+\.\d+\.\d+$/.test(input.expected_version)) throw new Error('Confirm the exact ready update version from app.status.')
      updates.requestRestart(input.expected_version)
      return { requested: true, ...updates.inspect() }
    default: throw new Error('Choose an app operation from the desktop catalog.')
  }
}
