import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import type { CaptureRecovery, CaptureRestored } from '../../../shared/desktop-sources';
import { CaptureRestoredNotice } from './CaptureRestore';

function PendingRecovery({ item, revision, busy, setBusy, complete }: {
  item: CaptureRecovery; revision?: string; busy: boolean; setBusy: (value: boolean) => void;
  complete: (receipt?: CaptureRestored) => void;
}) {
  const native = window.mnemion!;
  const cache = useQueryClient();
  const [file, setFile] = useState(''), [key, setKey] = useState('');
  const [discard, setDiscard] = useState(false), [error, setError] = useState<string>();
  async function run(work: () => Promise<void>) {
    setBusy(true); setError(undefined);
    try { await work(); }
    catch (error) { setError(error instanceof Error ? error.message : 'Read recovery status before retrying.'); }
    finally { setBusy(false); void cache.invalidateQueries({ queryKey: ['capture-recoveries'] }); }
  }
  return <div className="ws-notice" data-update-pending={busy || file || key || discard ? '' : undefined}>
    <strong>{item.name} · Recovery interrupted</strong>
    <p style={{ overflowWrap: 'anywhere' }}>{item.endpoint}</p>
    <p>{item.copy_available ? 'The local copy is ready to verify and finish. Unlock your operating system’s credential store if prompted.' : 'The copy did not finish. Choose the same archive and its separate recovery key to continue safely.'}</p>
    {item.previous_grant_revoked === false && <p>The previous device’s retirement is not yet confirmed. Finish while signed in as an administrator of this workspace. Mnemion checks the server before retrying; the replacement stays paused.</p>}
    {!item.copy_available && <>
      <button type="button" className="ws-button" disabled={busy} onClick={() => void run(async () => { const value = await native.sourceBackupChoose!('open'); if (value) setFile(value); })}>Choose original backup</button>
      {file && <p style={{ overflowWrap: 'anywhere' }}>{file}</p>}
      <label className="ws-field"><span>Backup recovery key</span><input type="password" data-update-safe autoComplete="off" spellCheck={false} maxLength={50} value={key} disabled={busy} onChange={event => setKey(event.target.value)} /></label>
    </>}
    <div className="ws-actions">
      <button type="button" className="ws-button" disabled={busy || !revision || (!item.copy_available && (!file || key.length !== 50))} onClick={() => void run(async () => {
        let retirement: { retirement_credential?: string } = {};
        if (item.previous_grant_revoked === false) {
          const session = (await native.workspaceStatus!()).active;
          if (!session?.me.administrator || session.endpoint !== item.endpoint.replace(/\/$/, '')) throw new Error('Connect as an administrator of this recovery’s original workspace before finishing.');
          retirement = { retirement_credential: session.sessionToken };
        }
        const value = await native.sourceRestoreFinish!({ id: item.id, expected_revision: revision!, confirm: true,
          ...retirement, ...(!item.copy_available ? { file, recovery_key: key } : {}) });
        setFile(''); setKey(''); cache.setQueryData(['desktop-sources'], value.view); complete(value.recovery);
      })}>Finish recovery</button>
      <button type="button" className="ws-button" disabled={busy} onClick={() => setDiscard(true)}>Discard unfinished recovery</button>
    </div>
    {discard && <div className="ws-notice"><p>Revoke the replacement device’s capture grant and delete this unfinished local copy? Your archive file and shared workspace memories remain. The workspace must confirm revocation before deletion.</p>
      <button type="button" className="ws-button" disabled={busy || !revision} onClick={() => void run(async () => {
        await native.sourceRestoreDiscard!({ id: item.id, expected_revision: revision!, confirm: true });
        setFile(''); setKey(''); setDiscard(false); complete();
      })}>Revoke replacement and discard copy</button>
      <button type="button" className="ws-button" disabled={busy} onClick={() => setDiscard(false)}>Keep recovery</button>
    </div>}
    {(file || key) && <button type="button" className="ws-button" disabled={busy} onClick={() => { setFile(''); setKey(''); }}>Clear key and file selection</button>}
    {error && <p role="alert" className="ws-error">{error}</p>}
  </div>;
}

export default function CaptureRecoveries({ revision, busy, setBusy, endpoint }: {
  revision?: string; busy: boolean; setBusy: (value: boolean) => void; endpoint?: string;
}) {
  const native = window.mnemion, cache = useQueryClient();
  const [receipt, setReceipt] = useState<CaptureRestored>();
  const query = useQuery({ queryKey: ['capture-recoveries'], queryFn: () => native!.sourceRecoveries!(),
    enabled: !!native?.sourceRecoveries && !busy, refetchInterval: 15000, retry: false });
  const items = query.data?.items.filter(item => !endpoint || item.endpoint.replace(/\/$/, '') === endpoint.replace(/\/$/, ''));
  if (!native?.sourceRecoveries || (!receipt && !query.error && !items?.length)) return null;
  return <section aria-label="Pending capture recoveries">
    {receipt && <CaptureRestoredNotice value={receipt} />}
    {query.error && <p className="ws-notice">Pending recoveries could not be checked. <button className="ws-button" disabled={busy} onClick={() => void query.refetch()}>Refresh recovery status</button></p>}
    {items?.map(item => <PendingRecovery key={item.id} item={item} revision={revision} busy={busy} setBusy={setBusy} complete={value => {
      setReceipt(value); void cache.invalidateQueries({ queryKey: ['capture-recoveries'] });
      void cache.invalidateQueries({ queryKey: ['desktop-sources'] });
    }} />)}
  </section>;
}
