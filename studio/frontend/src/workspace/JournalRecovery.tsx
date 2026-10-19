import { useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { FolderOpen, LoaderCircle } from 'lucide-react';
import { MnemionClient, MnemionError, type JournalRecoveryInput, type JournalRecoveryItem, type JournalRecoveryPreview, type JournalRecoveryReceipt } from '@mnemion/client';

const labels: Record<JournalRecoveryItem['action'], string> = {
  create: 'New memories', already_restored: 'Already restored', preserved_changes: 'Local changes preserved',
  stale_source: 'Older source ignored', withdraw: 'Memories to withdraw', deny: 'Withdrawals to retain',
  withdrawn: 'Already withdrawn', hold: 'Quarantined identities to retain', quarantine: 'Memories to quarantine',
  held: 'Already quarantined', release: 'Released content to restore', update: 'Recovered memories to update',
  conflict: 'Conflicting identities', rejected: 'Rejected records',
};
const describe = (error: unknown) => error instanceof MnemionError || error instanceof Error ? error.message : 'The recovery request failed. Retry with the same reviewed input.';
const text = async (file: File) => new TextDecoder('utf-8', { fatal: true, ignoreBOM: true }).decode(await file.arrayBuffer());

export default function JournalRecovery({ client, space }: { client: MnemionClient; space: string }) {
  const cache = useQueryClient();
  const [source, setSource] = useState<Pick<JournalRecoveryInput, 'catalog' | 'files'>>();
  const [folder, setFolder] = useState('');
  const [identityMode, setIdentityMode] = useState<'original' | 'copy'>('original');
  const [withdrawals, setWithdrawals] = useState('');
  const [personal, setPersonal] = useState(true);
  const [complete, setComplete] = useState(false), [sourceOnly, setSourceOnly] = useState(false);
  const [preview, setPreview] = useState<JournalRecoveryPreview>(), [result, setResult] = useState<JournalRecoveryReceipt>();
  const [busy, setBusy] = useState(false), [error, setError] = useState<unknown>();
  const picker = useRef<HTMLInputElement>(null);
  const pending = useRef<{ hash: string; key: string } | undefined>(undefined);
  function changed() { setPreview(undefined); setResult(undefined); setError(undefined); setComplete(false); setSourceOnly(false); pending.current = undefined; }
  function input(): JournalRecoveryInput {
    if (!source) throw new Error('Choose the folder containing catalog.json.');
    return { ...source, identity_mode: identityMode, withdrawn_ids: withdrawals.split(/[\s,]+/).filter(Boolean), reject_personal_data: personal };
  }
  async function load(selected: FileList | null) {
    changed(); setSource(undefined); setFolder('');
    const all = Array.from(selected ?? []);
    if (!all.length) return;
    setBusy(true);
    try {
      const paths = all.map(file => ({ file, path: file.webkitRelativePath.split('/').slice(1).join('/') }));
      const catalog = paths.find(row => row.path === 'catalog.json');
      const journals = paths.filter(row => row.path.endsWith('.jsonl'));
      if (!catalog) throw new Error('Choose the native journal folder that directly contains catalog.json, including its dated folders and _archive.');
      if (journals.length > 256 || catalog.file.size + journals.reduce((n, row) => n + row.file.size, 0) > 1024 ** 2) {
        throw new Error('This recovery accepts a complete journal up to 1 MiB and 256 files. Keep larger journals intact; do not split the folder or edit its catalog. Use a full workspace backup for larger recovery.');
      }
      const files: JournalRecoveryInput['files'] = [];
      for (const row of journals) files.push({ path: row.path, text: await text(row.file) });
      setSource({ catalog: await text(catalog.file), files });
      setFolder(all[0]?.webkitRelativePath.split('/')[0] ?? 'Native journal');
    } catch (problem) { setError(problem); if (picker.current) picker.current.value = ''; }
    finally { setBusy(false); }
  }
  async function inspect() {
    changed(); setBusy(true);
    try { setPreview(await client.previewJournalRecovery(space, input())); }
    catch (problem) { setError(problem); }
    finally { setBusy(false); }
  }
  async function restore() {
    if (!preview || !complete || !sourceOnly) return;
    setBusy(true); setError(undefined);
    if (pending.current?.hash !== preview.preview_sha256) pending.current = { hash: preview.preview_sha256, key: crypto.randomUUID() };
    try {
      setResult(await client.restoreJournal(space, {
        ...input(), preview_sha256: preview.preview_sha256, reviewed_complete_inventory: true,
        reviewed_withdrawals: true, acknowledge_source_only: true,
      }, pending.current.key));
      void cache.invalidateQueries({ queryKey: ['memories'] });
    } catch (problem) { setError(problem); }
    finally { setBusy(false); }
  }
  function clear() { changed(); setSource(undefined); setFolder(''); setWithdrawals(''); if (picker.current) picker.current.value = ''; }
  return <section className="ws-card ws-journal-backfill ws-buffer-import" data-update-pending={!result && (busy || !!source || !!withdrawals) ? true : undefined}>
    <h2><FolderOpen size={20} />Restore a native journal</h2>
    <p>Recover editable memories from a complete Mnemion journal into this private space. Later withdrawals and quarantines take precedence; original writers and permissions do not become workspace accounts.</p>
    <p className="ws-helper">Choose the folder containing catalog.json, its dated files and _archive. This guided recovery accepts up to 1 MiB, 10,000 records and 1,000 memory identities. It never publishes your selection to Git.</p>
    <form onSubmit={event => { event.preventDefault(); void inspect(); }}>
      <fieldset className="ws-form" disabled={busy || !!result}>
        <label className="ws-field"><span>Memory identities</span><select data-update-safe value={identityMode} onChange={event => { changed(); setIdentityMode(event.target.value as 'original' | 'copy'); }}><option value="original">Keep original memory IDs</option><option value="copy">Create independent copies</option></select></label>
        <p className="ws-helper">Keep original IDs when replacing a lost host. Choose independent copies when those memories already exist in this organization. Keep the same option and destination for retries.</p>
        <label className="ws-field"><span>Complete native journal folder</span><input data-update-safe ref={picker} type="file" multiple {...{ webkitdirectory: '' }} onChange={event => void load(event.target.files)} /></label>
        {source && <p className="ws-helper">{folder} · {source.files.length} journal files and catalog.json selected. Files stay in this page until you submit the review.</p>}
        <label className="ws-field"><span>Additional withdrawn memory IDs</span><textarea data-update-safe rows={3} spellCheck={false} autoCapitalize="none" value={withdrawals} onChange={event => { changed(); setWithdrawals(event.target.value); }} placeholder="Original memory IDs withdrawn after this snapshot. Leave empty only after checking the latest available history." /></label>
        <label className="ws-checkbox"><input data-update-safe type="checkbox" checked={personal} onChange={event => { changed(); setPersonal(event.target.checked); }} />Reject recognizable personal identifiers. Secret checks always remain on.</label>
        <button className="ws-button" disabled={!source}>{busy ? <LoaderCircle size={16} className="ws-spin" /> : <FolderOpen size={16} />}Review recovery</button>
      </fieldset>
    </form>
    {!!error && <p className="ws-notice ws-error" role="alert">{describe(error)}</p>}
    {preview && <>
      <h3>{result ? 'Recovery completed' : 'Review these changes'}</h3>
      <p className="ws-helper">{preview.records} distinct records checked · {preview.duplicates} repeated lines combined · {(preview.bytes / 1024).toFixed(1)} KiB</p>
      <div className="ws-stats">{Object.entries(preview.counts).map(([action, count]) => <div key={action}><span>{labels[action as JournalRecoveryItem['action']]}</span><strong>{count}</strong></div>)}</div>
      <details className="ws-details"><summary>Original identities and recovery decisions</summary>
        <p className="ws-helper">Original workspace and space: {preview.namespace}. Recovering into the same destination preserves the same memory IDs.</p>
        <ul>{preview.items.map(item => <li key={item.original_id}><code>{item.original_id}</code> · {labels[item.action]}{item.code && ' (' + item.code.replaceAll('_', ' ') + ')'}{result && ['create', 'release', 'update', 'already_restored'].includes(item.action) && <> · <Link className="ws-link" to={'/workspace/memory/' + item.memory_id}>Open memory</Link></>}</li>)}</ul>
      </details>
      {!result && (!preview.can_restore ? <p className="ws-notice">Resolve conflicting or rejected records before restoring. No memory was changed. Keep the original journal intact.</p> : <div className="ws-form">
        <label className="ws-checkbox"><input data-update-safe type="checkbox" checked={complete} disabled={busy} onChange={event => setComplete(event.target.checked)} />I checked the complete catalog, active files, archives and latest known withdrawals.</label>
        <label className="ws-checkbox"><input data-update-safe type="checkbox" checked={sourceOnly} disabled={busy} onChange={event => setSourceOnly(event.target.checked)} />I understand this recovers current memory content. Original accounts, access, vault secrets and full history require a complete workspace backup.</label>
        <button className="ws-button ws-primary" disabled={busy || !complete || !sourceOnly} onClick={() => void restore()}>{busy ? 'Restoring…' : 'Restore reviewed memories'}</button>
      </div>)}
      {result && <p className="ws-notice" role="status">The reviewed recovery is saved. New content is available to keyword search while semantic indexing continues. Share this private space only after your review.</p>}
    </>}
    <button className="ws-button ws-quiet" disabled={busy} onClick={clear}>{result ? 'Review another complete snapshot' : 'Clear selected journal'}</button>
    <p><Link className="ws-link" to="/workspace/help?doc=docs%2Fservice%2Fjournal-recovery.md">Recovery limits, identity mapping & agent instructions</Link></p>
  </section>;
}
