import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { Archive, Copy, FolderOpen, KeyRound, LoaderCircle, RefreshCw, ShieldCheck, Square } from 'lucide-react';
import type { BackupView, LocalStatus } from '../../../shared/local-workspace';
import { memorySize } from './MemoryControls';
import { localError } from './LocalSetup';
import './backups.css';

const stamp = (value?: string) => value ? new Date(value).toLocaleString() : 'No verified backup yet';
const fileSize = (value: number) => value < 1024 ? `${value} B` : value < 1024 ** 2
  ? `${(value / 1024).toLocaleString(undefined, { maximumFractionDigits: 1 })} KiB` : memorySize(value);

export default function Backups({ status, onStatus }: { status: LocalStatus; onStatus: (status: LocalStatus) => void }) {
  const desktop = window.mnemion;
  const [view, setView] = useState<BackupView>();
  const [folder, setFolder] = useState<{ id: string; path: string }>();
  const [key, setKey] = useState('');
  const [keySaved, setKeySaved] = useState(false);
  const [manualKey, setManualKey] = useState('');
  const [enabled, setEnabled] = useState(true);
  const [hours, setHours] = useState(24);
  const [minutes, setMinutes] = useState(15);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const [notice, setNotice] = useState('');
  const serial = useRef(0);
  async function refresh() {
    const request = ++serial.current;
    try { const next = await desktop!.localBackupStatus!(); if (request === serial.current) { setView(next); setError(undefined); } }
    catch (error) { if (request === serial.current) setError(error); }
  }
  useEffect(() => {
    void refresh();
    const unsubscribe = desktop?.onBackupStatus?.(() => { void refresh(); });
    return () => { ++serial.current; unsubscribe?.(); };
  }, [desktop, status.info?.settings?.workspace_id]);
  useEffect(() => {
    if (!view || dirty) return;
    setEnabled(view.configuration?.enabled ?? view.secure_storage);
    setHours(view.configuration?.snapshot_hours ?? 24);
    setMinutes(view.configuration?.ledger_minutes ?? 15);
  }, [view, dirty]);

  if (!desktop?.localBackupStatus || !status.info?.configured) return null;
  const configuration = view?.configuration;
  const activity = status.backup;
  const working = busy || activity?.state === 'running' || activity?.state === 'cancelling';
  const changed = () => { setDirty(true); setNotice(''); };
  const snapshot = view?.last_snapshot?.snapshot;
  return <section className="ws-device-settings ws-backup-panel" aria-labelledby="backups-title">
    <div className="ws-memory-heading"><h2 id="backups-title"><Archive size={19} />Backups & recovery</h2><button className="ws-button ws-quiet" type="button" disabled={working} onClick={() => void refresh()}><RefreshCw size={15} />Refresh</button></div>
    <p>Protect <strong>{status.info.settings?.workspace_name}</strong> on this computer. Snapshots include the complete local database, with a separate ledger for later deletions and access changes.</p>
    {!!error && <p className="ws-notice ws-error" role="alert">{localError(error)}</p>}
    {notice && <p className="ws-notice" role="status">{notice}</p>}
    {view?.last_error && !error && <p className="ws-notice ws-error" role="alert">Last attempt: {view.last_error}</p>}
    {view?.retry_at && view.last_error && configuration?.enabled && <p className="ws-helper">Automatic retry after {stamp(view.retry_at)}. You can also retry manually.</p>}
    <div className="ws-backup-facts">
      <div><span>Latest verified snapshot</span><strong>{stamp(view?.last_snapshot?.verified_at)}</strong>{snapshot && <small>{snapshot.memory_count.toLocaleString()} memories · {fileSize(snapshot.bytes)}</small>}</div>
      <div><span>Latest verified access ledger</span><strong>{stamp(view?.last_ledger?.verified_at)}</strong>{view?.last_ledger && <small>{view.last_ledger.tenant_count} organization{view.last_ledger.tenant_count === 1 ? '' : 's'} · {fileSize(view.last_ledger.ledger.bytes)}</small>}</div>
    </div>
    {((view?.snapshot_availability && view.snapshot_availability !== 'present') || (view?.ledger_availability && view.ledger_availability !== 'present')) && <p className="ws-notice ws-error">A previously verified backup file is missing, changed, or unavailable in the selected folder. Reconnect the drive or storage app and create a new backup. The dates above record the last successful verification.</p>}
    {configuration?.enabled && <p className="ws-helper">Next snapshot: {stamp(view?.next_snapshot_at)}. Next ledger: {stamp(view?.next_ledger_at)}. Due work starts when the local workspace is running.</p>}
    {activity && ['running', 'cancelling'].includes(activity.state) && <div className="ws-setup-progress" role="status"><p><LoaderCircle className="ws-spin" size={17} />{activity.message}</p><button type="button" className="ws-button" disabled={activity.state === 'cancelling'} onClick={() => { void desktop.localBackupCancel!().then(onStatus).catch(setError); }}><Square size={14} />Cancel safely</button></div>}
    <form data-update-pending={dirty || key || manualKey ? '' : undefined} onSubmit={async event => {
      event.preventDefault(); setBusy(true); setError(undefined); setNotice('');
      try {
        const next = await desktop.localBackupConfigure!({ expected_revision: configuration?.revision ?? null,
          destination_selection: folder?.id ?? null, enabled, snapshot_hours: hours, ledger_minutes: minutes,
          recovery_key: key || undefined, key_saved: keySaved });
        setView(next); setDirty(false); setFolder(undefined);
        if (!enabled && key) setManualKey(key);
        setKey(''); setKeySaved(false);
        setNotice(enabled ? 'Schedule saved. Recovery files are encrypted and verified before a run is marked successful.' : 'Manual backup settings saved. Supply the recovery key when you create a backup.');
      } catch (error) { setError(error); } finally { setBusy(false); }
    }}>
      <label className="ws-field"><span>Backup folder</span><div className="ws-backup-folder"><span className="ws-local-path">{folder?.path ?? configuration?.destination ?? 'Choose a separate drive or cloud-synchronized folder'}</span><button type="button" className="ws-button" disabled={working} onClick={async () => {
        try { const selected = await desktop.localBackupChoose!('folder'); if (selected) { setFolder(selected); changed(); } } catch (error) { setError(error); }
      }}><FolderOpen size={15} />Choose folder</button></div></label>
      <p className="ws-helper">Mnemion verifies the local encrypted files. Your storage app handles cloud upload; keep the recovery key separately.</p>
      <div className="ws-backup-key">
        <label className="ws-field"><span>{configuration ? 'New recovery key (optional rotation)' : 'Recovery key'}</span><input data-update-safe type="password" autoComplete="off" spellCheck={false} maxLength={50} value={key} disabled={working} placeholder={configuration ? 'Leave empty to keep the current key' : 'Generate a key or enter one you already saved'} onChange={event => { setKey(event.target.value); setKeySaved(false); changed(); }} /></label>
        <div className="ws-setup-actions"><button type="button" className="ws-button" disabled={working} onClick={async () => {
          try { setKey(await desktop.localBackupKey!()); setKeySaved(false); changed(); } catch (error) { setError(error); }
        }}><KeyRound size={15} />Generate key</button><button type="button" className="ws-button" disabled={!key || working} onClick={async () => {
          try { await navigator.clipboard.writeText(key); setNotice('Recovery key copied. Save it in a password manager or another safe place outside the backup folder.'); } catch (error) { setError(error); }
        }}><Copy size={15} />Copy key</button></div>
        {key && <label className="ws-backup-check"><input data-update-safe type="checkbox" checked={keySaved} disabled={working} onChange={event => setKeySaved(event.target.checked)} />I saved this key separately and can find it if this computer is lost.</label>}
        {configuration && <small>Current key ID: <code>{configuration.key_id}</code>. Changing the key leaves older backup files in place; keep their old keys.</small>}
      </div>
      <label className="ws-backup-check"><input data-update-safe type="checkbox" checked={enabled} disabled={working} onChange={event => { setEnabled(event.target.checked); changed(); }} />Back up automatically while this workspace is running</label>
      {enabled && <div className="ws-backup-grid"><label className="ws-field"><span>Full snapshot</span><select data-update-safe disabled={working} value={hours} onChange={event => { setHours(Number(event.target.value)); changed(); }}><option value={6}>Every 6 hours</option><option value={12}>Every 12 hours</option><option value={24}>Daily</option><option value={168}>Weekly</option></select></label><label className="ws-field"><span>Deletion & access ledger</span><select data-update-safe disabled={working} value={minutes} onChange={event => { setMinutes(Number(event.target.value)); changed(); }}><option value={15}>Every 15 minutes</option><option value={30}>Every 30 minutes</option><option value={60}>Hourly</option><option value={240}>Every 4 hours</option></select></label></div>}
      {!view?.secure_storage && <p className="ws-notice">The OS secure store is unavailable or locked. Unlock it for scheduled backups, or use manual backups with a key for each run.</p>}
      <p className="ws-helper">All backup files are retained. Manage older copies in your storage. Missed runs are coalesced after sleep; this schedule cannot wake a powered-off computer.</p>
      <div className="ws-setup-actions"><button className="ws-button ws-primary" disabled={working || !view || (!folder && !configuration) || (!configuration && !key) || (!!key && !keySaved) || (!dirty && !!configuration)}><ShieldCheck size={16} />Save backup settings</button>{dirty && configuration && <button type="button" className="ws-button ws-quiet" disabled={working} onClick={() => { setDirty(false); setFolder(undefined); setKey(''); setKeySaved(false); setNotice(''); }}>Discard changes</button>}</div>
    </form>
    {configuration && <div className="ws-backup-run" data-update-pending={manualKey ? '' : undefined}>
      <details className="ws-setup-advanced" open={!configuration.protected_key || !view?.secure_storage ? true : undefined}><summary>Use a recovery key for this run</summary><label className="ws-field"><span>Recovery key{configuration.protected_key ? ' (optional when the secure store is unlocked)' : ''}</span><input data-update-safe type="password" autoComplete="off" spellCheck={false} maxLength={50} value={manualKey} disabled={working} onChange={event => setManualKey(event.target.value)} /></label></details>
      <div className="ws-setup-actions">{[false, true].map(ledger => <button key={String(ledger)} type="button" className={ledger ? 'ws-button' : 'ws-button ws-primary'} disabled={working || dirty || status.state !== 'running' || (!configuration.protected_key && !manualKey)} onClick={async () => {
        setBusy(true); setError(undefined); setNotice('');
        try { await desktop.localBackupRun!({ ledger_only: ledger, recovery_key: manualKey || undefined }); setNotice(ledger ? 'Access ledger encrypted and verified locally.' : 'Snapshot and access ledger encrypted and verified locally.'); await refresh(); }
        catch (error) { setError(error); } finally { setBusy(false); setManualKey(''); }
      }}>{working ? <LoaderCircle className="ws-spin" size={15} /> : <Archive size={15} />}{ledger ? 'Refresh ledger' : 'Back up now'}</button>)}</div>
      {status.state !== 'running' && <p className="ws-helper">Resume this local workspace to create its next backup.</p>}
    </div>}
    <p><Link className="ws-link" to="/help?doc=docs%2Fservice%2Fnative-backups.md">Recovery guide</Link> · Recover a separate copy from the welcome screen’s <strong>Recover a workspace</strong> option.</p>
  </section>;
}
