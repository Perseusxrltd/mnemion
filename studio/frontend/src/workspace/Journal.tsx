import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { Archive, GitBranch, LoaderCircle, RefreshCw, Upload } from 'lucide-react';
import { MnemionClient, MnemionError, supportsJournal, supportsJournalFolding, type JournalPolicyInput, type JournalStatus } from '@mnemion/client';
import JournalHostSetup from './JournalHostSetup';

const states: Record<JournalStatus['state'], string> = {
  not_configured: 'Not enabled', ready: 'Automatic publication enabled', paused: 'Publication paused',
  publisher_unavailable: 'Publisher access needs repair', destination_changed: 'Destination needs approval',
};
const errors: Record<string, string> = {
  journal_remote_history_changed: 'Repository history changed or journal data was removed. The host operator must reconcile it before publishing.',
  journal_policy_changed: 'Settings changed during publication. Refresh before retrying.',
  journal_publication_changed: 'A queued memory changed or was withdrawn. Refresh and retry publication.',
  journal_storage_unavailable: 'The host cannot write its private journal. Check available storage and access.',
  journal_destination_unavailable: 'The host destination changed. An administrator must review and approve it.',
  journal_pending_changes: 'Publish the queued changes before organizing this journal. Automatic filing waits for publication to finish.',
  journal_note_conflict: 'A generated note was edited or its reserved filename is occupied. Preserve your copy outside the generated folder, then restore the generated view before retrying.',
  journal_incomplete_inventory: 'The journal is incomplete. Restore its missing records before organizing or archiving.',
  journal_inventory_limit: 'The journal exceeds this host’s supported inventory limit. Filing stopped without discarding history.',
  journal_file_too_large: 'A journal file reached its supported size limit. Ask the host operator to review journal capacity.',
};
const errorText = (error: unknown) => error instanceof MnemionError
  ? errors[error.code] ?? error.message : 'The journal request failed. Refresh its status before retrying.';
const bytes = (value: number) => value < 1024 ? `${value} B` : value < 1024 ** 2
  ? `${(value / 1024).toFixed(1)} KiB` : `${(value / 1024 ** 2).toFixed(1)} MiB`;

