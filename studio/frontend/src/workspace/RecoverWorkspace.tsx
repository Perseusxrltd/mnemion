import { useEffect, useState } from 'react';
import { ArrowLeft, ArchiveRestore, FolderOpen, LoaderCircle, ShieldCheck, Square } from 'lucide-react';
import type { BackupInspectionData, LocalStatus, RecoveryReceipt } from '../../../shared/local-workspace';
import { localError } from './LocalSetup';
import './backups.css';

export default function RecoverWorkspace({ onUse, onBack }: { onUse: (status: LocalStatus) => void; onBack: () => void }) {
  const desktop = window.mnemion!;
  const [snapshotFile, setSnapshotFile] = useState<{ id: string; path: string }>();
  const [ledgerFile, setLedgerFile] = useState<{ id: string; path: string }>();
  const [key, setKey] = useState('');
  const [ledgerKey, setLedgerKey] = useState('');
  const [sameKey, setSameKey] = useState(true);
  const [snapshot, setSnapshot] = useState<BackupInspectionData>();
  const [ledger, setLedger] = useState<BackupInspectionData>();
  const [primary, setPrimary] = useState('');
  const [confirmed, setConfirmed] = useState(false);
  const [hostConfirmed, setHostConfirmed] = useState(false);
  const [embedded, setEmbedded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const [activity, setActivity] = useState<LocalStatus['backup']>();
  const [copy, setCopy] = useState<{ id: string; receipt: RecoveryReceipt }>();
  const [copies, setCopies] = useState<Array<{ id: string; receipt: RecoveryReceipt }>>([]);
  const [originalAvailable, setOriginalAvailable] = useState(false);
  useEffect(() => {
    let active = true;
    void desktop.localRecoveryCopies!().then(value => { if (active) setCopies(value); }).catch(error => { if (active) setError(error); });
    void desktop.localStatus!().then(value => { if (active) setOriginalAvailable(!!value.preferences?.recoveryRoot && !!value.preferences?.originalAvailable); }).catch(error => { if (active) setError(error); });
    const unsubscribe = desktop.onLocalStatus?.(status => { if (active) setActivity(status.backup); });
    return () => { active = false; unsubscribe?.(); };
  }, [desktop]);
  async function perform(action: () => Promise<void>) {
    setBusy(true); setError(undefined);
    try { await action(); } catch (error) { setError(error); } finally { setBusy(false); }
  }
  const date = (value?: string) => value ? new Date(value).toLocaleString() : 'Not inspected';
  const selectedLedger = embedded && snapshot?.kind === 'host' && snapshot.embedded_ledger_sha256
    ? { ledger_at: snapshot.ledger_at, sha256: snapshot.embedded_ledger_sha256 } : ledger;
  const step = !snapshot ? 1 : !selectedLedger ? 2 : 3;
  const running = busy || activity?.state === 'running' || activity?.state === 'cancelling';
  const working = activity && ['running', 'cancelling'].includes(activity.state);
  const minimumLedgerDate = snapshot?.kind === 'host' ? snapshot.ledger_at : snapshot?.snapshot_at;
  const ledgerFresh = !!minimumLedgerDate && !!selectedLedger?.ledger_at && Date.parse(selectedLedger.ledger_at) >= Date.parse(minimumLedgerDate);
  return <section className="ws-local-setup ws-recover-workspace" aria-label="Recover a workspace" data-update-pending={key || ledgerKey || running ? '' : undefined}>
    <button className="ws-button ws-quiet" type="button" disabled={running} onClick={onBack}><ArrowLeft size={15} />Choose another workspace</button>
    <div className="ws-local-intro"><span className="ws-local-symbol"><ArchiveRestore size={23} /></span><div><h3>Recover a workspace</h3><p>Open a desktop snapshot or server backup and the newest available deletion/access ledger. Mnemion creates a separate local copy and keeps your current workspace.</p></div></div>
    {!!error && <p className="ws-notice ws-error" role="alert">{localError(error)}</p>}
    {working && <div className="ws-setup-progress" role="status"><p><LoaderCircle className="ws-spin" size={17} />{activity.message}</p><button type="button" className="ws-button" disabled={activity.state === 'cancelling'} onClick={() => { void desktop.localBackupCancel!().catch(setError); }}><Square size={14} />Cancel safely</button></div>}
    {!copy && <>
      <div className="ws-setup-steps" aria-label={'Recovery step ' + step + ' of 3'}>{['Snapshot', 'Access ledger', 'Review & recover'].map((label, index) => <span key={label} className={index + 1 === step ? 'current' : index + 1 < step ? 'complete' : ''}><b>{index + 1}</b>{label}</span>)}</div>
      <div className="ws-setup-fields">
        <label className="ws-field"><span>Encrypted snapshot or server backup</span><div className="ws-backup-folder"><span className="ws-local-path">{snapshotFile?.path ?? 'Choose a .mnemion.enc or .mnemion-host backup'}</span><button type="button" className="ws-button" disabled={running} onClick={() => void perform(async () => {
          const selected = await desktop.localBackupChoose!('file'); if (selected) { setSnapshotFile(selected); setSnapshot(undefined); setLedger(undefined); setConfirmed(false); setEmbedded(false); setHostConfirmed(false); }
        })}><FolderOpen size={15} />Choose snapshot</button></div></label>
        <label className="ws-field"><span>Snapshot recovery key</span><input data-update-safe type="password" autoComplete="off" spellCheck={false} maxLength={50} disabled={running} value={key} onChange={event => { setKey(event.target.value); setSnapshot(undefined); if (sameKey) setLedger(undefined); setConfirmed(false); setEmbedded(false); setHostConfirmed(false); }} /></label>
        {!snapshot && <button type="button" className="ws-button ws-primary" disabled={running || !snapshotFile || !key} onClick={() => void perform(async () => {
          const value = await desktop.localBackupInspect!({ selection_id: snapshotFile!.id, recovery_key: key });
          if (!['snapshot', 'host'].includes(value.kind) || !value.archive_verified) throw new Error('Choose a database snapshot or server backup, then review its access ledger.');
          setSnapshot(value); setPrimary(value.tenant_ids!.includes(value.context?.local_workspace?.primary_tenant_id ?? '') ? value.context!.local_workspace!.primary_tenant_id : value.tenant_ids![0] ?? '');
        })}><ShieldCheck size={16} />Inspect snapshot</button>}
      </div>
      {snapshot && <div className="ws-setup-fields">
        <p className="ws-notice"><ShieldCheck size={16} />Snapshot authenticated: {snapshot.memory_count?.toLocaleString()} memories from {date(snapshot.snapshot_at)}.</p>
        {snapshot.host_package && <div className="ws-notice">
          <p>Server backup from Mnemion {snapshot.host_package.service_version}. Its database can be recovered on this computer.</p>
          <p>The {snapshot.host_package.source_connectors} source connection{snapshot.host_package.source_connectors === 1 ? '' : 's'} and {snapshot.host_package.private_files} private configuration file{snapshot.host_package.private_files === 1 ? '' : 's'} stay in the original encrypted backup. Company sign-in, vault host keys, cloud models and network settings need separate setup.</p>
          <p>Included access ledger: {date(snapshot.ledger_at)}. Select a newer copy below if one is available.</p>
          <button type="button" className="ws-button" disabled={running || embedded} onClick={() => { setEmbedded(true); setConfirmed(false); setHostConfirmed(false); }}>Use included ledger</button>
          {embedded && <p role="status">Using the ledger authenticated inside this server backup.</p>}
        </div>}
        <label className="ws-field"><span>Newest encrypted deletion/access ledger</span><div className="ws-backup-folder"><span className="ws-local-path">{ledgerFile?.path ?? 'Choose the newest ledger-…mnemion.enc file'}</span><button className="ws-button" type="button" disabled={running} onClick={() => void perform(async () => {
          const selected = await desktop.localBackupChoose!('file'); if (selected) { setLedgerFile(selected); setLedger(undefined); setConfirmed(false); setEmbedded(false); setHostConfirmed(false); }
        })}><FolderOpen size={15} />Choose ledger</button></div></label>
        {!embedded && <label className="ws-backup-check"><input data-update-safe type="checkbox" checked={sameKey} disabled={running} onChange={event => { setSameKey(event.target.checked); setLedger(undefined); setConfirmed(false); }} />Use the snapshot’s recovery key</label>}
        {!embedded && !sameKey && <label className="ws-field"><span>Ledger recovery key</span><input data-update-safe type="password" autoComplete="off" spellCheck={false} maxLength={50} value={ledgerKey} disabled={running} onChange={event => { setLedgerKey(event.target.value); setLedger(undefined); setConfirmed(false); }} /></label>}
        {!embedded && !ledger && <button type="button" className="ws-button ws-primary" disabled={running || !ledgerFile || !(sameKey ? key : ledgerKey)} onClick={() => void perform(async () => {
          const value = await desktop.localBackupInspect!({ selection_id: ledgerFile!.id, recovery_key: sameKey ? key : ledgerKey });
          if (value.kind !== 'ledger') throw new Error('Choose an encrypted access ledger.');
          setLedger(value);
        })}><ShieldCheck size={16} />Inspect ledger</button>}
      </div>}
      {snapshot && selectedLedger && <div className="ws-setup-review">
        <h3>Review your recovery copy</h3>
        <dl><dt>Workspace</dt><dd>{snapshot.context?.local_workspace?.workspace_name ?? (snapshot.kind === 'host' ? 'Server backup' : 'Database backup')}</dd><dt>Snapshot</dt><dd>{date(snapshot.snapshot_at)}</dd><dt>Deletion & access ledger</dt><dd>{date(selectedLedger.ledger_at)}{embedded ? ' · included in the server backup' : ''}</dd><dt>Data</dt><dd>{snapshot.memory_count?.toLocaleString()} memories · {snapshot.tenant_count} organization{snapshot.tenant_count === 1 ? '' : 's'}</dd></dl>
        {(snapshot.tenant_ids?.length ?? 0) > 1 && <label className="ws-field"><span>Organization to open first</span><select data-update-safe value={primary} disabled={running} onChange={event => setPrimary(event.target.value)}>{snapshot.tenant_ids!.map(id => <option key={id} value={id}>{id === snapshot.context?.local_workspace?.primary_tenant_id ? snapshot.context.local_workspace.workspace_name : 'Organization ' + id}</option>)}</select></label>}
        <p>Original files stay in place. The recovered copy gets fresh administrator keys; people, sources and cloud models need their access reviewed. Changes after the selected ledger’s date cannot be reconstructed from these files.</p>
        {!ledgerFresh && <p className="ws-notice ws-error" role="alert">This ledger predates {snapshot.kind === 'host' ? 'the ledger already included in the server backup' : 'the snapshot'}. Choose one recorded at the same time or later.</p>}
        <label className="ws-backup-check"><input data-update-safe type="checkbox" checked={confirmed} disabled={running} onChange={event => setConfirmed(event.target.checked)} />I trust this backup and selected the newest available access ledger.</label>
        {snapshot.kind === 'host' && <label className="ws-backup-check"><input data-update-safe type="checkbox" checked={hostConfirmed} disabled={running} onChange={event => setHostConfirmed(event.target.checked)} />Restore the database with fresh access. I will configure sources, models, sign-in and sharing separately, and keep the original encrypted server backup.</label>}
        <p className="ws-helper">Only restore backups from a trusted operator. Restoring a database executes its stored database definitions.</p>
        <button type="button" className="ws-button ws-primary" disabled={running || !confirmed || !ledgerFresh || !primary || (snapshot.kind === 'host' && !hostConfirmed)} onClick={() => void perform(async () => {
          const value = await desktop.localBackupRestore!({ snapshot_selection: snapshotFile!.id, ledger_selection: embedded ? null : ledgerFile!.id,
            recovery_key: key, ledger_key: embedded || sameKey ? null : ledgerKey, snapshot_sha256: snapshot.sha256,
            ledger_sha256: selectedLedger.sha256, primary_tenant_id: primary, trusted_backup_confirmed: confirmed,
            source_kind: snapshot.kind === 'host' ? 'host' : 'snapshot', host_data_only_confirmed: snapshot.kind === 'host' ? hostConfirmed : undefined });
          setCopy(value); setKey(''); setLedgerKey('');
        })}><ArchiveRestore size={16} />Create verified recovery copy</button>
      </div>}
    </>}
    {copy && <div className="ws-local-ready"><ShieldCheck size={28} /><h3>Your recovery copy is verified</h3><p>Original data is retained. {copy.receipt.deletions_reconciled.toLocaleString()} deletion records were reconciled and fresh administrator access is ready.</p><p>Before sharing this copy as the team’s new host, stop the previous writer and update your team’s connection. External connections remain paused for review.</p><button className="ws-button ws-primary" disabled={running} onClick={() => void perform(async () => onUse(await desktop.localRecoveryUse!(copy.id)))}>Use this recovery copy</button><details className="ws-setup-advanced"><summary>Recovery details</summary><p className="ws-local-path">{copy.receipt.data_directory}</p><p>{copy.receipt.verified_tables} tables verified · {copy.receipt.tenant_count} organizations retained. Additional organizations’ administrator keys are in the private recovery-administrators.json file.</p></details></div>}
    {copies.length > 0 && !copy && <details className="ws-setup-advanced"><summary>Previously verified recovery copies</summary>{copies.map(saved => <div className="ws-backup-folder" key={saved.id}><span>{date(saved.receipt.restored_at)} · {saved.receipt.tenant_count} organizations</span><button className="ws-button" type="button" disabled={running} onClick={() => void perform(async () => onUse(await desktop.localRecoveryUse!(saved.id)))}>Use copy</button></div>)}</details>}
    {originalAvailable && <button type="button" className="ws-button ws-quiet" disabled={running} onClick={() => void perform(async () => onUse(await desktop.localRecoveryUse!(null)))}>Return to the original local workspace</button>}
  </section>;
}
