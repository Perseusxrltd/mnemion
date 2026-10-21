import { useEffect, useState } from 'react';
import type { CaptureReport } from '../../../shared/desktop-sources';
import { captureMessages } from '../../../electron/capture-messages';
import CaptureIndexStatus from './CaptureIndexStatus';

const mib = (bytes: number) => (bytes / 1024 ** 2).toLocaleString(undefined, { maximumFractionDigits: 1 });
const stamp = (value: string | null) => value ? new Date(value).toLocaleString() : 'not yet observed';
const age = (value: string, now: number) => {
  const minutes = Math.max(0, Math.floor((now - Date.parse(value)) / 60_000));
  return minutes < 60 ? `${minutes} min` : minutes < 1440 ? `${Math.floor(minutes / 60)} h ${minutes % 60} min` : `${Math.floor(minutes / 1440)} days`;
};
const cleanupReasons = {
  time_budget: 'Disk cleanup reached its time budget and will continue in a later scan.',
  byte_budget: 'Disk cleanup reached its work limit and will continue in a later scan.',
  disk_reserve: 'Disk cleanup is waiting for enough free space to work safely.',
  pending_legacy: 'Disk cleanup is waiting for pending deliveries to settle.',
  sqlite_failure: 'Disk cleanup could not finish. Check available storage before the next scan.',
};

