/** One-use window presentation after an update, never permission to install. */
import { randomUUID } from 'node:crypto'
import { closeSync, constants, fstatSync, lstatSync, openSync, readSync, renameSync, rmSync, writeFileSync, type Stats } from 'node:fs'

const maximumBytes = 512
const maximumAge = 60 * 60_000
const stableVersion = /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/

function ordinaryFile(value: Stats): boolean {
  return value.isFile() && value.nlink === 1 && value.size > 0 && value.size <= maximumBytes
    && (process.platform === 'win32' || (value.uid === process.geteuid?.() && (value.mode & 0o077) === 0))
}

export function clearUpdateRelaunch(path: string): boolean {
  try { rmSync(path, { force: true }); return true }
  catch { return false }
}

export function rememberUpdateRelaunch(path: string, version: string, background: boolean, now = Date.now()): void {
  const temporary = `${path}.${randomUUID()}.tmp`
  try {
    if (version.length > 64 || !stableVersion.test(version) || typeof background !== 'boolean'
        || !Number.isSafeInteger(now) || now <= 0) throw new Error('Invalid restart state')
    writeFileSync(temporary, JSON.stringify({ format: 1, version, background, createdAt: now }), { flag: 'wx', mode: 0o600 })
    renameSync(temporary, path)
  } catch {
    throw new Error('The app could not preserve its update restart state')
  } finally {
    try { rmSync(temporary, { force: true }) } catch { /* Never remove another path to complete a handoff. */ }
  }
}

export function consumeUpdateRelaunch(path: string, version: string, now = Date.now()): boolean | null {
  let file: number | undefined
  let background: boolean | null = null
  try {
    const before = lstatSync(path)
    if (ordinaryFile(before)) {
      file = openSync(path, constants.O_RDONLY | (constants.O_NOFOLLOW || 0) | (constants.O_NONBLOCK || 0))
      const opened = fstatSync(file)
      if (ordinaryFile(opened) && before.dev === opened.dev && before.ino === opened.ino) {
        const buffer = Buffer.alloc(maximumBytes + 1)
        const bytes = readSync(file, buffer, 0, buffer.length, 0)
        const after = fstatSync(file)
        if (ordinaryFile(after) && bytes === opened.size && bytes === after.size
            && opened.dev === after.dev && opened.ino === after.ino
            && opened.mtimeMs === after.mtimeMs && opened.ctimeMs === after.ctimeMs) {
          const value = JSON.parse(buffer.subarray(0, bytes).toString('utf8'))
          if (value && Object.keys(value).sort().join(',') === 'background,createdAt,format,version'
              && value.format === 1 && value.version === version && typeof value.background === 'boolean'
              && Number.isSafeInteger(value.createdAt) && value.createdAt > 0
              && Number.isSafeInteger(now) && now >= value.createdAt && now - value.createdAt <= maximumAge) {
            background = value.background
          }
        }
      }
    }
  } catch { /* Missing, stale or damaged hints retain normal startup behavior. */ }
  finally {
    if (file !== undefined) { try { closeSync(file) } catch { background = null } }
    // Do not apply a hint which could not be consumed; it must never become a
    // persistent setting that hides later deliberate launches of this version.
    if (!clearUpdateRelaunch(path)) background = null
  }
  return background
}
