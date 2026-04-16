import { app, BrowserWindow, shell, ipcMain } from 'electron'
import { join, dirname } from 'path'
import { fileURLToPath } from 'url'
import { spawn, ChildProcess } from 'child_process'
import { existsSync } from 'fs'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)

const isDev = !app.isPackaged
const BACKEND_PORT = 7891

let backendProcess: ChildProcess | null = null
let mainWindow: BrowserWindow | null = null

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
    icon: join(__dirname, '../../frontend/public/icon.png'),
  })

  // Open external links in browser
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url)
    return { action: 'deny' }
  })

  mainWindow.once('ready-to-show', () => mainWindow?.show())
  mainWindow.on('closed', () => { mainWindow = null })

  if (isDev) {
    mainWindow.loadURL('http://localhost:5173')
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

// ── IPC ───────────────────────────────────────────────────────────────────────

ipcMain.handle('app:version', () => app.getVersion())
ipcMain.handle('app:platform', () => process.platform)
ipcMain.handle('backend:port', () => BACKEND_PORT)

// ── App lifecycle ─────────────────────────────────────────────────────────────

app.whenReady().then(async () => {
  startBackend()
  await createWindow()

  app.on('activate', async () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      await createWindow()
    }
  })
})

app.on('window-all-closed', () => {
  stopBackend()
  if (process.platform !== 'darwin') app.quit()
})

app.on('before-quit', stopBackend)
