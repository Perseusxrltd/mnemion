import type { JournalAccess, JournalChange, JournalDestination } from '../shared/local-workspace.js'
import { isAbsolute } from 'node:path'

const uuid = /^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/
const revision = /^(?:not-configured|[a-f0-9-]{36}|[a-f0-9]{64})$/
const destinationFields = ['space_id', 'label', 'remote', 'branch', 'prefix', 'personal_data_scan', 'ssh']
function object(input: unknown, fields: readonly string[]): Record<string, unknown> {
  if (!input || typeof input !== 'object' || Array.isArray(input) || Object.keys(input).some(key => !fields.includes(key))) throw new Error('Check the journal settings and supported fields.')
  return input as Record<string, unknown>
}
function text(value: unknown, maximum: number): value is string {
  return typeof value === 'string' && value.length > 0 && value.length <= maximum && !!value.trim() && !/[\x00-\x1f\x7f]/.test(value)
}
export function journalDestination(input: unknown): JournalDestination {
  const value = object(input, destinationFields)
  if (typeof value.space_id !== 'string' || !uuid.test(value.space_id) || !text(value.label, 200) ||
      !text(value.remote, 2048) || !text(value.branch, 200) || !text(value.prefix, 200) || typeof value.personal_data_scan !== 'boolean') throw new Error('Choose a space, label, Git repository, branch and journal folder.')
  try {
    const parsed = new URL(value.remote)
    const ssh = parsed.protocol === 'ssh:'
    if ((!ssh && parsed.protocol !== 'https:') || !parsed.hostname || parsed.hostname.startsWith('-') || /[^\x00-\x7f]|%/.test(parsed.hostname) ||
        (ssh ? !/^[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}$/.test(parsed.username) : !!parsed.username) || parsed.password || parsed.search || parsed.hash ||
        !parsed.pathname || /\s|\\/.test(value.remote) || (parsed.port && Number(parsed.port) < 1) || ssh !== (value.ssh !== undefined)) throw new Error()
  } catch { throw new Error('Use HTTPS without credentials or ssh://user@host/repository with a dedicated deploy key and pinned host keys.') }
  if (value.ssh !== undefined) {
    const ssh = object(value.ssh, ['identity_file', 'known_hosts_file'])
    if (!text(ssh.identity_file, 4096) || !isAbsolute(ssh.identity_file) || !text(ssh.known_hosts_file, 4096) || !isAbsolute(ssh.known_hosts_file)) throw new Error('Choose absolute paths to the private SSH key and known-hosts files on this computer.')
  }
  if (/^[\-/]|[/.]$|\.\.|@\{|\/\/|[\s~^:?*\[\\]/.test(value.branch) || value.branch === '@' ||
      value.branch.split('/').some(part => part.startsWith('.') || part.endsWith('.lock'))) throw new Error('Use a literal Git branch name.')
  if (value.prefix.split('/').some(part => !part || part.startsWith('.') || /[\s. ]$|[<>:"\\|?*]/.test(part) ||
      /^(?:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)/i.test(part))) throw new Error('Use a portable relative journal folder.')
  return structuredClone(value) as JournalDestination
}
export function journalOptions(input: unknown): JournalChange {
  const value = object(input, ['workspace_id', 'expected_revision', 'action', 'destination', 'space_id'])
  if (typeof value.workspace_id !== 'string' || !uuid.test(value.workspace_id) || typeof value.expected_revision !== 'string' || !revision.test(value.expected_revision) ||
      Buffer.byteLength(JSON.stringify(value), 'utf8') > 8192) throw new Error('Refresh the current workspace and journal settings before continuing.')
  const base = { workspace_id: value.workspace_id, expected_revision: value.expected_revision }
  if (value.action === 'save' && value.space_id === undefined) return { ...base, action: 'save', destination: journalDestination(value.destination) }
  if (value.destination === undefined && value.action === 'remove' && typeof value.space_id === 'string' && uuid.test(value.space_id)) return { ...base, action: 'remove', space_id: value.space_id }
  if (value.destination === undefined && value.space_id === undefined && value.action === 'reset') return { ...base, action: 'reset' }
  throw new Error('Choose one journal destination operation.')
}
export function journalSnapshot(input: unknown): JournalAccess {
  const value = object(input, ['revision', 'repairable', 'state', 'git_found', 'destinations', 'message'])
  if (typeof value.revision !== 'string' || !(revision.test(value.revision) || value.revision === 'unreadable') ||
      typeof value.repairable !== 'boolean' || typeof value.git_found !== 'boolean' || !text(value.message, 512) ||
      !['not_configured', 'configured', 'configuration_error', 'external'].includes(String(value.state)) ||
      !Array.isArray(value.destinations) || value.destinations.length > 64) throw new Error('Invalid local journal settings status.')
  const destinations = value.destinations.map(journalDestination)
  if (new Set(destinations.map(d => d.space_id)).size !== destinations.length ||
      new Set(destinations.map(d => JSON.stringify([d.remote, d.branch, d.prefix.toLowerCase()]))).size !== destinations.length) throw new Error('Each space needs its own repository folder.')
  return { ...value, destinations } as JournalAccess
}
