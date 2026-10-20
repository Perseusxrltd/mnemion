import { useEffect, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { FolderSync, Pause, Play, Trash2 } from 'lucide-react';
import type { DesktopSource } from '../../../shared/desktop-sources';

/** These device controls remain available before signing in to a workspace. */
export default function DesktopSourcesOverview() {
  const native = window.mnemion;
  const cache = useQueryClient();
  const query = useQuery({ queryKey: ['desktop-sources'], queryFn: () => native!.sourceStatus!(), enabled: !!native?.sourceStatus, refetchInterval: 15000 });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const [remove, setRemove] = useState<string>();
  useEffect(() => native?.onSourceStatus?.(() => { void cache.invalidateQueries({ queryKey: ['desktop-sources'] }); }), [native, cache]);
  if (!native?.sourceStatus || (!query.error && !query.data?.sources.length)) return null;
  async function control(source: DesktopSource, removing = false) {
    if (!query.data) return;
    setBusy(true); setError(undefined);
    try {
      const view = await native!.sourceControl!(removing ? 'remove' : 'pause', {
        expected_revision: query.data.revision, id: source.id,
        ...(removing ? { confirm: true } : { enabled: !source.enabled }),
      });
      cache.setQueryData(['desktop-sources'], view); setRemove(undefined);
    } catch (error) { setError(error instanceof Error ? error.message : 'The device control could not finish.'); await query.refetch(); }
    finally { setBusy(false); }
  }
  return <details className="ws-device-settings ws-local-sources" data-update-pending={busy || remove ? '' : undefined}>
    <summary><FolderSync size={18} /> Sources on this computer{query.data ? ` · ${query.data.sources.length}` : ''}</summary>
    <p>These sources keep syncing with their saved workspaces while Studio runs. You can pause or remove them here even when a workspace is offline or you are signed out.</p>
    {(error || query.error) && <p className="ws-notice ws-error" role="alert">{error ?? (query.error instanceof Error ? query.error.message : 'Saved sources could not be read.')}</p>}
    {query.data?.sources.map(source => <div className="ws-card" key={source.id}>
      <div className="ws-section-title"><h3>{source.name}</h3><span className="ws-badge">{!source.enabled ? 'Paused' : source.activity.phase === 'scanning' ? 'Scanning' : 'Automatic scans on'}</span></div>
      <p className="ws-helper" style={{ overflowWrap: 'anywhere' }}>{source.endpoint}<br />{source.slack ? `Slack ${source.slack.team_id} · ${source.slack.channels.length} channels` : source.gdrive ? `Drive · ${source.gdrive.folder_ids.length} folders and ${source.gdrive.file_ids.length} files` : source.path}</p>
      {source.activity.message && <p className="ws-helper">{source.activity.message}</p>}
      <div className="ws-actions">
        <button type="button" className="ws-button" disabled={busy} onClick={() => void control(source)}>{source.enabled ? <Pause size={15} /> : <Play size={15} />}{source.enabled ? 'Pause source' : 'Resume source'}</button>
        <button type="button" className="ws-button" disabled={busy} onClick={() => setRemove(source.id)}><Trash2 size={15} />Remove from this computer</button>
      </div>
      {remove === source.id && <div className="ws-notice"><p>Stop local scans and forget this computer’s saved source credentials? Existing memories and server keys remain available to their authorized users.</p><button type="button" className="ws-button" disabled={busy} onClick={() => void control(source, true)}>Confirm removal</button><button type="button" className="ws-button" onClick={() => setRemove(undefined)}>Cancel</button></div>}
    </div>)}
    <p className="ws-helper">Connect to the relevant workspace and open Connections to change its sharing, scan limits or application key.</p>
    <Link className="ws-link" to="/help?doc=docs%2Fservice%2Fdesktop-sources.md">Desktop source guide</Link>
  </details>;
}
