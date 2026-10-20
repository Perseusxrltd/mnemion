import { useEffect, useState, type FormEvent } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { FolderOpen, Pause, Play, RefreshCw, Trash2 } from 'lucide-react';
import type { Connector, MnemionClient } from '@mnemion/client';
import type { DesktopSourceView, SourceConfigure } from '../../../shared/desktop-sources';

const message = (error: unknown) => error instanceof Error ? error.message : 'The source operation could not finish.';
const when = (value?: string) => value ? new Date(value).toLocaleString() : 'Waiting for its first scan';

export function DesktopSourceCard({ client, connection, endpoint, members, administrator }: {
  client: MnemionClient; connection: Connector; endpoint: string; members: string[]; administrator: boolean;
}) {
  const native = window.mnemion;
  const cache = useQueryClient();
  const query = useQuery({ queryKey: ['desktop-sources'], queryFn: () => native!.sourceStatus!(), refetchInterval: 15000 });
  const current = query.data?.sources.find(item => item.connector_id === connection.id && item.endpoint === endpoint.replace(/\/$/, ''));
  const [path, setPath] = useState('');
  const [interval, setIntervalMinutes] = useState(5);
  const [memory, setMemory] = useState(256);
  const [files, setFiles] = useState(10000);
  const [key, setKey] = useState('');
  const [publication, setPublication] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [revision, setRevision] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [removing, setRemoving] = useState(false);
  const [error, setError] = useState<string>();
  useEffect(() => native?.onSourceStatus?.(() => {
    void cache.invalidateQueries({ queryKey: ['desktop-sources'] });
    void cache.invalidateQueries({ queryKey: ['connectors'] });
    void cache.invalidateQueries({ queryKey: ['connector-sync', connection.id] });
    void cache.invalidateQueries({ queryKey: ['connector-scopes', connection.id] });
  }), [cache, native, connection.id]);
  useEffect(() => {
    if (dirty) return;
    setPath(current?.path ?? ''); setIntervalMinutes((current?.poll_seconds ?? 300) / 60);
    setMemory(current?.memory_limit_mib ?? 256); setFiles(current?.max_files ?? 10000);
    setKey(''); setPublication(false); setRevision(query.data?.revision);
  }, [current?.id, query.data?.revision, dirty]);
  function accept(value: DesktopSourceView) {
    cache.setQueryData(['desktop-sources'], value);
    void cache.invalidateQueries({ queryKey: ['connector-scopes', connection.id] });
    void cache.invalidateQueries({ queryKey: ['connector-sync', connection.id] });
  }
  async function control(action: 'pause' | 'sync' | 'remove') {
    if (!current || !query.data) return;
    setBusy(true); setError(undefined);
    try {
      accept(await native!.sourceControl!(action, { expected_revision: query.data.revision, id: current.id,
        ...(action === 'pause' ? { enabled: !current.enabled } : {}), ...(action === 'remove' ? { confirm: true } : {}) }));
      setRemoving(false);
    } catch (error) { setError(message(error)); await query.refetch(); }
    finally { setBusy(false); }
  }
  async function configure(event: FormEvent) {
    event.preventDefault();
    if (!query.data || !publication) return;
    setBusy(true); setError(undefined);
    const id = current?.id ?? crypto.randomUUID();
    let createdKey: string | undefined;
    try {
      const me = await client.me();
      let credential = key || undefined;
      if (!current && !credential) {
        const issued = await client.createKey(connection.principal_id, 'Studio source ' + id.slice(0, 8));
        createdKey = issued.id; credential = issued.api_key;
      }
      const source: SourceConfigure['source'] = { id, endpoint, tenant_id: me.tenant_id,
        connector_id: connection.id, principal_id: connection.principal_id, name: connection.name,
        provider: connection.provider as 'filesystem' | 'conversations', path, members,
        publish_to_mapped_members: true, poll_seconds: Math.round(interval * 60), memory_limit_mib: memory,
        max_files: files, enabled: current?.enabled ?? true };
      accept(await native!.sourceConfigure!({ expected_revision: revision ?? query.data.revision, source, ...(credential ? { credential } : {}) }));
      setKey(''); setDirty(false); setPublication(false);
    } catch (error) {
      let text = message(error);
      if (createdKey) {
        // The private settings write may have succeeded before a lost IPC reply.
        // Revoke a newly minted key only after confirming it was not installed.
        try {
          const observed = await native!.sourceStatus!(); accept(observed);
          if (!observed.sources.some(item => item.id === id)) await client.revokeKey(createdKey);
        } catch { text += ' Check this application’s keys in People & apps before creating another key.'; }
      }
      setError(text);
    } finally { setBusy(false); }
  }
  const scanning = current?.activity.phase === 'scanning';
  const stale = dirty && revision !== undefined && revision !== query.data?.revision;
  return <section className="ws-card" data-update-pending={busy || dirty || key || removing ? '' : undefined}>
    <div className="ws-section-title"><h2>Run on this computer</h2>{current && <span className="ws-badge">{scanning ? 'Scanning' : current.enabled ? 'Automatic scans on' : 'Paused'}</span>}</div>
    <p>Studio can keep this {connection.provider === 'conversations' ? 'conversation folder' : 'folder or Obsidian vault'} connected while the app runs in the background. It uses a dedicated application key protected by your operating system.</p>
    {(error || query.error) && <div className="ws-notice ws-error" role="alert">{error ?? message(query.error)}</div>}
    {query.data && !query.data.secure_storage && <p className="ws-notice">Enable or unlock secure credential storage in your desktop session to save a background source.</p>}
    {current && <>
      <p className="ws-helper" style={{ overflowWrap: 'anywhere' }}>{current.path}</p>
      <p>{current.activity.message ?? (scanning ? 'Reading and reconciling this source…' : current.enabled ? 'Changes are checked automatically.' : 'This computer’s scans are paused.')}</p>
      {current.activity.report && <p className="ws-helper">{when(current.activity.report.timestamp)} · {current.activity.report.changed} changed · {current.activity.report.removed} removed · {current.activity.report.unchanged} unchanged · {current.activity.report.duration_seconds.toFixed(1)} seconds</p>}
      <p className="ws-helper">Every {current.poll_seconds / 60} minutes · up to {current.memory_limit_mib} MiB RAM · {current.max_files.toLocaleString()} files. {current.enabled && !scanning && current.activity.next_scan_at ? `Next check: ${when(current.activity.next_scan_at)}.` : ''}</p>
      <div className="ws-actions">
        <button className="ws-button" disabled={busy || !current.enabled || !!connection.disabled_at} onClick={() => void control('sync')}><RefreshCw size={15} />{scanning ? 'Queue another scan' : 'Scan now'}</button>
        <button className="ws-button" disabled={busy} onClick={() => void control('pause')}>{current.enabled ? <Pause size={15} /> : <Play size={15} />}{current.enabled ? 'Pause on this computer' : 'Resume'}</button>
        <button className="ws-button" disabled={busy} onClick={() => setRemoving(!removing)}><Trash2 size={15} />Remove from this computer</button>
      </div>
      {removing && <div className="ws-notice"><p>This stops local scans and removes the saved connection here. Existing memories and the server’s application keys are retained. Revoke unused keys in People & apps.</p><button className="ws-button" disabled={busy} onClick={() => void control('remove')}>Confirm removal</button><button className="ws-button" onClick={() => setRemoving(false)}>Cancel</button></div>}
    </>}
    <details className="ws-details" open={!current || undefined}><summary>{current ? 'Source settings and key' : 'Choose your source'}</summary>
      <form className="ws-connector-form" onSubmit={event => void configure(event)}>
        <label>Source folder<input data-update-safe readOnly value={path} required placeholder="Choose a folder on this computer" /></label>
        {!current && <button className="ws-button" type="button" disabled={busy} onClick={async () => {
          try { const value = await native!.sourceChoose!(); if (value) { setPath(value); setDirty(true); } }
          catch (error) { setError(message(error)); }
        }}><FolderOpen size={16} />Choose folder</button>}
        <label>Check every (minutes)<input data-update-safe type="number" min="0.5" max="60" step="0.5" value={interval} onChange={e => { setIntervalMinutes(Number(e.target.value)); setDirty(true); }} required /></label>
        <label>Maximum source RAM (MiB)<input data-update-safe type="number" min="128" max="2048" step="1" value={memory} onChange={e => { setMemory(Number(e.target.value)); setDirty(true); }} required /></label>
        <label>Maximum files per scan<input data-update-safe type="number" min="1" max="100000" step="1" value={files} onChange={e => { setFiles(Number(e.target.value)); setDirty(true); }} required /></label>
        <label>{current ? 'Replace application key (optional)' : administrator ? 'Existing application key (optional)' : 'Dedicated application key'}<input data-update-safe type="password" autoComplete="new-password" value={key} onChange={e => { setKey(e.target.value); setDirty(true); }} required={!current && !administrator} /></label>
        {!current && administrator && <p className="ws-helper">Leave the key empty to create one for this connection’s application automatically.</p>}
        <label className="ws-checkbox"><input data-update-safe type="checkbox" checked={publication} onChange={e => { setPublication(e.target.checked); setDirty(true); }} required />Publish this folder to the {members.length} source {members.length === 1 ? 'identity' : 'identities'} mapped above.</label>
        <p className="ws-helper">Choose only material intended for this workspace. {connection.provider === 'conversations' ? 'Complete JSONL records are captured incrementally; unfinished records wait for the next scan.' : 'Text files are imported; the source folder and Obsidian files stay editable in their original apps.'} Each folder needs its own connection. Save again after changing its mapped audience.</p>
        {scanning && <p className="ws-helper">Pause the source before changing its settings.</p>}
        {stale && <p className="ws-notice">Source settings changed while you were editing. Discard edits to load the current settings before making another change.</p>}
        <button className="ws-button ws-primary" disabled={busy || scanning || stale || !path || !publication || !query.data?.secure_storage || !!connection.disabled_at || members.length > 128}><Play size={15} />{current ? 'Save source settings' : 'Save and start scanning'}</button>
        {dirty && <button className="ws-button" type="button" disabled={busy} onClick={() => {
          setPath(current?.path ?? ''); setIntervalMinutes((current?.poll_seconds ?? 300) / 60); setMemory(current?.memory_limit_mib ?? 256);
          setFiles(current?.max_files ?? 10000); setKey(''); setPublication(false); setDirty(false);
        }}>Discard edits</button>}
      </form>
    </details>
    <p className="ws-helper">Only one source scans at a time. Sources resume with Studio after a restart and wait during app updates. Keep “Run in background” and “Start at login” enabled for unattended capture. Requests from other agents are picked up by the next scheduled scan.</p>
  </section>;
}
