/** Pure validation shared with Studio and the independent HTML recovery viewer.
 * Keep the function self-contained: its compiled body is included in that kit.
 */
export interface RecoveryDirectoryRecord {
  tenant_id: string; revision: number; updated_at: string | null; updated_by: string | null;
  directory: {
    instructions: string; independent_url: string | null;
    hosts: { id: string; name: string; role: 'primary' | 'recovery' | 'ingestion';
      platform: 'windows' | 'macos' | 'linux' | 'managed' | 'other';
      workspace_url: string | null; operator_url: string | null; operator: string; notes: string }[];
    materials: { id: string; name: string; kind: 'database_backup' | 'recovery_ledger' | 'source_mirror';
      location: string; access_url: string | null; reported_verified_at: string | null; notes: string }[];
    contacts: { id: string; name: string; channel: string; responsibility: string }[];
  };
}

export function recoveryRecord(value: unknown, tenant?: string): RecoveryDirectoryRecord {
  const invalid = () => new Error('The recovery record is invalid or belongs to another workspace.');
  const uuid = (v: unknown): string => {
    if (typeof v !== 'string' || !/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/i.test(v)) throw invalid();
    return v;
  };
  const text = (v: unknown, max: number, required = false): string => {
    if (typeof v !== 'string' || [...v].length > max || (required && !v.trim()) ||
      /[\u0000-\u0008\u000b-\u001f\u007f]/.test(v)) throw invalid();
    return v;
  };
  const object = (v: unknown): Record<string, unknown> => {
    if (!v || typeof v !== 'object' || Array.isArray(v)) throw invalid();
    return v as Record<string, unknown>;
  };
  const list = (v: unknown): Record<string, unknown>[] => {
    if (!Array.isArray(v) || v.length > 16) throw invalid();
    return v.map(object);
  };
  const choice = <T extends string>(v: unknown, choices: readonly T[]): T => {
    if (typeof v !== 'string' || !choices.includes(v as T)) throw invalid();
    return v as T;
  };
  const date = (v: unknown): string | null => {
    if (v === null) return null;
    if (typeof v !== 'string' || v.length > 64 || !/T.*(?:Z|[+-]\d\d:\d\d)$/.test(v) || !Number.isFinite(Date.parse(v))) throw invalid();
    return v;
  };
  const address = (v: unknown, workspace = false): string | null => {
    if (v === null) return null;
    const raw = text(v, 2048, true);
    let url: URL;
    try { url = new URL(raw); } catch { throw invalid(); }
    const loopback = workspace && ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname);
    if ((url.protocol !== 'https:' && !(loopback && url.protocol === 'http:')) ||
      url.username || url.password || url.search || url.hash || /[\s\\]/.test(raw)) throw invalid();
    return raw;
  };
  const source = object(value), directory = object(source.directory);
  const identifier = uuid(source.tenant_id);
  if (tenant !== undefined && identifier !== tenant) throw invalid();
  if (!Number.isSafeInteger(source.revision) || (source.revision as number) < 0 || (source.revision as number) > 2147483647) throw invalid();
  const result: RecoveryDirectoryRecord = {
    tenant_id: identifier, revision: source.revision as number,
    updated_at: date(source.updated_at), updated_by: source.updated_by === null ? null : uuid(source.updated_by),
    directory: {
      instructions: text(directory.instructions, 2000), independent_url: address(directory.independent_url),
      hosts: list(directory.hosts).map(h => ({
        id: uuid(h.id), name: text(h.name, 120, true),
        role: choice(h.role, ['primary', 'recovery', 'ingestion']),
        platform: choice(h.platform, ['windows', 'macos', 'linux', 'managed', 'other']),
        workspace_url: address(h.workspace_url, true), operator_url: address(h.operator_url),
        operator: text(h.operator, 200), notes: text(h.notes, 600),
      })),
      materials: list(directory.materials).map(m => ({
        id: uuid(m.id), name: text(m.name, 120, true),
        kind: choice(m.kind, ['database_backup', 'recovery_ledger', 'source_mirror']),
        location: text(m.location, 1024, true), access_url: address(m.access_url),
        reported_verified_at: date(m.reported_verified_at), notes: text(m.notes, 600),
      })),
      contacts: list(directory.contacts).map(c => ({
        id: uuid(c.id), name: text(c.name, 120, true), channel: text(c.channel, 300, true),
        responsibility: text(c.responsibility, 300),
      })),
    },
  };
  const ids = [...result.directory.hosts, ...result.directory.materials, ...result.directory.contacts].map(i => i.id);
  if (new Set(ids).size !== ids.length || (result.revision === 0
    ? result.updated_at !== null || result.updated_by !== null
    : result.updated_at === null || result.updated_by === null)) throw invalid();
  const encoded = JSON.stringify(result.directory);
  if (new TextEncoder().encode(encoded).length > 6144 ||
    /\bmnm_[A-Za-z0-9_-]{20,}|\bBearer\s+\S+|-----BEGIN [A-Z ]*PRIVATE KEY-----|\bpostgres(?:ql)?:\/\//i.test(encoded)) throw invalid();
  return result;
}
