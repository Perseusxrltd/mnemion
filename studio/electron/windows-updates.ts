import { execFile, spawn } from 'node:child_process'
import { lstat, mkdir, opendir, rename, rm } from 'node:fs/promises'
import { dirname, join } from 'node:path'
import { compareWindowsVersions, stableWindowsVersion, verifyWindowsInstaller, verifyWindowsManifest,
  windowsArchitecture, windowsManifestURL, WINDOWS_MANIFEST_LIMIT, WINDOWS_READY_LIFETIME,
  type WindowsUpdate } from './windows-update-security.js'
import { downloadWindowsInstaller, fetchWindowsManifest, type UpdateFetch } from './windows-update-transfer.js'

export type WindowsUpdateEvent = {
  state: 'checking' | 'downloading' | 'verifying' | 'ready' | 'installing' | 'current' | 'cancelled' | 'error'
  version?: string
  percent?: number
}
export type WindowsUpdateTrust = { schema: number; algorithm: string; publicKey: string; publisherNames: string[] }
type Options = {
  version: string
  architecture: string
  cacheDirectory: string
  applicationPath: string
  resourcesPath: string
  trust: WindowsUpdateTrust
}
const cacheName = /^Mnemion-Studio-\d+\.\d+\.\d+-windows-(?:x64|arm64)\.exe(?:\.part)?$/

export function windowsInstallerEnvironment(source: NodeJS.ProcessEnv): NodeJS.ProcessEnv {
  const result: NodeJS.ProcessEnv = {}
  const allowed = new Set(['systemroot', 'windir', 'temp', 'tmp', 'userprofile', 'homedrive', 'homepath',
    'appdata', 'localappdata', 'allusersprofile', 'programdata', 'programfiles', 'programfiles(x86)',
    'programw6432', 'comspec', 'pathext', 'systemdrive', 'number_of_processors', 'processor_architecture', 'os'])
  for (const [name, value] of Object.entries(source)) if (allowed.has(name.toLowerCase()) && value) result[name] = value
  const systemRoot = Object.entries(result).find(([name]) => name.toLowerCase() === 'systemroot')?.[1]
  if (systemRoot) result.PATH = [join(systemRoot, 'System32'), systemRoot, join(systemRoot, 'System32', 'Wbem')].join(';')
  for (const policy of ['MNEMION_AUTO_UPDATE', 'MNEMION_START_AT_LOGIN']) if (source[policy] === '0') result[policy] = '0'
  return result
}

async function verifyPublisher(path: string, publishers: string[], signal: AbortSignal): Promise<void> {
  if (!publishers.length) return
  const env = windowsInstallerEnvironment(process.env)
  const systemRoot = Object.entries(env).find(([name]) => name.toLowerCase() === 'systemroot')?.[1]
  if (!systemRoot) throw new Error('Windows certificate verification is unavailable')
  // Values travel as data, never interpolated PowerShell source. No inherited module overrides.
  env.MNEMION_VERIFIED_INSTALLER_PATH = path
  env.MNEMION_EXPECTED_PUBLISHERS = JSON.stringify(publishers)
  const script = '$ErrorActionPreference="Stop"; $signature=Get-AuthenticodeSignature -LiteralPath $env:MNEMION_VERIFIED_INSTALLER_PATH; '
    + 'if ($signature.Status -ne "Valid") { exit 1 }; '
    + '$publisher=$signature.SignerCertificate.GetNameInfo([System.Security.Cryptography.X509Certificates.X509NameType]::SimpleName,$false); '
    + '$expected=ConvertFrom-Json -InputObject $env:MNEMION_EXPECTED_PUBLISHERS; '
    + 'if ($publisher -notin $expected) { exit 2 }'
  await new Promise<void>((resolve, reject) => {
    execFile(join(systemRoot, 'System32', 'WindowsPowerShell', 'v1.0', 'powershell.exe'),
      ['-NoProfile', '-NonInteractive', '-Command', script],
      { env, signal, timeout: 45_000, maxBuffer: 4096, windowsHide: true },
      error => error ? reject(new Error('Windows publisher verification failed')) : resolve())
  })
}

/** Start the standard full NSIS installer; retain the running app until spawn succeeds. */
export async function launchWindowsInstaller(path: string, applicationPath: string, resourcesPath: string): Promise<void> {
  const args = ['--updated', '/S', '--force-run', `/D=${dirname(applicationPath)}`]
  const env = windowsInstallerEnvironment(process.env)
  const launch = (command: string, arguments_: string[]) => new Promise<void>((resolve, reject) => {
    const child = spawn(command, arguments_, { detached: true, stdio: 'ignore', windowsHide: true, env })
    child.once('error', reject)
    child.once('spawn', () => { child.unref(); resolve() })
  })
  try { await launch(path, args) }
  catch (error) {
    if (!['EACCES', 'EPERM', 'UNKNOWN'].includes((error as NodeJS.ErrnoException).code || '')) throw error
    // Existing machine-wide installations can require UAC. The OS handles consent.
    await launch(join(resourcesPath, 'elevate.exe'), [path, ...args])
  }
}

/** Independent publisher authentication with bounded transport and a single cached full installer. */
export class WindowsUpdateBridge {
  private cycle?: Promise<void>
  private installation?: Promise<boolean>
  private controller?: AbortController
  private ready?: { update: WindowsUpdate; path: string; at: number }
  private expiry?: NodeJS.Timeout
  private committed = false

