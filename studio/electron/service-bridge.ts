import { app, dialog, ipcMain, net, safeStorage, type BrowserWindow, type IpcMainInvokeEvent } from 'electron'
import { spawn, type ChildProcess } from 'node:child_process'
import { randomUUID } from 'node:crypto'
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { mkdirSync, readFileSync, renameSync, writeFileSync } from 'node:fs'
import { WorkspaceStore, workspaceIdentity } from './workspace-store.js'
import { WorkspaceConnections, isWorkspaceSession } from './workspace-connections.js'
import { WorkspacePasswordAuth } from './workspace-auth.js'
import { macosCredentialCipher, macosCredentialMemory } from './macos-credentials.js'
import { workspaceFetch } from './workspace-fetch.js'
import { LocalWorkspace, localEnvironment, localOptions } from './local-workspace.js'
import type { LocalStatus } from '../shared/local-workspace.js'

const MAX_BYTES = 120 * 1024 * 1024
const selections = new Map<string, string>()
const children = new Set<ChildProcess>()

function workspaceCipher() {
  // Windows Chromium profile keys are flushed later. Direct current-user DPAPI
  // keeps a successful save readable even if a new app profile crashes at once.
  // The bundled helper only accepts fixed operations over private process pipes.
  if (process.platform === 'win32') return {
    available: () => app.isReady(),
    encrypt: async (value: string) => {
      const result = await runClient(['--credential', 'protect'], { input: JSON.stringify({ value }), credential: true })
      if (typeof result.value !== 'string' || result.value.length > 16384 || !/^[A-Za-z0-9+/]+={0,2}$/.test(result.value)) throw new Error('Windows did not return a protected connection.')
      return Buffer.from(result.value, 'base64')
    },
    decrypt: async (value: Buffer) => {
      const result = await runClient(['--credential', 'unprotect'], { input: JSON.stringify({ value: value.toString('base64') }), credential: true })
      if (typeof result.value !== 'string' || Buffer.byteLength(result.value) > 8192) throw new Error('Windows did not unlock the saved connection.')
      return result.value
    },
  }
  if (process.platform === 'darwin') return macosCredentialCipher
  return {
    available: () => {
      try {
        return safeStorage.isEncryptionAvailable() &&
          (process.platform !== 'linux' || !['basic_text', 'unknown'].includes(safeStorage.getSelectedStorageBackend()))
      } catch { return false }
    },
    encrypt: (value: string) => safeStorage.encryptString(value),
    decrypt: (value: Buffer) => safeStorage.decryptString(value),
  }
}

/** Called only by the native packaged-app gate, with a disposable profile. */
export async function verifyWorkspaceStorage(): Promise<Record<string, unknown>> {
  const cipher = workspaceCipher()
  const backend = process.platform === 'linux' ? safeStorage.getSelectedStorageBackend() : process.platform
  const directory = await mkdtemp(join(app.getPath('userData'), '.workspace-storage-probe-'))
  try {
    const store = new WorkspaceStore(directory, cipher)
    const credential = randomUUID() + randomUUID()
    const identity = { principal_id: randomUUID(), tenant_id: randomUUID(), name: 'Storage probe', tenant_name: 'Native validation', administrator: false }
    if (!await cipher.available()) {
      let refused = false
      try { await store.save('https://memory.example.invalid', credential, identity) } catch { refused = true }
      if (!refused || (await store.list()).length) throw new Error('Unavailable secure storage must not save a workspace key')
      return { backend, available: false, plaintextFallbackRefused: true }
    }
    const bookmark = await store.save('https://memory.example.invalid', credential, identity)
    if ((await readFile(join(directory, 'connections.json'), 'utf8')).includes(credential)) throw new Error('Workspace key was stored without encryption')
    const reopened = new WorkspaceStore(directory, workspaceCipher())
    if ((await reopened.credential(bookmark.id)).credential !== credential) throw new Error('OS-protected workspace key did not round-trip')
    await reopened.select(null)
    if ((await new WorkspaceStore(directory, workspaceCipher()).status()).activeId !== null) throw new Error('Disconnect selection did not persist')
    const inspection = await reopened.inspect(bookmark.id)
    if (inspection.accessStatus !== 'recorded' || inspection.access?.identity.principal_id !== identity.principal_id ||
        inspection.access.identity.administrator !== false || inspection.access.verifiedAt !== bookmark.updatedAt ||
        JSON.stringify(inspection).includes(credential) || (await reopened.status()).activeId !== null) {
      throw new Error('Offline workspace inspection did not preserve the protected identity and paused connection')
    }
    await reopened.remove(bookmark.id)
    return { backend, available: true, encryptedRoundTrip: true, disconnectPersisted: true, offlineInspection: true, forgotten: (await reopened.list()).length === 0 }
  } finally { await rm(directory, { recursive: true, force: true }) }
}

