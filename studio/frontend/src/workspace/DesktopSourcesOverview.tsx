import { useEffect, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { FolderSync, Pause, Play, Trash2 } from 'lucide-react';
import type { DesktopSource } from '../../../shared/desktop-sources';
import SourceScanHistory from './SourceScanHistory';
import CaptureStatus from './CaptureStatus';
import CaptureBackup from './CaptureBackup';

/** These device controls remain available before signing in to a workspace. */
export default function DesktopSourcesOverview() {
  const native = window.mnemion;
  const cache = useQueryClient();
  const query = useQuery({ queryKey: ['desktop-sources'], queryFn: () => native!.sourceStatus!(), enabled: !!native?.sourceStatus, refetchInterval: 15000 });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const [remove, setRemove] = useState<string>();
  const [retirementCredential, setRetirementCredential] = useState('');
  useEffect(() => native?.onSourceStatus?.(() => { void cache.invalidateQueries({ queryKey: ['desktop-sources'] }); }), [native, cache]);
  if (!native?.sourceStatus || (!query.error && !query.data?.sources.length && !native.sourceBackupInspect)) return null;
  async function control(source: DesktopSource, action: 'pause' | 'remove' | 'repair' = 'pause') {
    if (!query.data) return;
    setBusy(true); setError(undefined);
    try {
      const view = await native!.sourceControl!(action, {
        expected_revision: query.data.revision, id: source.id,
        ...(action === 'remove' && source.custody ? { discard_local_inbox: true } : {}),
        ...(action === 'remove' && source.custody && retirementCredential ? { retirement_credential: retirementCredential } : {}),
        ...(action === 'remove' ? { confirm: true } : action === 'repair' ? {
          confirm: true, repair_token: query.data.sources.find(item => item.id === source.id)?.activity.repair_token,
        } : { enabled: !source.enabled }),
      });
      cache.setQueryData(['desktop-sources'], view); setRemove(undefined); setRetirementCredential('');
    } catch (error) { setError(error instanceof Error ? error.message : 'The device control could not finish.'); await query.refetch(); }
    finally { setBusy(false); }
  }
  return <details className="ws-device-settings ws-local-sources" data-update-pending={busy || remove ? '' : undefined}>
    <summary><FolderSync size={18} /> Sources on this computer{query.data ? ` · ${query.data.sources.length}` : ''}</summary>
    <p>These sources keep syncing with their saved workspaces while Studio runs. You can pause them here while offline or signed out. Removing a retained inbox needs confirmed device-grant revocation; other local source settings can be removed offline.</p>
    {(error || query.error) && <p className="ws-notice ws-error" role="alert">{error ?? (query.error instanceof Error ? query.error.message : 'Saved sources could not be read.')}</p>}
    {query.data?.sources.map(source => <div className="ws-card" key={source.id}>
      <div className="ws-section-title"><h3>{source.name}</h3><span className="ws-badge">{!source.enabled ? 'Paused' : source.activity.phase === 'scanning' ? 'Scanning' : source.activity.phase === 'attention' ? 'Needs attention' : 'Automatic scans on'}</span></div>
      <p className="ws-helper" style={{ overflowWrap: 'anywhere' }}>{source.endpoint}<br />{source.slack ? `Slack ${source.slack.team_id} · ${source.slack.channels.length} channels` : source.gdrive ? `Drive · ${source.gdrive.folder_ids.length} folders and ${source.gdrive.file_ids.length} files` : source.path}</p>
      {source.activity.message && <p className="ws-helper">{source.activity.message}</p>}
      <SourceScanHistory activity={source.activity} busy={busy} onRepair={() => void control(source, 'repair')} />
      {source.custody && <CaptureStatus report={source.activity.report?.capture} />}
      {source.custody && <CaptureBackup source={source} revision={query.data?.revision} busy={busy} setBusy={setBusy} />}
      {source.enabled && source.activity.next_scan_at && source.activity.phase !== 'scanning' && <p className="ws-helper">Next check: {new Date(source.activity.next_scan_at).toLocaleString()}.</p>}
      <div className="ws-actions">
        <button type="button" className="ws-button" disabled={busy} onClick={() => void control(source)}>{source.enabled ? <Pause size={15} /> : <Play size={15} />}{source.enabled ? 'Pause source' : 'Resume source'}</button>
        <button type="button" className="ws-button" disabled={busy} onClick={() => { setRemove(source.id); setRetirementCredential(''); }}><Trash2 size={15} />Remove from this computer</button>
      </div>
      {remove === source.id && <div className="ws-notice"><p>{source.custody
        ? 'Pause first. Removal revokes this device’s capture grant and discards all pending local evidence, including unknown delivery outcomes. The workspace must confirm revocation online. Original files, server memories and the application key’s other permissions remain.'
        : 'Stop local scans and forget this computer’s saved source credentials? Existing memories and server keys remain available to their authorized users.'}</p>{source.custody && <details><summary>Device key unavailable?</summary><p>Sign in as a workspace administrator and remove this source in Connections, or supply a current administrator key for this workspace. It is used only to confirm removal and is never saved.</p><label>Administrator key for {source.endpoint}<input type="password" autoComplete="new-password" data-update-safe value={retirementCredential} disabled={busy} onChange={event => setRetirementCredential(event.target.value)} /></label></details>}<button type="button" className="ws-button" disabled={busy || (!!source.custody && source.enabled)} onClick={() => void control(source, 'remove')}>{source.custody ? 'Revoke grant and discard local inbox' : 'Confirm removal'}</button><button type="button" className="ws-button" onClick={() => { setRemove(undefined); setRetirementCredential(''); }}>Cancel</button></div>}
    </div>)}
    <CaptureBackup busy={busy} setBusy={setBusy} />
    <p className="ws-helper">Connect to the relevant workspace and open Connections to change its sharing, scan limits or application key.</p>
    <Link className="ws-link" to="/help?doc=docs%2Fservice%2Fdesktop-sources.md">Desktop source guide</Link>
  </details>;
}
