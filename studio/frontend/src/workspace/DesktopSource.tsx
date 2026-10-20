import { useEffect, useState, type FormEvent } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { FolderOpen, Pause, Play, RefreshCw, Trash2 } from 'lucide-react';
import type { Connector, MnemionClient } from '@mnemion/client';
import type { DesktopSourceView, SourceConfigure } from '../../../shared/desktop-sources';

const message = (error: unknown) => error instanceof Error ? error.message : 'The source operation could not finish.';
const when = (value?: string) => value ? new Date(value).toLocaleString() : 'Waiting for its first scan';

function driveIds(value: string): string[] {
  return [...new Set(value.split(/[\s,]+/).filter(Boolean).map(item => {
    if (!item.includes('://')) return item;
    let url: URL;
    try { url = new URL(item); } catch { throw new Error('Use a Drive folder/file ID or its Google HTTPS link.'); }
    if (url.protocol !== 'https:' || !['drive.google.com', 'docs.google.com'].includes(url.hostname) || url.username || url.password) throw new Error('Use a Drive folder/file ID or its Google HTTPS link.');
    const parts = url.pathname.split('/');
    const marker = parts.includes('folders') ? 'folders' : 'd';
    return parts[parts.indexOf(marker) + 1] || url.searchParams.get('id') || '';
  }))];
}

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
  const [captureMode, setCaptureMode] = useState<'complete' | 'messages'>('complete');
  const [conversationIdentity, setConversationIdentity] = useState('');
  const [key, setKey] = useState('');
  const [providerKey, setProviderKey] = useState('');
  const [team, setTeam] = useState(''), [channels, setChannels] = useState('');
  const [folders, setFolders] = useState(''), [driveFiles, setDriveFiles] = useState('');
  const [threads, setThreads] = useState(true), [recursive, setRecursive] = useState(true);
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
    setCaptureMode(current?.capture_mode ?? 'complete');
    setConversationIdentity(current?.scope_id ?? '');
    setKey(''); setProviderKey(''); setPublication(false); setRevision(query.data?.revision);
    setTeam(current?.slack?.team_id ?? ''); setChannels(current?.slack?.channels.join('\n') ?? '');
    setThreads(current?.slack?.include_threads ?? true); setRecursive(current?.gdrive?.recursive ?? true);
    setFolders(current?.gdrive?.folder_ids.join('\n') ?? ''); setDriveFiles(current?.gdrive?.file_ids.join('\n') ?? '');
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
      const selection = connection.provider === 'slack' ? { slack: { team_id: team.trim(),
        channels: [...new Set(channels.split(/[\s,]+/).filter(Boolean))], include_threads: threads } }
        : connection.provider === 'gdrive' ? { gdrive: { folder_ids: driveIds(folders), file_ids: driveIds(driveFiles), recursive } }
        : { path, ...(connection.provider === 'conversations' ? { capture_mode: captureMode } : {}) };
      const me = await client.me();
      let credential = key || undefined;
      if (!current && !credential) {
        const issued = await client.createKey(connection.principal_id, 'Studio source ' + id.slice(0, 8));
        createdKey = issued.id; credential = issued.api_key;
      }
      const source: SourceConfigure['source'] = { id, endpoint, tenant_id: me.tenant_id,
        connector_id: connection.id, principal_id: connection.principal_id, name: connection.name,
        provider: connection.provider as SourceConfigure['source']['provider'], ...selection, members,
        ...(current?.scope_id ? { scope_id: current.scope_id }
          : connection.provider === 'conversations' && conversationIdentity !== '' ? { scope_id: conversationIdentity } : {}),
        publish_to_mapped_members: true, poll_seconds: Math.round(interval * 60), memory_limit_mib: memory,
        max_files: files, enabled: current?.enabled ?? true };
      accept(await native!.sourceConfigure!({ expected_revision: revision ?? query.data.revision, source,
        ...(credential ? { credential } : {}), ...(providerKey ? { provider_credential: providerKey } : {}) }));
      setKey(''); setProviderKey(''); setDirty(false); setPublication(false);
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
    } finally { setBusy(false); setProviderKey(''); }
  }
  const scanning = current?.activity.phase === 'scanning';
  const stale = dirty && revision !== undefined && revision !== query.data?.revision;
  const cloud = ['slack', 'gdrive'].includes(connection.provider);
  const hasLocation = connection.provider === 'slack' ? !!team.trim() && !!channels.trim()
    : connection.provider === 'gdrive' ? !!folders.trim() || !!driveFiles.trim() : !!path;
  return <section className="ws-card" data-update-pending={busy || dirty || key || removing ? '' : undefined}>
    <div className="ws-section-title"><h2>Run on this computer</h2>{current && <span className="ws-badge">{scanning ? 'Scanning' : current.enabled ? 'Automatic scans on' : 'Paused'}</span>}</div>
    <p>Studio can keep this {connection.provider === 'slack' ? 'Slack source' : connection.provider === 'gdrive' ? 'Google Drive source' : connection.provider === 'conversations' ? 'conversation folder' : 'folder or Obsidian vault'} connected while the app runs in the background. It uses a dedicated application key protected by your operating system.</p>
    {(error || query.error) && <div className="ws-notice ws-error" role="alert">{error ?? message(query.error)}</div>}
    {query.data && !query.data.secure_storage && <p className="ws-notice">Enable or unlock secure credential storage in your desktop session to save a background source.</p>}
    {current && <>
      <p className="ws-helper" style={{ overflowWrap: 'anywhere' }}>{current.slack ? `Slack ${current.slack.team_id} · ${current.slack.channels.length} selected channels` : current.gdrive ? `Drive · ${current.gdrive.folder_ids.length} folders and ${current.gdrive.file_ids.length} files` : current.path}</p>
      <p>{current.activity.message ?? (scanning ? 'Reading and reconciling this source…' : current.enabled ? 'Changes are checked automatically.' : 'This computer’s scans are paused.')}</p>
      {current.activity.report && <p className="ws-helper">{when(current.activity.report.timestamp)} · {current.activity.report.changed} changed · {current.activity.report.removed} removed · {current.activity.report.unchanged} unchanged · {current.activity.report.duration_seconds.toFixed(1)} seconds</p>}
      <p className="ws-helper">Every {current.poll_seconds / 60} minutes · up to {current.memory_limit_mib} MiB RAM · {current.max_files.toLocaleString()} {cloud && connection.provider === 'slack' ? 'messages per channel' : 'files'}. {current.enabled && !scanning && current.activity.next_scan_at ? `Next check: ${when(current.activity.next_scan_at)}.` : ''}</p>
      <div className="ws-actions">
        <button className="ws-button" disabled={busy || !current.enabled || !!connection.disabled_at} onClick={() => void control('sync')}><RefreshCw size={15} />{scanning ? 'Queue another scan' : 'Scan now'}</button>
        <button className="ws-button" disabled={busy} onClick={() => void control('pause')}>{current.enabled ? <Pause size={15} /> : <Play size={15} />}{current.enabled ? 'Pause on this computer' : 'Resume'}</button>
        <button className="ws-button" disabled={busy} onClick={() => setRemoving(!removing)}><Trash2 size={15} />Remove from this computer</button>
      </div>
      {removing && <div className="ws-notice"><p>This stops local scans and removes the saved connection here. Existing memories and the server’s application keys are retained. Revoke unused keys in People & apps.</p><button className="ws-button" disabled={busy} onClick={() => void control('remove')}>Confirm removal</button><button className="ws-button" onClick={() => setRemoving(false)}>Cancel</button></div>}
    </>}
    <details className="ws-details" open={!current || undefined}><summary>{current ? 'Source settings and key' : 'Choose your source'}</summary>
      <form className="ws-connector-form" onSubmit={event => void configure(event)}>
        {!cloud && <label>Source folder<input disabled={busy} data-update-safe readOnly value={path} required placeholder="Choose a folder on this computer" /></label>}
        {connection.provider === 'filesystem' && <p className="ws-helper">Reconnecting an existing folder keeps its original memory space. Choose that folder or its restored copy on this computer. Stop the previous computer’s source runner before starting its replacement.</p>}
        {!cloud && !current && <button className="ws-button" type="button" disabled={busy} onClick={async () => {
          try { const value = await native!.sourceChoose!(); if (value) { setPath(value); setDirty(true); } }
          catch (error) { setError(message(error)); }
        }}><FolderOpen size={16} />Choose folder</button>}
        {connection.provider === 'conversations' && <>
          <details className="ws-details"><summary>Reconnect an existing conversation source</summary>
            <label>Original conversation identity<input disabled={busy} data-update-safe readOnly={!!current} value={conversationIdentity} maxLength={400} placeholder="Default for sources created in Studio" onChange={event => {
              setConversationIdentity(event.target.value); setDirty(true); setPublication(false);
            }} /></label>
            <p className="ws-helper">For a source first connected through an adapter, use its original provider.scope_id. Keep the same relative file paths and stop the previous runner before reconnecting. Studio verifies existing capture identity before importing.</p>
          </details>
          <label>What to remember<select disabled={busy} data-update-safe value={captureMode} onChange={event => {
            setCaptureMode(event.target.value as 'complete' | 'messages'); setDirty(true); setPublication(false);
          }}><option value="complete">Messages and exposed session events</option><option value="messages">Messages only</option></select></label>
          <p className="ws-helper">{captureMode === 'complete'
            ? 'Keep the selected session records, including tool activity and reasoning traces your agent actually saves, plus readable messages.'
            : 'Copy supported user and assistant message text. Structured tool and reasoning records remain in the original files. Unknown formats produce no message copy.'}
            {' '}Changing this choice takes effect after a complete scan. Earlier copies, reviewed edits and backups follow their existing retention rules.</p>
        </>}
        {connection.provider === 'slack' && <>
          <label>Slack workspace ID<input disabled={busy} data-update-safe value={team} readOnly={!!current} maxLength={128} required placeholder="T0123456789" onChange={event => { setTeam(event.target.value); setDirty(true); setPublication(false); }} /></label>
          <label>Channel IDs<textarea disabled={busy} data-update-safe rows={3} value={channels} maxLength={16384} required placeholder="C0123456789, C9876543210" onChange={event => { setChannels(event.target.value); setDirty(true); setPublication(false); }} /></label>
          <label className="ws-checkbox"><input disabled={busy} data-update-safe type="checkbox" checked={threads} onChange={event => { setThreads(event.target.checked); setDirty(true); setPublication(false); }} />Include thread replies when the Slack token permits them</label>
          <label>{current ? 'Replace Slack token (blank retains it)' : 'Slack access token'}<input disabled={busy} data-update-safe type="password" autoComplete="new-password" value={providerKey} maxLength={4096} required={!current} onChange={event => { setProviderKey(event.target.value); setDirty(true); setPublication(false); }} /></label>
          <p className="ws-helper">Use your organization’s approved read token and invite its app to the selected channels. Workspace and channel IDs are in Slack’s web address. Mnemion reads selected history and membership; it never sends messages. A token must have the required history/member scopes, including replies when enabled.</p>
        </>}
        {connection.provider === 'gdrive' && <>
          <label>Drive folder IDs or links<textarea disabled={busy} data-update-safe rows={2} value={folders} maxLength={16384} placeholder="Paste selected Google Drive folder links" onChange={event => { setFolders(event.target.value); setDirty(true); setPublication(false); }} /></label>
          <label>Drive file IDs or links<textarea disabled={busy} data-update-safe rows={2} value={driveFiles} maxLength={16384} placeholder="Paste selected Drive or Google Docs links" onChange={event => { setDriveFiles(event.target.value); setDirty(true); setPublication(false); }} /></label>
          <p className="ws-helper">Choose at least one folder or file. Separate multiple IDs or links with spaces, commas or new lines.</p>
          <label className="ws-checkbox"><input disabled={busy} data-update-safe type="checkbox" checked={recursive} onChange={event => { setRecursive(event.target.checked); setDirty(true); setPublication(false); }} />Include subfolders</label>
          <label>{current ? 'Replacement Google service-account JSON (blank retains it)' : 'Google service-account JSON key'}<textarea disabled={busy} data-update-safe rows={4} value={providerKey} maxLength={8192} required={!current} autoComplete="off" spellCheck={false} onChange={event => { setProviderKey(event.target.value); setDirty(true); setPublication(false); }} /></label>
          <label>Choose a service-account key file<input disabled={busy} data-update-safe type="file" accept=".json,application/json" onChange={async event => {
            const file = event.target.files?.[0]; event.target.value = '';
            if (!file) return;
            if (file.size > 8192) { setError('Choose a service-account JSON key no larger than 8 KiB.'); return; }
            try { setProviderKey(await file.text()); setDirty(true); setPublication(false); }
            catch { setError('The selected key file could not be read.'); }
          }} /></label>
          <p className="ws-helper">An organization administrator enables the Drive API for its existing Google project and shares the selected files with this service account. Mnemion requests read-only access and renews its short-lived tokens automatically. People and agents still need mapped Google permission IDs above. Personal Drive folders can also use the Obsidian / folder option with Drive for desktop.</p>
        </>}
        <label>Check every (minutes)<input disabled={busy} data-update-safe type="number" min="0.5" max="60" step="0.5" value={interval} onChange={e => { setIntervalMinutes(Number(e.target.value)); setDirty(true); }} required /></label>
        <label>Maximum source RAM (MiB)<input disabled={busy} data-update-safe type="number" min="128" max="2048" step="1" value={memory} onChange={e => { setMemory(Number(e.target.value)); setDirty(true); }} required /></label>
        <label>{connection.provider === 'slack' ? 'Maximum messages per channel' : 'Maximum files per scan'}<input disabled={busy} data-update-safe type="number" min="1" max="100000" step="1" value={files} onChange={e => { setFiles(Number(e.target.value)); setDirty(true); }} required /></label>
        <label>{current ? 'Replace application key (optional)' : administrator ? 'Existing application key (optional)' : 'Dedicated application key'}<input disabled={busy} data-update-safe type="password" autoComplete="new-password" value={key} onChange={e => { setKey(e.target.value); setDirty(true); }} required={!current && !administrator} /></label>
        {!current && administrator && <p className="ws-helper">Leave the key empty to create one for this connection’s application automatically.</p>}
        <label className="ws-checkbox"><input disabled={busy} data-update-safe type="checkbox" checked={publication} onChange={e => { setPublication(e.target.checked); setDirty(true); }} required />{cloud ? `I have reviewed the selected source and ${members.length} mapped identities. Current provider permissions will govern access.` : `Publish this folder to the ${members.length} source ${members.length === 1 ? 'identity' : 'identities'} mapped above.`}</label>
        <p className="ws-helper">Choose only material intended for this workspace. {cloud ? 'Provider credentials stay in OS-protected storage on this computer. The first scan checks the selected channels or files and their memberships before publishing. Partial scans retain earlier good memories; Source status shows permission and quota failures.' : connection.provider === 'conversations' ? 'Complete JSONL records are captured incrementally; unfinished records wait for the next scan.' : 'Text files are imported; the source folder and Obsidian files stay editable in their original apps.'} Save again after changing its mapped audience.</p>
        {scanning && <p className="ws-helper">Pause the source before changing its settings.</p>}
        {stale && <p className="ws-notice">Source settings changed while you were editing. Discard edits to load the current settings before making another change.</p>}
        <button className="ws-button ws-primary" disabled={busy || scanning || stale || !hasLocation || !publication || (cloud && !current && !providerKey) || !query.data?.secure_storage || !!connection.disabled_at || members.length > 128}><Play size={15} />{current ? 'Save source settings' : 'Save and start scanning'}</button>
        {dirty && <button className="ws-button" type="button" disabled={busy} onClick={() => {
          setPath(current?.path ?? ''); setIntervalMinutes((current?.poll_seconds ?? 300) / 60); setMemory(current?.memory_limit_mib ?? 256);
          setFiles(current?.max_files ?? 10000); setCaptureMode(current?.capture_mode ?? 'complete'); setKey(''); setProviderKey(''); setPublication(false); setDirty(false);
        }}>Discard edits</button>}
      </form>
    </details>
    <p className="ws-helper">Only one source scans at a time. Sources resume with Studio after a restart and wait during app updates. Keep “Run in background” and “Start at login” enabled for unattended capture. Requests from other agents are picked up by the next scheduled scan.</p>
  </section>;
}
