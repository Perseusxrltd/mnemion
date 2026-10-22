import { useQuery } from '@tanstack/react-query';
import type { MnemionClient } from '@mnemion/client';

type Status = {
  observed_at: string; families: number; pending_families: number; due_families: number;
  expired_families: number; failed_families: number; purges_pending: number;
  next_deadline: string | null; last_cleanup_at: string | null; error_code: string | null;
};

export default function CaptureRetentionStatus({ client, route, endpoint }: {
  client: MnemionClient; route: string; endpoint: string;
}) {
  const query = useQuery({ queryKey: ['capture-retention', endpoint, route],
    queryFn: () => client.request<Status>('GET', route + '/retention'), refetchInterval: 30000 });
  const status = query.data;
  return <section data-capture-retention-status={status ? 'ready' : 'loading'}>
    <div className="ws-section-title"><h3>Retention cleanup</h3><button className="ws-button" disabled={query.isFetching} onClick={() => void query.refetch()}>Refresh cleanup</button></div>
    {query.error && <p className="ws-notice ws-error" role="alert">Cleanup status could not be refreshed. Any figures below are the last successful observation.</p>}
    {status && <>
      <p><strong>{status.pending_families.toLocaleString()}</strong> scheduled families · <strong>{status.due_families.toLocaleString()}</strong> due for cleanup · <strong>{status.expired_families.toLocaleString()}</strong> removed from active memory</p>
      <p>{status.purges_pending.toLocaleString()} memory records awaiting content purging · {status.failed_families.toLocaleString()} families waiting after a cleanup error</p>
      {status.error_code && <p className="ws-notice">{status.error_code === 'space_paused' ? 'Cleanup is waiting for the workspace migration or recovery pause to end.' : `Cleanup will retry automatically (${status.error_code}).`}</p>}
      <p className="ws-helper">{status.next_deadline ? `Earliest outstanding deadline: ${new Date(status.next_deadline).toLocaleString()}. ` : 'No outstanding expiry deadline. '}
        {status.last_cleanup_at && `Last completed family: ${new Date(status.last_cleanup_at).toLocaleString()}. `}Observed {new Date(status.observed_at).toLocaleString()}.</p>
      <p className="ws-helper">Cleanup runs on the workspace server without a model or device connection. Due memories may remain readable until cleanup finishes. Original files, offline inboxes and backups are outside this cleanup.</p>
    </>}
  </section>;
}