export default function CaptureStatus({ report }: { report?: CaptureReport }) {
  const [now, setNow] = useState(Date.now);
  const observed = !!report?.coverage;
  useEffect(() => {
    if (!observed) return;
    const refresh = () => { if (!document.hidden) setNow(Date.now()); };
    const timer = window.setInterval(refresh, 60_000);
    document.addEventListener('visibilitychange', refresh);
    return () => { window.clearInterval(timer); document.removeEventListener('visibilitychange', refresh); };
  }, [observed]);
  if (!report) return <p className="ws-helper">Retained capture is selected. Local intake and delivery have not yet been observed.</p>;
  const coverage = report.coverage;
  const history = report.history;
  return <div className="ws-notice" aria-label="Retained capture status">
    <p><strong>{report.pending_events.toLocaleString()} queued</strong> · {report.stored_events.toLocaleString()} acknowledged by the workspace · {report.forgotten_events.toLocaleString()} forgotten</p>
    <p className="ws-helper">Last scan accepted {report.locally_accepted.toLocaleString()} fragments locally and received {report.remote_committed_events.toLocaleString()} delivery acknowledgements.</p>
    <p className="ws-helper">This inbox: {mib(report.pending_bytes)} MiB pending · {mib(report.database_bytes)} MiB encrypted storage. This computer: {mib(report.device_pending_bytes)} / 1,024 MiB pending content.</p>
    {report.unknown_pages > 0 && <p>{report.unknown_pages} delivery {report.unknown_pages === 1 ? 'page awaits' : 'pages await'} reconciliation. Its saved identity is retained after a lost reply.</p>}
    {report.reason_code && <p>{captureMessages[report.reason_code]}</p>}
    {report.over_limit && <p>New intake is paused at the current capacity limit. Accepted evidence remains eligible for delivery and forgetting.</p>}
    <details>
      <summary style={{ cursor: 'pointer' }}>Capture coverage and history</summary>
      {history ? <>
        <p><strong>Local history</strong> · largest counter {Math.max(history.events, history.producer_events, history.fragments, history.denials).toLocaleString()} / {history.event_limit.toLocaleString()} entries</p>
        <progress aria-label="Local history capacity used" max={history.event_limit} value={Math.min(history.event_limit, Math.max(history.events, history.producer_events, history.fragments, history.denials))} />
        <p className="ws-helper">{history.events.toLocaleString()} accepted fragments · {history.producer_events.toLocaleString()} source event identities · {history.fragments.toLocaleString()} saved source fragments · {history.denials.toLocaleString()} deletion records. The entry limit applies separately to each counter.</p>
        <p className="ws-helper">{history.scopes.toLocaleString()} / {history.scope_limit.toLocaleString()} tracked file identities · {history.delivery_pages.toLocaleString()} delivery pages · {mib(history.database_bytes)} / {mib(history.database_limit_bytes)} MiB effective storage limit.</p>
        <p className="ws-helper">Raise history or storage limits in Source settings and key, then scan again to resume. Deleting held memories remains available above the history limit; their deletion protection is retained.</p>
        {history.fence_history_blocked && report.reason_code !== 'capture_fence_capacity' && <p>{captureMessages.capture_fence_capacity}</p>}
      </> : <p className="ws-helper">History usage and capacity are unknown until this source records a new scan.</p>}
      {report.storage && <>
        <p className="ws-helper">Disk cleanup released {mib(report.storage.reclaimed_bytes)} MiB during this scan. {mib(report.storage.reclaimable_bytes)} MiB of unused database pages remain available for reuse or later cleanup.</p>
        {report.storage.reason && <p>{cleanupReasons[report.storage.reason]}</p>}
      </>}
      <CaptureIndexStatus progress={coverage?.index} />
    {coverage ? <>
      {coverage.catalog === 'unobserved' ? <p className="ws-helper">Prefix coverage has not yet been observed.</p> : <>
      <p><strong>Observed file prefixes</strong> · {coverage.records.selected.toLocaleString()} selected lines · {coverage.records.omitted.toLocaleString()} omitted by selection or deduplication · {coverage.records.unsupported.toLocaleString()} unsupported by the selected reader</p>
      <p className="ws-helper">{mib(coverage.examined_prefix_bytes)} MiB examined in the last accepted prefixes; {mib(coverage.unaccepted_observed_bytes)} MiB of observed source bytes still unaccepted. {coverage.capture_mode === 'complete' ? 'Detailed capture retains complete source lines. A retained line can still contain an unsupported record format.' : 'Message capture retains selected text. A selected line may contain multiple messages and fields that were omitted.'}</p>
      <p className="ws-helper">Last complete set of available prefixes: {stamp(coverage.complete_prefix_at)}. Source catalog: {coverage.catalog}. {coverage.checking_scopes} files awaiting verification; {coverage.failed_scopes} failed; {coverage.missing_scopes} missing.</p>
      </>}
      {(coverage.unknown_prefix_scopes > 0 || coverage.uncertain_scopes > 0 || coverage.uncertain_intervals > 0) && <p>Files with unknown prefix coverage: {coverage.unknown_prefix_scopes}; files with uncertain history: {coverage.uncertain_scopes}; unavailable or interrupted observation periods: {coverage.uncertain_intervals}. {mib(coverage.unresolved_previous_bytes)} MiB from earlier observed generations remain unresolved. A later scan cannot prove what disappeared between observations.</p>}
      <p className="ws-helper">Last confirmed workspace contact: {coverage.last_contact_at ? `${age(coverage.last_contact_at, now)} ago (${stamp(coverage.last_contact_at)})` : 'not yet observed'}. Last delivery acknowledgement: {stamp(coverage.last_acknowledged_at)}.</p>
      {report.pending_events > 0 && <p className="ws-helper">Queue continuously non-empty since {coverage.queue_nonempty_since ? `${stamp(coverage.queue_nonempty_since)} (${age(coverage.queue_nonempty_since, now)})` : 'an unknown time'}. This is queue age; individual fragments may be newer.</p>}
      <p className="ws-helper">Tracking began {stamp(coverage.tracked_from)}. History before tracking and records never exposed by the producer are unknown.</p>
    </> : <p className="ws-helper">Prefix coverage, selection counts and queue age are unknown until this source records a new scan.</p>}
    </details>
    <p className="ws-helper">These are the last saved observations. Pending evidence has no automatic expiry.</p>
  </div>;
}
