import { useState } from 'react';
import type { CaptureArchiveInfo, DesktopSource } from '../../../shared/desktop-sources';

/** Device evidence remains accessible while the selected workspace is offline. */
export default function CaptureBackup({ source, revision, busy, setBusy }: {
  source?: DesktopSource; revision?: string; busy: boolean; setBusy: (value: boolean) => void;
}) {
  const native = window.mnemion;
  const [file, setFile] = useState(''), [key, setKey] = useState('');
  const [keySaved, setKeySaved] = useState(false), [visibleKey, setVisibleKey] = useState(false);
  const [error, setError] = useState<string>();
  const [receipt, setReceipt] = useState<{ file: string; value: CaptureArchiveInfo }>();
  if (!native?.sourceBackup || !native.sourceBackupInspect || !native.sourceBackupChoose) return null;
  const exporting = !!source;
  const failure = (value: unknown) => setError(value instanceof Error ? value.message : 'The capture archive operation could not finish.');
  async function choose() {
    setBusy(true); setError(undefined);
    try { const selected = await native!.sourceBackupChoose!(exporting ? 'save' : 'open'); if (selected) { setFile(selected); setReceipt(undefined); } }
    catch (error) { failure(error); }
    finally { setBusy(false); }
  }
  async function run() {
    setBusy(true); setError(undefined);
    try {
      const value = source ? await native!.sourceBackup!({ id: source.id, expected_revision: revision!, file, recovery_key: key, confirm: true })
        : await native!.sourceBackupInspect!({ file, recovery_key: key });
      setReceipt({ file, value }); setFile(''); setKey(''); setKeySaved(false); setVisibleKey(false);
    } catch (error) { failure(error); }
    finally { setBusy(false); }
  }
  return <details className="ws-details" data-update-pending={file || key ? '' : undefined}>
    <summary>{exporting ? 'Back up this capture inbox' : 'Inspect a capture backup'}</summary>
    <p className="ws-helper">This archive protects pending memories, capture checkpoints and deletion history on a computer. Already delivered memories need a separate workspace backup. The archive includes no workspace access key.</p>
    {source?.enabled && <p className="ws-notice">Pause this source before creating its backup.</p>}
    <button type="button" className="ws-button" disabled={busy || !!source?.enabled} onClick={() => void choose()}>{exporting ? 'Choose where to save' : 'Choose backup file'}</button>
    {file && <p className="ws-helper" style={{ overflowWrap: 'anywhere' }}>{file}</p>}
    <label className="ws-field"><span>Separate recovery key</span><input type={visibleKey ? 'text' : 'password'} autoComplete="off" spellCheck={false} data-update-safe value={key} maxLength={50} disabled={busy} onChange={event => { setKey(event.target.value); setKeySaved(false); }} /></label>
    <div className="ws-actions">
      {exporting && <button type="button" className="ws-button" disabled={busy || !native.localBackupKey} onClick={async () => {
        try { setKey(await native.localBackupKey!()); setKeySaved(false); setVisibleKey(true); setError(undefined); }
        catch (error) { failure(error); }
      }}>Generate recovery key</button>}
      {key && <button type="button" className="ws-button" disabled={busy} onClick={() => setVisibleKey(!visibleKey)}>{visibleKey ? 'Hide key' : 'Show key'}</button>}
      {key && <button type="button" className="ws-button" disabled={busy} onClick={() => { void navigator.clipboard.writeText(key).catch(failure); }}>Copy key</button>}
    </div>
    {exporting && <label className="ws-checkbox"><input type="checkbox" data-update-safe checked={keySaved} disabled={busy || !key} onChange={event => setKeySaved(event.target.checked)} />I saved this key separately and can find it if this computer is lost.</label>}
    <div className="ws-actions">
      <button type="button" className="ws-button" disabled={busy || !file || key.length !== 50 || !!source?.enabled || (exporting && (!keySaved || !revision))} onClick={() => void run()}>{busy ? 'Working…' : exporting ? 'Create encrypted backup' : 'Verify backup'}</button>
      {(file || key) && <button type="button" className="ws-button" disabled={busy} onClick={() => { setFile(''); setKey(''); setKeySaved(false); setVisibleKey(false); setError(undefined); }}>Clear</button>}
    </div>
    {error && <p className="ws-notice ws-error" role="alert">{error}</p>}
    {receipt && <div className="ws-notice" data-capture-backup="verified">
      <strong>{exporting ? 'Encrypted backup created and verified' : 'Capture backup verified'}</strong>
      <p style={{ overflowWrap: 'anywhere' }}>{receipt.file}</p>
      <p>{receipt.value.name} · {new Date(receipt.value.created_at).toLocaleString()}<br />
        {receipt.value.status.pending_events.toLocaleString()} pending fragments · {receipt.value.status.stored_events.toLocaleString()} delivered · {receipt.value.status.forgotten_events.toLocaleString()} forgotten</p>
      <p className="ws-helper">Verifying an archive does not connect a device or resume capture. Its recovery key is still required to use this backup.</p>
      <details><summary>Archive identity</summary><code style={{ overflowWrap: 'anywhere' }}>{receipt.value.archive_sha256}</code></details>
    </div>}
  </details>;
}
