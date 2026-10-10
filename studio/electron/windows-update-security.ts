import { createHash, createPublicKey, timingSafeEqual, verify } from 'node:crypto'
import { constants, closeSync, fstatSync, lstatSync, openSync, readSync } from 'node:fs'

export const WINDOWS_RELEASES = 'https://github.com/Perseusxrltd/mnemion/releases'
export const WINDOWS_MANIFEST_LIMIT = 16 * 1024
export const WINDOWS_INSTALLER_LIMIT = 1024 ** 3
export const WINDOWS_INSTALLER_MINIMUM = 40 * 1024 ** 2
export const WINDOWS_READY_LIFETIME = 24 * 60 * 60_000
export type WindowsArchitecture = 'x64' | 'arm64'
export type WindowsUpdate = Readonly<{
  schema: 1
  application: 'com.perseusxr.mnemion-studio'
  platform: 'windows'
  architecture: WindowsArchitecture
  version: string
  filename: string
  url: string
  size: number
  sha512: string
}>

function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('Invalid update metadata')
  return value as Record<string, unknown>
}
function exactKeys(value: Record<string, unknown>, keys: string[]) {
  if (Object.keys(value).sort().join(',') !== keys.sort().join(',')) throw new Error('Unsupported update metadata')
}
function base64(value: unknown, size?: number): Buffer {
  if (typeof value !== 'string' || value.length > WINDOWS_MANIFEST_LIMIT) throw new Error('Invalid update encoding')
  const bytes = Buffer.from(value, 'base64')
  if (bytes.toString('base64') !== value || (size !== undefined && bytes.length !== size)) throw new Error('Invalid update encoding')
  return bytes
}
export function windowsArchitecture(value: string): WindowsArchitecture {
  if (value !== 'x64' && value !== 'arm64') throw new Error('Unsupported Windows architecture')
  return value
}
export function stableWindowsVersion(value: unknown): string {
  if (typeof value !== 'string' || !/^(0|[1-9]\d{0,7})\.(0|[1-9]\d{0,7})\.(0|[1-9]\d{0,7})$/.test(value)
    || Number(value.split('.')[0]) < 4) throw new Error('Unsupported stable update version')
  return value
}
export function compareWindowsVersions(left: string, right: string): number {
  const a = stableWindowsVersion(left).split('.').map(Number)
  const b = stableWindowsVersion(right).split('.').map(Number)
  for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) return a[i] > b[i] ? 1 : -1
  return 0
}
export function windowsManifestURL(architecture: string): string {
  return `${WINDOWS_RELEASES}/latest/download/latest-${windowsArchitecture(architecture)}-windows.json`
}

/** Only authenticated bytes become actionable metadata. No unsigned YAML fields are used. */
export function verifyWindowsManifest(bytes: Uint8Array, publicKey: string, architecture: string): WindowsUpdate {
  if (!bytes.byteLength || bytes.byteLength > WINDOWS_MANIFEST_LIMIT) throw new Error('Oversized update metadata')
  const decoder = new TextDecoder('utf-8', { fatal: true })
  const envelope = object(JSON.parse(decoder.decode(bytes)))
  exactKeys(envelope, ['schema', 'payload', 'signature'])
  if (envelope.schema !== 1) throw new Error('Unsupported update envelope')
  const payload = base64(envelope.payload)
  const key = createPublicKey({
    key: Buffer.concat([Buffer.from('302a300506032b6570032100', 'hex'), base64(publicKey, 32)]),
    format: 'der', type: 'spki',
  })
  if (!verify(null, payload, key, base64(envelope.signature, 64))) throw new Error('Invalid publisher update signature')
  const data = object(JSON.parse(decoder.decode(payload)))
  exactKeys(data, ['schema', 'application', 'platform', 'architecture', 'version', 'filename', 'url', 'size', 'sha512'])
  const version = stableWindowsVersion(data.version)
  const arch = windowsArchitecture(architecture)
  const filename = `Mnemion-Studio-${version}-windows-${arch}.exe`
  if (data.schema !== 1 || data.application !== 'com.perseusxr.mnemion-studio' || data.platform !== 'windows'
    || data.architecture !== arch || data.filename !== filename
    || data.url !== `${WINDOWS_RELEASES}/download/v${version}/${filename}`
    || !Number.isSafeInteger(data.size) || (data.size as number) < WINDOWS_INSTALLER_MINIMUM
    || (data.size as number) > WINDOWS_INSTALLER_LIMIT) throw new Error('Update does not match this application')
  base64(data.sha512, 64)
  return Object.freeze(data as WindowsUpdate)
}

/** The request may follow GitHub's asset redirects, never an arbitrary host or protocol. */
export function allowedWindowsRedirect(from: string, destination: string, initial: string): boolean {
  try {
    const previous = new URL(from), next = new URL(destination), origin = new URL(initial)
    if (next.protocol !== 'https:' || next.username || next.password || next.port || next.hash) return false
    if (previous.hostname === 'release-assets.githubusercontent.com') return false
    if (previous.hostname !== 'github.com' || origin.hostname !== 'github.com') return false
    if (next.hostname === 'release-assets.githubusercontent.com') return true
    if (next.hostname !== 'github.com' || next.search) return false
    // The moving feed may redirect only to that same feed in a stable tagged release.
    const name = origin.pathname.split('/').at(-1)
    const prefix = '/Perseusxrltd/mnemion/releases/'
    if (!origin.pathname.startsWith(prefix + 'latest/download/') || !name) return false
    const match = next.pathname.match(/^\/Perseusxrltd\/mnemion\/releases\/download\/v([^/]+)\/([^/]+)$/)
    return !!match && stableWindowsVersion(match[1]) === match[1] && match[2] === name
  } catch { return false }
}

/** Bounded memory, exact size, no symlinks, and a new digest immediately before execution. */
export function verifyWindowsInstaller(path: string, update: WindowsUpdate): void {
  const before = lstatSync(path)
  if (!before.isFile() || before.isSymbolicLink() || before.size !== update.size) throw new Error('Invalid cached installer')
  const descriptor = openSync(path, constants.O_RDONLY | (constants.O_NOFOLLOW || 0))
  try {
    const opened = fstatSync(descriptor)
    if (!opened.isFile() || opened.size !== update.size || opened.ino !== before.ino || opened.dev !== before.dev) throw new Error('Installer changed during verification')
    const hash = createHash('sha512')
    const buffer = Buffer.allocUnsafe(1024 * 1024)
    let total = 0
    for (;;) {
      const length = readSync(descriptor, buffer, 0, Math.min(buffer.length, update.size - total + 1), null)
      if (!length) break
      total += length
      if (total > update.size) throw new Error('Oversized cached installer')
      hash.update(buffer.subarray(0, length))
    }
    const after = fstatSync(descriptor)
    const final = lstatSync(path)
    if (total !== update.size || after.size !== opened.size || after.mtimeMs !== opened.mtimeMs
      || final.isSymbolicLink() || final.ino !== opened.ino || final.dev !== opened.dev
      || final.size !== opened.size || final.mtimeMs !== opened.mtimeMs
      || !timingSafeEqual(hash.digest(), base64(update.sha512, 64))) throw new Error('Installer digest does not match the signed release')
  } finally { closeSync(descriptor) }
}
