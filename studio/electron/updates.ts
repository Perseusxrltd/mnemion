import { app, net, powerMonitor, session, type BrowserWindow } from 'electron'
import updaterPackage from 'electron-updater'
import { join } from 'node:path'
import { existsSync, mkdirSync, readFileSync, renameSync, rmSync, writeFileSync } from 'node:fs'
import { updateRestartBlocker, desktopExec, updateChannel, type UpdateRestartBlocker } from './update-policy.js'
import { MacUpdateBridge, type MacUpdateEvent } from './macos-updates.js'
import { WindowsUpdateBridge, type WindowsUpdateEvent, type WindowsUpdateTrust } from './windows-updates.js'
import { createWindowsUpdateFetch } from './windows-update-network.js'
import { refreshLinuxLoginEntry } from './linux-startup.js'

let autoUpdater: typeof updaterPackage.autoUpdater
type Preferences = { automaticUpdates: boolean; startAtLogin: boolean; background: boolean }
const defaults: Preferences = { automaticUpdates: true, startAtLogin: true, background: true }
const retryDelays = [60_000, 5 * 60_000, 15 * 60_000]
export type UpdateStatus = { state: string; version?: string; percent?: number; checkedAt?: string }

export class DesktopUpdates {
  preferences: Preferences = { ...defaults }
  status: UpdateStatus = { state: 'Starting' }
  private checking = false
  private checkRequested = false
  private downloaded = false
  private readyVersion?: string
  private installing = false
  private cancelDownload?: () => void
  private mac?: MacUpdateBridge
  private windows?: WindowsUpdateBridge
  private timers: NodeJS.Timeout[] = []
  private retryTimer?: NodeJS.Timeout
  private requestedRestartTimer?: NodeJS.Timeout
  private retryAttempts = 0
  private stopped = false
  private readonly path = join(app.getPath('userData'), 'desktop-preferences.json')
  private readonly managed = process.env.MNEMION_AUTO_UPDATE === '0'
  private readonly supported = app.isPackaged && !process.env.MNEMION_STUDIO_SMOKE_FILE
    && !process.env.MNEMION_STUDIO_SMOKE_HEADLESS
    && (process.platform !== 'linux' || !!process.env.APPIMAGE)

