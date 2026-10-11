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
  workspaceResume: () => transfer('workspaces:resume'),
  workspaceConnect: (input: unknown) => transfer('workspaces:connect', input),
  workspaceRestore: (id: string) => transfer('workspaces:restore', id),
  workspaceForget: (id: string) => transfer('workspaces:forget', id),
  workspaceDisconnect: () => transfer('workspaces:disconnect'),
  workspaceReset: () => transfer('workspaces:reset'),
  localStatus: () => transfer('local:status'),
  localCreate: (input: unknown) => transfer('local:create', input),
  localStart: () => transfer('local:start'),
  localOpen: () => transfer('local:open'),
  localStop: () => transfer('local:stop'),
  localMemory: (input: unknown) => transfer('local:memory', input),
  localPort: (input: unknown) => transfer('local:port', input),
  onLocalStatus: (callback: (status: unknown) => void) => {
    const listener = (_event: IpcRendererEvent, status: unknown) => callback(status)
    ipcRenderer.on('local:changed', listener)
    return () => ipcRenderer.removeListener('local:changed', listener)
  },
  chooseVault: () => transfer('vault:choose'),
  refreshVault: (selection: string, bytes: Uint8Array) => transfer('vault:refresh', selection, bytes),
  updateSafety: () => {
    for (const element of edited) if (!element.isConnected) edited.delete(element)
    return pending === 0 && edited.size === 0
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
