import { useEffect, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { FolderOpen, LoaderCircle, Pause, RefreshCw } from 'lucide-react';
import {
  JOURNAL_CHUNK_BYTES, journalChunk, verifyJournalPrefix, MnemionClient,
  type JournalRecoveryItem, type JournalUploadAdvance, type JournalUploadDecisions, type JournalUploadStatus,
} from '@mnemion/client';

const labels: Record<JournalRecoveryItem['action'], string> = {
  create: 'New memories', already_restored: 'Already restored', preserved_changes: 'Local changes preserved',
  stale_source: 'Older source ignored', withdraw: 'Memories to withdraw', deny: 'Withdrawals to retain',
  withdrawn: 'Already withdrawn', hold: 'Quarantined identities to retain', quarantine: 'Memories to quarantine',
  held: 'Already quarantined', release: 'Released content to restore', update: 'Recovered memories to update',
  conflict: 'Conflicting identities', rejected: 'Rejected records',
};
const states = { uploading: 'Upload in progress', reviewing: 'Checking complete history', reviewed: 'Ready for your review', restoring: 'Restoring approved memories', completed: 'Recovery completed', cancelled: 'Recovery cancelled' };
const size = (bytes: number) => bytes >= 1024 ** 3 ? `${(bytes / 1024 ** 3).toFixed(2)} GiB` : `${(bytes / 1024 ** 2).toFixed(2)} MiB`;
type Source = { catalog: string; files: Map<string, File>; label: string; bytes: number };

export default function JournalUpload({ client, space }: { client: MnemionClient; space: string }) {
  const cache = useQueryClient();
  const uploads = useQuery({ queryKey: ['journal-uploads', space], queryFn: () => client.listJournalUploads(space), retry: false });
  const [source, setSource] = useState<Source>();
  const [current, setCurrent] = useState<JournalUploadStatus>();
  const [identity, setIdentity] = useState<'original' | 'copy'>('original');
  const [personal, setPersonal] = useState(true), [withdrawals, setWithdrawals] = useState('');
  const [complete, setComplete] = useState(false), [sourceOnly, setSourceOnly] = useState(false), [batches, setBatches] = useState(false);
  const [busy, setBusy] = useState(false), [phase, setPhase] = useState(''), [error, setError] = useState('');
  const [decisions, setDecisions] = useState<JournalUploadDecisions>(), [decisionCursor, setDecisionCursor] = useState(0);
  const stopped = useRef(false), active = useRef(true), pending = useRef<string | undefined>(undefined);
  const status = useRef<JournalUploadStatus | undefined>(undefined), picker = useRef<HTMLInputElement>(null);
  useEffect(() => { active.current = true; return () => { active.current = false; stopped.current = true; }; }, []);
  const paused = () => stopped.current || !active.current;
  function observed(value: JournalUploadStatus) { status.current = value; if (active.current) setCurrent(value); return value; }
  function resetApproval() { setComplete(false); setSourceOnly(false); setBatches(false); setDecisions(undefined); setDecisionCursor(0); }
  async function run(task: () => Promise<unknown>) {
    if (busy) return;
    stopped.current = false; setBusy(true); setError('');
    try { await task(); }
    catch (problem) {
      if (active.current) setError(problem instanceof Error ? problem.message : 'The request could not finish. Refresh to see saved progress.');
      if (status.current) {
        try { observed(await client.journalUpload(space, status.current.id)); } catch { /* Keep the last observed receipt visible. */ }
      }
    } finally {
      if (active.current) { setBusy(false); setPhase(''); void uploads.refetch(); void cache.invalidateQueries({ queryKey: ['memories'] }); }
    }
  }
  async function select(files: FileList | null) {
    if (!files?.length) return;
    setSource(undefined); setError(''); pending.current = undefined;
    try {
      let catalog: File | undefined, bytes = 0;
      const journals = new Map<string, File>();
      for (const file of files) {
        const path = file.webkitRelativePath.split('/').slice(1).join('/');
        if (path === 'catalog.json') catalog = file;
        else if (path.endsWith('.jsonl')) {
          if (journals.has(path)) throw new Error('Duplicate journal file paths. Select one complete native journal folder.');
          journals.set(path, file); bytes += file.size;
          if (journals.size > 8192 || bytes > 2 * 1024 ** 3) throw new Error('The complete journal limit is 2 GiB and 8,192 files. Keep larger journals intact and use a full workspace backup.');
        }
      }
      if (!catalog || catalog.size > 4096) throw new Error('Choose the native journal folder directly containing catalog.json, its dated folders and _archive.');
      if (bytes + catalog.size > 2 * 1024 ** 3) throw new Error('The complete journal, including its catalog, exceeds 2 GiB.');
      const text = new TextDecoder('utf-8', { fatal: true }).decode(await catalog.arrayBuffer());
      const value = JSON.parse(text);
      if (current && (`${value.tenant_id}:${value.space_id}` !== current.namespace || value.records !== current.expected_records)) throw new Error('This catalog differs from the selected recovery. Choose its original complete journal folder.');
      setSource({ catalog: text, files: journals, bytes, label: files[0]?.webkitRelativePath.split('/')[0] ?? 'Native journal' });
    } catch (problem) { setError(problem instanceof Error ? problem.message : 'Cannot read this catalog.'); if (picker.current) picker.current.value = ''; }
  }
  async function step(value: JournalUploadStatus, action: JournalUploadAdvance['action'], approval: Partial<JournalUploadAdvance> = {}) {
    return observed(await client.advanceJournalUpload(space, value.id, { expected_version: value.version, action, ...approval }));
  }
  async function continueReview(value: JournalUploadStatus) {
    while (value.state === 'reviewing' && !paused()) { setPhase('Checking identities and current permissions'); value = await step(value, 'review'); }
    if (value.state === 'reviewed' && !paused()) { setDecisions(await client.journalUploadDecisions(space, value.id)); setDecisionCursor(0); }
  }
  async function transfer() {
    resetApproval();
    let value = status.current;
    if (!value) {
      if (!source) return;
      pending.current ??= crypto.randomUUID();
      setPhase('Registering complete inventory');
      value = observed(await client.beginJournalUpload(space, {
        catalog: source.catalog, files: Array.from(source.files, ([path, file]) => ({ path, bytes: file.size })),
        identity_mode: identity, reject_personal_data: personal, withdrawn_ids: withdrawals.split(/[\s,]+/).filter(Boolean),
      }, pending.current));
    }
    if (value.state === 'uploading' && value.completed_files !== value.files) {
      if (!source) throw new Error('Select the original journal folder to continue its upload.');
      if (source.files.size !== value.files) throw new Error('The selected folder has a different file inventory. Select the original complete folder.');
      let cursor: number | null = 0;
      while (cursor !== null && !paused()) {
        const page = await client.journalUploadFiles(space, value.id, cursor);
        for (const receipt of page.items) {
          if (paused()) break;
          const file = source.files.get(receipt.path);
          if (!file) throw new Error('A declared file is missing. Select the original complete journal folder.');
          setPhase(`Checking ${receipt.path}`);
          if (!await verifyJournalPrefix(file, receipt, paused)) return;
          for (let offset = receipt.received; offset < file.size && !paused(); offset += JOURNAL_CHUNK_BYTES) {
            setPhase(`Uploading ${receipt.path}`);
            const part = await journalChunk(await file.slice(offset, offset + JOURNAL_CHUNK_BYTES).arrayBuffer(), offset);
            if (paused()) return;
            value = observed((await client.sendJournalChunk(space, value.id, receipt.index, part)).upload);
          }
        }
        cursor = page.next_cursor;
      }
    }
    if (paused()) return;
    if (value.state === 'uploading') value = await step(value, 'finish_upload');
    await continueReview(value);
  }
  async function restore() {
    let value = status.current;
    if (!value) return;
    if (value.state === 'reviewed') {
      if (!complete || !sourceOnly || !batches || !value.can_restore) return;
      value = await step(value, 'authorize', { preview_sha256: value.preview_sha256,
        reviewed_complete_inventory: true, reviewed_withdrawals: true,
        acknowledge_source_only: true, acknowledge_resumable_batches: true });
    }
    while (value.state === 'restoring' && !paused()) { setPhase('Saving reviewed batches'); value = await step(value, 'restore'); }
    if (value.state === 'completed') setSource(undefined);
  }
  function open(value: JournalUploadStatus) { observed(value); setSource(undefined); setError(''); resetApproval(); if (picker.current) picker.current.value = ''; }
  const total = current?.state === 'uploading' ? current.bytes : current?.identities ?? 0;
  const done = current?.state === 'uploading' ? current.received : current?.state === 'reviewing' || current?.state === 'reviewed' ? current.reviewed_identities : current?.processed_identities ?? 0;
  return <section className="ws-card ws-journal-backfill ws-buffer-import" data-update-pending={busy || (!current && (!!source || !!withdrawals)) ? true : undefined}>
    <h2><FolderOpen size={20} />Restore a native journal</h2>
    <p>Bring editable memories into this private space from a complete journal. Large transfers can pause and resume here or on another device with your administrator login.</p>
    <p className="ws-helper">Up to 2 GiB, one million records and 100,000 memory identities. Files stay unchanged. Nothing is searchable until the complete history is checked and you approve recovery.</p>
    {!!uploads.data?.items.length && <label className="ws-field"><span>Saved recoveries</span><select data-update-safe value={current?.id ?? ''} disabled={busy} onChange={event => { const selected = uploads.data?.items.find(item => item.id === event.target.value); if (selected) open(selected); }}>
      <option value="" disabled>Select a saved recovery</option>{uploads.data.items.map(item => <option key={item.id} value={item.id}>{new Date(item.created_at).toLocaleString()} · {states[item.state]} · {size(item.bytes)}</option>)}
    </select></label>}
    {!current && <div className="ws-form"><label className="ws-field"><span>Memory identities</span><select data-update-safe disabled={busy} value={identity} onChange={event => { setIdentity(event.target.value as 'original' | 'copy'); pending.current = undefined; }}><option value="original">Keep original memory IDs</option><option value="copy">Create independent copies</option></select></label>
      <p className="ws-helper">Keep original IDs to replace a lost host. Choose independent copies if these identities already exist in another space.</p>
      <label className="ws-field"><span>Additional withdrawn memory IDs</span><textarea data-update-safe disabled={busy} rows={3} spellCheck={false} value={withdrawals} onChange={event => { setWithdrawals(event.target.value); pending.current = undefined; }} placeholder="Original IDs withdrawn since this snapshot. Leave empty only after checking the latest history." /></label>
      <label className="ws-checkbox"><input data-update-safe disabled={busy} type="checkbox" checked={personal} onChange={event => { setPersonal(event.target.checked); pending.current = undefined; }} />Reject recognizable personal identifiers. Secret checks always remain on.</label>
    </div>}
    {(!current || current.state === 'uploading') && <label className="ws-field"><span>Complete native journal folder</span><input data-update-safe ref={picker} type="file" multiple disabled={busy} {...{ webkitdirectory: '' }} onChange={event => void select(event.target.files)} /></label>}
    {source && <p className="ws-helper">{source.label} · {source.files.size.toLocaleString()} journal files · {size(source.bytes)}</p>}
    {current && <>
      <h3>{states[current.state]}</h3>
      <progress aria-label="Recovery progress" max={Math.max(1, total)} value={done} />
      <div className="ws-stats"><div><span>Uploaded</span><strong>{size(current.received)} / {size(current.bytes)}</strong></div><div><span>Records checked</span><strong>{current.records.toLocaleString()} / {current.expected_records.toLocaleString()}</strong></div><div><span>Reviewed identities</span><strong>{current.reviewed_identities.toLocaleString()}</strong></div><div><span>Saved this review</span><strong>{current.processed_identities.toLocaleString()} / {current.identities.toLocaleString()}</strong></div></div>
      <p className="ws-helper">Progress is saved on the workspace host. Staging expires after 24 hours without an accepted step. Current expiry: {new Date(current.expires_at).toLocaleString()}. Completed recoveries retain staging for up to 24 hours; cancel to request earlier cleanup.</p>
      {!!Object.keys(current.counts).length && <div className="ws-stats">{Object.entries(current.counts).map(([action, count]) => <div key={action}><span>{labels[action as JournalRecoveryItem['action']]}</span><strong>{count?.toLocaleString()}</strong></div>)}</div>}
      {decisions && <details className="ws-details"><summary>Recovery decisions</summary><ul>{decisions.items.map(item => <li key={item.original_id}><code>{item.original_id}</code> · {labels[item.action]}{item.code && ` (${item.code.replaceAll('_', ' ')})`}</li>)}</ul><div className="ws-actions">
        <button className="ws-button ws-quiet" disabled={busy || decisionCursor === 0} onClick={() => void run(async () => { setDecisionCursor(0); setDecisions(await client.journalUploadDecisions(space, current.id)); })}>First decisions</button>
        {decisions.next_cursor !== null && <button className="ws-button" disabled={busy} onClick={() => void run(async () => { const cursor = decisions.next_cursor!; setDecisions(await client.journalUploadDecisions(space, current.id, cursor)); setDecisionCursor(cursor); })}>Next decisions</button>}
      </div></details>}
      {current.state === 'reviewed' && (current.can_restore ? <div className="ws-form">
        <label className="ws-checkbox"><input data-update-safe type="checkbox" disabled={busy} checked={complete} onChange={event => setComplete(event.target.checked)} />I checked the complete catalog, archives, continuations and later withdrawals.</label>
        <label className="ws-checkbox"><input data-update-safe type="checkbox" disabled={busy} checked={sourceOnly} onChange={event => setSourceOnly(event.target.checked)} />I understand this restores current content. Accounts, vault secrets, permissions and full history require a workspace backup.</label>
        <label className="ws-checkbox"><input data-update-safe type="checkbox" disabled={busy} checked={batches} onChange={event => setBatches(event.target.checked)} />Save in resumable batches. Pausing or cancelling keeps memories already restored; changed destinations require a new review.</label>
      </div> : <p className="ws-notice">Resolve conflicting or rejected records before continuing. The source journal stays intact. Earlier approved batches, if any, remain saved.</p>)}
      {current.state === 'completed' && <p className="ws-notice" role="status">Recovery is saved. Keyword search is available while semantic indexing continues. Review the space before sharing it.</p>}
      {current.state === 'cancelled' && <p className="ws-notice" role="status">No more batches will run. Private staging is queued for cleanup; previously restored memories remain.</p>}
    </>}
    {error && <p className="ws-notice ws-error" role="alert">{error}</p>}
    {uploads.error && !current && <p className="ws-helper">Saved recoveries are unavailable. Use a private space with only your administrator access and no Git publication.</p>}
    {busy && <p role="status"><LoaderCircle size={16} className="ws-spin" /> {phase || 'Reading saved progress…'}</p>}
    <div className="ws-actions">
      {busy ? <button className="ws-button" onClick={() => { stopped.current = true; setPhase('Pausing after the current step'); }}><Pause size={16} />Pause</button> : <>
        {(!current || ['uploading', 'reviewing'].includes(current.state)) && <button className="ws-button ws-primary" disabled={!source && (!current || current.state === 'uploading' && current.completed_files !== current.files)} onClick={() => void run(transfer)}>{!current ? 'Upload & review complete journal' : 'Continue upload & review'}</button>}
        {current?.state === 'reviewed' && <button className="ws-button ws-primary" disabled={!current.can_restore || !complete || !sourceOnly || !batches} onClick={() => void run(restore)}>Restore reviewed memories</button>}
        {current?.state === 'restoring' && <button className="ws-button ws-primary" onClick={() => void run(restore)}>Continue approved recovery</button>}
        {current && <button className="ws-button ws-quiet" disabled={current.state === 'cancelled'} onClick={() => void run(async () => { const value = observed(await client.journalUpload(space, current.id)); if (value.reviewed_batches) setDecisions(await client.journalUploadDecisions(space, current.id)); })}><RefreshCw size={16} />Refresh progress</button>}
        {current && ['reviewing', 'reviewed', 'restoring'].includes(current.state) && <button className="ws-button" onClick={() => void run(async () => { resetApproval(); await continueReview(await step(current, 'restart_review')); })}>Review current destination again</button>}
        {current && current.state !== 'cancelled' && <button className="ws-button ws-quiet" onClick={() => void run(async () => { await step(current, 'cancel'); setSource(undefined); })}>Cancel & clean staging</button>}
        <button className="ws-button ws-quiet" onClick={() => { status.current = undefined; setCurrent(undefined); setSource(undefined); setWithdrawals(''); setError(''); pending.current = undefined; resetApproval(); if (picker.current) picker.current.value = ''; }}>Start another recovery</button>
      </>}
    </div>
    <p className="ws-helper">Staged history is private workspace database content and can be included in host backups. It is never sent to a model or published to Git by this recovery.</p>
    <p><Link className="ws-link" to="/workspace/help?doc=docs%2Fservice%2Fjournal-recovery.md">Recovery, retention & agent instructions</Link></p>
  </section>;
}
