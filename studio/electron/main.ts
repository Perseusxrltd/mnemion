import { app, BrowserWindow, shell, ipcMain, Menu, Tray, nativeImage, type MenuItemConstructorOptions } from 'electron'
import { join, dirname } from 'path'
import { fileURLToPath } from 'url'
import { spawn, ChildProcess } from 'child_process'
import { existsSync, mkdirSync, writeFileSync } from 'fs'
import { randomBytes } from 'crypto'
import { createServer } from 'net'
import { installServiceBridge, localClientBusy, verifyLocalClient } from './service-bridge.js'
import { DesktopUpdates } from './updates.js'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)

const isDev = !app.isPackaged
const legacyEnabled = process.env.MNEMION_LEGACY_STUDIO === '1'
const DEFAULT_BACKEND_PORT = 7891
const STUDIO_TOKEN = process.env.MNEMION_STUDIO_TOKEN || randomBytes(32).toString('hex')
const APP_ID = 'com.perseusxr.mnemion-studio'

let backendProcess: ChildProcess | null = null
let mainWindow: BrowserWindow | null = null
let tray: Tray | null = null
let updates: DesktopUpdates | null = null
let isQuitting = false
let backendPort = parsePort(process.env.MNEMION_STUDIO_PORT) ?? DEFAULT_BACKEND_PORT
let trayIconLoaded = false
let trayIconSource: string | null = null
const isHeadlessSmoke = process.env.MNEMION_STUDIO_SMOKE_HEADLESS === '1'

app.setAppUserModelId(APP_ID)
if (process.env.MNEMION_ENABLE_HARDWARE_ACCELERATION !== '1') {
  app.disableHardwareAcceleration()
  app.commandLine.appendSwitch('disable-gpu')
  app.commandLine.appendSwitch('disable-gpu-compositing')
  app.commandLine.appendSwitch('disable-gpu-rasterization')
}
if (isHeadlessSmoke) {
  app.commandLine.appendSwitch('disable-gpu-sandbox')
  app.commandLine.appendSwitch('disable-software-rasterizer')
}
configureUserDataPath()

function parsePort(raw: string | undefined): number | null {
  if (!raw) return null
  const parsed = Number(raw)
  if (!Number.isInteger(parsed) || parsed < 1 || parsed > 65535) return null
  return parsed
}

function configureUserDataPath() {
  const override = process.env.MNEMION_STUDIO_USER_DATA
  if (!override) return
  mkdirSync(override, { recursive: true })
  app.setPath('userData', override)
}

function getIconPath(): string {
  const ext = 'png'
  if (isDev) {
    return join(__dirname, `../../frontend/public/icon.${ext}`)
  } else {
    return join(process.resourcesPath, `frontend/dist/icon.${ext}`)
  }
}

function getAssetPath(name: string): string {
  return isDev
    ? join(__dirname, `../../frontend/public/${name}`)
    : join(process.resourcesPath, `frontend/dist/${name}`)
}

function getTrayIconPaths(): string[] {
  if (process.platform === 'win32') {
    return [getAssetPath('icon.ico'), getAssetPath('icon-tray.png'), getAssetPath('icon.png')]
  }
  return [getAssetPath('icon-tray.png'), getAssetPath('icon.png')]
}

function ensureUserDataRoot(): string {
  const userDataRoot = join(app.getPath('userData'), 'data')
  mkdirSync(userDataRoot, { recursive: true })
  return userDataRoot
}

function writeSmokeStatus(stage: string, extra: Record<string, unknown> = {}) {
  const smokeFile = process.env.MNEMION_STUDIO_SMOKE_FILE
  if (!smokeFile) return

  try {
    mkdirSync(dirname(smokeFile), { recursive: true })
    writeFileSync(
      smokeFile,
      JSON.stringify({
        stage,
        version: app.getVersion(),
        backendPort,
        userDataRoot: ensureUserDataRoot(),
        trayCreated: tray !== null,
        trayIconLoaded,
        trayIconSource,
        windowCreated: mainWindow !== null,
        ...extra,
      }, null, 2),
      'utf8',
    )
  } catch (e) {
    console.error('[main] Failed to write smoke status:', e)
  }
}

// Backend launcher

