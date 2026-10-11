import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, LockKeyhole, ShieldCheck } from 'lucide-react';
import type { WorkspaceBookmark, WorkspaceInspection } from './connection-types';

function date(value: string): string {
  return new Date(value).toLocaleString();
}

/** Local context stays useful when a workspace or its original agent is offline. */
export default function WorkspaceRecovery({ bookmark, busy, onReconnect, onNewConnection }: {
  bookmark: WorkspaceBookmark;
  busy: boolean;
  onReconnect: () => void;
  onNewConnection: () => void;
}) {
  const [inspection, setInspection] = useState<WorkspaceInspection>();
  const [unavailable, setUnavailable] = useState(false);

  useEffect(() => {
    let current = true;
    setInspection(undefined);
    setUnavailable(false);
    if (!window.mnemion?.workspaceInspect) {
      setUnavailable(true);
      return;
    }
    void window.mnemion.workspaceInspect(bookmark.id).then(value => {
      if (current) setInspection(value);
    }, () => {
      if (current) setUnavailable(true);
    });
    return () => { current = false; };
  }, [bookmark.id, bookmark.updatedAt]);

  const access = inspection?.access;
  const saved = inspection?.bookmark ?? bookmark;
  const role = access ? access.identity.administrator ? 'Organization administrator' : 'Member' : 'Not available offline';
  return <section className="ws-recovery" aria-label={`Recovery details for ${bookmark.label}`}>
    <div className="ws-recovery-heading"><ShieldCheck size={18} /><h4>Workspace details & recovery</h4></div>
    <p className="ws-helper">Saved on this device. This view works without the workspace server.</p>
    <dl className="ws-recovery-facts">
      <div><dt>Workspace address</dt><dd>{saved.endpoint}</dd></div>
      <div><dt>Workspace ID</dt><dd className="ws-recovery-id">{saved.tenantId}</dd></div>
      <div><dt>Your identity</dt><dd>{saved.principalName}</dd></div>
      <div><dt>Identity ID</dt><dd className="ws-recovery-id">{saved.principalId}</dd></div>
      <div><dt>Last successful connection</dt><dd><time dateTime={saved.updatedAt}>{date(saved.updatedAt)}</time></dd></div>
      <div><dt>Last verified organization role</dt><dd aria-live="polite">{!inspection && !unavailable ? 'Reading protected connection…' : role}</dd></div>
    </dl>
    <div className="ws-recovery-access" role="status">
      {access ? <p>Your role was verified on <time dateTime={access.verifiedAt}>{date(access.verifiedAt)}</time>. Reconnecting checks your current key and permissions. Space access remains separately controlled.</p>
        : inspection?.accessStatus === 'locked' ? <p><LockKeyhole size={14} /> Unlock your operating system’s secure store to read the saved access record. The workspace address and recovery guides remain available.</p>
        : inspection?.accessStatus === 'not-recorded' ? <p>This connection was saved by an earlier version without a role record. A successful reconnection will record your current role.</p>
        : unavailable || inspection?.accessStatus === 'unavailable' ? <p>The protected access record could not be read. Keep this connection and reconnect with a current key when available.</p>
        : null}
    </div>
    <div className="ws-recovery-step">
      <h4>Get connected</h4>
      <p>Retry the saved address when the service is running. Confirm any replacement address with your administrator before entering a key.</p>
      <div className="ws-recovery-actions">
        <button type="button" className="ws-button ws-primary" disabled={busy || inspection?.accessStatus === 'locked'} onClick={onReconnect}><ArrowRight size={15} />Reconnect and verify access</button>
        <button type="button" className="ws-button" disabled={busy} onClick={onNewConnection}>Use another address or key</button>
      </div>
    </div>
    <div className="ws-recovery-step">
      <h4>Manage an offline host</h4>
      <p>Starting the server or its tunnel requires the host owner’s operator access. A saved workspace connection identifies your account; it does not enroll this computer as a database replica.</p>
      <Link className="ws-link" to="/help?doc=docs%2Fservice%2Fconnection-diagnostics.md">Connection and host recovery guide<ArrowRight size={13} /></Link>
    </div>
    <div className="ws-recovery-step">
      <h4>Recover your data</h4>
      <p>A Git or cloud source mirror can recover its tracked documents. Complete workspace restoration also needs a verified database backup and the current access and deletion ledger.</p>
      <Link className="ws-link" to="/help?doc=docs%2Fservice%2Frecovery.md">Backup and restoration guide<ArrowRight size={13} /></Link>
      <Link className="ws-link" to="/help?doc=docs%2Fservice%2Forganizations.md">Independent administration guide<ArrowRight size={13} /></Link>
    </div>
  </section>;
}