  constructor(private window: () => BrowserWindow | null, private busy: () => boolean,
    private beforeRestart: () => boolean | Promise<boolean>, private changed: () => void,
    private restartCancelled: () => void = () => {}) {
    const firstLaunch = !existsSync(this.path)
    try {
      const text = readFileSync(this.path, 'utf8')
      if (text.length > 4096) throw new Error('Invalid preferences')
      const saved = JSON.parse(text)
      for (const key of Object.keys(defaults) as (keyof Preferences)[]) {
        if (typeof saved[key] === 'boolean') this.preferences[key] = saved[key]
      }
    } catch { /* Missing or damaged preferences use the documented defaults. */ }
    if (process.env.MNEMION_START_AT_LOGIN === '0') this.preferences.startAtLogin = false
    if (this.managed) this.preferences.automaticUpdates = false
    if (firstLaunch && app.isPackaged && !process.env.MNEMION_STUDIO_SMOKE_FILE && process.env.MNEMION_STUDIO_SMOKE_HEADLESS !== '1') {
      try { this.applyLogin(); this.save() } catch { this.status = { state: 'Startup setup needs attention' } }
    }
    if (!firstLaunch && process.platform === 'linux' && this.supported && this.preferences.startAtLogin) {
      try { this.refreshLinuxLogin(process.env.APPIMAGE!) }
      catch { this.status = { state: 'Startup setup needs attention' } }
    }
    if (process.platform === 'darwin') {
      this.mac = new MacUpdateBridge(join(process.resourcesPath, '..', 'MacOS', 'MnemionUpdater'),
        event => this.platformEvent(event))
    } else if (process.platform === 'win32') {
      const trust: WindowsUpdateTrust = JSON.parse(readFileSync(new URL('./windows-updates.json', import.meta.url), 'utf8'))
      const network = session.fromPartition('mnemion-signed-updates', { cache: false })
      this.windows = new WindowsUpdateBridge({ version: app.getVersion(), architecture: process.arch,
        cacheDirectory: join(app.getPath('userData'), 'updates-windows'), applicationPath: process.execPath,
        resourcesPath: process.resourcesPath, trust }, createWindowsUpdateFetch(url => net.request({
          url, method: 'GET', session: network, redirect: 'manual', credentials: 'omit',
          cache: 'no-store', bypassCustomProtocolHandlers: true,
        })),
      event => this.platformEvent(event))
    } else {
      autoUpdater = updaterPackage.autoUpdater
      autoUpdater.setFeedURL({ provider: 'github', owner: 'Perseusxrltd', repo: 'mnemion',
        private: false, channel: updateChannel(process.arch) })
      autoUpdater.channel = updateChannel(process.arch)
      autoUpdater.allowDowngrade = false
      autoUpdater.allowPrerelease = false
      autoUpdater.disableWebInstaller = true
      autoUpdater.logger = null // Provider errors can contain URLs; expose bounded status only.
      this.applyUpdatePolicy()
      autoUpdater.on('update-available', info => this.setStatus({ state: 'Downloading update', version: info.version }))
      autoUpdater.on('update-not-available', () => {
        this.clearRetry()
        this.setStatus({ state: 'Up to date', checkedAt: new Date().toISOString() })
      })
      autoUpdater.on('download-progress', progress => this.setStatus({ state: 'Downloading update', percent: Math.round(progress.percent) }))
      autoUpdater.on('update-downloaded', info => {
        this.clearRetry()
        this.downloaded = true
        this.readyVersion = info.version
        this.setStatus({ state: 'Update ready · waiting for a safe restart', version: info.version })
      })
      autoUpdater.on('appimage-filename-updated', (filename: string) => {
        if (!this.preferences.startAtLogin) return
        try { this.refreshLinuxLogin(filename, process.env.APPIMAGE) }
        catch { this.setStatus({ state: 'Startup setup needs attention' }) }
      })
      autoUpdater.on('error', () => {
        if (this.installing) this.restartCancelled()
        this.downloaded = false
        this.installing = false
        this.scheduleRetry()
      })
    }
    this.status = { state: this.enabled ? 'Automatic updates enabled' : this.managed ? 'Updates managed by administrator' : !this.supported ? 'Updates managed by installer or package manager' : 'Automatic updates paused' }
    if (this.supported) {
      // Spread checks across an organization and avoid competing with startup.
      this.timers.push(setTimeout(() => void this.check(), 60_000 + Math.random() * 60_000))
      this.timers.push(setInterval(() => void this.check(), 6 * 60 * 60_000 + Math.random() * 15 * 60_000))
      this.timers.push(setInterval(() => void this.restartIfSafe(), 30_000))
      for (const timer of this.timers) timer.unref()
    }
    app.on('will-quit', () => {
      this.stopped = true
      this.clearRetry()
      if (this.requestedRestartTimer) clearTimeout(this.requestedRestartTimer)
      for (const timer of this.timers) clearTimeout(timer)
    })
  }

  get enabled() { return this.supported && !this.managed && this.preferences.automaticUpdates }
  get policyManaged() { return this.managed }
  get canRequestRestart() { return this.enabled && this.downloaded && !this.installing }
  inspect() {
    return { version: app.getVersion(), platform: process.platform, architecture: process.arch,
      preferences: { ...this.preferences }, enabled: this.enabled, managed: this.managed,
      supported: this.supported, status: { ...this.status }, can_request_restart: this.canRequestRestart,
      ready_version: this.downloaded ? this.readyVersion ?? null : null,
      regular_check_seconds: { minimum: 21600, maximum: 22500 },
      automatic_restart_idle_seconds: 600 }
  }
  requestRestart(expectedVersion: string) {
    if (!this.canRequestRestart || expectedVersion !== this.readyVersion) throw new Error('The ready update changed. Read app.status before requesting its restart.')
    if (this.requestedRestartTimer) return
    // Return the private operator receipt and release its mutation guard first.
    // This is a single deliberate attempt, with all normal draft/work checks;
    // it never leaves a persistent request to bypass inactivity checks later.
    this.requestedRestartTimer = setTimeout(() => {
      this.requestedRestartTimer = undefined
      if (!this.stopped && this.readyVersion === expectedVersion) void this.restartIfSafe(true)
    }, 0)
    this.requestedRestartTimer.unref()
  }
  get quitNeedsUpdateCleanup() {
    const updater = this.mac || this.windows
    return !!updater?.active && !updater.installing
  }

