import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import type { Connector, MnemionClient } from '@mnemion/client';
import type { CaptureArchiveInfo, CapturePreview, CaptureRestored, SourcePreviewSelection } from '../../../shared/desktop-sources';
import CapturePreviewPanel from './CapturePreviewPanel';

export function CaptureRestoredNotice({ value }: { value: CaptureRestored }) {
  return <div className="ws-notice" data-capture-restored="ready" data-source-id={value.id}>
    <strong>{value.source_enabled ? 'Capture recovery confirmed' : 'Capture recovered and paused'}</strong>
    <p>{value.status.pending_events.toLocaleString()} pending fragments · {value.status.stored_events.toLocaleString()} delivered · {value.status.forgotten_events.toLocaleString()} forgotten</p>
    <p>The previous device’s capture grant is revoked. {value.source_enabled ? 'This source is running.' : 'Resume this source when you are ready to deliver its queue and watch the selected folder.'}</p>
  </div>;
}

export default function CaptureRestore({ client, connection, endpoint, existing, revision, busy, setBusy }: {
  client: MnemionClient; connection: Connector; endpoint: string; existing: boolean;
  revision?: string; busy: boolean; setBusy: (value: boolean) => void;
}) {
  const native = window.mnemion, cache = useQueryClient();
  const [file, setFile] = useState(''), [key, setKey] = useState(''), [path, setPath] = useState('');
  const [archive, setArchive] = useState<CaptureArchiveInfo>();
  const [preview, setPreview] = useState<{ selection: string; value: CapturePreview }>();
  const [memory, setMemory] = useState(256), [pending, setPending] = useState(256);
  const [confirmed, setConfirmed] = useState(false), [error, setError] = useState<string>();
  const [receipt, setReceipt] = useState<CaptureRestored>();
  if (!native?.sourceRestore || !native.sourceBackupInspect || !native.sourcePreview || (existing && !receipt)) return null;
  const selection: SourcePreviewSelection | undefined = archive ? { path, capture_mode: archive.binding.capture_mode,
    capture_policy: archive.binding.capture_policy, keep_accepted: true, pending_limit_mib: pending, memory_limit_mib: memory, max_files: 10000 } : undefined;
  const selectionKey = JSON.stringify(selection);
  const ready = preview && preview.selection === selectionKey ? preview.value : undefined;
  async function run(work: () => Promise<void>) {
    setBusy(true); setError(undefined);
    try { await work(); }
    catch (error) { setError(error instanceof Error ? error.message : 'Capture recovery could not finish. Inspect pending recoveries before retrying.'); }
    finally { setBusy(false); }
  }
  async function restore() {
    if (!archive || !ready || !revision || !confirmed) return;
    const id = crypto.randomUUID();
    let createdKey: string | undefined;
    try {
      const session = (await native!.workspaceStatus!()).active;
      if (!session?.me.administrator || session.me.tenant_id !== archive.binding.tenant_id || session.endpoint !== endpoint.replace(/\/$/, '')) throw new Error('Use a current administrator connection to this archive’s original workspace.');
      const source = await client.request<{ members: string[]; revoked_at: string | null }>('GET', `/v1/connectors/${connection.id}/capture-sources/${archive.binding.source_id}`);
      if (source.revoked_at || !Array.isArray(source.members)) throw new Error('This source no longer has active capture authorization. Review it with the workspace administrator.');
      const issued = await client.createKey(connection.principal_id, 'Recovered Studio source ' + id.slice(0, 8));
      createdKey = issued.id;
      const grant = crypto.randomUUID();
      await client.request('PUT', `/v1/capture-sources/${archive.binding.source_id}/grants/${grant}`, { body: { device_key_id: issued.id } });
      const result = await native!.sourceRestore!({ expected_revision: revision, file, recovery_key: key,
        archive_sha256: archive.archive_sha256, preview_hash: ready.configuration_hash, confirm: true,
        credential: issued.api_key, retirement_credential: session.sessionToken,
        source: { id, endpoint, tenant_id: archive.binding.tenant_id, connector_id: connection.id,
          principal_id: connection.principal_id, provider: 'conversations', name: connection.name,
          path, scope_id: archive.binding.namespace, capture_mode: archive.binding.capture_mode,
          ...(archive.binding.capture_policy ? { capture_policy: archive.binding.capture_policy } : {}),
          custody: { source_id: archive.binding.source_id, grant_id: grant, keep_accepted: true, pending_limit_mib: pending },
          members: source.members, publish_to_mapped_members: true, enabled: false,
          memory_limit_mib: memory, max_files: 10000, poll_seconds: 300 } });
      setReceipt(result.recovery); setFile(''); setKey(''); setPath(''); setArchive(undefined); setPreview(undefined); setConfirmed(false);
      cache.setQueryData(['desktop-sources'], result.view);
      void cache.invalidateQueries({ queryKey: ['capture-recoveries'] });
    } catch (error) {
      if (createdKey) {
        try {
          // A lost reply can follow a durable source or recovery-intent write.
          // Revoke only after both records establish that the key is unused.
          const current = await native!.sourceStatus!();
          const recoveries = await native!.sourceRecoveries!();
          cache.setQueryData(['desktop-sources'], current); cache.setQueryData(['capture-recoveries'], recoveries);
          if (!current.sources.some(item => item.id === id) && !recoveries.items.some(item => item.id === id)) await client.revokeKey(createdKey);
        } catch { throw new Error('Recovery was not confirmed. Read Sources on this computer and pending recoveries before creating another device key.'); }
      }
      throw error;
    }
  }
  return <details className="ws-details" data-capture-restore="form" data-update-pending={busy || file || key || path ? '' : undefined}>
    <summary>Recover an existing capture inbox</summary>
    {receipt ? <CaptureRestoredNotice value={receipt} /> : <div className="ws-form">
      <p>Recover this connection’s pending memories from an encrypted capture backup. A new device key replaces the previous capture grant. The recovered source stays paused for review.</p>
      <button type="button" className="ws-button" disabled={busy} onClick={() => void run(async () => {
        const selected = await native!.sourceBackupChoose!('open');
        if (selected) { setFile(selected); setArchive(undefined); setPreview(undefined); setConfirmed(false); }
      })}>Choose capture backup</button>
      {file && <p className="ws-helper" style={{ overflowWrap: 'anywhere' }}>{file}</p>}
      <label className="ws-field"><span>Backup recovery key</span><input type="password" data-update-safe autoComplete="off" spellCheck={false} maxLength={50} value={key} disabled={busy} onChange={event => { setKey(event.target.value); setArchive(undefined); setPreview(undefined); setConfirmed(false); }} /></label>
      <button type="button" className="ws-button" disabled={busy || !file || key.length !== 50} onClick={() => void run(async () => {
        const value = await native!.sourceBackupInspect!({ file, recovery_key: key });
        const me = await client.me();
        if (value.binding.tenant_id !== me.tenant_id || value.binding.connector_id !== connection.id) throw new Error('Choose the archive’s original workspace and connection before restoring it.');
        setArchive(value); setPreview(undefined); setConfirmed(false);
      })}>Verify recovery archive</button>
      {archive && <>
        <p className="ws-notice">{archive.status.pending_events.toLocaleString()} queued fragments · {archive.binding.capture_policy?.preset ?? archive.binding.capture_mode} capture. The original source identity, capture rules and deletion history will be retained.</p>
        <button type="button" className="ws-button" disabled={busy} onClick={() => void run(async () => {
          const folder = await native!.sourceChoose!(); if (folder) { setPath(folder); setPreview(undefined); setConfirmed(false); }
        })}>Choose this computer’s conversation folder</button>
        {path && <p className="ws-helper" style={{ overflowWrap: 'anywhere' }}>{path}</p>}
        <p className="ws-helper">Use the copied conversation folder, or an empty folder if the original logs are gone. Matching files must retain their captured prefixes; pending memories remain recoverable from the archive.</p>
        <label className="ws-field"><span>Source RAM allowance (MiB)</span><input type="number" min={128} max={2048} data-update-safe disabled={busy} value={memory} onChange={event => { setMemory(Number(event.target.value)); setConfirmed(false); }} /></label>
        <label className="ws-field"><span>Pending capture allowance (MiB)</span><input type="number" min={1} max={1024} data-update-safe disabled={busy} value={pending} onChange={event => { setPending(Number(event.target.value)); setConfirmed(false); }} /></label>
        <button type="button" className="ws-button" disabled={busy || !path} onClick={() => void run(async () => { setPreview({ selection: selectionKey, value: await native!.sourcePreview!(selection!) }); setConfirmed(false); })}>Preview recovered source</button>
        {ready && <CapturePreviewPanel preview={ready} />}
        <label className="ws-checkbox"><input type="checkbox" data-update-safe checked={confirmed} disabled={busy || !ready} onChange={event => setConfirmed(event.target.checked)} />I approve this folder and capture policy, and revoke the previous device’s capture grant.</label>
        <button type="button" className="ws-button" disabled={busy || !ready || !confirmed || !revision} onClick={() => void run(restore)}>{busy ? 'Working…' : 'Recover as a paused source'}</button>
      </>}
      {(file || key || path) && <button type="button" className="ws-button" disabled={busy} onClick={() => { setFile(''); setKey(''); setPath(''); setArchive(undefined); setPreview(undefined); setConfirmed(false); setError(undefined); }}>Clear recovery choices</button>}
    </div>}
    {error && <p className="ws-notice ws-error" role="alert">{error}</p>}
  </details>;
}
