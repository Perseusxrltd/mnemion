import { app, BrowserWindow, shell, ipcMain, Menu, Tray } from 'electron'
import { join, dirname } from 'path'
import { fileURLToPath } from 'url'
import { spawn, ChildProcess } from 'child_process'
import { existsSync } from 'fs'
import { randomBytes } from 'crypto'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)

const isDev = !app.isPackaged
const BACKEND_PORT = 7891
const STUDIO_TOKEN = process.env.MNEMION_STUDIO_TOKEN || randomBytes(32).toString('hex')

let backendProcess: ChildProcess | null = null
let mainWindow: BrowserWindow | null = null
let tray: Tray | null = null
let isQuitting = false

function getIconPath(): string {
  const ext = process.platform === 'win32' ? 'ico' : 'png'
  if (isDev) {
    return join(__dirname, `../../frontend/public/icon.${ext}`)
  } else {
    return join(process.resourcesPath, `frontend/dist/icon.${ext}`)
  }
}

// ── Backend launcher ──────────────────────────────────────────────────────────

function startBackend() {
  // In production: resources/backend.exe (PyInstaller bundle)
  // In development: python -m studio.backend.main
  if (isDev) {
    console.log('[main] Dev mode — backend should already be running on port', BACKEND_PORT)
    return
  }

  const backendExe = join(process.resourcesPath, 'backend', 'backend.exe')
  if (!existsSync(backendExe)) {
    console.error('[main] backend.exe not found at', backendExe)
    return
  }

  console.log('[main] Starting backend:', backendExe)
  backendProcess = spawn(backendExe, [], {
    env: {
      ...process.env,
      MNEMION_STUDIO_PORT: String(BACKEND_PORT),
      MNEMION_STUDIO_TOKEN: STUDIO_TOKEN,
    },
    detached: false,
  })

  backendProcess.stdout?.on('data', (d: Buffer) => console.log('[backend]', d.toString().trim()))
  backendProcess.stderr?.on('data', (d: Buffer) => console.error('[backend]', d.toString().trim()))
  backendProcess.on('exit', (code) => console.log('[main] Backend exited with code', code))
}

function stopBackend() {
  if (backendProcess) {
    backendProcess.kill()
    backendProcess = null
  }
}

// ── Wait for backend to be ready ──────────────────────────────────────────────

async function findDevPort(ports: number[]): Promise<number | null> {
  // Probe each port and only accept one that looks like a Vite dev server —
  // a random HTTP service on the same port (notebook, other dev server, …)
  // must NOT be picked. Vite's index.html embeds `/@vite/client` and
  // `/@react-refresh` as <script type="module"> sources.
  for (const p of ports) {
    try {
      const res = await fetch(`http://localhost:${p}/`, {
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
      const res = await fetch(url)
      if (res.ok) return
    } catch {
      // not ready yet
    }
    await new Promise(r => setTimeout(r, 300))
  }
  throw new Error('Backend did not start within ' + maxMs + 'ms')
}

// ── Window ────────────────────────────────────────────────────────────────────

async function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 960,
    minHeight: 600,
    backgroundColor: '#161616',
    titleBarStyle: 'hiddenInset',
    frame: process.platform !== 'darwin', // native frame on Windows/Linux
    webPreferences: {
      preload: join(__dirname, 'preload.js'),
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
    shell.openExternal(url)
    return { action: 'deny' }
  })

  mainWindow.once('ready-to-show', () => mainWindow?.show())
  mainWindow.on('close', (event) => {
    if (!isQuitting) {
      event.preventDefault()
      mainWindow?.hide()
    }
  })
  mainWindow.on('closed', () => { mainWindow = null })

  if (isDev) {
    // Vite may bump the port if 5173 is busy. Probe 5173→5179 in order.
    const devPort = process.env.VITE_DEV_PORT ?? (await findDevPort([5173, 5174, 5175, 5176, 5177, 5178, 5179]))
    if (devPort) {
      console.log('[main] Loading dev frontend on port', devPort)
      mainWindow.loadURL(`http://localhost:${devPort}`)
    } else {
      console.error('[main] No Vite dev server found on ports 5173–5179')
    }
    mainWindow.webContents.openDevTools()
  } else {
    // Wait for backend to be alive, then load app
    try {
      await waitForBackend(`http://127.0.0.1:${BACKEND_PORT}/api/status`)
    } catch (e) {
      console.error('[main] Backend timeout:', e)
    }
    mainWindow.loadFile(join(__dirname, '../../frontend/dist/index.html'))
  }
}

// ── Tray ──────────────────────────────────────────────────────────────────────

function createTray() {
  const iconPath = getIconPath()
  tray = new Tray(iconPath)
  const contextMenu = Menu.buildFromTemplate([
    { label: 'Show Mnemion Studio', click: () => { mainWindow?.show(); mainWindow?.focus(); } },
    { label: 'Hide Mnemion Studio', click: () => { mainWindow?.hide(); } },
    { type: 'separator' },
    { label: 'Restart Backend', click: () => { stopBackend(); startBackend(); } },
    { type: 'separator' },
    { label: 'Quit', click: () => {
        isQuitting = true
        app.quit()
      }
    }
  ])
  
  tray.setToolTip('Mnemion Studio')
  tray.setContextMenu(contextMenu)

  tray.on('click', () => {
    if (mainWindow) {
      if (mainWindow.isVisible()) {
        mainWindow.hide()
      } else {
        mainWindow.show()
        mainWindow.focus()
      }
    }
  })
}

// ── IPC ───────────────────────────────────────────────────────────────────────

ipcMain.handle('app:version', () => app.getVersion())
ipcMain.handle('app:platform', () => process.platform)
ipcMain.handle('backend:port', () => BACKEND_PORT)
ipcMain.handle('backend:token', () => STUDIO_TOKEN)

// ── App lifecycle ─────────────────────────────────────────────────────────────

app.whenReady().then(async () => {
  startBackend()
  await createWindow()
  createTray()

  app.on('activate', async () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      await createWindow()
    }
  })
})

app.on('window-all-closed', () => {
  // Do not quit, run in background tray
})

app.on('before-quit', () => {
  isQuitting = true
  stopBackend()
})
