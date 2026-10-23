import { useEffect, useState } from 'react'
import type { HostBackupsStatus } from '../../../shared/host-control'

type Props = {
  state: HostBackupsStatus | undefined;
  actions: string[];
  busy: boolean;
  pending: boolean;
  recoveryRequired: boolean;
  onRequest: (action: 'backup.create' | 'backup.verify', fields: Record<string, unknown>) => Promise<void>;
}

const when = (value?: string | null) => value ? new Date(value).toLocaleString() : 'Not recorded'
const size = (bytes: number) => `${(bytes / 1024 ** 2).toLocaleString(undefined, { maximumFractionDigits: 1 })} MiB`

export default function HostBackups({ state, actions, busy, pending, recoveryRequired, onRequest }: Props) {
  const [approval, setApproval] = useState(false)
  const configuration = state?.configuration_sha256
  useEffect(() => { setApproval(false) }, [configuration])
  const unavailable = busy || pending || !approval || !state?.configured || !configuration || !!state?.inspection_required
  const canCreate = actions.includes('backup.create')
  const canVerify = actions.includes('backup.verify')

  async function request(action: 'backup.create' | 'backup.verify', backupId?: string) {
    if (unavailable || (action === 'backup.create' && recoveryRequired)) return
    setApproval(false)
    await onRequest(action, {
      configuration_sha256: configuration,
      approve_backup_transfer: true,
      ...(backupId ? { backup_id: backupId } : {}),
    })
  }

  return <section className="ws-card" aria-labelledby="host-backups-heading">
    <div className="ws-section-title"><h2 id="host-backups-heading">Independent backups</h2>
      {canCreate && <button className="ws-button" disabled={unavailable || recoveryRequired}
        onClick={() => void request('backup.create')}>Create encrypted backup</button>}
    </div>
    <p>Copy this host’s memories and access/deletion ledger to the owner’s configured Git storage. Source imports pause while the copy is prepared. The memory service keeps its current running or stopped state.</p>
    <dl className="ws-host-facts">
      <div><dt>Storage</dt><dd>{state?.configured ? 'Owner configured' : 'Owner setup required'}</dd></div>
      <div><dt>Maximum backup size</dt><dd>{state?.maximum_bytes ? size(state.maximum_bytes) : 'Not configured'}</dd></div>
      <div><dt>Last verified readback</dt><dd>{when(state?.last_verified_at)}</dd></div>
      <div><dt>Recovery key ID</dt><dd><code>{state?.key_id ?? 'Not configured'}</code></dd></div>
    </dl>
    {state?.inspection_required && <p className="ws-notice">The backup configuration or inventory needs inspection before new work.</p>}
    {recoveryRequired && <p className="ws-notice">Resolve the existing host operation or update before creating a new backup. A retained copy can still be verified once active work ends.</p>}
    {(canCreate || canVerify) && <label className="ws-checkbox"><input type="checkbox" checked={approval}
      disabled={busy || pending || !state?.configured || !configuration || !!state?.inspection_required}
      onChange={event => setApproval(event.target.checked)} />I approve encrypted backup transfers using this host’s configured storage and limits.</label>}
    {!!state?.items?.length ? <div className="ws-table-wrap"><table className="ws-table">
      <thead><tr><th>Memory snapshot</th><th>Version</th><th>Size</th><th>Last readback</th><th>Action</th></tr></thead>
      <tbody>{state.items.map(item => <tr key={item.backup_id}>
        <td>{when(item.snapshot_at)}</td><td>{item.service_version ?? 'Not recorded'}</td>
        <td>{size(item.bytes)}</td><td>{when(item.last_verified_at)}</td>
        <td>{canVerify && <button className="ws-link" disabled={unavailable}
          onClick={() => void request('backup.verify', item.backup_id)}>Verify stored copy</button>}
          <details><summary>Recovery details</summary><p>Backup ID: <code>{item.backup_id}</code></p>
            <p>Key ID: <code>{item.key_id}</code> · Access/deletion ledger: {when(item.ledger_at)}</p>
            <pre className="ws-code">{JSON.stringify(item.files, null, 2)}</pre>
          </details></td>
      </tr>)}</tbody>
    </table></div> : <p className="ws-helper">No verified independent backup is recorded.</p>}
    <p className="ws-helper">Creation uploads and reads back the copy; verification downloads it again. Readback verifies delivery, while restore tests are separate. These copies exclude host-control identities and device keys; keep their recovery custody separately.</p>
  </section>
}