  constructor(private options: Options, private fetcher: UpdateFetch,
    private notify: (event: WindowsUpdateEvent) => void,
    private launch: typeof launchWindowsInstaller = launchWindowsInstaller) {
    stableWindowsVersion(options.version)
    windowsArchitecture(options.architecture)
    const trust = options.trust
    if (trust.schema !== 1 || trust.algorithm !== 'ed25519' || typeof trust.publicKey !== 'string'
      || !Array.isArray(trust.publisherNames) || trust.publisherNames.length > 8
      || trust.publisherNames.some(name => typeof name !== 'string' || !name.trim() || name.length > 256)) throw new Error('Invalid Windows update trust configuration')
  }

  get active() { return !!this.cycle || !!this.installation || !!this.ready }
  get installing() { return this.committed }

  async check(): Promise<void> {
    if (this.cycle) return this.cycle
    if (this.ready || this.installation || this.committed) return
    const controller = new AbortController()
    this.controller = controller
    this.cycle = this.performCheck(controller.signal)
    try { await this.cycle } finally { this.cycle = undefined }
  }

  private async prepareCache(filename: string): Promise<void> {
    const directory = this.options.cacheDirectory
    await mkdir(directory, { recursive: true, mode: 0o700 })
    const stat = await lstat(directory)
    if (!stat.isDirectory() || stat.isSymbolicLink()) throw new Error('Unsafe Windows update cache')
    let count = 0
    for await (const entry of await opendir(directory)) {
      if (++count > 64) throw new Error('Unexpected Windows update cache contents')
      if (!cacheName.test(entry.name)) continue
      if (entry.isDirectory()) throw new Error('Unsafe Windows update cache entry')
      if (entry.name !== filename || entry.isSymbolicLink()) await rm(join(directory, entry.name), { force: true })
    }
  }

  private async performCheck(signal: AbortSignal): Promise<void> {
    let temporary: string | undefined
    let candidate: string | undefined
    this.notify({ state: 'checking' })
    try {
      const bytes = await fetchWindowsManifest(this.fetcher, windowsManifestURL(this.options.architecture), WINDOWS_MANIFEST_LIMIT, signal)
      const update = verifyWindowsManifest(bytes, this.options.trust.publicKey, this.options.architecture)
      signal.throwIfAborted()
      if (compareWindowsVersions(update.version, this.options.version) <= 0) { this.notify({ state: 'current' }); return }
      await this.prepareCache(update.filename)
      signal.throwIfAborted()
      candidate = join(this.options.cacheDirectory, update.filename)
      let cached = false
      try { verifyWindowsInstaller(candidate, update); cached = true }
      catch { await rm(candidate, { force: true }) }
      if (!cached) {
        temporary = candidate + '.part'
        this.notify({ state: 'downloading', version: update.version, percent: 0 })
        await downloadWindowsInstaller(this.fetcher, temporary, update, signal,
          percent => this.notify({ state: 'downloading', version: update.version, percent }))
        signal.throwIfAborted()
        await rename(temporary, candidate)
        temporary = undefined
      }
      this.notify({ state: 'verifying', version: update.version })
      await verifyPublisher(candidate, this.options.trust.publisherNames, signal)
      signal.throwIfAborted()
      verifyWindowsInstaller(candidate, update)
      this.ready = { update, path: candidate, at: Date.now() }
      this.expiry = setTimeout(() => { void this.cancel() }, WINDOWS_READY_LIFETIME)
      this.expiry.unref()
      this.notify({ state: 'ready', version: update.version })
    } catch {
      if (temporary) await rm(temporary, { force: true }).catch(() => {})
      if (candidate) await rm(candidate, { force: true }).catch(() => {})
      if (!signal.aborted) this.notify({ state: 'error' })
    }
  }

  async install(canInstall: () => Promise<boolean>): Promise<boolean> {
    if (this.installation || this.committed || !this.ready) return false
    this.installation = this.performInstall(canInstall)
    try { return await this.installation } finally { this.installation = undefined }
  }

  private async performInstall(canInstall: () => Promise<boolean>): Promise<boolean> {
    const ready = this.ready!
    const signal = this.controller!.signal
    try {
      if (Date.now() - ready.at > WINDOWS_READY_LIFETIME || Date.now() < ready.at) throw new Error('Update authorization expired')
      signal.throwIfAborted()
      await verifyPublisher(ready.path, this.options.trust.publisherNames, signal)
      if (!await canInstall() || ready !== this.ready || signal.aborted) return false
      // Recheck even same-session cache hits. No installer runs on its filename alone.
      verifyWindowsInstaller(ready.path, ready.update)
      signal.throwIfAborted()
      this.committed = true
      await this.launch(ready.path, this.options.applicationPath, this.options.resourcesPath)
      if (this.expiry) clearTimeout(this.expiry)
      this.notify({ state: 'installing', version: ready.update.version })
      return true
    } catch {
      this.committed = false
      this.ready = undefined
      if (this.expiry) clearTimeout(this.expiry)
      await rm(ready.path, { force: true }).catch(() => {})
      if (!signal.aborted) this.notify({ state: 'error' })
      return false
    }
  }

  async cancel(): Promise<boolean> {
    if (this.committed) return true
    const wasActive = this.active
    const ready = this.ready
    this.ready = undefined
    this.controller?.abort()
    if (this.expiry) clearTimeout(this.expiry)
    this.expiry = undefined
    await this.cycle
    await this.installation
    if (ready) await rm(ready.path, { force: true }).catch(() => {})
    if (wasActive) this.notify({ state: 'cancelled' })
    return true
  }
}
