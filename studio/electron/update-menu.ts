/** The application and tray share these explicit update/preference actions. */
import type { MenuItemConstructorOptions } from 'electron'
import type { DesktopUpdates } from './updates.js'

export type UpdateMenuAction = 'app.update-check' | 'app.update-restart' | 'app.preferences'
type Observe = (action: UpdateMenuAction, run: () => unknown) => unknown

export function desktopUpdateMenu(updates: DesktopUpdates | null, observe: Observe): MenuItemConstructorOptions[] {
  const invoke = (action: UpdateMenuAction, run: (current: DesktopUpdates) => unknown) => {
    if (updates) return observe(action, () => run(updates))
  }
  const preference = (key: 'automaticUpdates' | 'startAtLogin' | 'background', enabled: boolean) =>
    invoke('app.preferences', current => {
      current.setPreference(key, enabled)
      return { applied: current.preferences[key] === enabled }
    })
  return [
    { label: updates?.status.version ? `${updates.status.state} · ${updates.status.version}` : updates?.status.state || 'Automatic updates', enabled: false },
    { label: 'Check for updates', enabled: !!updates?.enabled,
      click: () => invoke('app.update-check', current => { void current.check() }) },
    { label: 'Restart to update', enabled: !!updates?.canRequestRestart,
      click: () => invoke('app.update-restart', current => { void current.restartIfSafe(true) }) },
    { label: 'Automatic updates and safe restarts', type: 'checkbox', checked: updates?.preferences.automaticUpdates ?? true,
      enabled: !updates?.policyManaged,
      click: item => preference('automaticUpdates', item.checked) },
    { label: 'Start at login', type: 'checkbox', checked: updates?.preferences.startAtLogin ?? true,
      click: item => preference('startAtLogin', item.checked) },
    { label: 'Keep running in background', type: 'checkbox', checked: updates?.preferences.background ?? true,
      click: item => preference('background', item.checked) },
  ]
}
