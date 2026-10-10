import { app, dialog, ipcMain, net, type BrowserWindow, type IpcMainInvokeEvent } from 'electron'
import { spawn, type ChildProcess } from 'node:child_process'
import { randomUUID } from 'node:crypto'
import { mkdtemp, rm, writeFile } from 'node:fs/promises'
import { join } from 'node:path'

const MAX_BYTES = 120 * 1024 * 1024
const selections = new Map<string, string>()
const children = new Set<ChildProcess>()

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

async function boundedBody(response: Response): Promise<Uint8Array> {
  if (Number(response.headers.get('content-length')) > MAX_BYTES) throw new Error('Service response is too large')
  if (!response.body) return new Uint8Array()
  const chunks: Uint8Array[] = []
  let size = 0
  const reader = response.body.getReader()
  try {
    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      size += value.byteLength
      if (size > MAX_BYTES) throw new Error('Service response is too large')
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

async function runClient(args: string[]): Promise<Record<string, unknown>> {
  const command = app.isPackaged ? clientExecutable() : (process.env.MNEMION_BUILD_PYTHON || 'python3')
  const commandArgs = app.isPackaged ? args : [join(app.getAppPath(), '../bridge/main.py'), ...args]
  return new Promise((resolve, reject) => {
    const child = spawn(command, commandArgs, { stdio: ['ignore', 'pipe', 'pipe'], windowsHide: true })
    children.add(child)
    let output = ''
    let failure: Error | null = null
    // Wait for close after termination so the archive is not removed while the
    // Windows client still holds it, and all stdout has arrived before parsing.
    const timer = setTimeout(() => {
      failure = new Error('Vault refresh timed out; refresh again to reconcile its saved progress')
      child.kill()
    }, 180_000)
    child.stdout.on('data', (chunk: Buffer) => {
      output += chunk.toString('utf8')
      if (output.length > 8 * 1024 * 1024) {
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
  function trusted(event: IpcMainInvokeEvent) {
    const window = getWindow()
    if (!window || event.sender !== window.webContents || event.senderFrame !== window.webContents.mainFrame) {
      throw new Error('This request did not come from Studio')
    }
  }

  ipcMain.handle('service:request', async (event, input: unknown) => {
    trusted(event)
    if (!input || typeof input !== 'object') throw new Error('Invalid request')
    const request = input as { url: unknown; method: string; headers: Record<string, string>; body?: string }
    const url = allowedServiceUrl(request.url)
    if (!['GET', 'POST', 'PUT', 'DELETE'].includes(request.method)) throw new Error('Unsupported method')
    if (request.body !== undefined && (typeof request.body !== 'string' || Buffer.byteLength(request.body) > 2 * 1024 * 1024)) throw new Error('Request is too large')
    const headers = new Headers()
    for (const [name, value] of Object.entries(request.headers || {})) {
      if (!['accept', 'authorization', 'content-type', 'idempotency-key'].includes(name.toLowerCase()) || typeof value !== 'string' || value.length > 1024) throw new Error('Unsupported request header')
      headers.set(name, value)
    }
    const response = await net.fetch(url.toString(), { method: request.method, headers, body: request.body, redirect: 'error', credentials: 'omit', signal: AbortSignal.timeout(60_000) })
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
    for (const child of children) child.kill()
    selections.clear()
  })
}
