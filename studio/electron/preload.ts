import { contextBridge, ipcRenderer, type IpcRendererEvent } from 'electron'

let pending = 0
const edited = new Set<Element>()
window.addEventListener('input', event => {
  const target = event.target
  if (target instanceof Element && !target.matches('input[type="search"], [data-update-safe]')) edited.add(target)
}, true)
window.addEventListener('change', event => {
  const target = event.target
  if (target instanceof Element && !target.matches('input[type="search"], [data-update-safe]')) edited.add(target)
}, true)
async function transfer(channel: string, ...args: unknown[]) {
  pending++
  try { return await ipcRenderer.invoke(channel, ...args) } finally { pending-- }
}

// Expose a minimal, safe bridge to the renderer
contextBridge.exposeInMainWorld('mnemion', {
  version:      () => ipcRenderer.invoke('app:version'),
  platform:     () => ipcRenderer.invoke('app:platform'),
  backendPort:  () => ipcRenderer.invoke('backend:port'),
  studioToken:  () => ipcRenderer.invoke('backend:token'),
  serviceRequest: (request: unknown) => transfer('service:request', request),
  workspaceStatus: () => transfer('workspaces:status'),
  workspaceInspect: (id: string) => transfer('workspaces:inspect', id),
  workspaceRecoveryRefresh: (sessionToken: string) => transfer('workspaces:recovery-refresh', sessionToken),
  workspaceResume: () => transfer('workspaces:resume'),
  workspaceConnect: (input: unknown) => transfer('workspaces:connect', input),
  workspaceSignIn: (input: unknown) => transfer('workspaces:sign-in', input),
  workspaceCompanyConfiguration: (input: unknown) => transfer('workspaces:company-configuration', input),
  workspaceCompanySignIn: (input: unknown) => transfer('workspaces:company-sign-in', input),
  workspaceCompanyCancel: () => transfer('workspaces:company-cancel'),
  workspaceInvitationPreview: (input: unknown) => transfer('workspaces:invitation-preview', input),
  workspaceInvitationAccept: (input: unknown) => transfer('workspaces:invitation-accept', input),
  workspaceRestore: (id: string) => transfer('workspaces:restore', id),
  workspaceForget: (id: string) => transfer('workspaces:forget', id),
  workspaceDisconnect: () => transfer('workspaces:disconnect'),
  workspaceReset: () => transfer('workspaces:reset'),
  onWorkspaceClosed: (callback: (sessionToken: string) => void) => {
    const listener = (_event: IpcRendererEvent, sessionToken: unknown) => {
      if (typeof sessionToken === 'string' && /^mnm_session_[A-Za-z0-9_-]{43}$/.test(sessionToken)) callback(sessionToken)
    }
    ipcRenderer.on('workspaces:closed', listener)
    return () => ipcRenderer.removeListener('workspaces:closed', listener)
  },
  localStatus: () => transfer('local:status'),
  localCreate: (input: unknown) => transfer('local:create', input),
  localStart: () => transfer('local:start'),
  localOpen: () => transfer('local:open'),
  localStop: () => transfer('local:stop'),
  localMemory: (input: unknown) => transfer('local:memory', input),
  localPort: (input: unknown) => transfer('local:port', input),
  localRemote: (input: unknown) => transfer('local:remote', input),
  localRemoteCheck: (input: unknown) => transfer('local:remote-check', input),
  localCompany: (input: unknown) => transfer('local:company', input),
  localCompanyDiscover: (input: unknown) => transfer('local:company-discover', input),
  localVault: (input: unknown) => transfer('local:vault', input),
  localVaultKey: (input: unknown) => transfer('local:vault-key', input),
  localBackupStatus: () => transfer('local:backup-status'),
  localBackupKey: () => transfer('local:backup-key'),
  localBackupChoose: (kind: 'folder' | 'file') => transfer('local:backup-choose', kind),
  localBackupConfigure: (input: unknown) => transfer('local:backup-configure', input),
  localBackupRun: (input: unknown) => transfer('local:backup-run', input),
  localBackupInventory: () => transfer('local:backup-inventory'),
  localBackupPrune: (input: unknown) => transfer('local:backup-prune', input),
  localBackupCancel: () => transfer('local:backup-cancel'),
  localBackupInspect: (input: unknown) => transfer('local:backup-inspect', input),
  localBackupRestore: (input: unknown) => transfer('local:backup-restore', input),
  localRecoveryCopies: () => transfer('local:recovery-copies'),
  localRecoveryUse: (id: string | null) => transfer('local:recovery-use', id),
  onBackupStatus: (callback: () => void) => {
    const listener = () => callback()
    ipcRenderer.on('local:backups-changed', listener)
    return () => ipcRenderer.removeListener('local:backups-changed', listener)
  },
  onLocalStatus: (callback: (status: unknown) => void) => {
    const listener = (_event: IpcRendererEvent, status: unknown) => callback(status)
    ipcRenderer.on('local:changed', listener)
    return () => ipcRenderer.removeListener('local:changed', listener)
  },
  onLocalSelection: (callback: (phase: 'changing' | 'changed' | 'unchanged') => void) => {
    const listener = (_event: IpcRendererEvent, phase: unknown) => {
      if (phase === 'changing' || phase === 'changed' || phase === 'unchanged') callback(phase)
    }
    ipcRenderer.on('local:selection-changed', listener)
    return () => ipcRenderer.removeListener('local:selection-changed', listener)
  },
  chooseVault: () => transfer('vault:choose'),
  refreshVault: (selection: string, bytes: Uint8Array) => transfer('vault:refresh', selection, bytes),
  updateSafety: () => {
    for (const element of edited) if (!element.isConnected) edited.delete(element)
    return pending === 0 && edited.size === 0 && document.querySelector('[data-update-pending]') === null
  },
  onNavigate: (callback: (route: string) => void) => {
    const listener = (_event: IpcRendererEvent, route: unknown) => {
      if (typeof route === 'string' && route.startsWith('/')) {
        callback(route)
      }
    }
    ipcRenderer.on('app:navigate', listener)
    return () => ipcRenderer.removeListener('app:navigate', listener)
  },
})