export default function Journal({ client, space, writer, serviceVersion, endpoint, label }: {
  client: MnemionClient; space: string; writer: boolean; serviceVersion?: string | null; endpoint: string; label: string;
}) {
  const cache = useQueryClient();
  const supported = supportsJournal(serviceVersion);
  const foldingSupported = supportsJournalFolding(serviceVersion);
  const query = useQuery({ queryKey: ['journal', space], queryFn: () => client.journalStatus(space),
    enabled: supported, refetchInterval: 10000, refetchIntervalInBackground: false });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const [notice, setNotice] = useState('');
  async function act(task: () => Promise<JournalStatus>, message: string) {
    setBusy(true); setError(undefined); setNotice('');
    try { const result = await task(); cache.setQueryData(['journal', space], result); setNotice(message); }
    catch (failure) { setError(failure); await query.refetch(); }
    finally { setBusy(false); }
  }
  const data = query.data;
  return <div className="ws-page ws-narrow">
    <header className="ws-page-heading"><div><p className="ws-eyebrow">Memory continuity</p><h1>Git journal</h1>
      <p>Keep future changes in a shared repository, independently of the agent that saved them.</p></div>
      {supported && <button className="ws-button ws-quiet" disabled={query.isFetching} onClick={() => void query.refetch()}><RefreshCw size={15} />Refresh</button>}
    </header>
    {!supported ? <p className="ws-notice">Git journals need workspace server 4.15.0 or later. <Link to="/workspace/setup">Check app & server versions</Link>, then reconnect after updating the host.</p>
      : query.isPending ? <p className="ws-loading"><LoaderCircle size={18} className="ws-spin" />Reading journal status…</p>
      : query.error && !data ? <p className="ws-notice ws-error" role="alert">{errorText(query.error)}</p> : null}
    {!!error && <p className="ws-notice ws-error" role="alert">{errorText(error)}</p>}
    {notice && <p className="ws-notice" role="status">{notice}</p>}
    {data && <>
      {query.isError && <p className="ws-notice" role="status">Status refresh failed. These are the last observed values.</p>}
      {data.can_configure && <JournalHostSetup endpoint={endpoint} space={space} label={label} />}
      <section className="ws-card"><h2><GitBranch size={20} /> {states[data.state]}</h2>
        {data.destination ? <><p><strong>{data.destination.label}</strong></p><p>{data.destination.repository}</p>
          <p className="ws-helper">Branch {data.destination.branch} · Folder {data.destination.prefix}</p>
          <p className="ws-helper">Secret checks are always on. Personal-data patterns: {data.destination.personal_data_scan ? 'on' : 'off'}.
            {data.destination.custom_scanner ? ' A host-approved scanner also checks every save.' : ' Your operator can add a custom scanner.'}</p></>
          : <p>Register a repository for this space on its host first. A current desktop host provides registration above; other hosts use the operator command in the setup guide.</p>}
        {data.last_error && <p className="ws-notice" role="status">{errors[data.last_error] ?? `Last publication could not finish (${data.last_error.replaceAll('_', ' ')}). Check the host's Git connection and credential manager.`}</p>}
        {data.configured && <><div className="ws-stats"><div><span>Visible pending entries</span><strong>{data.pending_entries.toLocaleString()}</strong></div>
          <div><span>Pending content</span><strong>{bytes(data.pending_content_bytes)}</strong></div>
          <div><span>Publication interval</span><strong>{data.interval_seconds}s</strong></div></div>
          <p>Last confirmed push: {data.last_push_at ? new Date(data.last_push_at).toLocaleString() : 'None yet'}{data.last_commit && <> · <code>{data.last_commit.slice(0, 12)}</code></>}</p>
          <p className="ws-helper">Local capture continues while publication is paused. A host reset can lose entries that have not reached the repository. Important saves require a confirmed Git push before success is returned.</p>
          {writer && <button className="ws-button" disabled={busy || data.state !== 'ready'} onClick={() => void act(() => client.pushJournal(space, data.version), 'Publication checked. Remaining entries continue in bounded batches.')}><Upload size={15} />{busy ? 'Working…' : 'Push now'}</button>}</>}
      </section>
      {data.configured && foldingSupported && <section className="ws-card"><h2><Archive size={20} />Library & archive</h2>
        <p>The librarian files current memories as readable Markdown notes for Obsidian. Original journal files move intact into the archive once every record is old enough.</p>
        <p><strong>{data.fold_enabled ? 'Automatic filing enabled' : 'Automatic filing not enabled'}</strong>
          {data.fold_enabled && <> · Minimum age {data.fold_after_hours} hours · Runs every {data.fold_interval_seconds}s</>}</p>
        {data.notes_prefix && <p className="ws-helper">Generated notes: <code>{data.notes_prefix}</code>. Edit the original memories in Mnemion; these files are derived views.</p>}
        {data.last_fold_error && <p className="ws-notice" role="status">{errors[data.last_fold_error] ?? `Filing could not finish (${data.last_fold_error.replaceAll('_', ' ')}). Check the host's Git connection and journal status.`}</p>}
        {data.last_fold_at && <><div className="ws-stats">
          <div><span>Notes updated last run</span><strong>{(data.last_fold_notes ?? 0).toLocaleString()}</strong></div>
          <div><span>Files archived last run</span><strong>{(data.last_fold_archived_files ?? 0).toLocaleString()}</strong></div>
          <div><span>Journal data scanned</span><strong>{bytes(data.last_fold_read_bytes ?? 0)}</strong></div>
        </div><p>Last completed: {new Date(data.last_fold_at).toLocaleString()}{data.last_fold_commit && <> · <code>{data.last_fold_commit.slice(0, 12)}</code></>}</p>
          {!!((data.last_fold_pending_notes ?? 0) + (data.last_fold_pending_files ?? 0)) && <p role="status">Remaining after that run: {data.last_fold_pending_notes ?? 0} notes and {data.last_fold_pending_files ?? 0} journal files. Automatic filing continues in bounded batches.</p>}</>}
        {data.fold_enabled && data.next_fold_at && <p className="ws-helper">Next scheduled check: {new Date(data.next_fold_at).toLocaleString()}. Publication and current permissions are checked first.</p>}
        {data.can_organize && data.fold_enabled && <button className="ws-button" disabled={busy || data.state !== 'ready' || data.pending_entries > 0}
          onClick={() => void act(() => client.organizeJournal(space, data.version), 'Filing checked. Original journal history is retained; any remaining work continues automatically.')}>
          <Archive size={15} />{busy ? 'Working…' : 'Organize & archive now'}</button>}
        {data.fold_enabled && data.pending_entries > 0 && <p className="ws-helper">Queued changes must reach Git before filing starts.</p>}
        <p className="ws-helper">Filing uses no language model and makes no paid calls. Model-assisted organization remains available in the <Link to="/workspace/librarian">librarian</Link>. Generated notes are excluded from connector replay so an old copy cannot bring back a deleted memory.</p>
      </section>}
      <section className="ws-notice"><p>Git history retains published text. Deleting a memory prevents it from returning in journal replay, but cannot erase copies or old Git commits. Do not use this journal for credentials or information that must be fully erased from external storage.</p>
        <p>Only changes made after enabling the journal are captured. Existing memories are not backfilled. Journal replay restores stable source identities; a complete workspace recovery archive also preserves accounts, permissions and native database IDs.</p></section>
      {data.can_configure && data.destination && <JournalSettings key={`${space}:${data.version}`} data={data} busy={busy} foldingSupported={foldingSupported} save={input => void act(() => client.configureJournal(space, input), 'Journal settings saved.')} />}
      {!data.can_configure && <p className="ws-helper">Changing the destination or publisher requires organization administration and administrator access to this space.</p>}
    </>}
    <p><Link className="ws-link" to="/workspace/help?doc=docs%2Fservice%2Fgit-journal.md">Setup, privacy, recovery & agent controls</Link></p>
  </div>;
}

