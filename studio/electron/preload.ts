import { contextBridge, ipcRenderer } from 'electron'

// Expose a minimal, safe bridge to the renderer
contextBridge.exposeInMainWorld('mnemion', {
  version:      () => ipcRenderer.invoke('app:version'),
  platform:     () => ipcRenderer.invoke('app:platform'),
  backendPort:  () => ipcRenderer.invoke('backend:port'),
})