function getTrayImage() {
  const iconSize = process.platform === 'win32' ? 16 : 18
  for (const iconPath of getTrayIconPaths()) {
    if (!existsSync(iconPath)) continue
    const image = nativeImage.createFromPath(iconPath)
    if (image.isEmpty()) continue
    const resized = image.resize({ width: iconSize, height: iconSize, quality: 'best' })
    resized.setTemplateImage(false)
    trayIconLoaded = true
    trayIconSource = iconPath
    return resized
  }
  console.error('[main] No usable tray icon found')
  trayIconLoaded = false
  trayIconSource = null
  return nativeImage.createEmpty()
}

async function chooseBackendPort(): Promise<number> {
  const explicitPort = parsePort(process.env.MNEMION_STUDIO_PORT)
  if (explicitPort) return explicitPort
  if (isDev) return DEFAULT_BACKEND_PORT

  return new Promise((resolve, reject) => {
    const server = createServer()
    server.once('error', reject)
    server.listen(0, '127.0.0.1', () => {
      const address = server.address()
      const selected = typeof address === 'object' && address ? address.port : DEFAULT_BACKEND_PORT
      server.close(() => resolve(selected))
    })
  })
}

function isSafeExternalUrl(rawUrl: string): boolean {
  try {
    const parsed = new URL(rawUrl)
    return ['http:', 'https:', 'mailto:'].includes(parsed.protocol) || (parsed.protocol === 'obsidian:' && parsed.hostname === 'open')
  } catch {
    return false
  }
}

function startBackend() {
  if (!legacyEnabled) return
  // In production: resources/backend.exe (PyInstaller bundle)
  // In development: python -m studio.backend.main
  if (isDev) {
    console.log('[main] Dev mode - backend should already be running on port', backendPort)
    return
  }

  const backendExe = join(process.resourcesPath, 'backend', 'backend.exe')
  if (!existsSync(backendExe)) {
    console.error('[main] backend.exe not found at', backendExe)
    return
  }

  console.log('[main] Starting backend:', backendExe)
  const userDataRoot = ensureUserDataRoot()
  backendProcess = spawn(backendExe, [], {
    env: {
      ...process.env,
      MNEMION_HOME: userDataRoot,
      MNEMION_STUDIO_PORT: String(backendPort),
      MNEMION_STUDIO_TOKEN: STUDIO_TOKEN,
    },
    detached: false,
  })

  backendProcess.on('spawn', () => writeSmokeStatus('backend-spawned'))
  backendProcess.stdout?.on('data', (d: Buffer) => console.log('[backend]', d.toString().trim()))
  backendProcess.stderr?.on('data', (d: Buffer) => console.error('[backend]', d.toString().trim()))
  backendProcess.on('exit', (code) => {
    console.log('[main] Backend exited with code', code)
    writeSmokeStatus('backend-exit', { code })
  })
}

function stopBackend() {
  if (backendProcess) {
    backendProcess.kill()
    backendProcess = null
  }
}

async function showMainWindow(): Promise<void> {
  if (mainWindow) {
    if (mainWindow.isMinimized()) mainWindow.restore()
    mainWindow.show()
    mainWindow.focus()
    return
  }
  await createWindow()
}

function hideMainWindow() {
  mainWindow?.hide()
}

function restartMemoryService() {
  if (legacyEnabled) { stopBackend(); startBackend() }
  else mainWindow?.webContents.reload()
}

function quitApp() {
  isQuitting = true
  app.quit()
}

function updateMenu(): MenuItemConstructorOptions[] {
  return [
    { label: updates?.status.state || 'Automatic updates', enabled: false },
    { label: 'Check for updates', enabled: !!updates?.enabled, click: () => { void updates?.check() } },
    { label: 'Automatic updates and safe restarts', type: 'checkbox', checked: updates?.preferences.automaticUpdates ?? true,
      enabled: !updates?.policyManaged, click: item => updates?.setPreference('automaticUpdates', item.checked) },
    { label: 'Start at login', type: 'checkbox', checked: updates?.preferences.startAtLogin ?? true,
      click: item => updates?.setPreference('startAtLogin', item.checked) },
    { label: 'Keep running in background', type: 'checkbox', checked: updates?.preferences.background ?? true,
      click: item => updates?.setPreference('background', item.checked) },
  ]
}

function refreshMenus() {
  if (!app.isReady()) return
  Menu.setApplicationMenu(buildApplicationMenu())
  if (tray) tray.setContextMenu(buildTrayMenu())
}

