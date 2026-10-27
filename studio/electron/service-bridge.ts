import { app, dialog, ipcMain, net, powerMonitor, safeStorage, shell, type BrowserWindow, type IpcMainInvokeEvent } from 'electron'
import { spawn, type ChildProcess } from 'node:child_process'
import { randomUUID } from 'node:crypto'
import { AsyncLocalStorage } from 'node:async_hooks'
import { lstat, mkdir, mkdtemp, readFile, readdir, rm, writeFile } from 'node:fs/promises'
import { isAbsolute, join } from 'node:path'
import { existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from 'node:fs'
import { WorkspaceStore, workspaceIdentity } from './workspace-store.js'
import { WorkspaceConnections, isWorkspaceSession } from './workspace-connections.js'
import { markWorkspaceSelection } from './workspace-selection.js'
import { WorkspacePasswordAuth, type SignInRequest } from './workspace-auth.js'
import { WorkspaceCompanyAuth } from './workspace-company-auth.js'
import { macosCredentialCipher, macosCredentialMemory } from './macos-credentials.js'
import { workspaceFetch } from './workspace-fetch.js'
import { ServiceRequests } from './service-requests.js'
import { LocalWorkspace, localEnvironment, localOptions } from './local-workspace.js'
import { localDiagnostic } from './local-diagnostics.js'
import { LocalBackups, createRecoveryKey, readBackupDocument, recoveryKey } from './local-backups.js'
import { backupResult } from './local-backup-protocol.js'
import { DesktopOperator, type DesktopRequest } from './desktop-operator.js'
import { desktopAction, desktopActions } from './desktop-actions.js'
import { DesktopWorkspaceActions } from './desktop-workspace-actions.js'
import { DesktopSources } from './desktop-sources.js'
import { sourceProcess } from './desktop-source-process.js'
import { DesktopAgents } from './desktop-agents.js'
import { HostProfiles } from './host-profiles.js'
import { hostMessages } from './host-control-messages.js'
import { ProductTelemetry, telemetryMessages } from './product-telemetry.js'
import { NativeTelemetryStore, nativeTelemetryDefinitions } from './telemetry-store.js'
import { DesktopTelemetryActivity } from './telemetry-activity.js'
import { DesktopTelemetryConditions } from './telemetry-conditions.js'
import { desktopIpcSelection, desktopTelemetryOrigins, measureDesktop } from './desktop-measurement.js'
import type { TelemetryReview, TelemetryStamp } from '../shared/product-telemetry.js'
import type { HostConnection, HostRequest } from '../shared/host-control.js'
import type { AgentInstall, AgentRemove, AgentSetup } from '../shared/desktop-agents.js'
import type { CaptureBackupInput, CaptureDrainInput, CaptureInspectInput, CaptureRestoreControl, CaptureRestoreInput, SourceConfigure, SourceControl, SourcePreviewSelection } from '../shared/desktop-sources.js'
import type { BackupSettings, DesktopOperatorStatus, LocalStatus, RecoveryReceipt } from '../shared/local-workspace.js'

const MAX_BYTES = 120 * 1024 * 1024
const selections = new Map<string, string>()
const children = new Set<ChildProcess>()

export function workspaceCipher() {
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
    return { backend, available: true, encryptedRoundTrip: true, disconnectPersisted: true, offlineInspection: true,
      forgotten: (await reopened.list()).length === 0 }
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

export function installServiceBridge(getWindow: () => BrowserWindow | null,
  appControl?: (action: string, input: Record<string, unknown>, signal: AbortSignal) => unknown) {
  let connections: WorkspaceConnections | undefined
  let local: LocalWorkspace | undefined
  let backups: LocalBackups | undefined
  let sources: DesktopSources | undefined
  let agentSetup: DesktopAgents | undefined
  let hosts: HostProfiles | undefined
  let measurements: DesktopTelemetryActivity | undefined
  let telemetryDisabledUntil = 0
  const serviceRequests = new ServiceRequests()
  const serviceOwners = new WeakSet<BrowserWindow['webContents']>()
  const telemetryPauses = new Set<string>()
  const telemetryConditions = new DesktopTelemetryConditions({ online: () => net.isOnline(),
    thermal: () => powerMonitor.getCurrentThermalState() })
  function pauseTelemetry(reason: string) { telemetryPauses.add(reason); measurements?.pauseDelivery(reason) }
  function resumeTelemetry(reason: string) { telemetryPauses.delete(reason); measurements?.resumeDelivery(reason) }
  const backupSelections = new Map<string, { kind: 'folder' | 'file'; path: string }>()
  let localOpenGeneration = 0
  let localSwitching = false
  let operator: DesktopOperator | undefined
  let operatorInfo: DesktopOperatorStatus | undefined
  let operatorMutation: string | undefined
  let operatorWork: Promise<unknown> | undefined
  let operatorSelectionChanged = false
  const operatorContext = new AsyncLocalStorage<string>()
  function requireLocalSteady(): void {
    if (localSwitching) throw new Error('The local workspace is switching. Wait for it to finish.')
    if (operatorMutation && operatorContext.getStore() !== operatorMutation) throw new Error('A local agent operation is finishing. Wait for it to finish or cancel the backup.')
  }
  async function disconnectForLocalSelection(): Promise<void> {
    await workspaceConnections().disconnect()
    if (operatorMutation && operatorContext.getStore() === operatorMutation) operatorSelectionChanged = true
  }
  type LocalPreferences = { selected: boolean; startWithApp: boolean; recoveryRoot?: string }
  function localPreferences(): LocalPreferences {
    try {
      const body = readFileSync(join(app.getPath('userData'), 'local-workspace-preferences.json'), 'utf8')
      if (body.length > 2048) throw new Error('Invalid local preferences')
      const value = JSON.parse(body)
      if (typeof value.selected !== 'boolean' || typeof value.startWithApp !== 'boolean') throw new Error('Invalid local preferences')
      if (value.recoveryRoot !== undefined && (typeof value.recoveryRoot !== 'string' || !/^[a-f0-9-]{36}$/.test(value.recoveryRoot))) throw new Error('Invalid local workspace selection')
      return { selected: value.selected, startWithApp: value.startWithApp, recoveryRoot: value.recoveryRoot }
    } catch { return { selected: false, startWithApp: true } }
  }
  function saveLocalPreferences(value: LocalPreferences) {
    const file = join(app.getPath('userData'), 'local-workspace-preferences.json')
    mkdirSync(app.getPath('userData'), { recursive: true })
    const temporary = file + '.' + randomUUID() + '.tmp'
    writeFileSync(temporary, JSON.stringify({ ...localPreferences(), ...value }), { mode: 0o600, flag: 'wx' })
    renameSync(temporary, file)
  }
  function deselectLocal() {
    ++localOpenGeneration
    const selected = localPreferences().selected
    if (selected) saveLocalPreferences({ ...localPreferences(), selected: false })
    return selected
  }
  function desktopLocalStatus(status: LocalStatus): LocalStatus {
    // The desktop may be native while its service uses OS compatibility. Add
    // this trusted observation only to IPC, without mutating engine state.
    return { ...status, operator: operatorInfo, preferences: { ...localPreferences(), originalAvailable: existsSync(join(localBase(), 'mnemion-local-workspace', 'configuration.json')) }, info: status.info ? {
      ...status.info, resources: { ...status.info.resources, desktop_architecture: process.arch },
    } : undefined }
  }
  function localBase(create = true): string {
    const base = process.env.MNEMION_STUDIO_USER_DATA ? app.getPath('userData') :
      process.platform === 'win32' ? (process.env.LOCALAPPDATA || join(app.getPath('home'), 'AppData', 'Local')) :
      process.platform === 'darwin' ? app.getPath('appData') : (process.env.XDG_DATA_HOME || join(app.getPath('home'), '.local', 'share'))
    if (create) mkdirSync(base, { recursive: true, mode: 0o700 })
    return base
  }
  function localWorkspace(): LocalWorkspace {
    if (local) return local
    const selected = localPreferences().recoveryRoot
    const root = selected ? join(localBase(), 'mnemion-recovered-workspaces', selected) : join(localBase(), 'mnemion-local-workspace')
    const executable = engineExecutable()
    const database = !app.isPackaged && process.env.MNEMION_LOCAL_DATABASE ? process.env.MNEMION_LOCAL_DATABASE : join(process.resourcesPath, 'postgresql')
    local = new LocalWorkspace({ executable, database, root, version: app.getVersion(), environment: localEnvironment(process.env, root),
      desktopMemory: () => app.getAppMetrics().reduce((sum, metric) => sum + metric.memory.workingSetSize * 1024, 0) + macosCredentialMemory() + (sources?.memoryBytes ?? 0) }, status => {
      const window = getWindow()
      if (window && !window.webContents.isDestroyed()) window.webContents.send('local:changed', desktopLocalStatus(status))
    })
    backups = new LocalBackups(local, workspaceCipher(), () => {
      const window = getWindow()
      if (window && !window.webContents.isDestroyed()) window.webContents.send('local:backups-changed')
    })
    backups.start()
    return local
  }
  function localBackups(): LocalBackups { localWorkspace(); return backups! }
  function engineExecutable(): string {
    return !app.isPackaged && process.env.MNEMION_LOCAL_ENGINE ? process.env.MNEMION_LOCAL_ENGINE :
      join(process.resourcesPath, 'engine', process.platform === 'win32' ? 'mnemion-engine.exe' : 'mnemion-engine')
  }
  function desktopSources(): DesktopSources {
    if (sources) return sources
    const root = join(localBase(), 'mnemion-desktop-sources')
    sources = new DesktopSources({ cipher: workspaceCipher(), telemetry: telemetryStore, retirementCredential: async (source, supplied) => {
      const header = 'Bearer ' + supplied
      // Renderer handles remain bound to their own origin and API prefix. The
      // server independently checks current tenant/grant authority for removal.
      return (await workspaceConnections().authorization(new URL(source.endpoint + '/v1/capture-grants/' + source.custody!.grant_id), header)).replace(/^Bearer /, '')
    }, call: sourceProcess({ executable: engineExecutable(), root,
      environment: localEnvironment(process.env, root), privateRoots: [app.getPath('userData'),
        join(localBase(), 'mnemion-local-workspace'), join(localBase(), 'mnemion-recovered-workspaces'),
        join(localBase(), 'mnemion-desktop-control'), join(localBase(), 'mnemion-desktop-agents'),
        join(localBase(), 'mnemion-host-logins')] }), changed: () => {
      const window = getWindow()
      if (window && !window.webContents.isDestroyed()) window.webContents.send('sources:changed')
    } })
    return sources
  }
  function desktopAgents(): DesktopAgents {
    if (agentSetup) return agentSetup
    const root = join(localBase(), 'mnemion-desktop-agents'), executable = engineExecutable()
    const environment = localEnvironment(process.env, root)
    for (const key of ['CODEX_HOME', 'XDG_CONFIG_HOME']) if (process.env[key]) environment[key] = process.env[key]
    agentSetup = new DesktopAgents(sourceProcess({ executable, root, privateRoots: [],
      command: 'desktop-agent', arguments: ['--engine-executable', executable], deadlineMs: 180000,
      environment }))
    return agentSetup
  }
  function hostProfiles(): HostProfiles {
    if (hosts) return hosts
    const root = join(localBase(), 'mnemion-host-logins')
    hosts = new HostProfiles(root, workspaceCipher(), sourceProcess({ executable: engineExecutable(), root,
      privateRoots: [], command: 'desktop-host', environment: localEnvironment(process.env, root),
      deadlineMs: 30000, messages: hostMessages }))
    return hosts
  }
  async function telemetryAction(action: string, input: Record<string, unknown> = {}, signal?: AbortSignal) {
    const root = join(localBase(), 'mnemion-product-telemetry')
    const result = await new ProductTelemetry(sourceProcess({ executable: engineExecutable(), root,
      privateRoots: [], command: 'telemetry', environment: localEnvironment(process.env, root),
      deadlineMs: 15000, messages: telemetryMessages }), () => {
      telemetryDisabledUntil = performance.now() + 60000
      measurements?.noteUserDisabled(telemetryDisabledUntil)
    }).execute(action, input, signal)
    const inspection = result as unknown as Partial<TelemetryReview>
    if (action === 'telemetry.approve_report' && inspection.review?.outcome === 'approved' && inspection.status?.effective_enabled === true && !signal?.aborted) {
      const owner = telemetryStore()
      if (owner instanceof DesktopTelemetryActivity) owner.offerApproved({ revision: inspection.status.revision,
        store_generation: inspection.status.store_generation })
    }
    return result
  }
  function telemetryStore(): NativeTelemetryStore {
    if (!measurements) {
      const { disclosure, catalog } = nativeTelemetryDefinitions()
      measurements = new DesktopTelemetryActivity(join(localBase(false), 'mnemion-product-telemetry'), disclosure, catalog,
        () => telemetryConditions.read(), undefined, undefined,
        { prepare: stop => telemetryConditions.prepare(stop), close: () => telemetryConditions.close() })
      measurements.noteUserDisabled(telemetryDisabledUntil)
      for (const reason of telemetryPauses) measurements.pauseDelivery(reason)
    }
    return measurements
  }
  function measureAction<T>(action: string, input: Record<string, unknown>, surface: 'desktop' | 'native_agent', run: () => T | Promise<T>): T | Promise<T> {
    let store: NativeTelemetryStore
    try { store = telemetryStore() } catch { return run() }
    return measureDesktop(store, action, input, surface, run)
  }
  function handle(channel: string, listener: Parameters<typeof ipcMain.handle>[1]): void {
    ipcMain.handle(channel, (event, ...args) => {
      let selection: ReturnType<typeof desktopIpcSelection> = null
      try { selection = desktopIpcSelection(channel, args) } catch { /* Optional ownership selection. */ }
      if (!selection) return listener(event, ...args)
      trusted(event)
      return measureAction(selection.action, selection.input, 'desktop', () => listener(event, ...args))
    })
  }
  function hostAction(action: string, input: Record<string, unknown>, signal?: AbortSignal) {
    desktopAction(action, input)
    switch (action) {
      case 'host.profiles': return hostProfiles().status()
      case 'host.schema': return hostProfiles().schema(signal)
      case 'host.inspect': return hostProfiles().inspect(input.id as string, signal)
      case 'host.create': return hostProfiles().create(input.name as string, signal)
      case 'host.enroll': return hostProfiles().enroll(input.id as string, input.connection as HostConnection, input.confirm === true, signal)
      case 'host.forget': return hostProfiles().remove(input.id as string, input.confirm === true, input.acknowledge_outstanding === true)
      case 'host.recoveries': return hostProfiles().recoveries()
      case 'host.recovery': return hostProfiles().recovery(input.id as string)
      case 'host.request.archive': return hostProfiles().archiveRequest(input.id as string, input.confirm === true)
      case 'host.request': return hostProfiles().request(input.id as string, input.request as HostRequest, signal)
      default: throw new Error('Choose a documented host-control action.')
    }
  }
  function workspaceConnections(): WorkspaceConnections {
    const signInRequest: SignInRequest = async (endpoint, operation, input) => {
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
    }
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
    }, new WorkspacePasswordAuth(signInRequest), bookmark => localWorkspace().prepareSavedConnection(bookmark.endpoint, bookmark.tenantId, localPreferences().startWithApp), sessionToken => {
      const window = getWindow()
      if (window && !window.webContents.isDestroyed()) window.webContents.send('workspaces:closed', sessionToken)
    }, async (endpoint, credential) => {
      let response: Response
      try {
        response = await workspaceFetch(net.fetch.bind(net), endpoint + '/v1/recovery-directory', {
          headers: { Authorization: 'Bearer ' + credential, Accept: 'application/json' },
          redirect: 'error', credentials: 'omit', signal: AbortSignal.timeout(4000),
        })
      } catch { return undefined }
      if (!response.ok) {
        await response.body?.cancel()
        return response.status === 401 || response.status === 403 ? null : undefined
      }
      try { return JSON.parse(Buffer.from(await boundedBody(response, 16 * 1024)).toString('utf8')) }
      catch { throw new Error('The workspace did not return a valid recovery directory.') }
    }, new WorkspaceCompanyAuth(signInRequest, url => shell.openExternal(url)))
    return connections
  }
  function trusted(event: IpcMainInvokeEvent) {
    const window = getWindow()
    if (!window || event.sender !== window.webContents || event.senderFrame !== window.webContents.mainFrame) {
      throw new Error('This request did not come from Studio')
    }
  }

  handle('workspaces:status', event => { trusted(event); return workspaceConnections().status() })
  handle('workspaces:inspect', (event, id: unknown) => {
    trusted(event)
    if (typeof id !== 'string' || id.length > 64) throw new Error('Choose a saved workspace.')
    return workspaceConnections().inspect(id)
  })
  handle('workspaces:recovery-refresh', (event, sessionToken: unknown) => {
    trusted(event)
    requireLocalSteady()
    if (typeof sessionToken !== 'string' || sessionToken.length > 128) throw new Error('Use the active workspace connection.')
    return workspaceConnections().refreshRecovery(sessionToken)
  })
  handle('workspaces:resume', event => { trusted(event); requireLocalSteady(); return workspaceConnections().resume() })
  handle('workspaces:invitation-preview', (event, input: unknown) => {
    trusted(event)
    if (!input || typeof input !== 'object' || Array.isArray(input)) throw new Error('Paste a complete invitation.')
    const value = input as { endpoint: string; invitation: string }
    if (typeof value.endpoint !== 'string' || typeof value.invitation !== 'string' ||
        Object.keys(value).some(key => !['endpoint', 'invitation'].includes(key))) throw new Error('Paste a complete invitation.')
    return workspaceConnections().previewInvitation(value.endpoint, value.invitation)
  })
  for (const action of ['sign-in', 'invitation-accept', 'company-sign-in'] as const) {
    handle('workspaces:' + action, (event, input: unknown) => {
      trusted(event)
      requireLocalSteady()
      if (!input || typeof input !== 'object' || Array.isArray(input)) throw new Error('Invalid sign-in request.')
      const value = input as { endpoint: string; credentials: unknown; remember: boolean }
      if (typeof value.endpoint !== 'string' || typeof value.remember !== 'boolean' ||
          Object.keys(value).some(key => !['endpoint', 'credentials', 'remember'].includes(key))) throw new Error('Invalid sign-in request.')
      deselectLocal()
      return action === 'company-sign-in' ? workspaceConnections().companySignIn(value.endpoint, value.credentials, value.remember) :
        action === 'sign-in' ? workspaceConnections().signIn(value.endpoint, value.credentials, value.remember) :
        workspaceConnections().acceptInvitation(value.endpoint, value.credentials, value.remember)
    })
  }
  handle('workspaces:company-configuration', (event, input: unknown) => {
    trusted(event)
    if (!input || typeof input !== 'object' || Array.isArray(input)) throw new Error('Use a workspace sign-in link.')
    const value = input as { endpoint: string; workspace_id: string }
    if (typeof value.endpoint !== 'string' || typeof value.workspace_id !== 'string' ||
        Object.keys(value).some(key => !['endpoint', 'workspace_id'].includes(key))) throw new Error('Use a workspace sign-in link.')
    return workspaceConnections().companyConfiguration(value.endpoint, value.workspace_id)
  })
  handle('workspaces:company-cancel', event => { trusted(event); requireLocalSteady(); workspaceConnections().cancelCompanySignIn() })
  handle('workspaces:connect', (event, input: unknown) => {
    trusted(event)
    requireLocalSteady()
    if (!input || typeof input !== 'object' || Array.isArray(input)) throw new Error('Invalid workspace connection.')
    const value = input as { endpoint: string; credential: string; remember: boolean }
    if (typeof value.endpoint !== 'string' || typeof value.credential !== 'string' || typeof value.remember !== 'boolean' ||
        Object.keys(value).some(key => !['endpoint', 'credential', 'remember'].includes(key))) throw new Error('Invalid workspace connection.')
    deselectLocal()
    return workspaceConnections().connect(value.endpoint, value.credential, value.remember)
  })
  handle('workspaces:restore', async (event, id: unknown) => {
    trusted(event)
    requireLocalSteady()
    if (typeof id !== 'string' || id.length > 64) throw new Error('Choose a saved workspace.')
    const fromLocal = deselectLocal()
    const result = await workspaceConnections().restore(id)
    return fromLocal ? markWorkspaceSelection(result, 'switched') : result
  })
  handle('workspaces:forget', (event, id: unknown) => {
    trusted(event)
    requireLocalSteady()
    if (typeof id !== 'string' || id.length > 64) throw new Error('Choose a saved workspace.')
    return workspaceConnections().forget(id)
  })
  handle('workspaces:disconnect', event => { trusted(event); requireLocalSteady(); deselectLocal(); return workspaceConnections().disconnect() })
  handle('workspaces:reset', event => { trusted(event); requireLocalSteady(); return workspaceConnections().reset() })

  async function localStatus(): Promise<LocalStatus> {
    const host = localWorkspace()
    if (localSwitching) return desktopLocalStatus({ ...host.status, state: 'starting', stage: 'recovery_switch', message: 'Switching to the selected local workspace…' })
    if (host.status.available) await host.inspect()
    return desktopLocalStatus(host.status)
  }
  handle('local:status', event => { trusted(event); return localStatus() })
  handle('telemetry:action', (event, action: string, input: Record<string, unknown> = {}) => {
    trusted(event)
    if (!input || typeof input !== 'object' || Array.isArray(input)) throw new Error(telemetryMessages.telemetry_invalid_request)
    return telemetryAction(action, input)
  })
  handle('telemetry:snapshot', async (event, workflow?: unknown) => {
    trusted(event)
    // Fixed UI scopes let the store drop already-exhausted samples before
    // opening SQLite. A renderer cannot choose another producer's surface.
    if (workflow !== undefined && (typeof workflow !== 'string' || workflow.length > 128)) return null
    try { return await telemetryStore().snapshot(workflow, workflow === undefined ? undefined : 'desktop') } catch { return null }
  })
  handle('telemetry:record', async (event, input: unknown, stamp: TelemetryStamp) => {
    trusted(event)
    try {
      // Only a paired desktop UI submission/outcome can enter this bridge.
      // It cannot assign native-agent ownership or submit resource samples.
      if (!Array.isArray(input) || input.length !== 2) return false
      const [submission, outcome] = input
      if (!submission || !outcome || submission.kind !== 'submission' || outcome.kind !== 'outcome' ||
          submission.surface !== 'desktop' || outcome.surface !== 'desktop' || submission.workflow !== outcome.workflow) return false
      return await telemetryStore().recordMany(input, stamp)
    } catch { return false }
  })
  handle('agents:status', event => { trusted(event); return desktopAgents().status() })
  handle('hosts:action', (event, action: string, input: Record<string, unknown>) => {
    trusted(event)
    if (!input || typeof input !== 'object' || Array.isArray(input) || Buffer.byteLength(JSON.stringify(input)) > 24576) throw new Error('Use a bounded host-control request.')
    return hostAction(action, input)
  })
  handle('agents:choose', async (event, client: unknown) => {
    trusted(event)
    const profile = (await desktopAgents().status()).profiles.find(item => item.client === client)
    if (!profile) throw new Error('Choose an agent profile.')
    const result = await dialog.showSaveDialog({ title: 'Choose the agent configuration file',
      ...(profile.config_path ? { defaultPath: profile.config_path } : {}),
      filters: [{ name: 'Agent configuration', extensions: ['codex', 'grok-build'].includes(profile.client) ? ['toml'] : profile.client === 'hermes' ? ['yaml', 'yml'] : profile.client === 'openclaw' ? ['json', 'json5'] : ['json'] }] })
    return result.canceled ? null : result.filePath ?? null
  })
  handle('agents:preview', (event, setup: AgentSetup) => { trusted(event); return desktopAgents().preview(setup) })
  handle('agents:install', (event, input: AgentInstall) => { trusted(event); requireLocalSteady(); return desktopAgents().install(input) })
  handle('agents:remove', (event, input: AgentRemove) => { trusted(event); requireLocalSteady(); return desktopAgents().remove(input) })
  handle('sources:status', event => { trusted(event); return desktopSources().status() })
  handle('sources:preview', (event, selection: SourcePreviewSelection) => { trusted(event); return desktopSources().preview(selection) })
  handle('sources:backup', (event, input: CaptureBackupInput) => { trusted(event); requireLocalSteady(); return desktopSources().backup(input) })
  handle('sources:backup-inspect', (event, input: CaptureInspectInput) => { trusted(event); requireLocalSteady(); return desktopSources().inspectBackup(input) })
  handle('sources:restore', (event, input: CaptureRestoreInput) => { trusted(event); requireLocalSteady(); return desktopSources().restore(input) })
  handle('sources:drain', (event, input: CaptureDrainInput) => { trusted(event); requireLocalSteady(); return desktopSources().drain(input) })
  handle('sources:recoveries', event => { trusted(event); requireLocalSteady(); return desktopSources().recoveries() })
  handle('sources:restore-finish', (event, input: CaptureRestoreControl) => { trusted(event); requireLocalSteady(); return desktopSources().finishRecovery(input) })
  handle('sources:restore-discard', (event, input: CaptureRestoreControl) => { trusted(event); requireLocalSteady(); return desktopSources().finishRecovery(input, true) })
  handle('sources:backup-choose', async (event, kind: unknown) => {
    trusted(event)
    const filters = [{ name: 'Mnemion capture archive', extensions: ['mnemion-capture'] }]
    if (kind === 'save') {
      const result = await dialog.showSaveDialog({ title: 'Save an encrypted capture backup', filters,
        defaultPath: join(app.getPath('documents'), `mnemion-capture-${Date.now()}.mnemion-capture`) })
      return result.canceled ? null : result.filePath ?? null
    }
    if (kind !== 'open') throw new Error('Choose a capture archive operation.')
    const result = await dialog.showOpenDialog({ title: 'Inspect an encrypted capture backup', filters, properties: ['openFile'] })
    return result.canceled ? null : result.filePaths[0] ?? null
  })
  handle('sources:choose', async event => {
    trusted(event)
    const result = await dialog.showOpenDialog({ title: 'Choose a memory source folder', properties: ['openDirectory'] })
    return result.canceled ? null : result.filePaths[0] ?? null
  })
  handle('sources:configure', (event, input: SourceConfigure) => {
    trusted(event); requireLocalSteady(); return desktopSources().configure(input)
  })
  handle('sources:control', (event, action: unknown, input: SourceControl) => {
    trusted(event); requireLocalSteady()
    if (action !== 'pause' && action !== 'sync' && action !== 'remove' && action !== 'repair') throw new Error('Choose a source control.')
    return desktopSources().control(action, input)
  })
  async function createLocal(input: unknown): Promise<LocalStatus> {
    requireLocalSteady()
    const options = localOptions(input)
    const host = localWorkspace(), generation = ++localOpenGeneration
    saveLocalPreferences({ selected: true, startWithApp: true })
    await disconnectForLocalSelection()
    if (generation !== localOpenGeneration) throw new Error('Another workspace connection was selected.')
    return desktopLocalStatus(await host.start(options))
  }
  handle('local:create', (event, input: unknown) => { trusted(event); return createLocal(input) })
  async function startLocal(): Promise<LocalStatus> {
    requireLocalSteady()
    ++localOpenGeneration
    saveLocalPreferences({ ...localPreferences(), startWithApp: true })
    return desktopLocalStatus(await localWorkspace().start())
  }
  handle('local:start', event => { trusted(event); return startLocal() })
  handle('local:memory', async (event, input: unknown) => {
    trusted(event)
    requireLocalSteady()
    return desktopLocalStatus(await localWorkspace().changeMemory(input))
  })
  handle('local:port', async (event, input: unknown) => {
    trusted(event)
    requireLocalSteady()
    return desktopLocalStatus(await localWorkspace().changePort(input))
  })
  handle('local:remote', async (event, input: unknown) => {
    trusted(event)
    requireLocalSteady()
    return desktopLocalStatus(await localWorkspace().changeRemote(input))
  })
  handle('local:remote-check', async (event, input: unknown) => {
    trusted(event)
    requireLocalSteady()
    return desktopLocalStatus(await localWorkspace().checkRemote(input))
  })
  handle('local:models', async (event, input: unknown) => {
    trusted(event)
    requireLocalSteady()
    return desktopLocalStatus(await localWorkspace().changeModels(input))
  })
  handle('local:company', async (event, input: unknown) => {
    trusted(event)
    requireLocalSteady()
    return desktopLocalStatus(await localWorkspace().changeCompany(input))
  })
  handle('local:company-discover', async (event, input: unknown) => {
    trusted(event)
    requireLocalSteady()
    return localWorkspace().discoverCompany(input)
  })
  handle('local:vault', async (event, input: unknown) => {
    trusted(event)
    requireLocalSteady()
    return desktopLocalStatus(await localWorkspace().changeVault(input))
  })
  handle('local:vault-key', async (event, input: unknown) => {
    trusted(event)
    requireLocalSteady()
    return localWorkspace().revealVaultKey(input)
  })
  handle('local:journal-choose', async (event, kind: unknown) => {
    trusted(event)
    if (kind !== 'identity' && kind !== 'known_hosts') throw new Error('Choose an SSH deploy key or pinned known-hosts file.')
    const selected = await dialog.showOpenDialog(getWindow()!, {
      title: kind === 'identity' ? 'Choose this repository’s private SSH deploy key' : 'Choose its verified SSH known-hosts file',
      properties: ['openFile'],
    })
    return selected.canceled ? null : selected.filePaths[0] ?? null
  })
  handle('local:journal', async (event, input: unknown) => {
    trusted(event)
    requireLocalSteady()
    return desktopLocalStatus(await localWorkspace().changeJournal(input))
  })
  async function openLocal() {
    requireLocalSteady()
    const generation = ++localOpenGeneration
    const connection = localWorkspace().privateConnection()
    const session = await workspaceConnections().connect(connection.endpoint, connection.credential, false)
    if (generation !== localOpenGeneration) throw new Error('Another workspace connection was selected.')
    saveLocalPreferences({ ...localPreferences(), selected: true })
    return session
  }
  handle('local:open', event => { trusted(event); return openLocal() })
  async function stopLocal(): Promise<boolean> {
    requireLocalSteady()
    if (backups?.busy && !local?.backupActive) throw new Error('Finish or cancel the backup settings operation before stopping the workspace.')
    const host = localWorkspace()
    ++localOpenGeneration
    const selected = localPreferences().selected
    saveLocalPreferences({ selected: false, startWithApp: false })
    if (selected) await disconnectForLocalSelection()
    return host.stop()
  }
  handle('local:stop', event => { trusted(event); return stopLocal() })

  async function backupStatus() {
    const host = localWorkspace()
    if (!host.status.info && !host.busy) await host.inspect()
    return localBackups().status()
  }
  handle('local:backup-status', event => { trusted(event); return backupStatus() })
  handle('local:backup-key', event => { trusted(event); return createRecoveryKey() })
  handle('local:backup-choose', async (event, kind: unknown) => {
    trusted(event)
    if (kind !== 'folder' && kind !== 'file') throw new Error('Choose a backup folder or encrypted recovery file.')
    const selected = await dialog.showOpenDialog(getWindow()!, kind === 'folder'
      ? { title: 'Choose a backup folder', properties: ['openDirectory', 'createDirectory'] }
      : { title: 'Choose an encrypted snapshot, server package or access ledger', properties: ['openFile'], filters: [{ name: 'Mnemion recovery files', extensions: ['enc', 'mnemion-host', 'mnemion-ledger'] }, { name: 'All files', extensions: ['*'] }] })
    if (selected.canceled || !selected.filePaths[0]) return null
    const id = randomUUID(), path = selected.filePaths[0]
    while (backupSelections.size >= 16) backupSelections.delete(backupSelections.keys().next().value!)
    backupSelections.set(id, { kind, path })
    return { id, path }
  })
  function backupSelection(id: unknown, kind: 'folder' | 'file'): string {
    const value = typeof id === 'string' ? backupSelections.get(id) : undefined
    if (!value || value.kind !== kind) throw new Error('Choose the recovery file or folder again.')
    return value.path
  }
  function backupInput(value: unknown): Record<string, any> {
    if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('Check the backup settings.')
    return value as Record<string, any>
  }
  handle('local:backup-configure', async (event, input: unknown) => {
    trusted(event)
    requireLocalSteady()
    const value = backupInput(input)
    const manager = localBackups()
    const destination = value.destination_selection == null ? (await manager.status()).configuration?.destination : backupSelection(value.destination_selection, 'folder')
    if (!destination) throw new Error('Choose the backup folder first.')
    return manager.configure({ expected_revision: value.expected_revision, destination, enabled: value.enabled,
      snapshot_hours: value.snapshot_hours, ledger_minutes: value.ledger_minutes, recovery_key: value.recovery_key, key_saved: value.key_saved, retention: value.retention })
  })
  handle('local:backup-inventory', event => { trusted(event); requireLocalSteady(); return localBackups().inventory() })
  handle('local:backup-prune', (event, input: unknown) => {
    trusted(event); requireLocalSteady()
    const value = backupInput(input)
    return localBackups().prune({ expected_revision: value.expected_revision, plan_token: value.plan_token, confirm: value.confirm })
  })
  handle('local:backup-run', async (event, input: unknown) => {
    trusted(event)
    requireLocalSteady()
    const value = backupInput(input)
    if (value.ledger_only !== undefined && typeof value.ledger_only !== 'boolean') throw new Error('Choose a snapshot or ledger backup.')
    return localBackups().run(value.ledger_only === true, value.recovery_key)
  })
  handle('local:backup-cancel', event => {
    trusted(event); localBackups().cancel(); return desktopLocalStatus(localWorkspace().status)
  })
  handle('local:backup-inspect', async (event, input: unknown) => {
    trusted(event)
    requireLocalSteady()
    const value = backupInput(input)
    return localWorkspace().runBackup('backup-inspect', { source: backupSelection(value.selection_id, 'file'), recovery_key: recoveryKey(value.recovery_key) })
  })
  async function restoreBackup(value: Record<string, any>, source: string, ledger_source: string | null, signal?: AbortSignal) {
    requireLocalSteady()
    const host = localWorkspace()
    await host.waitForInspection()
    signal?.throwIfAborted()
    if (backups?.busy || host.busy) throw new Error('Finish the current local operation before restoring.')
    const id = randomUUID(), parent = join(localBase(), 'mnemion-recovered-workspaces')
    await mkdir(parent, { recursive: true, mode: 0o700 })
    const receipt = await host.runBackup('backup-restore', { source, ledger_source, destination: join(parent, id),
      recovery_key: recoveryKey(value.recovery_key), ledger_key: value.ledger_key == null ? null : recoveryKey(value.ledger_key),
      snapshot_sha256: value.snapshot_sha256, ledger_sha256: value.ledger_sha256,
      primary_tenant_id: value.primary_tenant_id, trusted_backup_confirmed: value.trusted_backup_confirmed,
      source_kind: value.source_kind, host_data_only_confirmed: value.host_data_only_confirmed }, signal) as RecoveryReceipt
    return { id, receipt }
  }
  handle('local:backup-restore', (event, input: unknown) => {
    trusted(event)
    const value = backupInput(input)
    return restoreBackup(value, backupSelection(value.snapshot_selection, 'file'), value.ledger_selection == null ? null : backupSelection(value.ledger_selection, 'file'))
  })
  async function recoveryCopy(id: unknown): Promise<RecoveryReceipt> {
    if (typeof id !== 'string' || !/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/.test(id)) throw new Error('Choose a verified recovery copy.')
    const root = join(localBase(), 'mnemion-recovered-workspaces', id)
    const directory = await lstat(root)
    if (!directory.isDirectory() || directory.isSymbolicLink()) throw new Error('The recovery data folder is not available.')
    const receipt = backupResult('backup-restore', await readBackupDocument(join(root, 'recovery.json'))) as RecoveryReceipt
    if (receipt.data_directory !== root) throw new Error('The recovery copy does not match its saved location.')
    return receipt
  }
  async function recoveryCopies() {
    const parent = join(localBase(), 'mnemion-recovered-workspaces')
    let entries
    try { entries = await readdir(parent, { withFileTypes: true }) } catch (error) {
      if ((error as NodeJS.ErrnoException).code === 'ENOENT') return []
      throw new Error('The local recovery directory could not be read.')
    }
    const candidates = entries.filter(entry => entry.isDirectory() && /^[a-f0-9-]{36}$/.test(entry.name)).slice(0, 64)
    const copies = await Promise.all(candidates.map(async entry => {
      try { return { id: entry.name, receipt: await recoveryCopy(entry.name) } } catch { return null }
    }))
    return copies.filter(copy => copy !== null).sort((a, b) => b.receipt.restored_at.localeCompare(a.receipt.restored_at))
  }
  handle('local:recovery-copies', event => { trusted(event); return recoveryCopies() })
  async function useRecovery(id: unknown): Promise<LocalStatus> {
    requireLocalSteady()
    const host = localWorkspace()
    localSwitching = true
    try {
      await host.waitForInspection()
      if (host.busy || backups?.busy) throw new Error('Finish or cancel the current operation before switching workspaces.')
      const receipt = id === null ? undefined : await recoveryCopy(id)
      const root = id === null ? join(localBase(), 'mnemion-local-workspace') : receipt!.data_directory
      const configuration = await readBackupDocument(join(root, 'configuration.json'))
      if (!configuration || configuration.format !== 1 || typeof configuration.workspace_id !== 'string' ||
          (receipt && configuration.workspace_id !== receipt.workspace_id)) throw new Error('This local workspace is unavailable. The current workspace has been kept open.')
      if (!await host.close()) throw new Error('The current workspace is still stopping. Its data was retained.')
      ++localOpenGeneration
      await disconnectForLocalSelection()
      backups?.close()
      local = undefined; backups = undefined
      saveLocalPreferences({ selected: true, startWithApp: true, recoveryRoot: id === null ? undefined : id as string })
      return desktopLocalStatus(await localWorkspace().start())
    } finally { localSwitching = false }
  }
  handle('local:recovery-use', (event, id: unknown) => { trusted(event); return useRecovery(id) })

  function operatorPath(value: unknown): string {
    if (typeof value !== 'string' || !isAbsolute(value) || value.length > 4096 || /[\x00-\x1f\x7f]/.test(value)) throw new Error('Use an absolute local file or folder path without control characters.')
    return value
  }
  async function executeOperator(request: DesktopRequest, signal: AbortSignal): Promise<unknown> {
    let selecting = false
    const spec = desktopAction(request.action, request.input)
    // Privacy choice must remain available while memory or a different agent
    // operation is busy. Its own store serializes changes without a workspace.
    if (request.action.startsWith('telemetry.')) return telemetryAction(request.action, request.input, signal)
    if (spec.mutation && operatorMutation) throw new Error('Another local agent operation is finishing. Read status or cancel its backup before continuing.')
    if (spec.workspace) {
      const check = () => {
        if (request.action === 'backup.cancel') {
          if (localSwitching) throw new Error('The selected workspace is switching. Wait for it to finish.')
        } else requireLocalSteady()
      }
      check()
      const host = localWorkspace()
      if (!host.status.info && !host.busy) await host.inspect()
      await host.waitForInspection()
      signal.throwIfAborted()
      check()
      const actual = host.status.info?.settings?.workspace_id ?? null
      if (host !== local || !Object.hasOwn(request, 'expected_workspace_id') || request.expected_workspace_id !== actual) throw new Error('The selected workspace changed. Read desktop status and confirm its workspace identity before retrying.')
      if (request.action === 'local.create' && actual !== null) throw new Error('This desktop already has a local workspace. Use its start or recovery controls.')
    }
    const run = async (): Promise<unknown> => {
      signal.throwIfAborted()
      const input = request.input
      const beforeSelectionChange = async () => {
        const window = getWindow()
        if (window && !window.webContents.isDestroyed() &&
            !await window.webContents.executeJavaScript('window.mnemion?.updateSafety?.() === true')) {
          throw new Error('Save or discard edits and finish pending requests in the app before changing its workspace.')
        }
        signal.throwIfAborted()
        selecting = true
        if (window && !window.webContents.isDestroyed()) window.webContents.send('local:selection-changed', 'changing')
      }
      if (['local.company', 'local.vault', 'local.journal', 'local.models'].includes(request.action) && localPreferences().selected) {
        const window = getWindow()
        if (window && !window.webContents.isDestroyed() && !await window.webContents.executeJavaScript('window.mnemion?.updateSafety?.() === true')) throw new Error('Save or discard edits and finish pending requests in the app before restarting its workspace.')
        signal.throwIfAborted()
      }
      if (request.action === 'local.create' || request.action === 'recovery.use' ||
          (request.action === 'local.stop' && localPreferences().selected)) {
        await beforeSelectionChange()
      }
      if (request.action.startsWith('workspace.') || request.action === 'local.open') {
        if (spec.mutation) requireLocalSteady()
        return new DesktopWorkspaceActions({ connections: workspaceConnections(),
          localSelected: () => localPreferences().selected, deselectLocal, openLocal,
          beforeChange: beforeSelectionChange, changed: () => { operatorSelectionChanged = true },
        }).execute(request.action, input, signal)
      }
      if (request.action.startsWith('host.')) return hostAction(request.action, input, signal)
      switch (request.action) {
        case 'catalog': return { protocol: 1, scope: 'owning_os_account', version: app.getVersion(), operations: desktopActions,
          request_limit_bytes: 16384, response_limit_bytes: 262144, same_request_replay_seconds: 600,
          guide: 'https://github.com/Perseusxrltd/mnemion/blob/main/docs/service/desktop-operator.md',
          product_telemetry_ownership: desktopTelemetryOrigins }
        case 'status': return localStatus()
        case 'source.status': return desktopSources().status()
        case 'source.preview': return desktopSources().preview(input.selection as SourcePreviewSelection, signal)
        case 'source.backup': return desktopSources().backup(input as CaptureBackupInput, signal)
        case 'source.backup.inspect': return desktopSources().inspectBackup(input as CaptureInspectInput, signal)
        case 'source.restore': return desktopSources().restore(input as CaptureRestoreInput, signal)
        case 'source.drain': return desktopSources().drain(input as CaptureDrainInput, signal)
        case 'source.restore.list': return desktopSources().recoveries(signal)
        case 'source.restore.finish': return desktopSources().finishRecovery(input as CaptureRestoreControl, false, signal)
        case 'source.restore.discard': return desktopSources().finishRecovery(input as CaptureRestoreControl, true, signal)
        case 'agent.status': return desktopAgents().status()
        case 'agent.preview': return desktopAgents().preview(input.setup as AgentSetup, signal)
        case 'agent.install': return desktopAgents().install(input as AgentInstall, signal)
        case 'agent.remove': return desktopAgents().remove(input as AgentRemove, signal)
        case 'source.configure': return desktopSources().configure(input as SourceConfigure, signal)
        case 'source.pause': case 'source.sync': case 'source.remove': case 'source.repair':
          return desktopSources().control(request.action.slice(7) as 'pause' | 'sync' | 'remove' | 'repair', input as SourceControl)
        case 'app.status': case 'app.preferences': case 'app.update-check': case 'app.update-restart':
          if (!appControl) throw new Error('The desktop app controls are not available in this session.')
          return appControl(request.action, input, signal)
        case 'local.create': return createLocal(input)
        case 'local.start': return startLocal()
        case 'local.stop': return { stopped: await stopLocal() }
        case 'local.memory': return desktopLocalStatus(await localWorkspace().changeMemory(input))
        case 'local.port': return desktopLocalStatus(await localWorkspace().changePort(input))
        case 'local.remote': return desktopLocalStatus(await localWorkspace().changeRemote(input))
        case 'local.remote-check': return desktopLocalStatus(await localWorkspace().checkRemote(input))
        case 'local.models': return desktopLocalStatus(await localWorkspace().changeModels(input))
        case 'local.company': return desktopLocalStatus(await localWorkspace().changeCompany(input))
        case 'local.company-discover': return localWorkspace().discoverCompany(input)
        case 'local.vault': return desktopLocalStatus(await localWorkspace().changeVault(input))
        case 'local.vault-key': return localWorkspace().revealVaultKey(input)
        case 'local.journal': return desktopLocalStatus(await localWorkspace().changeJournal(input))
        case 'local.preferences':
          if (typeof input.start_with_app !== 'boolean') throw new Error('Choose whether this workspace starts with the app.')
          saveLocalPreferences({ ...localPreferences(), startWithApp: input.start_with_app })
          return desktopLocalStatus(localWorkspace().status)
        case 'backup.status': return backupStatus()
        case 'backup.key': return { recovery_key: createRecoveryKey() }
        case 'backup.configure': return localBackups().configure({ ...input, destination: operatorPath(input.destination) } as BackupSettings, signal)
        case 'backup.run':
          if (input.ledger_only !== undefined && typeof input.ledger_only !== 'boolean') throw new Error('Choose a snapshot or ledger backup.')
          return localBackups().run(input.ledger_only === true, input.recovery_key === undefined ? undefined : recoveryKey(input.recovery_key), signal)
        case 'backup.inventory': return localBackups().inventory(signal)
        case 'backup.prune':
          if (typeof input.expected_revision !== 'string' || typeof input.plan_token !== 'string' || typeof input.confirm !== 'boolean') throw new Error('Review and confirm the current cleanup plan.')
          return localBackups().prune({ expected_revision: input.expected_revision, plan_token: input.plan_token, confirm: input.confirm }, signal)
        case 'backup.cancel': localBackups().cancel(); return desktopLocalStatus(localWorkspace().status)
        case 'backup.inspect': return localWorkspace().runBackup('backup-inspect', { source: operatorPath(input.source), recovery_key: recoveryKey(input.recovery_key) }, signal)
        case 'backup.restore': return restoreBackup(input, operatorPath(input.source), input.ledger_source == null ? null : operatorPath(input.ledger_source), signal)
        case 'recovery.list': return recoveryCopies()
        case 'recovery.use': return useRecovery(input.id)
        default: throw new Error('Choose an operation from the desktop catalog.')
      }
    }
    const observedRun = () => measureAction(request.action, request.input, 'native_agent', run)
    if (!spec.mutation) return observedRun()
    // The renderer and operator share one mutation gate, including across awaits.
    if (operatorMutation) throw new Error('Another local agent operation started. Refresh status before continuing.')
    operatorMutation = request.request_id
    const work = Promise.resolve(operatorContext.run(request.request_id, observedRun))
    operatorWork = work
    try { return await work } finally {
      if (operatorWork === work) { operatorWork = undefined; operatorMutation = undefined }
      const window = getWindow()
      if (window && !window.webContents.isDestroyed()) window.webContents.send('local:changed', desktopLocalStatus(localWorkspace().status))
      if (selecting || operatorSelectionChanged) {
        const phase = operatorSelectionChanged ? 'changed' : 'unchanged'
        operatorSelectionChanged = false
        if (window && !window.webContents.isDestroyed()) window.webContents.send('local:selection-changed', phase)
      }
    }
  }

  async function bootOperator(): Promise<void> {
    if (operatorInfo) return
    desktopAgents().start()
    const directory = join(localBase(), 'mnemion-desktop-control')
    operatorInfo = { state: 'starting', message: 'Starting private controls for local agents.', control_directory: directory,
      command: { executable: engineExecutable(), arguments: ['desktop-control', '--control-directory', directory] } }
    operator = new DesktopOperator({ directory, version: app.getVersion(), execute: executeOperator,
      publish: async input => {
        const result = await runClient(['--desktop-control'], { input: JSON.stringify(input), credential: true })
        if (result.format !== 1 || result.protected !== true || result.session_id !== input.endpoint.session_id) throw new Error('The private desktop control endpoint could not be confirmed.')
      } })
    try {
      await operator.start()
      operatorInfo = { ...operatorInfo, state: 'ready', message: 'Authorized agents running under this OS account can manage this desktop through its private pipe.' }
    } catch {
      operatorInfo = { ...operatorInfo, state: 'unavailable', message: 'Private desktop controls could not start. Check the local operator guide and restart the app.' }
    }
    const window = getWindow()
    if (window && !window.webContents.isDestroyed()) window.webContents.send('local:changed', desktopLocalStatus(localWorkspace().status))
  }

  handle('service:request', async (event, input: unknown) => {
    trusted(event)
    if (!input || typeof input !== 'object') throw new Error('Invalid request')
    const request = input as { requestId?: unknown; url: unknown; method: string; headers: Record<string, string>; body?: string }
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
    const contents = event.sender, owner = contents.id
    if (!serviceOwners.has(contents)) {
      serviceOwners.add(contents)
      contents.once('destroyed', () => serviceRequests.closeOwner(owner))
      contents.on('render-process-gone', () => serviceRequests.closeOwner(owner))
      contents.on('did-start-navigation', (_event, _url, inPlace, mainFrame) => {
        if (mainFrame && !inPlace) serviceRequests.closeOwner(owner)
      })
    }
    return serviceRequests.run(owner, request.requestId, async signal => {
      signal.throwIfAborted()
      const authorization = headers.get('authorization')
      let currentAuthorization: (() => Promise<string>) | undefined
      if (authorization && isWorkspaceSession(authorization)) {
        currentAuthorization = () => workspaceConnections().authorization(url, authorization)
        // Existing session rotation owns its durable credential result. Let
        // that lookup settle, but never send memory work after cancellation.
        headers.set('authorization', await currentAuthorization())
      } else {
        url = allowedServiceUrl(request.url)
      }
      signal.throwIfAborted()
      let rejected: string | null = null
      const response = await workspaceFetch(async (address, options) => {
        const credential = new Headers(options.headers).get('authorization')
        const result = await net.fetch(address, options)
        if (result.status === 401) rejected = credential
        return result
      }, url.toString(), { method: request.method, headers, body: request.body, signal }, currentAuthorization)
      if (response.status === 401 && authorization && isWorkspaceSession(authorization) && rejected) {
        await workspaceConnections().rejectedAuthorization(authorization, rejected)
      }
      signal.throwIfAborted()
      return { status: response.status, headers: Object.fromEntries(response.headers.entries()), body: await boundedBody(response) }
    })
  })
  handle('service:cancel', (event, requestId: unknown) => {
    trusted(event)
    return serviceRequests.cancel(event.sender.id, requestId)
  })

  handle('vault:choose', async event => {
    trusted(event)
    const window = getWindow()!
    const selection = await dialog.showOpenDialog(window, { title: 'Choose an Obsidian vault folder', properties: ['openDirectory', 'createDirectory'] })
    if (selection.canceled || !selection.filePaths[0]) return null
    const id = randomUUID(), path = selection.filePaths[0]
    selections.clear()
    selections.set(id, path)
    return { id, path }
  })

  handle('vault:refresh', async (event, id: unknown, bytes: unknown) => {
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
    pauseTelemetry('quit')
    connections?.lock()
    for (const child of children) child.kill()
    selections.clear()
    backupSelections.clear()
  })
  app.on('will-quit', () => { serviceRequests.close(); measurements?.closeDelivery(); backups?.close(); void sources?.close(); void agentSetup?.close(); void hosts?.close(); void operator?.close() })
  app.whenReady().then(() => {
    powerMonitor.on('suspend', () => pauseTelemetry('suspend'))
    powerMonitor.on('resume', () => resumeTelemetry('suspend'))
  }).catch(() => {})

  return {
    localDiagnostic: () => localDiagnostic(local?.status.diagnostic),
    backupDiagnostic: () => localDiagnostic(local?.status.backup?.diagnostic),
    maintenanceTelemetry: telemetryStore,
    measureMenuAction: (action: 'app.update-check' | 'app.update-restart' | 'app.preferences', run: () => unknown) =>
      measureAction(action, {}, 'desktop', run),
    localBusy: () => localSwitching || !!operatorMutation || !!backups?.busy || !!sources?.busy || !!agentSetup?.busy || !!hosts?.busy || (local?.busy ?? false),
    localActive: () => localSwitching || !!operatorMutation || !!backups?.busy || !!sources?.busy || !!agentSetup?.busy || !!hosts?.busy || (local?.active ?? false),
    stopLocal: () => local?.stop() ?? Promise.resolve(true),
    stopLocalForUpdate: async () => {
      if (localSwitching || (sources && !sources.pauseForUpdate())) return false
      if (agentSetup && !agentSetup.pauseForUpdate()) { sources?.resumeAfterUpdate(); return false }
      if (hosts && !hosts.pauseForUpdate()) { sources?.resumeAfterUpdate(); agentSetup?.resumeAfterUpdate(); return false }
      pauseTelemetry('update')
      try {
        const stopped = await (local?.stopForUpdate() ?? Promise.resolve(true))
        if (!stopped) { resumeTelemetry('update'); sources?.resumeAfterUpdate(); agentSetup?.resumeAfterUpdate(); hosts?.resumeAfterUpdate() }
        return stopped
      } catch (error) { resumeTelemetry('update'); sources?.resumeAfterUpdate(); agentSetup?.resumeAfterUpdate(); hosts?.resumeAfterUpdate(); throw error }
    },
    resumeLocalAfterCancelledUpdate: async () => { try { await local?.cancelUpdateStop() } finally { resumeTelemetry('update'); sources?.resumeAfterUpdate(); agentSetup?.resumeAfterUpdate(); hosts?.resumeAfterUpdate() } },
    closeLocal: async () => {
      if (localSwitching) return false
      pauseTelemetry('quit')
      operator?.cancel()
      await sources?.close()
      await agentSetup?.close()
      await hosts?.close()
      const stopped = await (local?.close() ?? Promise.resolve(true))
      if (operatorWork) await Promise.race([operatorWork.catch(() => {}), new Promise(resolve => setTimeout(resolve, 5000))])
      const canClose = stopped && !operatorMutation && !backups?.busy
      if (!canClose) resumeTelemetry('quit')
      return canClose
    },
    bootOperator,
    bootLocal: async () => {
      // File sources can feed any reachable workspace without a local database.
      void desktopSources().start().catch(() => {})
      const host = localWorkspace()
      if (!host.status.available) return
      try {
        const status = await host.inspect()
        if (status.configured && localPreferences().startWithApp) await host.start()
      } catch { /* The setup screen shows the specific status when opened. */ }
    },
  }
}
