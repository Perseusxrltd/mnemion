import { randomUUID } from 'node:crypto'
import { existsSync, lstatSync, readFileSync, renameSync, rmSync, writeFileSync } from 'node:fs'
import { desktopExec } from './update-policy.js'

/** Follow a versioned AppImage without resetting the desktop's startup choices. */
export function refreshLinuxLoginEntry(path: string, executable: string, previousExecutable?: string): boolean {
  if (!existsSync(path)) return false // Removing the entry is an OS-level opt-out.
  const before = lstatSync(path)
  if (before.isSymbolicLink() || !before.isFile() || before.size > 8192) return false
  const original = readFileSync(path, 'utf8')
  const lines = original.split('\n')
  let main = false, index = -1
  for (let i = 0; i < lines.length; i++) {
    if (lines[i].startsWith('[')) main = lines[i].trim() === '[Desktop Entry]'
    if (main && lines[i].startsWith('Exec=')) {
      if (index !== -1) return false
      index = i
    }
  }
  if (index === -1) return false
  const next = `Exec=${desktopExec(executable)}`
  if (lines[index] === next) return false
  const previous = previousExecutable && `Exec=${desktopExec(previousExecutable)}`
  const official = /^Exec=".*\/Mnemion-Studio-\d+\.\d+\.\d+-linux-(?:x86_64|arm64)\.AppImage" --background$/.test(lines[index])
  if (!official && lines[index] !== previous) return false // Preserve a custom startup command.
  lines[index] = next
  const temporary = `${path}.${randomUUID()}.tmp`
  try {
    writeFileSync(temporary, lines.join('\n'), { mode: 0o600, flag: 'wx' })
    const current = lstatSync(path)
    if (current.isSymbolicLink() || before.ino !== current.ino || before.mtimeMs !== current.mtimeMs) return false
    renameSync(temporary, path)
    return true
  } finally { rmSync(temporary, { force: true }) }
}
