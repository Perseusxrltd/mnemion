import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { GitBranch, LoaderCircle, RefreshCw, Upload } from 'lucide-react';
import { MnemionClient, MnemionError, supportsJournal, type JournalPolicyInput, type JournalStatus } from '@mnemion/client';

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
};
const errorText = (error: unknown) => error instanceof MnemionError
  ? errors[error.code] ?? error.message : 'The journal request failed. Refresh its status before retrying.';
const bytes = (value: number) => value < 1024 ? `${value} B` : value < 1024 ** 2
  ? `${(value / 1024).toFixed(1)} KiB` : `${(value / 1024 ** 2).toFixed(1)} MiB`;

export default function Journal({ client, space, writer, serviceVersion }: {
  client: MnemionClient; space: string; writer: boolean; serviceVersion?: string | null;
}) {
  const cache = useQueryClient();
  const supported = supportsJournal(serviceVersion);
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
      <section className="ws-card"><h2><GitBranch size={20} /> {states[data.state]}</h2>
        {data.destination ? <><p><strong>{data.destination.label}</strong></p><p>{data.destination.repository}</p>
          <p className="ws-helper">Branch {data.destination.branch} · Folder {data.destination.prefix}</p>
          <p className="ws-helper">Secret checks are always on. Personal-data patterns: {data.destination.personal_data_scan ? 'on' : 'off'}.
            {data.destination.custom_scanner ? ' A host-approved scanner also checks every save.' : ' Your operator can add a custom scanner.'}</p></>
          : <p>A host operator must register a repository for this space first. The setup guide includes a single command and credential-manager instructions.</p>}
        {data.last_error && <p className="ws-notice" role="status">{errors[data.last_error] ?? `Last publication could not finish (${data.last_error.replaceAll('_', ' ')}). Check the host's Git connection and credential manager.`}</p>}
        {data.configured && <><div className="ws-stats"><div><span>Visible pending entries</span><strong>{data.pending_entries.toLocaleString()}</strong></div>
          <div><span>Pending content</span><strong>{bytes(data.pending_content_bytes)}</strong></div>
          <div><span>Publication interval</span><strong>{data.interval_seconds}s</strong></div></div>
          <p>Last confirmed push: {data.last_push_at ? new Date(data.last_push_at).toLocaleString() : 'None yet'}{data.last_commit && <> · <code>{data.last_commit.slice(0, 12)}</code></>}</p>
          <p className="ws-helper">Local capture continues while publication is paused. A host reset can lose entries that have not reached the repository. Important saves require a confirmed Git push before success is returned.</p>
          {writer && <button className="ws-button" disabled={busy || data.state !== 'ready'} onClick={() => void act(() => client.pushJournal(space, data.version), 'Publication checked. Remaining entries continue in bounded batches.')}><Upload size={15} />{busy ? 'Working…' : 'Push now'}</button>}</>}
      </section>
      <section className="ws-notice"><p>Git history retains published text. Deleting a memory prevents it from returning in journal replay, but cannot erase copies or old Git commits. Do not use this journal for credentials or information that must be fully erased from external storage.</p>
        <p>Only changes made after enabling the journal are captured. Existing memories are not backfilled. Journal replay restores stable source identities; a complete workspace recovery archive also preserves accounts, permissions and native database IDs.</p></section>
      {data.can_configure && data.destination && <JournalSettings key={`${space}:${data.version}`} data={data} busy={busy} save={input => void act(() => client.configureJournal(space, input), 'Journal settings saved.')} />}
      {!data.can_configure && <p className="ws-helper">Changing the destination or publisher requires organization administration and administrator access to this space.</p>}
    </>}
    <p><Link className="ws-link" to="/workspace/help?doc=docs%2Fservice%2Fgit-journal.md">Setup, privacy, recovery & agent controls</Link></p>
  </div>;
}

function JournalSettings({ data, busy, save }: { data: JournalStatus; busy: boolean; save: (input: JournalPolicyInput) => void }) {
  const [interval, setInterval] = useState(data.interval_seconds ?? 300);
  const [paused, setPaused] = useState(data.paused ?? false);
  const [publish, setPublish] = useState(false);
  const [history, setHistory] = useState(false);
  const [repair, setRepair] = useState(false);
  return <section className="ws-card"><h2>{data.configured ? 'Journal settings' : 'Enable this destination'}</h2>
    <form className="ws-form" onSubmit={event => { event.preventDefault(); if (publish && history && data.destination) save({ expected_version: data.version,
      destination_id: data.destination.id, publish_to_repository: true, acknowledge_retained_git_history: true,
      interval_seconds: interval, paused, repair_publisher: repair }); }}>
      <fieldset disabled={busy} className="ws-form">
        <label className="ws-field"><span>Publication interval (seconds)</span><input type="number" min={30} max={86400} step={1} required value={interval} onChange={event => setInterval(event.target.valueAsNumber)} /></label>
        <label className="ws-checkbox"><input type="checkbox" checked={paused} onChange={event => setPaused(event.target.checked)} />Pause automatic and manual publication; keep capturing locally</label>
        {data.configured && <label className="ws-checkbox"><input type="checkbox" checked={repair} onChange={event => setRepair(event.target.checked)} />Replace the publisher identity and revoke its previous access</label>}
        <label className="ws-checkbox"><input type="checkbox" required checked={publish} onChange={event => setPublish(event.target.checked)} />Allow future changes in this space to be published to the displayed repository</label>
        <label className="ws-checkbox"><input type="checkbox" required checked={history} onChange={event => setHistory(event.target.checked)} />I understand that Git history retains published content after deletion</label>
        <button className="ws-button ws-primary" disabled={!publish || !history || !Number.isInteger(interval)}>{busy ? 'Saving…' : 'Save journal settings'}</button>
      </fieldset>
    </form>
  </section>;
}