function JournalSettings({ data, busy, foldingSupported, save }: { data: JournalStatus; busy: boolean; foldingSupported: boolean; save: (input: JournalPolicyInput) => void }) {
  const [interval, setInterval] = useState(data.interval_seconds ?? 300);
  const [paused, setPaused] = useState(data.paused ?? false);
  const [publish, setPublish] = useState(false);
  const [history, setHistory] = useState(false);
  const [repair, setRepair] = useState(false);
  const [filing, setFiling] = useState(data.fold_enabled ?? false);
  const [filingAge, setFilingAge] = useState(data.fold_after_hours ?? 24);
  const [filingInterval, setFilingInterval] = useState(data.fold_interval_seconds ?? 3600);
  return <section className="ws-card"><h2>{data.configured ? 'Journal settings' : 'Enable this destination'}</h2>
    <form className="ws-form" onSubmit={event => { event.preventDefault(); if (publish && history && data.destination) save({ expected_version: data.version,
      destination_id: data.destination.id, publish_to_repository: true, acknowledge_retained_git_history: true,
      interval_seconds: interval, paused, repair_publisher: repair,
      ...(foldingSupported ? { fold_enabled: filing, fold_after_hours: filingAge, fold_interval_seconds: filingInterval } : {}) }); }}>
      <fieldset disabled={busy} className="ws-form">
        <label className="ws-field"><span>Publication interval (seconds)</span><input type="number" min={30} max={86400} step={1} required value={interval} onChange={event => setInterval(event.target.valueAsNumber)} /></label>
        <label className="ws-checkbox"><input type="checkbox" checked={paused} onChange={event => setPaused(event.target.checked)} />Pause publication and filing; keep capturing locally</label>
        {foldingSupported && <><label className="ws-checkbox"><input type="checkbox" checked={filing} onChange={event => setFiling(event.target.checked)} />Automatically file readable notes and archive older journals</label>
          <p className="ws-helper">This also manages Markdown views in <code>{data.notes_prefix}</code>. Filing keeps the complete original journal and uses current revisions and denials.</p>
          <label className="ws-field"><span>Minimum record age before archiving (hours)</span><input type="number" min={24} max={8760} step={1} required value={filingAge} onChange={event => setFilingAge(event.target.valueAsNumber)} /></label>
          <label className="ws-field"><span>Filing interval (seconds)</span><input type="number" min={60} max={86400} step={1} required value={filingInterval} onChange={event => setFilingInterval(event.target.valueAsNumber)} /></label></>}
        {data.configured && <label className="ws-checkbox"><input type="checkbox" checked={repair} onChange={event => setRepair(event.target.checked)} />Replace the publisher identity and revoke its previous access</label>}
        <label className="ws-checkbox"><input type="checkbox" required checked={publish} onChange={event => setPublish(event.target.checked)} />Allow future changes in this space to be published to the displayed repository</label>
        <label className="ws-checkbox"><input type="checkbox" required checked={history} onChange={event => setHistory(event.target.checked)} />I understand that Git history retains published content after deletion</label>
        <button className="ws-button ws-primary" disabled={!publish || !history || !Number.isInteger(interval) || (foldingSupported && (!Number.isInteger(filingAge) || !Number.isInteger(filingInterval)))}>{busy ? 'Saving…' : 'Save journal settings'}</button>
      </fieldset>
    </form>
  </section>;
}
