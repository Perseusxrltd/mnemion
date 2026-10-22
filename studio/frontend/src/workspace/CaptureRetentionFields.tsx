export function CaptureRetentionExplanation({ days }: { days?: number }) {
  return <p className="ws-helper">{days
    ? `Schedule removal ${days} days after this fragment is first accepted by the server under an expiry policy. Cleanup covers every retained revision and projection of the same fragment, including earlier copies and adjacent messages. An existing earlier deadline cannot be extended. Due fragments refuse new capture; existing memories may remain readable until the worker completes cleanup.`
    : 'Accepted memories remain until explicitly deleted, unless an earlier approved family deadline already applies.'}
    {' '}Original files, offline pending content and backups keep their own retention. Restoring a workspace preserves approved deadlines and deletion decisions.</p>;
}

export default function CaptureRetentionFields({ expiring, days, disabled, supported = true, onChange }: {
  expiring: boolean; days: number; disabled?: boolean; supported?: boolean;
  onChange: (expiring: boolean, days: number) => void;
}) {
  return <div data-capture-retention-policy>
    <label className="ws-field"><span>Server retention</span><select data-update-safe disabled={disabled} value={expiring ? 'expire_after' : 'until_deleted'} onChange={event => onChange(event.target.value === 'expire_after', days)}>
      <option value="until_deleted">Keep until deleted</option>
      <option value="expire_after" disabled={!supported}>Schedule expiry</option>
    </select></label>
    {expiring && <label className="ws-field"><span>Days after first server acceptance</span><input data-update-safe type="number" min={1} max={3650} step={1} required disabled={disabled} value={days} onChange={event => onChange(true, Number(event.target.value))} /></label>}
    {!supported && <p className="ws-helper">Update the workspace server to use scheduled capture expiry.</p>}
    <CaptureRetentionExplanation days={expiring ? days : undefined} />
  </div>;
}
