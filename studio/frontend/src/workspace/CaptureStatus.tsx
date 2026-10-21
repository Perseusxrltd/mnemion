import type { CaptureReport } from '../../../shared/desktop-sources';
import { captureMessages } from '../../../electron/capture-messages';

const mib = (bytes: number) => (bytes / 1024 ** 2).toLocaleString(undefined, { maximumFractionDigits: 1 });

export default function CaptureStatus({ report }: { report?: CaptureReport }) {
  if (!report) return <p className="ws-helper">Retained capture is selected. Local intake and delivery have not yet been observed.</p>;
  return <div className="ws-notice" aria-label="Retained capture status">
    <p><strong>{report.pending_events.toLocaleString()} queued</strong> · {report.stored_events.toLocaleString()} acknowledged by the workspace · {report.forgotten_events.toLocaleString()} forgotten</p>
    <p className="ws-helper">Last scan accepted {report.locally_accepted.toLocaleString()} events locally and received {report.remote_committed_events.toLocaleString()} delivery acknowledgements. Indexing and librarian work happen afterward.</p>
    <p className="ws-helper">This inbox: {mib(report.pending_bytes)} MiB pending · {mib(report.database_bytes)} MiB encrypted storage. This computer: {mib(report.device_pending_bytes)} / 1,024 MiB pending content.</p>
    {report.unknown_pages > 0 && <p>{report.unknown_pages} delivery {report.unknown_pages === 1 ? 'page awaits' : 'pages await'} reconciliation. Its saved identity is retained after a lost reply.</p>}
    {report.reason_code && <p>{captureMessages[report.reason_code]}</p>}
    {report.over_limit && <p>New intake is paused at the current capacity limit. Accepted evidence remains eligible for delivery and forgetting.</p>}
    <p className="ws-helper">These are the last saved observations. Pending evidence has no automatic expiry.</p>
  </div>;
}