  private platformEvent(event: MacUpdateEvent | WindowsUpdateEvent) {
    if (event.state === 'ready') {
      if (!this.enabled) { void (this.mac || this.windows)?.cancel(); return }
      this.clearRetry()
      this.downloaded = true
      this.readyVersion = event.version
      this.setStatus({ state: 'Update ready · waiting for a safe restart', version: event.version })
    } else if (event.state === 'downloading') {
      if (this.enabled) this.setStatus({ state: 'Downloading update', version: event.version, percent: event.percent })
    } else if (event.state === 'verifying') {
      if (this.enabled) this.setStatus({ state: 'Verifying update' })
    } else if (event.state === 'current') {
      this.clearRetry()
      this.setStatus({ state: 'Up to date', checkedAt: new Date().toISOString() })
    } else if (event.state === 'error') {
      if (this.installing) this.restartCancelled()
      this.downloaded = false
      this.installing = false
      this.scheduleRetry()
    } else if (event.state === 'cancelled') {
      this.downloaded = false
      this.installing = false
      this.setStatus({ state: this.enabled ? 'Automatic updates enabled' : 'Automatic updates paused' })
    }
  }

  async prepareQuit(): Promise<boolean> {
    if (!this.quitNeedsUpdateCleanup) return true
    this.setStatus({ state: 'Finishing update cleanup' })
    const stopped = await (this.mac || this.windows)!.cancel()
    if (!stopped) this.setStatus({ state: 'Update cleanup is still running · try quitting again shortly' })
    return stopped
  }

