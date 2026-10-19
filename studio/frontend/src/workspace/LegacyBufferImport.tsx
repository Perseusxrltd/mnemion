import { useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { FileInput, LoaderCircle } from 'lucide-react';
import { MnemionClient, MnemionError, type BufferPreview, type BufferPreviewInput, type BufferImported, type BufferPlanItem } from '@mnemion/client';

const labels: Record<BufferPlanItem['action'], string> = {
  create: 'New memories', already_imported: 'Already imported', preserved_changes: 'Local changes preserved',
  withdrawn: 'Already withdrawn', withdraw: 'Memories to withdraw', deny: 'Withdrawals to retain', conflict: 'Conflicting records', rejected: 'Rejected by privacy checks',
};
const describe = (error: unknown) => error instanceof MnemionError ? error.message : error instanceof Error ? error.message : 'The import request failed. Retry with the same reviewed input.';

export default function LegacyBufferImport({ client, space }: { client: MnemionClient; space: string }) {
  const cache = useQueryClient();
  const [namespace, setNamespace] = useState('legacy-buffer');
  const [jsonl, setJsonl] = useState('');
  const [files, setFiles] = useState<string[]>([]);
  const [withdrawals, setWithdrawals] = useState('');
  const [personal, setPersonal] = useState(true);
  const [reviewed, setReviewed] = useState(false), [sourceOnly, setSourceOnly] = useState(false);
  const [preview, setPreview] = useState<BufferPreview>(), [result, setResult] = useState<BufferImported>();
  const [busy, setBusy] = useState(false), [error, setError] = useState<unknown>();
  const fileInput = useRef<HTMLInputElement>(null);
  const pending = useRef<{ hash: string; key: string } | undefined>(undefined);
  function changed() { setPreview(undefined); setResult(undefined); setError(undefined); setReviewed(false); setSourceOnly(false); pending.current = undefined; }
  function input(): BufferPreviewInput { return { namespace, jsonl, withdrawn_ids: withdrawals.split(/[\s,]+/).filter(Boolean), reject_personal_data: personal }; }
  async function load(selected: FileList | null) {
    changed(); setJsonl(''); setFiles([]);
    const rows = Array.from(selected ?? []);
    if (!rows.length) return;
    setBusy(true);
    try {
      if (rows.length > 32 || rows.reduce((total, file) => total + file.size, 0) > 1024 ** 2) throw new Error('Select at most 32 complete journal files totaling 1 MiB. Larger archives need separate batches with the same import source name.');
      let text = '';
      for (const file of rows) {
        const part = new TextDecoder('utf-8', { fatal: true }).decode(await file.arrayBuffer());
        if (part && !part.endsWith('\n')) throw new Error('A selected journal has an unfinished final line. Recover the complete file before importing it.');
        text += part;
      }
      setJsonl(text); setFiles(rows.map(file => file.name));
    } catch (problem) { setError(problem); if (fileInput.current) fileInput.current.value = ''; }
    finally { setBusy(false); }
  }
  async function inspect() {
    setBusy(true); setError(undefined); setResult(undefined); setReviewed(false); setSourceOnly(false); pending.current = undefined;
    try { setPreview(await client.previewLegacyBuffer(space, input())); }
    catch (problem) { setError(problem); setPreview(undefined); }
    finally { setBusy(false); }
  }
  async function apply() {
    if (!preview || !reviewed || !sourceOnly) return;
    setBusy(true); setError(undefined);
    if (pending.current?.hash !== preview.preview_sha256) pending.current = { hash: preview.preview_sha256, key: crypto.randomUUID() };
    try {
      const receipt = await client.importLegacyBuffer(space, { ...input(), preview_sha256: preview.preview_sha256, reviewed_withdrawals: true, acknowledge_source_only: true }, pending.current.key);
      setResult(receipt);
      void cache.invalidateQueries({ queryKey: ['memories'] });
    } catch (problem) { setError(problem); }
    finally { setBusy(false); }
  }
  function clear() { changed(); setJsonl(''); setFiles([]); setWithdrawals(''); if (fileInput.current) fileInput.current.value = ''; }
  return <section className="ws-card ws-journal-backfill ws-buffer-import" data-update-pending={!result && (busy || !!jsonl || !!withdrawals) ? true : undefined}>
    <h2><FileInput size={20} />Recover an older buffer</h2>
    <p>Choose a private native space with only your administrator grant to recover an older agent journal. Keep the original files and review withdrawals first. Your account creates the new memories; old writer labels grant no access.</p>
    <p className="ws-helper">Use complete, decrypted JSONL files: up to 100 distinct records and 1 MiB per batch. Files stay in this page until sent to your workspace for review. This tool does not publish to Git or prove which older records reached the remote repository.</p>
    <form onSubmit={event => { event.preventDefault(); void inspect(); }}>
      <fieldset className="ws-form" disabled={busy || !!result}>
        <label className="ws-field"><span>Import source name</span><input required spellCheck={false} autoCapitalize="none" pattern="[a-z0-9]([a-z0-9_]|-)*" maxLength={80} value={namespace} onChange={event => { changed(); setNamespace(event.target.value); }} /></label>
        <p className="ws-helper">Keep this name and the same destination space for every batch or retry from this buffer. It keeps record identities stable.</p>
        <label className="ws-field"><span>Journal files</span><input ref={fileInput} type="file" accept=".jsonl,application/x-ndjson" multiple onChange={event => void load(event.target.files)} /></label>
        {!!files.length && <p className="ws-helper">Selected: {files.join(', ')}</p>}
        <label className="ws-field"><span>Withdrawn record IDs</span><textarea rows={3} spellCheck={false} autoCapitalize="none" value={withdrawals} onChange={event => { changed(); setWithdrawals(event.target.value); }} placeholder="One original record ID per line. Leave empty only after checking that none were withdrawn." /></label>
        <label className="ws-checkbox"><input type="checkbox" checked={personal} onChange={event => { changed(); setPersonal(event.target.checked); }} />Reject recognizable email addresses, phone numbers and personal identifiers. Secret checks always remain on.</label>
        <button className="ws-button" disabled={!jsonl && !withdrawals.trim()}>{busy ? <LoaderCircle size={16} className="ws-spin" /> : <FileInput size={16} />}Review import</button>
      </fieldset>
    </form>
    {!!error && <p className="ws-notice ws-error" role="alert">{describe(error)}</p>}
    {preview && <>
      <h3>{result ? 'Import completed' : 'Review these changes'}</h3>
      <div className="ws-stats">{Object.entries(preview.counts).map(([action, count]) => <div key={action}><span>{result && action === 'withdraw' ? 'Withdrawn now' : result && action === 'deny' ? 'Withdrawals retained' : labels[action as BufferPlanItem['action']]}</span><strong>{count}</strong></div>)}</div>
      {!!preview.duplicates && <p>{preview.duplicates} identical duplicate {preview.duplicates === 1 ? 'line was' : 'lines were'} combined.</p>}
      {!!preview.writers.length && <p className="ws-helper">Original writer labels: {preview.writers.join(', ')}. They are retained as provenance.</p>}
      <details className="ws-details"><summary>Review record identities and exclusions</summary><ul>{preview.items.map(item => <li key={item.legacy_id}><code>{item.legacy_id}</code> · {labels[item.action]}{item.code ? ` (${item.code.replaceAll('_', ' ')})` : ''}{result && ['create', 'already_imported', 'preserved_changes'].includes(item.action) && <> · <Link className="ws-link" to={`/workspace/memory/${item.memory_id}`}>Open memory</Link></>}</li>)}</ul></details>
      {!result && (!preview.can_import ? <p className="ws-notice">Reconcile conflicting or rejected records in a separate working copy, then review again. This batch has not changed the workspace.</p> : <div className="ws-form">
        <label className="ws-checkbox"><input type="checkbox" checked={reviewed} disabled={busy} onChange={event => setReviewed(event.target.checked)} />I checked the available history and supplied every known withdrawal for these records.</label>
        <label className="ws-checkbox"><input type="checkbox" checked={sourceOnly} disabled={busy} onChange={event => setSourceOnly(event.target.checked)} />I understand that this recovers available records. Original accounts, permissions, secrets and missing history require a complete backup.</label>
        <button className="ws-button ws-primary" disabled={busy || !reviewed || !sourceOnly} onClick={() => void apply()}>{busy ? 'Importing…' : 'Import reviewed batch'}</button>
      </div>)}
      {result && <p className="ws-notice" role="status">The reviewed changes are saved. Any new memories are available to keyword search; semantic indexing continues in the background. Share the space or configure publication separately after your recovery review.</p>}
    </>}
    <button className="ws-button ws-quiet" disabled={busy} onClick={clear}>{result ? 'Prepare another batch' : 'Clear selected files'}</button>
    <p><Link className="ws-link" to="/workspace/help?doc=docs%2Fservice%2Flegacy-buffer.md">Recovery limits, encrypted sources & agent instructions</Link></p>
  </section>;
}
