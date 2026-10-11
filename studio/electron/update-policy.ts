/** Background restarts must never discard a draft or interrupt a vault transfer. */
export function canRestartForUpdate(value: {
  enabled: boolean; downloaded: boolean; idleSeconds: number;
  focused: boolean; visible: boolean; minimized: boolean; safe: boolean; busy: boolean;
}): boolean {
  // Electron can retain focus after a Linux window is minimized/hidden. Only
  // an actually visible, restored focused window can represent active use.
  const activeFocus = value.focused && value.visible && !value.minimized
  return value.enabled && value.downloaded && Number.isFinite(value.idleSeconds)
    && value.idleSeconds >= 600 && !activeFocus && value.safe && !value.busy
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