export function localClientBusy(): boolean { return children.size > 0 }

export function allowedServiceUrl(value: unknown): URL {
  if (typeof value !== 'string' || value.length > 4096) throw new Error('Invalid service URL')
  const url = new URL(value)
  const local = ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname)
  if ((url.protocol !== 'https:' && !(url.protocol === 'http:' && local)) || url.username || url.password) {
    throw new Error('Use HTTPS for a remote memory service')
  }
  if (!url.pathname.startsWith('/v1/') && !['/health/live', '/health/ready'].includes(url.pathname)) {
    throw new Error('Only the Mnemion API is available through this bridge')
  }
  return url
}

async function boundedBody(response: Response, maximum = MAX_BYTES): Promise<Uint8Array> {
  if (Number(response.headers.get('content-length')) > maximum) throw new Error('Service response is too large')
  if (!response.body) return new Uint8Array()
  const chunks: Uint8Array[] = []
  let size = 0
  const reader = response.body.getReader()
  try {
    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      size += value.byteLength
      if (size > maximum) throw new Error('Service response is too large')
      chunks.push(value)
    }
  } finally {
    await reader.cancel().catch(() => {})
  }
  const result = new Uint8Array(size)
  let offset = 0
  for (const chunk of chunks) { result.set(chunk, offset); offset += chunk.byteLength }
  return result
}

export function clientExecutable(): string {
  return join(process.resourcesPath, 'client', process.platform === 'win32' ? 'mnemion-client.exe' : 'mnemion-client')
}

async function runClient(args: string[], options: { input?: string; credential?: boolean } = {}): Promise<Record<string, unknown>> {
  const command = app.isPackaged ? clientExecutable() : (process.env.MNEMION_BUILD_PYTHON || 'python3')
  const commandArgs = app.isPackaged ? args : [join(app.getAppPath(), '../bridge/main.py'), ...args]
  return new Promise((resolve, reject) => {
    const child = spawn(command, commandArgs, { stdio: ['pipe', 'pipe', 'pipe'], windowsHide: true })
    children.add(child)
    let output = ''
    let failure: Error | null = null
    // Wait for close after termination so the archive is not removed while the
    // Windows client still holds it, and all stdout has arrived before parsing.
    const timer = setTimeout(() => {
      failure = new Error(options.credential ? 'Windows credential protection timed out. Try again or connect without remembering.' : 'Vault refresh timed out; refresh again to reconcile its saved progress')
      child.kill()
    }, options.credential ? 15_000 : 180_000)
    // Credentials never enter command-line arguments, environment or a file.
    child.stdin.on('error', () => { failure ??= new Error('The local client could not receive the request') })
    child.stdin.end(options.input)
    child.stdout.on('data', (chunk: Buffer) => {
      output += chunk.toString('utf8')
      if (output.length > (options.credential ? 24 * 1024 : 8 * 1024 * 1024)) {
        failure = new Error('The local vault client returned too much output')
        child.kill()
      }
    })
    // Python diagnostics may contain local source paths. The structured result
    // provides the operator error without sending raw process logs to the UI.
    child.stderr.resume()
    child.on('error', () => { failure = new Error('The local vault client could not be started') })
    child.on('close', (code) => {
      clearTimeout(timer); children.delete(child)
      if (failure) { reject(failure); return }
      try {
        const result = JSON.parse(output)
        if (code !== 0 || result.error) reject(new Error(result.message || 'Vault refresh failed'))
        else resolve(result)
      } catch { reject(new Error('The local vault client did not return a valid result')) }
    })
  })
}