async function navigateTo(route: string): Promise<void> {
  await showMainWindow()
  const targetWindow = mainWindow
  if (!targetWindow) return

  const sendRoute = () => targetWindow.webContents.send('app:navigate', route)
  if (targetWindow.webContents.isLoading()) {
    targetWindow.webContents.once('did-finish-load', sendRoute)
  } else {
    sendRoute()
  }
}

function buildApplicationMenu(): Menu {
  const viewMenu: MenuItemConstructorOptions[] = [
    { role: 'resetZoom', label: 'Actual Size' },
    { role: 'zoomIn', label: 'Zoom In' },
    { role: 'zoomOut', label: 'Zoom Out' },
    { type: 'separator' },
    { role: 'togglefullscreen', label: 'Toggle Full Screen' },
  ]

  if (isDev) {
    viewMenu.push(
      { type: 'separator' },
      { role: 'reload', label: 'Reload' },
      { role: 'forceReload', label: 'Force Reload' },
      { role: 'toggleDevTools', label: 'Toggle Developer Tools' },
    )
  }

  const template: MenuItemConstructorOptions[] = [
    {
      label: 'Mnemion Studio',
      submenu: [
        { label: 'Open Memory Workspace', accelerator: 'CommandOrControl+Shift+M', click: () => { void navigateTo(legacyEnabled ? '/dashboard' : '/workspace') } },
        { label: 'Team and Applications', click: () => { void navigateTo(legacyEnabled ? '/connect' : '/workspace/team') } },
        { label: 'Obsidian', click: () => { void navigateTo(legacyEnabled ? '/settings' : '/workspace/obsidian') } },
        { type: 'separator' },
        { label: 'Hide to Tray', accelerator: 'CommandOrControl+W', click: hideMainWindow },
        { type: 'separator' },
        { label: legacyEnabled ? 'Restart Legacy Service' : 'Reconnect Workspace', click: restartMemoryService },
        { label: 'Background and updates', submenu: updateMenu() },
        { type: 'separator' },
        { label: 'Quit Mnemion Studio', accelerator: process.platform === 'darwin' ? 'Command+Q' : 'Alt+F4', click: quitApp },
      ],
    },
    {
      label: 'Edit',
      submenu: [
        { role: 'undo', label: 'Undo' },
        { role: 'redo', label: 'Redo' },
        { type: 'separator' },
        { role: 'cut', label: 'Cut' },
        { role: 'copy', label: 'Copy' },
        { role: 'paste', label: 'Paste' },
        { role: 'selectAll', label: 'Select All' },
      ],
    },
    { label: 'View', submenu: viewMenu },
    {
      label: 'Window',
      submenu: [
        { role: 'minimize', label: 'Minimize' },
        { label: 'Bring Mnemion Studio to Front', click: () => { void showMainWindow() } },
      ],
    },
    {
      label: 'Help',
      submenu: [
        { label: 'Documentation and Roadmap', click: () => { void navigateTo('/help') } },
        { label: 'Team and Applications', click: () => { void navigateTo(legacyEnabled ? '/connect' : '/workspace/team') } },
        { label: 'Open Obsidian View', click: () => { void navigateTo(legacyEnabled ? '/settings' : '/workspace/obsidian') } },
        { type: 'separator' },
        { label: 'Open Data Folder', click: () => { void shell.openPath(ensureUserDataRoot()) } },
      ],
    },
  ]

  return Menu.buildFromTemplate(template)
}

// Wait for backend to be ready

async function findDevPort(ports: number[]): Promise<number | null> {
  // Probe each port and only accept one that looks like a Vite dev server.
  // A random HTTP service on the same port must not be picked.
  // Vite's index.html embeds `/@vite/client` and
  // `/@react-refresh` as <script type="module"> sources.
  for (const p of ports) {
    try {
      const res = await fetch(`http://127.0.0.1:${p}/`, {
        headers: { Accept: 'text/html' },
      })
      if (!res.ok) continue
      const body = await res.text()
      if (body.includes('/@vite/client') || body.includes('/@react-refresh')) {
        return p
      }
    } catch {
      // port not listening or refused
    }
  }
  return null
}

async function waitForBackend(url: string, maxMs = 15_000): Promise<void> {
  const deadline = Date.now() + maxMs
  while (Date.now() < deadline) {
    try {
      const res = await fetch(url, {
        headers: { 'X-Mnemion-Studio-Token': STUDIO_TOKEN },
      })
      if (res.ok) return
    } catch {
      // not ready yet
    }
    await new Promise(r => setTimeout(r, 300))
  }
  throw new Error('Backend did not start within ' + maxMs + 'ms')
}

