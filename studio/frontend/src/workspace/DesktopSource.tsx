import { useEffect, useState, type FormEvent } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { FolderOpen, Pause, Play, RefreshCw, Trash2 } from 'lucide-react';
import type { Connector, MnemionClient } from '@mnemion/client';
import type { CapturePolicy, CapturePreview, DesktopSourceView, SourceConfigure, SourcePreviewSelection } from '../../../shared/desktop-sources';
import SourceScanHistory from './SourceScanHistory';
import CaptureStatus from './CaptureStatus';
import CapturePreviewPanel from './CapturePreviewPanel';
import CaptureRestore from './CaptureRestore';

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
  const [keepAccepted, setKeepAccepted] = useState(false);
  const [pendingLimit, setPendingLimit] = useState(256);
  const [historyLimit, setHistoryLimit] = useState(100000);
  const [databaseLimit, setDatabaseLimit] = useState(512);
  const [deviceKeyId, setDeviceKeyId] = useState('');
  const [conversationIdentity, setConversationIdentity] = useState('');
  const [key, setKey] = useState('');
  const [providerKey, setProviderKey] = useState('');
  const [preset, setPreset] = useState<CapturePolicy['preset']>('detailed');
  const [sessionIncludes, setSessionIncludes] = useState('*.jsonl'), [sessionExcludes, setSessionExcludes] = useState('');
  const [maxFileBytes, setMaxFileBytes] = useState(1_000_000_000), [maxRecordBytes, setMaxRecordBytes] = useState(2_000_000);
  const [previewState, setPreviewState] = useState<{ configuration: string; result: CapturePreview }>();
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
    setPreset(current?.capture_policy?.preset ?? (current?.capture_mode === 'messages' ? 'conversation' : 'detailed'));
    setSessionIncludes(current?.capture_policy?.include.join('\n') ?? '*.jsonl'); setSessionExcludes(current?.capture_policy?.exclude.join('\n') ?? '');
    setMaxFileBytes(current?.capture_policy?.max_file_bytes ?? 1_000_000_000); setMaxRecordBytes(current?.capture_policy?.max_record_bytes ?? 2_000_000);
    setPreviewState(undefined);
    setKeepAccepted(!!current?.custody); setPendingLimit(current?.custody?.pending_limit_mib ?? 256); setDeviceKeyId('');
    setHistoryLimit(current?.custody?.history_limit_events ?? 100000); setDatabaseLimit(current?.custody?.database_limit_mib ?? 512);
    setConversationIdentity(current?.scope_id ?? '');
    setKey(''); setProviderKey(''); setPublication(false); setRevision(query.data?.revision);
    setTeam(current?.slack?.team_id ?? ''); setChannels(current?.slack?.channels.join('\n') ?? '');
    setThreads(current?.slack?.include_threads ?? true); setRecursive(current?.gdrive?.recursive ?? true);
    setFolders(current?.gdrive?.folder_ids.join('\n') ?? ''); setDriveFiles(current?.gdrive?.file_ids.join('\n') ?? '');
  }, [current?.id, query.data?.revision, dirty]);
  const rules = (text: string) => text.split('\n').map(value => value.trim()).filter(Boolean);
  const capturePolicy: CapturePolicy | undefined = connection.provider === 'conversations' && (!current?.custody || current.capture_policy) ? {
    format: 'mnemion-capture-policy-v1', preset, capture_mode: captureMode,
    include: rules(sessionIncludes), exclude: rules(sessionExcludes), retention: keepAccepted ? 'until_deleted' : 'source_mirror',
    max_file_bytes: maxFileBytes, max_record_bytes: maxRecordBytes,
  } : undefined;
  const previewSelection: SourcePreviewSelection = { path, capture_mode: captureMode, capture_policy: capturePolicy,
    keep_accepted: keepAccepted, memory_limit_mib: memory, max_files: files, pending_limit_mib: keepAccepted ? pendingLimit : 256,
    history_limit_events: keepAccepted ? historyLimit : 100000, database_limit_mib: keepAccepted ? databaseLimit : 512 };
  const previewConfiguration = JSON.stringify(previewSelection);
  const capturePreview = previewState?.configuration === previewConfiguration ? previewState.result : undefined;
  async function previewCapture() {
    setBusy(true); setError(undefined);
    try {
      if (!native?.sourcePreview) throw new Error('Update Studio to preview capture settings.');
      const result = await native.sourcePreview(previewSelection);
      setPreviewState({ configuration: previewConfiguration, result });
    } catch (error) { setError(message(error)); }
    finally { setBusy(false); }
  }
  function accept(value: DesktopSourceView) {
    cache.setQueryData(['desktop-sources'], value);
    void cache.invalidateQueries({ queryKey: ['connector-scopes', connection.id] });
    void cache.invalidateQueries({ queryKey: ['connector-sync', connection.id] });
  }
  async function control(action: 'pause' | 'sync' | 'remove' | 'repair') {
    if (!current || !query.data) return;
    setBusy(true); setError(undefined);
    try {
      const session = action === 'remove' && current.custody && administrator ? (await native!.workspaceStatus?.())?.active : undefined;
      const retirement = session?.me.administrator && session.me.tenant_id === current.tenant_id && session.endpoint === current.endpoint ? session.sessionToken : undefined;
      accept(await native!.sourceControl!(action, { expected_revision: query.data.revision, id: current.id,
        ...(action === 'pause' ? { enabled: !current.enabled } : {}), ...(action === 'remove' ? { confirm: true } : {}),
        ...(action === 'remove' && current.custody ? { discard_local_inbox: true } : {}),
        ...(retirement ? { retirement_credential: retirement } : {}),
        ...(action === 'repair' ? { confirm: true, repair_token: current.activity.repair_token } : {}) }));
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
      if (capturePolicy && !capturePreview) throw new Error('Preview these capture settings before saving.');
      const selection = connection.provider === 'slack' ? { slack: { team_id: team.trim(),
        channels: [...new Set(channels.split(/[\s,]+/).filter(Boolean))], include_threads: threads } }
        : connection.provider === 'gdrive' ? { gdrive: { folder_ids: driveIds(folders), file_ids: driveIds(driveFiles), recursive } }
        : { path, ...(connection.provider === 'conversations' ? { capture_mode: captureMode, ...(capturePolicy ? { capture_policy: capturePolicy } : {}) } : {}) };
      const me = await client.me();
      if (keepAccepted) {
        const health = await client.request<{ durable_capture?: string }>('GET', '/health/live');
        if (health.durable_capture !== 'v1') throw new Error('Update this workspace server before enabling retained conversation capture.');
        const catalog = await client.request<{ items: unknown[]; next_cursor?: string | null }>('GET', `/v1/connectors/${encodeURIComponent(connection.id)}/scopes?limit=1`);
        if (!Array.isArray(catalog.items) || catalog.items.length || catalog.next_cursor) throw new Error('This connection already mirrors conversation history. Keep its current policy until a reviewed migration is available; retained capture needs a new connection.');
        if (!current && key && !/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/.test(deviceKeyId)) throw new Error('Provide the ID of this dedicated application key so its device grant can be bound correctly.');
      }
      let credential = key || undefined;
      let issuedKeyId = deviceKeyId;
      if (!current && !credential) {
        const issued = await client.createKey(connection.principal_id, 'Studio source ' + id.slice(0, 8));
        createdKey = issued.id; credential = issued.api_key; issuedKeyId = issued.id;
      }
      const custody = keepAccepted ? { ...(current?.custody ?? { source_id: id, grant_id: crypto.randomUUID(), keep_accepted: true as const }),
        pending_limit_mib: pendingLimit, history_limit_events: historyLimit, database_limit_mib: databaseLimit } : undefined;
      if (custody) {
        const route = `/v1/connectors/${encodeURIComponent(connection.id)}/capture-sources/${encodeURIComponent(custody.source_id)}`;
        const policy = { namespace: current?.scope_id ?? (conversationIdentity || 'selected-source'),
          name: connection.name, members, capture_mode: captureMode, keep_accepted: true,
          ...(capturePolicy ? { capture_policy: capturePolicy } : {}) };
        const existing = current?.custody ? await client.request<{ version: number; name: string; members: string[];
          capture_mode: 'messages' | 'complete'; capture_policy?: CapturePolicy | null }>('GET', route) : undefined;
        if (!existing || existing.name !== policy.name || JSON.stringify([...existing.members].sort()) !== JSON.stringify([...members].sort())) {
          await client.request('PUT', route, { body: { ...policy,
            ...(existing ? { capture_mode: existing.capture_mode, capture_policy: existing.capture_policy ?? null } : {}),
            expected_version: existing?.version ?? 0 } });
        }
        if (!current?.custody) await client.request('PUT', `/v1/capture-sources/${encodeURIComponent(custody.source_id)}/grants/${encodeURIComponent(custody.grant_id)}`, { body: { device_key_id: issuedKeyId } });
      }
      const source: SourceConfigure['source'] = { id, endpoint, tenant_id: me.tenant_id,
        connector_id: connection.id, principal_id: connection.principal_id, name: connection.name,
        provider: connection.provider as SourceConfigure['source']['provider'], ...selection, members,
        ...(custody ? { custody } : {}),
        ...(current?.scope_id ? { scope_id: current.scope_id }
          : connection.provider === 'conversations' && conversationIdentity !== '' ? { scope_id: conversationIdentity } : {}),
        publish_to_mapped_members: true, poll_seconds: Math.round(interval * 60), memory_limit_mib: memory,
        max_files: files, enabled: current?.enabled ?? true };
      accept(await native!.sourceConfigure!({ expected_revision: revision ?? query.data.revision, source,
        ...(capturePolicy && capturePreview ? { preview_hash: capturePreview.configuration_hash } : {}),
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
    <div className="ws-section-title"><h2>Run on this computer</h2>{current && <span className="ws-badge">{scanning ? 'Scanning' : !current.enabled ? 'Paused' : current.activity.phase === 'backfill' ? 'Backfilling' : current.activity.phase === 'attention' ? 'Needs attention' : 'Automatic scans on'}</span>}</div>
    <p>Studio can keep this {connection.provider === 'slack' ? 'Slack source' : connection.provider === 'gdrive' ? 'Google Drive source' : connection.provider === 'conversations' ? 'conversation folder' : 'folder or Obsidian vault'} connected while the app runs in the background. It uses a dedicated application key protected by your operating system.</p>
    {(error || query.error) && <div className="ws-notice ws-error" role="alert">{error ?? message(query.error)}</div>}
    {query.data && !query.data.secure_storage && <p className="ws-notice">Enable or unlock secure credential storage in your desktop session to save a background source.</p>}
    {current && <>
      <p className="ws-helper" style={{ overflowWrap: 'anywhere' }}>{current.slack ? `Slack ${current.slack.team_id} · ${current.slack.channels.length} selected channels` : current.gdrive ? `Drive · ${current.gdrive.folder_ids.length} folders and ${current.gdrive.file_ids.length} files` : current.path}</p>
      <p>{current.activity.message ?? (scanning ? 'Reading and reconciling this source…' : current.enabled ? 'Changes are checked automatically.' : 'This computer’s scans are paused.')}</p>
      {current.activity.report && <p className="ws-helper">Last report: {when(current.activity.report.timestamp)} · {current.activity.report.changed} changed · {current.activity.report.removed} removed · {current.activity.report.unchanged} unchanged · {current.activity.report.duration_seconds.toFixed(1)} seconds</p>}
      <SourceScanHistory activity={current.activity} busy={busy} onRepair={() => void control('repair')} />
      {current.custody && <CaptureStatus report={current.activity.report?.capture} />}
      <p className="ws-helper">Every {current.poll_seconds / 60} minutes · up to {current.memory_limit_mib} MiB RAM · {current.max_files.toLocaleString()} {cloud && connection.provider === 'slack' ? 'messages per channel' : 'files'}. {current.enabled && !scanning && current.activity.next_scan_at ? `Next check: ${when(current.activity.next_scan_at)}.` : ''}</p>
      <div className="ws-actions">
        <button className="ws-button" disabled={busy || !current.enabled || !!connection.disabled_at} onClick={() => void control('sync')}><RefreshCw size={15} />{scanning ? 'Queue another scan' : 'Scan now'}</button>
        <button className="ws-button" disabled={busy} onClick={() => void control('pause')}>{current.enabled ? <Pause size={15} /> : <Play size={15} />}{current.enabled ? 'Pause on this computer' : 'Resume'}</button>
        <button className="ws-button" disabled={busy} onClick={() => setRemoving(!removing)}><Trash2 size={15} />Remove from this computer</button>
      </div>
      {removing && <div className="ws-notice"><p>{current.custody
        ? 'Pause this source first. Removal revokes this device’s capture grant and permanently discards every locally queued memory, including deliveries with an unknown outcome. The workspace must be reachable to confirm revocation. Original chat files and server memories remain; the application key’s other permissions remain until you revoke it in People & apps.'
        : 'This stops local scans and removes the saved connection here. Existing memories and the server’s application keys are retained. Revoke unused keys in People & apps.'}</p>{current.custody && administrator && <p>Your current administrator connection can confirm removal if this device’s saved key is unavailable.</p>}<button className="ws-button" disabled={busy || (!!current.custody && current.enabled)} onClick={() => void control('remove')}>{current.custody ? 'Revoke device grant and discard local inbox' : 'Confirm removal'}</button><button className="ws-button" onClick={() => setRemoving(false)}>Cancel</button></div>}
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
          <label>What to remember<select disabled={busy || !!current?.custody} data-update-safe value={preset === 'selected' && capturePolicy ? 'selected' : captureMode} onChange={event => {
            if (event.target.value === 'selected') setPreset('selected');
            else { setCaptureMode(event.target.value as 'complete' | 'messages'); setPreset(event.target.value === 'complete' ? 'detailed' : 'conversation'); }
            setDirty(true); setPublication(false);
          }}><option value="complete">Detailed · messages and exposed session events</option><option value="messages">Conversation · messages only</option>{capturePolicy && <option value="selected">Selected · choose sessions and content</option>}</select></label>
          {capturePolicy && preset === 'selected' && <label className="ws-checkbox"><input type="checkbox" data-update-safe disabled={busy || !!current?.custody} checked={captureMode === 'complete'} onChange={event => {
            setCaptureMode(event.target.checked ? 'complete' : 'messages'); setDirty(true); setPublication(false);
          }} />Include exposed tool activity and session events in selected sessions</label>}
          <p className="ws-helper">{captureMode === 'complete'
            ? 'Keep the selected session records, including tool activity and reasoning traces your agent actually saves, plus readable messages.'
            : 'Copy supported user and assistant message text. Structured tool and reasoning records remain in the original files. Unknown formats produce no message copy.'}
            {' '}{current?.custody ? 'This retained inbox keeps its approved selection. Changing selection requires a reviewed migration.' : 'Changing this choice takes effect after a complete scan. Earlier copies, reviewed edits and backups follow their existing retention rules.'}</p>
          {capturePolicy && <details className="ws-details" open={preset === 'selected' || undefined}><summary>Session filters and capture sizes</summary>
            <label>Include filenames or patterns<textarea disabled={busy || !!current?.custody} data-update-safe rows={2} maxLength={32768} value={sessionIncludes} onChange={event => { setSessionIncludes(event.target.value); setPreset('selected'); setDirty(true); setPublication(false); }} /></label>
            <label>Additional exclusions<textarea disabled={busy || !!current?.custody} data-update-safe rows={2} maxLength={32768} value={sessionExcludes} onChange={event => { setSessionExcludes(event.target.value); setPreset('selected'); setDirty(true); setPublication(false); }} /></label>
            <p className="ws-helper">One relative filename or pattern per line, such as team/*.jsonl or private/*.jsonl. Patterns are case-sensitive and * can match subfolders. Built-in private-file exclusions always apply. New matching files are included automatically.</p>
            <label>Maximum file size (MB)<input type="number" disabled={busy || !!current?.custody} data-update-safe min="0.001" max="1000000" step="0.001" value={maxFileBytes / 1_000_000} onChange={event => { setMaxFileBytes(Math.round(Number(event.target.value) * 1_000_000)); setDirty(true); setPublication(false); }} /></label>
            <label>Maximum event record (KB)<input type="number" disabled={busy || !!current?.custody} data-update-safe min="0.001" max="16000" step="0.001" value={maxRecordBytes / 1000} onChange={event => { setMaxRecordBytes(Math.round(Number(event.target.value) * 1000)); setDirty(true); setPublication(false); }} /></label>
          </details>}
          <label className="ws-checkbox"><input disabled={busy || !!current || !administrator} data-update-safe type="checkbox" checked={keepAccepted} onChange={event => {
            setKeepAccepted(event.target.checked); setDirty(true); setPublication(false);
          }} />Keep captured memories when original chat logs rotate or are removed</label>
          <p className="ws-helper">Retained capture stores only the selected mode in a separately encrypted local inbox before delivery. The workspace administrator approves its audience and device grant. Existing source mirrors keep their current policy; changing an established source needs a reviewed migration.</p>
          {keepAccepted && <>
            <label>Maximum pending content for this source (MiB)<input disabled={busy} data-update-safe type="number" min="1" max="1024" step="1" value={pendingLimit} onChange={event => { setPendingLimit(Number(event.target.value)); setDirty(true); }} required /></label>
            <label>Maximum entries per history counter<input disabled={busy} data-update-safe type="number" min="1000" max="500000" step="1" value={historyLimit} onChange={event => { setHistoryLimit(Number(event.target.value)); setDirty(true); setPublication(false); }} required /></label>
            <label>Maximum encrypted storage for this source (MiB)<input disabled={busy} data-update-safe type="number" min="64" max="2048" step="1" value={databaseLimit} onChange={event => { setDatabaseLimit(Number(event.target.value)); setDirty(true); setPublication(false); }} required /></label>
            <p className="ws-helper">History protects against duplicate capture and restores deletion decisions. Its entry limit applies separately to accepted fragments, source event identities, saved source fragments and deletion records. Changing these limits preserves the inbox, its key and delivery history.</p>
            <p className="ws-helper">Across this computer, pending selected content is capped at 1 GiB; encrypted databases have separate size limits. New intake needs at least 512 MiB free disk. Accepted evidence waits without automatic expiry. Reducing a limit stops new intake while existing evidence can still be delivered.</p>
          </>}
          <button className="ws-button" type="button" disabled={busy || !path} onClick={() => void previewCapture()}>Preview capture</button>
          {capturePreview && <CapturePreviewPanel preview={capturePreview} />}
          {capturePolicy && !capturePreview && <p className="ws-helper">Preview the current folder, content choices and limits before saving. Changing these choices requires a new preview.</p>}
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
        <label>{current?.custody ? 'Dedicated key retained with this inbox' : current ? 'Replace application key (optional)' : administrator ? 'Existing application key (optional)' : 'Dedicated application key'}<input disabled={busy || !!current?.custody} data-update-safe type="password" autoComplete="new-password" value={key} onChange={e => { setKey(e.target.value); setDirty(true); }} required={!current && !administrator} /></label>
        {keepAccepted && !current && key && <label>Dedicated application key ID<input disabled={busy} data-update-safe value={deviceKeyId} maxLength={36} required placeholder="Key ID from People & apps" onChange={event => { setDeviceKeyId(event.target.value); setDirty(true); }} /></label>}
        {!current && administrator && <p className="ws-helper">Leave the key empty to create one for this connection’s application automatically.</p>}
        <label className="ws-checkbox"><input disabled={busy} data-update-safe type="checkbox" checked={publication} onChange={e => { setPublication(e.target.checked); setDirty(true); }} required />{cloud ? `I have reviewed the selected source and ${members.length} mapped identities. Current provider permissions will govern access.` : `Publish this folder to the ${members.length} source ${members.length === 1 ? 'identity' : 'identities'} mapped above.`}</label>
        {members.length === 0 && <p className="ws-notice">Only the source application can read imported memories until you map a person or agent above. Organization administration alone does not grant access to this source’s content.</p>}
        <p className="ws-helper">Choose only material intended for this workspace. {cloud ? 'Provider credentials stay in OS-protected storage on this computer. The first scan checks the selected channels or files and their memberships before publishing. Partial scans retain earlier good memories; Source status shows permission and quota failures.' : connection.provider === 'conversations' ? 'Complete JSONL records are captured incrementally; unfinished records wait for the next scan.' : 'Text files are imported; the source folder and Obsidian files stay editable in their original apps.'} Save again after changing its mapped audience.</p>
        {scanning && <p className="ws-helper">Pause the source before changing its settings.</p>}
        {stale && <p className="ws-notice">Source settings changed while you were editing. Discard edits to load the current settings before making another change.</p>}
        <button className="ws-button ws-primary" disabled={busy || scanning || stale || !hasLocation || !publication || (!!capturePolicy && !capturePreview) || (cloud && !current && !providerKey) || !query.data?.secure_storage || !!connection.disabled_at || members.length > 128}><Play size={15} />{current ? 'Save source settings' : 'Save and start scanning'}</button>
        {dirty && <button className="ws-button" type="button" disabled={busy} onClick={() => {
          setPath(current?.path ?? ''); setIntervalMinutes((current?.poll_seconds ?? 300) / 60); setMemory(current?.memory_limit_mib ?? 256);
          setFiles(current?.max_files ?? 10000); setCaptureMode(current?.capture_mode ?? 'complete'); setKey(''); setProviderKey(''); setPublication(false); setDirty(false);
        }}>Discard edits</button>}
      </form>
    </details>
    {connection.provider === 'conversations' && administrator && <CaptureRestore key={connection.id}
      client={client} connection={connection} endpoint={endpoint} existing={!!current}
      revision={query.data?.revision} busy={busy} setBusy={setBusy} />}
    <p className="ws-helper">Only one source scans at a time. Sources resume with Studio after a restart and wait during app updates. Keep “Run in background” and “Start at login” enabled for unattended capture. Requests from other agents are picked up by the next scheduled scan.</p>
  </section>;
}
