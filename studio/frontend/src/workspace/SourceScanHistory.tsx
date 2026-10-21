import type { SourceActivity } from '../../../shared/desktop-sources';

/** Scan observations are not a guarantee of complete source-history capture. */
export default function SourceScanHistory({ activity, onRepair, busy }: {
  activity: SourceActivity; onRepair?: () => void; busy?: boolean;
}) {
  const when = (value: string) => new Date(value).toLocaleString();
  return <div className="ws-helper">
    <p>{activity.last_success_report ? `Last successful scan: ${when(activity.last_success_report.timestamp)}.` : 'No successful scan is recorded for these settings.'}</p>
    {activity.last_failure && <p>Last failed or interrupted attempt observed: {when(activity.last_failure.observed_at)}.</p>}
    {activity.reason_code === 'interrupted' && activity.started_at && <p>Unfinished attempt began {when(activity.started_at)}; its outcome is unknown.</p>}
    {activity.durability === 'unavailable' && <p role="status">The latest scan status has not been confirmed as saved for restart.</p>}
    {activity.reason_code === 'source_status_invalid' && activity.repair_token && onRepair && <details className="ws-details">
      <summary>Repair saved scan history</summary>
      <p>This preserves the damaged diagnostic file and resets scan history for <strong>every source on this computer</strong> to unknown. Source settings, credentials, memories and capture progress are retained. It does not start a scan; normal automatic checks resume at their next interval.</p>
      <button type="button" className="ws-button" disabled={busy} onClick={onRepair}>Confirm repair of device scan history</button>
    </details>}
  </div>;
}