// Window

async function createWindow() {
  if (mainWindow) {
    if (mainWindow.isMinimized()) mainWindow.restore()
    mainWindow.show()
    mainWindow.focus()
    return
  }

  mainWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 420,
    minHeight: 560,
    backgroundColor: '#161616',
    // Native window controls remain accessible on macOS, Windows, and Linux.
    frame: true,
    webPreferences: {
      preload: join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
    show: false, // show after ready
    title: 'Mnemion Studio',
    icon: getIconPath(),
  })

  // Open external links in browser
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (isSafeExternalUrl(url)) {
      shell.openExternal(url)
    }
    return { action: 'deny' }
  })
  mainWindow.webContents.on('will-navigate', (event, url) => {
    event.preventDefault()
    if (isSafeExternalUrl(url)) void shell.openExternal(url)
  })

  mainWindow.once('ready-to-show', () => {
    const background = process.argv.includes('--background')
      || (process.platform === 'darwin' && app.getLoginItemSettings().wasOpenedAtLogin)
    if (!background || process.env.MNEMION_STUDIO_SMOKE_FILE) mainWindow?.show()
    else if (process.platform === 'linux') { mainWindow?.show(); mainWindow?.minimize() }
  })
  mainWindow.on('close', (event) => {
    if (!isQuitting) {
      if (updates?.preferences.background === false) { quitApp(); return }
      event.preventDefault()
      // Linux shells do not consistently expose StatusNotifier icons. Retain a
      // minimized taskbar window so background mode is always recoverable.
      if (process.platform === 'linux' || !tray) mainWindow?.minimize()
      else mainWindow?.hide()
    }
  })
  mainWindow.on('closed', () => { mainWindow = null })

  if (isDev) {
    // Vite may bump the port if 5173 is busy. Probe 5173-5179 in order.
    const devPort = process.env.VITE_DEV_PORT ?? (await findDevPort([5173, 5174, 5175, 5176, 5177, 5178, 5179]))
    if (devPort) {
      console.log('[main] Loading dev frontend on port', devPort)
      mainWindow.loadURL(`http://127.0.0.1:${devPort}`)
    } else {
      console.error('[main] No Vite dev server found on ports 5173-5179')
    }
    mainWindow.webContents.openDevTools()
  } else {
    // Wait for backend to be alive, then load app
    try {
      if (legacyEnabled) await waitForBackend(`http://127.0.0.1:${backendPort}/api/status`)
    } catch (e) {
      console.error('[main] Backend timeout:', e)
      writeSmokeStatus('backend-timeout', { error: String(e) })
    }
    await mainWindow.loadFile(join(process.resourcesPath, 'frontend/dist/index.html'), { hash: legacyEnabled ? '/dashboard' : '/workspace' })
    const localClient = await verifyLocalClient()
    let renderer: Record<string, unknown> | null = null
    if (process.env.MNEMION_STUDIO_SMOKE_FILE) {
      // Probe the real packaged renderer and sandboxed preload. A successful
      // file load alone misses broken asset paths and CommonJS preload errors.
      const deadline = Date.now() + 15_000
      do {
        renderer = await mainWindow.webContents.executeJavaScript(`({
          workspace: document.body.innerText.includes('Connect to Mnemion'),
          serviceBridge: typeof window.mnemion?.serviceRequest === 'function',
          vaultBridge: typeof window.mnemion?.refreshVault === 'function',
          updateGuard: (() => {
            const clean = window.mnemion?.updateSafety?.();
            const field = document.createElement('textarea'); document.body.append(field);
            field.value = 'Unsaved smoke-test draft'; field.dispatchEvent(new Event('input', { bubbles: true }));
            const edited = window.mnemion?.updateSafety?.(); field.remove();
            return { clean, edited, removed: window.mnemion?.updateSafety?.() };
          })(),
          nodeAvailable: typeof window.require !== 'undefined',
          route: location.hash
        })`)
        if (renderer?.workspace && renderer?.serviceBridge && renderer?.vaultBridge) break
        await new Promise(resolve => setTimeout(resolve, 100))
      } while (Date.now() < deadline)
      // Help must load entirely from packaged assets before any service connects.
      await mainWindow.webContents.executeJavaScript("location.hash = '/help?doc=docs%2FROADMAP.md'")
      const helpDeadline = Date.now() + 10_000
      let documentation = false
      do {
        documentation = await mainWindow.webContents.executeJavaScript(`
          document.querySelector('.mn-docs-article h1')?.textContent === 'Mnemion product roadmap'
          && document.querySelector('.mn-docs-header')?.textContent.includes('Version ${app.getVersion()}')
        `)
        if (documentation) break
        await new Promise(resolve => setTimeout(resolve, 100))
      } while (Date.now() < helpDeadline)
      renderer = { ...renderer, documentation }
    }
    writeSmokeStatus('client-ready', { legacyEnabled, localClient, renderer })
  }
}

