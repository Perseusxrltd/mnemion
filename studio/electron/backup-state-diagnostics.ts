/** Fixed local-file failure categories; no paths, settings or OS error text. */
import { basename } from 'node:path'

const fields = {
  document: ['policy', 'snapshot', 'ledger', 'retention', 'failure', 'configuration', 'other'],
  stage: ['path', 'path_private', 'open', 'descriptor', 'descriptor_private', 'replacement_limit',
    'metadata_before_read', 'read', 'metadata_after_read', 'json', 'close', 'policy', 'failure_record'],
  filesystem: ['none', 'missing', 'denied', 'busy', 'other'],
} as const
export type BackupStateDiagnostic = { [K in keyof typeof fields]: typeof fields[K][number] }
export const backupStateMessage = 'Backup settings could not be read safely. Existing recovery files were retained.'

export function backupStateDiagnostic(input: unknown): BackupStateDiagnostic | undefined {
  if (input === undefined) return undefined
  if (!input || typeof input !== 'object' || Array.isArray(input)) throw new Error('Invalid backup-state diagnostic')
  const value = input as Record<string, unknown>
  if (Object.keys(value).length !== 3 || Object.keys(value).some(key => !Object.hasOwn(fields, key))) {
    throw new Error('Invalid backup-state diagnostic')
  }
  for (const [key, allowed] of Object.entries(fields)) {
    if (typeof value[key] !== 'string' || !(allowed as readonly string[]).includes(value[key] as string)) {
      throw new Error('Invalid backup-state diagnostic')
    }
  }
  return { document: value.document, stage: value.stage, filesystem: value.filesystem } as BackupStateDiagnostic
}

export class BackupStateError extends Error {
  readonly diagnostic: BackupStateDiagnostic
  constructor(path: string, stage: BackupStateDiagnostic['stage'], error?: unknown) {
    super(backupStateMessage)
    const documents: Record<string, BackupStateDiagnostic['document']> = {
      'backup-policy.json': 'policy', 'last-backup.json': 'snapshot', 'last-ledger.json': 'ledger',
      'last-retention.json': 'retention', 'backup-failure.json': 'failure', 'configuration.json': 'configuration',
    }
    const code = error && typeof error === 'object' ? (error as NodeJS.ErrnoException).code : undefined
    const filesystem = code === undefined ? 'none' : code === 'ENOENT' ? 'missing' :
      code === 'EACCES' || code === 'EPERM' ? 'denied' : code === 'EBUSY' ? 'busy' : 'other'
    this.diagnostic = Object.freeze(backupStateDiagnostic({
      document: Object.hasOwn(documents, basename(path)) ? documents[basename(path)] : 'other', stage, filesystem,
    })!)
  }
}