export async function verifyLocalClient(): Promise<Record<string, unknown>> {
  return runClient(['--version'])
}

export function installServiceBridge(getWindow: () => BrowserWindow | null) {
  let connections: WorkspaceConnections | undefined
  let local: LocalWorkspace | undefined
  let localOpenGeneration = 0
  type LocalPreferences = { selected: boolean; startWithApp: boolean }
  function localPreferences(): LocalPreferences {
    try {
      const body = readFileSync(join(app.getPath('userData'), 'local-workspace-preferences.json'), 'utf8')
      if (body.length > 2048) throw new Error('Invalid local preferences')
      const value = JSON.parse(body)
      if (typeof value.selected !== 'boolean' || typeof value.startWithApp !== 'boolean') throw new Error('Invalid local preferences')
      return value
    } catch { return { selected: false, startWithApp: true } }
  }
  function saveLocalPreferences(value: LocalPreferences) {
    const file = join(app.getPath('userData'), 'local-workspace-preferences.json')
    mkdirSync(app.getPath('userData'), { recursive: true })
    const temporary = file + '.' + randomUUID() + '.tmp'
    writeFileSync(temporary, JSON.stringify(value), { mode: 0o600, flag: 'wx' })
    renameSync(temporary, file)
  }
  function deselectLocal() {
    ++localOpenGeneration
    if (localPreferences().selected) saveLocalPreferences({ ...localPreferences(), selected: false })
  }
  function desktopLocalStatus(status: LocalStatus): LocalStatus {
    // The desktop may be native while its service uses OS compatibility. Add
    // this trusted observation only to IPC, without mutating engine state.
    return { ...status, preferences: localPreferences(), info: status.info ? {
      ...status.info, resources: { ...status.info.resources, desktop_architecture: process.arch },
    } : undefined }
  }
  function localWorkspace(): LocalWorkspace {
    if (local) return local
    const base = process.env.MNEMION_STUDIO_USER_DATA ? app.getPath('userData') :
      process.platform === 'win32' ? (process.env.LOCALAPPDATA || join(app.getPath('home'), 'AppData', 'Local')) :
      process.platform === 'darwin' ? app.getPath('appData') : (process.env.XDG_DATA_HOME || join(app.getPath('home'), '.local', 'share'))
    mkdirSync(base, { recursive: true, mode: 0o700 })
    const root = join(base, 'mnemion-local-workspace')
    const executable = !app.isPackaged && process.env.MNEMION_LOCAL_ENGINE ? process.env.MNEMION_LOCAL_ENGINE :
      join(process.resourcesPath, 'engine', process.platform === 'win32' ? 'mnemion-engine.exe' : 'mnemion-engine')
    const database = !app.isPackaged && process.env.MNEMION_LOCAL_DATABASE ? process.env.MNEMION_LOCAL_DATABASE : join(process.resourcesPath, 'postgresql')
    local = new LocalWorkspace({ executable, database, root, version: app.getVersion(), environment: localEnvironment(process.env, root),
      desktopMemory: () => app.getAppMetrics().reduce((sum, metric) => sum + metric.memory.workingSetSize * 1024, 0) + macosCredentialMemory() }, status => {
      const window = getWindow()
      if (window && !window.webContents.isDestroyed()) window.webContents.send('local:changed', desktopLocalStatus(status))
    })
    return local
  }
  function workspaceConnections(): WorkspaceConnections {
    connections ??= new WorkspaceConnections(new WorkspaceStore(join(app.getPath('userData'), 'workspaces'), workspaceCipher()), async (endpoint, credential) => {
      let response: Response
      try {
        response = await workspaceFetch(net.fetch.bind(net), endpoint + '/v1/me', {
          headers: { Authorization: 'Bearer ' + credential, Accept: 'application/json' },
          redirect: 'error', credentials: 'omit', signal: AbortSignal.timeout(15_000),
        })
      } catch { throw new Error('The workspace could not be reached. Check its address and your network or VPN. If an agent hosts it, use the host’s operator controls to check that its computer and network connection are running.') }
      if (response.headers.get('ngrok-error-code') === 'ERR_NGROK_3200') {
        await response.body?.cancel()
        throw new Error('The workspace tunnel is offline. Restart its connection through the host’s operator controls; changing the workspace key will not reconnect the host.')
      }
      if (response.status === 401 || response.status === 403) throw new Error('This key is expired, revoked or does not grant workspace access. Use a current key.')
      if (!response.ok) throw new Error('The workspace is not ready. Try again or check its service status.')
      const bytes = await boundedBody(response, 128 * 1024)
      try { return workspaceIdentity(JSON.parse(Buffer.from(bytes).toString('utf8'))) }
      catch { throw new Error('This address did not return a Mnemion workspace identity.') }
    }, new WorkspacePasswordAuth(async (endpoint, operation, input) => {
      let response: Response
      try {
        response = await workspaceFetch(net.fetch.bind(net), endpoint + '/v1/sign-in/' + operation, {
          method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
          body: JSON.stringify(input), signal: AbortSignal.timeout(20_000),
        })
      } catch { throw new Error('The workspace could not confirm this sign-in request. Check the connection and sign in again.') }
      if (!response.ok) {
        await response.body?.cancel()
        if (response.status === 404) throw new Error('Update this workspace server to use individual sign-in. Existing workspace keys still work.')
        if (response.status === 429) throw new Error('Too many sign-in attempts. Wait a few minutes and try again.')
        if (response.status === 401 || response.status === 403) throw new Error('Sign-in could not be completed. Check your login or ask for a new invitation.')
        if (response.status === 409) throw new Error('This account or login changed. Choose another login name or ask an administrator to check your sessions.')
        if (response.status === 422) throw new Error('Check the fields. Choose a unique password of at least 15 characters, such as several unrelated words.')
        throw new Error('The workspace could not complete the sign-in request. Try again when it is ready.')
      }
      try { return JSON.parse(Buffer.from(await boundedBody(response, 128 * 1024)).toString('utf8')) }
      catch { throw new Error('The workspace returned an invalid sign-in response.') }
    }), bookmark => localWorkspace().prepareSavedConnection(bookmark.endpoint, bookmark.tenantId, localPreferences().startWithApp), sessionToken => {
      const window = getWindow()
      if (window && !window.webContents.isDestroyed()) window.webContents.send('workspaces:closed', sessionToken)
    })
    return connections
  }
  function trusted(event: IpcMainInvokeEvent) {
    const window = getWindow()
    if (!window || event.sender !== window.webContents || event.senderFrame !== window.webContents.mainFrame) {
      throw new Error('This request did not come from Studio')
    }
  }

  ipcMain.handle('workspaces:status', event => { trusted(event); return workspaceConnections().status() })
  ipcMain.handle('workspaces:inspect', (event, id: unknown) => {
    trusted(event)
    if (typeof id !== 'string' || id.length > 64) throw new Error('Choose a saved workspace.')
    return workspaceConnections().inspect(id)
  })
  ipcMain.handle('workspaces:resume', event => { trusted(event); return workspaceConnections().resume() })
  ipcMain.handle('workspaces:invitation-preview', (event, input: unknown) => {
    trusted(event)
    if (!input || typeof input !== 'object' || Array.isArray(input)) throw new Error('Paste a complete invitation.')
    const value = input as { endpoint: string; invitation: string }
    if (typeof value.endpoint !== 'string' || typeof value.invitation !== 'string' ||
        Object.keys(value).some(key => !['endpoint', 'invitation'].includes(key))) throw new Error('Paste a complete invitation.')
    return workspaceConnections().previewInvitation(value.endpoint, value.invitation)
  })
  for (const action of ['sign-in', 'invitation-accept'] as const) {
    ipcMain.handle('workspaces:' + action, (event, input: unknown) => {
      trusted(event)
      if (!input || typeof input !== 'object' || Array.isArray(input)) throw new Error('Invalid sign-in request.')
      const value = input as { endpoint: string; credentials: unknown; remember: boolean }
      if (typeof value.endpoint !== 'string' || typeof value.remember !== 'boolean' ||
          Object.keys(value).some(key => !['endpoint', 'credentials', 'remember'].includes(key))) throw new Error('Invalid sign-in request.')
      deselectLocal()
      return action === 'sign-in' ? workspaceConnections().signIn(value.endpoint, value.credentials, value.remember) :
        workspaceConnections().acceptInvitation(value.endpoint, value.credentials, value.remember)
    })
  }
  ipcMain.handle('workspaces:connect', (event, input: unknown) => {
    trusted(event)
    if (!input || typeof input !== 'object' || Array.isArray(input)) throw new Error('Invalid workspace connection.')
    const value = input as { endpoint: string; credential: string; remember: boolean }
    if (typeof value.endpoint !== 'string' || typeof value.credential !== 'string' || typeof value.remember !== 'boolean' ||
        Object.keys(value).some(key => !['endpoint', 'credential', 'remember'].includes(key))) throw new Error('Invalid workspace connection.')
    deselectLocal()
    return workspaceConnections().connect(value.endpoint, value.credential, value.remember)
  })
  ipcMain.handle('workspaces:restore', (event, id: unknown) => {
    trusted(event)
    if (typeof id !== 'string' || id.length > 64) throw new Error('Choose a saved workspace.')
    deselectLocal()
    return workspaceConnections().restore(id)
  })
  ipcMain.handle('workspaces:forget', (event, id: unknown) => {
    trusted(event)
    if (typeof id !== 'string' || id.length > 64) throw new Error('Choose a saved workspace.')
    return workspaceConnections().forget(id)
  })
  ipcMain.handle('workspaces:disconnect', event => { trusted(event); deselectLocal(); return workspaceConnections().disconnect() })
  ipcMain.handle('workspaces:reset', event => { trusted(event); return workspaceConnections().reset() })

  ipcMain.handle('local:status', async event => {
    trusted(event)
    const host = localWorkspace()
    if (host.status.available) await host.inspect()
    return desktopLocalStatus(host.status)
  })
  ipcMain.handle('local:create', async (event, input: unknown) => {
    trusted(event)
    const options = localOptions(input)
    ++localOpenGeneration
    saveLocalPreferences({ selected: true, startWithApp: true })
    await workspaceConnections().disconnect()
    return desktopLocalStatus(await localWorkspace().start(options))
  })
  ipcMain.handle('local:start', async event => {
    trusted(event)
    ++localOpenGeneration
    saveLocalPreferences({ ...localPreferences(), startWithApp: true })
    return desktopLocalStatus(await localWorkspace().start())
  })
  ipcMain.handle('local:memory', async (event, input: unknown) => {
    trusted(event)
    return desktopLocalStatus(await localWorkspace().changeMemory(input))
  })
  ipcMain.handle('local:port', async (event, input: unknown) => {
    trusted(event)
    return desktopLocalStatus(await localWorkspace().changePort(input))
  })
  ipcMain.handle('local:remote', async (event, input: unknown) => {
    trusted(event)
    return desktopLocalStatus(await localWorkspace().changeRemote(input))
  })
  ipcMain.handle('local:remote-check', async (event, input: unknown) => {
    trusted(event)
    return desktopLocalStatus(await localWorkspace().checkRemote(input))
  })
  ipcMain.handle('local:open', async event => {
    trusted(event)
    const generation = ++localOpenGeneration
    const connection = localWorkspace().privateConnection()
    const session = await workspaceConnections().connect(connection.endpoint, connection.credential, false)
    if (generation !== localOpenGeneration) throw new Error('Another workspace connection was selected.')
    saveLocalPreferences({ ...localPreferences(), selected: true })
    return session
  })
  ipcMain.handle('local:stop', async event => {
    trusted(event)
    ++localOpenGeneration
    const selected = localPreferences().selected
    saveLocalPreferences({ selected: false, startWithApp: false })
    if (selected) await workspaceConnections().disconnect()
    return localWorkspace().stop()
  })

  ipcMain.handle('service:request', async (event, input: unknown) => {
    trusted(event)
    if (!input || typeof input !== 'object') throw new Error('Invalid request')
    const request = input as { url: unknown; method: string; headers: Record<string, string>; body?: string }
    if (typeof request.url !== 'string' || request.url.length > 4096) throw new Error('Invalid service URL')
    let url = new URL(request.url)
    if (!['GET', 'POST', 'PUT', 'DELETE'].includes(request.method)) throw new Error('Unsupported method')
    if (request.body !== undefined && (typeof request.body !== 'string' || Buffer.byteLength(request.body) > 2 * 1024 * 1024)) throw new Error('Request is too large')
    const headers = new Headers()
    if (!request.headers || typeof request.headers !== 'object' || Array.isArray(request.headers)) throw new Error('Invalid request headers')
    for (const [name, value] of Object.entries(request.headers || {})) {
      if (!['accept', 'authorization', 'content-type', 'idempotency-key'].includes(name.toLowerCase()) || typeof value !== 'string' || value.length > 1024) throw new Error('Unsupported request header')
      if (headers.has(name)) throw new Error('Duplicate request header')
      headers.set(name, value)
    }
    const authorization = headers.get('authorization')
    let currentAuthorization: (() => Promise<string>) | undefined
    if (authorization && isWorkspaceSession(authorization)) {
      currentAuthorization = () => workspaceConnections().authorization(url, authorization)
      headers.set('authorization', await currentAuthorization())
    } else {
      url = allowedServiceUrl(request.url)
    }
    let rejected: string | null = null
    const response = await workspaceFetch(async (address, options) => {
      const credential = new Headers(options.headers).get('authorization')
      const result = await net.fetch(address, options)
      if (result.status === 401) rejected = credential
      return result
    }, url.toString(), { method: request.method, headers, body: request.body, signal: AbortSignal.timeout(60_000) }, currentAuthorization)
    if (response.status === 401 && authorization && isWorkspaceSession(authorization) && rejected) {
      await workspaceConnections().rejectedAuthorization(authorization, rejected)
    }
    return { status: response.status, headers: Object.fromEntries(response.headers.entries()), body: await boundedBody(response) }
  })

  ipcMain.handle('vault:choose', async event => {
    trusted(event)
    const window = getWindow()!
    const selection = await dialog.showOpenDialog(window, { title: 'Choose an Obsidian vault folder', properties: ['openDirectory', 'createDirectory'] })
    if (selection.canceled || !selection.filePaths[0]) return null
    const id = randomUUID(), path = selection.filePaths[0]
    selections.clear()
    selections.set(id, path)
    return { id, path }
  })

  ipcMain.handle('vault:refresh', async (event, id: unknown, bytes: unknown) => {
    trusted(event)
    const path = typeof id === 'string' ? selections.get(id) : undefined
    if (!path) throw new Error('Choose the vault folder before refreshing')
    if (!(bytes instanceof Uint8Array) || !bytes.byteLength || bytes.byteLength > MAX_BYTES) throw new Error('Invalid vault archive')
    const directory = await mkdtemp(join(app.getPath('temp'), 'mnemion-vault-'))
    try {
      const archive = join(directory, 'export.zip')
      await writeFile(archive, bytes, { mode: 0o600, flag: 'wx' })
      return await runClient(['--archive', archive, '--vault', path])
    } finally {
      await rm(directory, { recursive: true, force: true })
    }
  })

  app.on('before-quit', () => {
    connections?.lock()
    for (const child of children) child.kill()
    selections.clear()
  })

  return {
    localBusy: () => local?.busy ?? false,
    localActive: () => local?.active ?? false,
    stopLocal: () => local?.stop() ?? Promise.resolve(true),
    stopLocalForUpdate: () => local?.stopForUpdate() ?? Promise.resolve(true),
    resumeLocalAfterCancelledUpdate: () => local?.cancelUpdateStop() ?? Promise.resolve(),
    closeLocal: () => local?.close() ?? Promise.resolve(true),
    bootLocal: async () => {
      const host = localWorkspace()
      if (!host.status.available) return
      try {
        const status = await host.inspect()
        if (status.configured && localPreferences().startWithApp) await host.start()
      } catch { /* The setup screen shows the specific status when opened. */ }
    },
  }
}
