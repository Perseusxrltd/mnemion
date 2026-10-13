/** Explicit user restarts still protect drafts, transfers and administrator policy. */
export type UpdateRestartState = {
  enabled: boolean; downloaded: boolean; idleSeconds: number;
  focused: boolean; visible: boolean; minimized: boolean; safe: boolean; busy: boolean;
  locked?: boolean;
}
export type UpdateRestartBlocker = 'disabled' | 'not-downloaded' | 'busy' | 'work' | 'focused' | 'inactivity'

export function updateRestartBlocker(value: UpdateRestartState, requested = false): UpdateRestartBlocker | null {
  if (!value.enabled) return 'disabled'
  if (!value.downloaded) return 'not-downloaded'
  if (value.busy) return 'busy'
  if (!value.safe) return 'work'
  if (requested) return null
  // Electron can retain focus after a Linux window is minimized/hidden. Only
  // an actually visible, restored focused window can represent active use.
  // A window shown by an updater can retain focus behind the OS lock screen.
  // The locked session still needs the same real inactivity and work guards.
  const activeFocus = value.focused && value.visible && !value.minimized && !value.locked
  if (activeFocus) return 'focused'
  if (!Number.isFinite(value.idleSeconds) || value.idleSeconds < 600) return 'inactivity'
  return null
}

/** Background restarts must never discard a draft or interrupt a vault transfer. */
export function canRestartForUpdate(value: UpdateRestartState, requested = false): boolean {
  return updateRestartBlocker(value, requested) === null
}

export function updateChannel(architecture: string): string {
  if (!['x64', 'arm64'].includes(architecture)) throw new Error('Unsupported update architecture')
  return `latest-${architecture}`
}

export function desktopExec(executable: string): string {
  if (!executable.startsWith('/') || /[\r\n\0]/.test(executable)) throw new Error('Invalid startup executable')
  // Desktop Entry quoting is not shell quoting. Percent introduces field codes.
  return `"${executable.replace(/([\\"`$])/g, '\\$1').replaceAll('%', '%%')}" --background`
}