  private setStatus(status: UpdateStatus) { this.status = status; this.changed() }
  private save() {
    mkdirSync(app.getPath('userData'), { recursive: true })
    writeFileSync(`${this.path}.tmp`, JSON.stringify(this.preferences), { mode: 0o600 })
    renameSync(`${this.path}.tmp`, this.path)
  }
  private applyUpdatePolicy() {
    if (this.mac || this.windows || process.platform === 'darwin' || process.platform === 'win32') return
    autoUpdater.autoDownload = this.enabled
    autoUpdater.autoInstallOnAppQuit = this.enabled
    autoUpdater.autoRunAppAfterInstall = true
  }
  setPreference(key: keyof Preferences, enabled: boolean) {
    if (key === 'automaticUpdates' && this.managed) return
    const previous = this.preferences[key]
    this.preferences[key] = enabled
    try {
      if (key === 'startAtLogin') this.applyLogin()
      this.save()
      this.applyUpdatePolicy()
      if (!this.enabled) {
        this.clearRetry()
        this.cancelDownload?.()
        const updater = this.mac || this.windows
        if (updater) void updater.cancel().then(() => { if (this.enabled) void this.check() })
      }
      this.setStatus({ state: this.enabled ? 'Automatic updates enabled' : 'Automatic updates paused' })
      if (key === 'automaticUpdates' && enabled) void this.check()
    } catch { this.preferences[key] = previous; this.applyUpdatePolicy(); this.setStatus({ state: 'Preference could not be saved' }) }
  }
  private refreshLinuxLogin(executable: string, previousExecutable?: string) {
    const directory = join(process.env.XDG_CONFIG_HOME || join(app.getPath('home'), '.config'), 'autostart')
    refreshLinuxLoginEntry(join(directory, 'com.perseusxr.mnemion-studio.desktop'), executable, previousExecutable)
  }
  private applyLogin() {
    if (!app.isPackaged) return
    const enabled = this.preferences.startAtLogin
    if (process.platform !== 'linux') {
      app.setLoginItemSettings({ openAtLogin: enabled, args: ['--background'], path: process.execPath })
      return
    }
    const directory = join(process.env.XDG_CONFIG_HOME || join(app.getPath('home'), '.config'), 'autostart')
    const path = join(directory, 'com.perseusxr.mnemion-studio.desktop')
    if (!enabled) { rmSync(path, { force: true }); return }
    const executable = process.env.APPIMAGE || process.execPath
    mkdirSync(directory, { recursive: true, mode: 0o700 })
    writeFileSync(path, `[Desktop Entry]\nType=Application\nName=Mnemion Studio\nExec=${desktopExec(executable)}\nTerminal=false\nX-GNOME-Autostart-enabled=true\n`, { mode: 0o600 })
  }
  private clearRetry(resetAttempts = true) {
    if (this.retryTimer) clearTimeout(this.retryTimer)
    this.retryTimer = undefined
    if (resetAttempts) this.retryAttempts = 0
  }
  private scheduleRetry() {
    if (!this.enabled || this.downloaded || this.stopped || this.retryTimer) return
    const base = retryDelays[this.retryAttempts]
    if (base === undefined) {
      this.setStatus({ state: 'Update unavailable · next scheduled check will retry' })
      return
    }
    // Bound retry traffic during outages and spread organization-wide downloads.
    // Every attempt still passes through the platform's normal signature checks.
    const delay = Math.round(base * (1 + Math.random() * 0.25))
    const minutes = Math.ceil(delay / 60_000)
    this.retryAttempts++
    this.setStatus({ state: `Update unavailable · retry in about ${minutes} minute${minutes === 1 ? '' : 's'}` })
    this.retryTimer = setTimeout(() => {
      this.retryTimer = undefined
      void this.check(true)
    }, delay)
    this.retryTimer.unref()
  }
  async check(retrying = false) {
    if (!this.enabled || this.downloaded || this.stopped) return
    if (this.checking) { if (!retrying) this.checkRequested = true; return }
    this.clearRetry(!retrying)
    this.checking = true
    this.setStatus({ state: 'Checking for updates' })
    try {
      if (this.mac) { await this.mac.check(); return }
      if (this.windows) { await this.windows.check(); return }
      const result = await autoUpdater.checkForUpdates()
      this.cancelDownload = () => result?.cancellationToken?.cancel()
      if (!this.enabled) this.cancelDownload()
      await result?.downloadPromise
    } catch { this.scheduleRetry() }
    finally {
      this.checking = false
      if (this.checkRequested) { this.checkRequested = false; queueMicrotask(() => void this.check()) }
    }
  }
  private waitingToRestart(reason: UpdateRestartBlocker | 'window' | null) {
    if (!this.enabled || !this.downloaded || !reason) return
    const messages: Partial<Record<UpdateRestartBlocker | 'window', string>> = {
      busy: 'Update ready · waiting for a workspace operation to finish',
      work: 'Update ready · save your work and close open editors first',
      focused: 'Update ready · waiting for Mnemion to be in the background',
      inactivity: 'Update ready · waiting for 10 minutes of computer inactivity',
      window: 'Update ready · waiting for the app to respond before checking open work',
    }
    const state = messages[reason]
    if (state && (this.status.state !== state || this.status.version !== this.readyVersion)) {
      this.setStatus({ state, version: this.readyVersion })
    }
  }
  private async restartIsSafe(requested = false): Promise<boolean> {
    if (!this.enabled || !this.downloaded) return false
    const window = this.window()
    let safe = !window
    try { if (window) safe = await window.webContents.executeJavaScript('window.mnemion?.updateSafety?.() === true') }
    catch { this.waitingToRestart('window'); return false }
    const reason = updateRestartBlocker({ enabled: this.enabled, downloaded: this.downloaded,
      idleSeconds: powerMonitor.getSystemIdleTime(), focused: window?.isFocused() || false,
      locked: powerMonitor.getSystemIdleState(600) === 'locked',
      visible: window?.isVisible() || false, minimized: window?.isMinimized() || false,
      safe, busy: this.busy() }, requested)
    this.waitingToRestart(reason)
    return reason === null
  }
  async restartIfSafe(requested = false) {
    if (this.installing || !await this.restartIsSafe(requested)) return
    // A second timer can finish its renderer check while the first starts installing.
    if (this.installing) return
    this.installing = true
    this.changed()
    try {
      // Close the managed service/database before replacing bundled runtimes.
      // Recheck drafts and real inactivity after that asynchronous shutdown.
      if (!await this.beforeRestart()) {
        this.waitingToRestart('busy')
        this.installing = false; this.restartCancelled(); return
      }
      if (!await this.restartIsSafe(requested)) {
        this.installing = false; this.restartCancelled(); return
      }
      if (this.mac) {
        if (!this.mac.install()) { this.installing = false; this.restartCancelled() }
      } else if (this.windows) {
        const started = await this.windows.install(() => this.restartIsSafe(requested))
        if (started) app.quit()
        else { this.installing = false; this.restartCancelled() }
      } else {
        autoUpdater.quitAndInstall(true, true)
      }
    } catch {
      this.installing = false
      this.restartCancelled()
      this.setStatus({ state: 'Update could not restart safely · retry scheduled' })
    } finally {
      this.changed()
    }
  }
}