// Tray

function buildTrayMenu(): Menu {
  return Menu.buildFromTemplate([
    { label: 'Open Memory Workspace', click: () => { void navigateTo(legacyEnabled ? '/dashboard' : '/workspace') } },
    { label: 'Team and Applications', click: () => { void navigateTo(legacyEnabled ? '/connect' : '/workspace/team') } },
    { label: 'Obsidian', click: () => { void navigateTo(legacyEnabled ? '/settings' : '/workspace/obsidian') } },
    { label: 'Hide to Tray', click: hideMainWindow },
    { type: 'separator' },
    { label: legacyEnabled ? 'Restart Legacy Service' : 'Reconnect Workspace', click: restartMemoryService },
    { label: 'Background and updates', submenu: updateMenu() },
    { type: 'separator' },
    { label: 'Quit Mnemion Studio', click: quitApp }
  ])
}

function createTray() {
  if (tray) return
  tray = new Tray(getTrayImage())
  
  tray.setToolTip('Mnemion Studio')
  tray.setContextMenu(buildTrayMenu())
  writeSmokeStatus('tray-ready')

  tray.on('click', () => {
    if (mainWindow) {
      if (mainWindow.isVisible()) {
        mainWindow.hide()
      } else {
        void showMainWindow()
      }
    } else {
      void showMainWindow()
    }
  })
}

// IPC

ipcMain.handle('app:version', () => app.getVersion())
ipcMain.handle('app:platform', () => process.platform)
ipcMain.handle('backend:port', () => backendPort)
ipcMain.handle('backend:token', () => STUDIO_TOKEN)
installServiceBridge(() => mainWindow)

// App lifecycle

const hasSingleInstanceLock = app.requestSingleInstanceLock()

if (!hasSingleInstanceLock) {
  app.quit()
} else {
  app.on('second-instance', async () => {
    await createWindow()
  })

  app.whenReady().then(async () => {
    try {
      backendPort = await chooseBackendPort()
      startBackend()
      updates = new DesktopUpdates(() => mainWindow, localClientBusy, () => { isQuitting = true }, refreshMenus)
      const backendReady = legacyEnabled ? waitForBackend(`http://127.0.0.1:${backendPort}/api/status`)
        .then(() => writeSmokeStatus('backend-ready'))
        .catch((e) => writeSmokeStatus('backend-timeout', { error: String(e) })) : Promise.resolve()

      Menu.setApplicationMenu(buildApplicationMenu())
      try { createTray() } catch (error) {
        if (process.platform !== 'linux') throw error
        console.warn('[main] This desktop has no notification area; the window remains available')
      }
      if (isHeadlessSmoke) {
        writeSmokeStatus('client-ready', { legacyEnabled, localClient: await verifyLocalClient() })
      } else {
        await createWindow()
      }
      await backendReady

      app.on('activate', async () => {
        if (BrowserWindow.getAllWindows().length === 0) {
          await createWindow()
        } else {
          mainWindow?.show()
          mainWindow?.focus()
        }
      })
    } catch (e) {
      console.error('[main] App startup failed:', e)
      writeSmokeStatus('startup-error', { error: String(e) })
    }
  })
}

process.on('uncaughtException', (e) => {
  writeSmokeStatus('uncaught-exception', { error: String(e) })
  throw e
})

process.on('unhandledRejection', (e) => {
  writeSmokeStatus('unhandled-rejection', { error: String(e) })
})

app.on('window-all-closed', () => {
  // Do not quit, run in background tray
})

app.on('before-quit', () => {
  isQuitting = true
  stopBackend()
})
