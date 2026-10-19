import { useEffect, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { History, LoaderCircle, Pause, Play, RefreshCw, Square } from 'lucide-react';
import { MnemionClient, MnemionError, type JournalBackfillStart, type JournalBackfillStatus, type JournalStatus } from '@mnemion/client';

const errors: Record<string, string> = {
  journal_secret_detected: 'A recognizable secret was found.',
  journal_personal_data_detected: 'A personal-data pattern was found.',
  journal_scanner_rejected: 'The host’s scanner did not approve this memory.',
  journal_record_too_large: 'This memory exceeds the journal record limit.',
  journal_record_invalid: 'This older record needs review before it can be journaled.',
  journal_scanner_unavailable: 'The host’s scanner could not run. Repair it, then resume.',
  journal_policy_changed: 'Journal settings changed. Review the current destination and approve resuming.',
  journal_backfill_approval_expired: 'The approving administrator no longer has access. Another authorized administrator can review and resume.',
  journal_destination_unavailable: 'The host destination needs approval in journal settings.',
  journal_paused: 'Journal publication is paused. Resume publication before continuing this scan.',
  journal_publisher_unavailable: 'Repair publisher access in journal settings before resuming.',
};
const states = { running: 'Scanning in the background', paused: 'Scan paused', blocked: 'Scan needs attention', completed: 'Scan finished', cancelled: 'Scan cancelled' };
const describe = (error: unknown) => error instanceof MnemionError ? errors[error.code] ?? error.message : 'The request could not finish. Refresh before retrying.';
const bytes = (value: number) => value < 1024 ? `${value} B` : value < 1024 ** 2 ? `${(value / 1024).toFixed(1)} KiB` : `${(value / 1024 ** 2).toFixed(1)} MiB`;

export default function JournalBackfill({ client, space, journal }: { client: MnemionClient; space: string; journal: JournalStatus }) {
  const cache = useQueryClient();
  const query = useQuery({ queryKey: ['journal-backfill', space], queryFn: () => client.journalBackfillStatus(space),
    refetchInterval: query => query.state.data?.run?.state === 'running' ? 5000 : 30000, refetchIntervalInBackground: false });
  const [busy, setBusy] = useState(false), [publish, setPublish] = useState(false), [history, setHistory] = useState(false);
  const [error, setError] = useState<unknown>(), [notice, setNotice] = useState('');
  const attempt = useRef<{ input: string; key: string } | null>(null);
  const data = query.data, run = data?.run;
  useEffect(() => { setPublish(false); setHistory(false); }, [data?.policy_version, run?.id]);
  const active = run && ['running', 'paused', 'blocked'].includes(run.state);
  const resume = active && (run.state !== 'running' || data?.waiting_reason === 'journal_policy_changed' || data?.waiting_reason === 'journal_backfill_approval_expired');
  async function act(task: () => Promise<JournalBackfillStatus>, message: string) {
    setBusy(true); setError(undefined); setNotice('');
    try {
      cache.setQueryData(['journal-backfill', space], await task());
      setNotice(message); setPublish(false); setHistory(false); attempt.current = null;
      void cache.invalidateQueries({ queryKey: ['journal', space] });
    } catch (failure) { setError(failure); await query.refetch(); }
    finally { setBusy(false); }
  }
  function start() {
    if (!data || !publish || !history) return;
    const input: JournalBackfillStart = { expected_version: data.policy_version, publish_existing_memories: true,
      acknowledge_retained_git_history: true, ...(resume && run ? { resume_run: run.id } : {}) };
    const fingerprint = JSON.stringify(input);
    if (attempt.current?.input !== fingerprint) attempt.current = { input: fingerprint, key: crypto.randomUUID() };
    const key = attempt.current.key;
    void act(() => client.startJournalBackfill(space, input, key), 'Scan approved. The workspace host continues in bounded batches without keeping this page open.');
  }
  return <section className="ws-card ws-journal-backfill">
    <h2><History size={20} />Include existing memories</h2>
    <p>Add current versions of older native memories to this repository. Every candidate passes the same privacy checks as a new save; original memories, authors and dates remain intact.</p>
    {query.isPending && <p className="ws-loading"><LoaderCircle size={18} className="ws-spin" />Reading existing-memory coverage…</p>}
    {query.isError && <p className="ws-notice ws-error" role="alert">{describe(query.error)}{data && ' Displayed values are from the last successful check.'}</p>}
    {!!error && <p className="ws-notice ws-error" role="alert">{describe(error)}</p>}
    {notice && <p className="ws-notice" role="status">{notice}</p>}
    {data && <>
      <div className="ws-stats"><div><span>Current versions awaiting capture</span><strong>{data.eligible_memories.toLocaleString()}</strong></div>
        <div><span>Candidate text</span><strong>{bytes(data.eligible_content_bytes)}</strong></div></div>
      <p className="ws-helper">Counts are before privacy scanning. Deleted, quarantined and source-managed memories are excluded. Only the current version is included; attachments, core blocks and older revision history need a full recovery backup.</p>
      {run && <>
        <h3>{states[run.state]}</h3>
        <p>{run.examined.toLocaleString()} checked · {run.total_at_start.toLocaleString()} records at the start</p>
        <progress aria-label="Existing-memory scan progress" value={Math.min(run.examined, Math.max(run.total_at_start, 1))} max={Math.max(run.total_at_start, 1)} />
        <div className="ws-stats"><div><span>Queued for publication</span><strong>{run.queued.toLocaleString()}</strong></div>
          <div><span>Already captured</span><strong>{run.already_journaled.toLocaleString()}</strong></div>
          <div><span>Rejected by checks</span><strong>{run.rejected.toLocaleString()}</strong></div>
          <div><span>Excluded from export</span><strong>{run.excluded.toLocaleString()}</strong></div></div>
        <p className="ws-helper">Queued means captured in the database. Check pending entries and the last confirmed push above for Git delivery. {run.finished_at && <>Scan ended {new Date(run.finished_at).toLocaleString()}.</>}</p>
        {run.errors.length > 0 && <details className="ws-details"><summary>Review {run.rejected.toLocaleString()} rejected {run.rejected === 1 ? 'memory' : 'memories'}</summary>
          <p>These versions were not exported. Review them in Mnemion, then start another scan if needed. Original content was not changed.</p>
          <ul>{run.errors.map(item => <li key={`${item.memory_id}:${item.version}`}><Link className="ws-link" to={`/workspace/memory/${item.memory_id}`}>Open memory {item.memory_id.slice(0, 8)}</Link> · version {item.version}: {errors[item.code] ?? 'Publication checks did not approve this record.'}</li>)}</ul>
          {run.rejected > run.errors.length && <p className="ws-helper">Showing the first {run.errors.length} rejection details.</p>}</details>}
        {run.last_error && <p className="ws-notice" role="status">{errors[run.last_error] ?? 'The scan needs attention from the host operator.'}</p>}
        {active && <div className="ws-actions">
          {run.state === 'running' && <button className="ws-button" disabled={busy || query.isError} onClick={() => void act(() => client.controlJournalBackfill(space, { expected_version: data.policy_version, run_id: run.id, action: 'pause' }), 'Scanning paused. Already queued entries retain their publication schedule.')}><Pause size={15} />Pause scan</button>}
          <button className="ws-button ws-quiet" disabled={busy || query.isError} onClick={() => void act(() => client.controlJournalBackfill(space, { expected_version: data.policy_version, run_id: run.id, action: 'cancel' }), 'Further scanning cancelled. Already queued entries and Git history are retained.')}><Square size={15} />Cancel remaining scan</button>
        </div>}
      </>}
      {data.waiting_reason && <p className="ws-notice" role="status">{errors[data.waiting_reason] ?? 'Review journal settings before continuing.'}</p>}
      {(!active || resume) && <form className="ws-form" onSubmit={event => { event.preventDefault(); start(); }}>
        <fieldset className="ws-form" disabled={busy || query.isError || journal.state !== 'ready'}>
          <label className="ws-checkbox"><input type="checkbox" required checked={publish} onChange={event => setPublish(event.target.checked)} />Publish approved current versions of existing memories to the displayed repository</label>
          <label className="ws-checkbox"><input type="checkbox" required checked={history} onChange={event => setHistory(event.target.checked)} />I understand that Git history retains this content after deletion</label>
          <button className="ws-button ws-primary" disabled={!publish || !history || (!resume && data.eligible_memories === 0)}><Play size={15} />{busy ? 'Saving…' : resume ? 'Approve & resume scan' : 'Approve & start scan'}</button>
        </fieldset>
      </form>}
      <p className="ws-helper">Pausing or cancelling stops further scanning. To stop delivery of queued entries too, pause journal publication. This scan runs without a model and resumes from its saved position after a service restart.</p>
    </>}
    <button className="ws-button ws-quiet" disabled={query.isFetching || busy} onClick={() => void query.refetch()}><RefreshCw size={15} />Refresh existing-memory status</button>
  </section>;
}
