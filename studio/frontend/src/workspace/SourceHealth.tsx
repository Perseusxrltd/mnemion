import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { RefreshCw } from 'lucide-react';
import { type Connector, type MnemionClient, type SourceDiagnostic } from '@mnemion/client';

const recovery: Record<SourceDiagnostic['recovery'], string> = {
  restore_connector_identity: 'A tenant administrator must restore an active, dedicated connector identity.',
  enable_connector: 'A tenant administrator must enable this connector before it can check access.',
  resume_source: 'Intentionally paused. A tenant administrator can resume it when appropriate; source permissions must then be rechecked.',
  request_source_sync: 'Request a new scan from the source runner to recheck current permissions. The runner must be online.',
  repair_source_files: 'Review unreadable files in source controls, repair them at the source, then request another scan.',
};
const reasonNames: Record<string, string> = {
  connector_disabled: 'Connector disabled',
  connector_identity_disabled: 'Connector identity disabled',
  connector_identity_not_dedicated: 'Connector identity has organization privileges',
  operator_paused: 'Paused by an administrator',
  permissions_expired: 'Access check expired',
  source_access_lost: 'Source access lost',
  provider_unavailable: 'Source provider unavailable',
  permissions_recheck_required: 'Permissions need rechecking',
  inventory_incomplete: 'Some files could not be read',
};

export function SourceHealthPanel({ client, sessionIdentity, connectors, select }: {
  client: MnemionClient; sessionIdentity: string; connectors: Connector[]; select: (id: string) => void;
}) {
  const [after, setAfter] = useState<string>();
  const query = useQuery({
    queryKey: ['source-health', sessionIdentity, after],
    queryFn: ({ signal }) => client.sourceHealth({ details: true, after, limit: 20, signal }),
    gcTime: 0,
  });
  const details = query.isError ? undefined : query.data?.diagnostics;
  return <section className="ws-card" aria-label="Source availability">
    <div className="ws-section-title"><h2>Source availability</h2>
      <button type="button" className="ws-button" disabled={query.isFetching} onClick={() => void query.refetch()}><RefreshCw size={14} />Refresh</button>
    </div>
    {query.isError ? <p role="status">Source status could not be loaded. Refresh to check your current access.</p>
      : query.isPending ? <p className="ws-helper">Checking current source access…</p>
      : <>
        <p className="ws-helper">Your assigned sources: {query.data.unavailable_scopes} unavailable · {query.data.incomplete_scopes} with unreadable files.</p>
        {!details ? <p className="ws-helper">This server provides summary status. Update it to see affected sources and recovery steps here.</p>
          : details.visibility === 'unavailable' ? <p className="ws-notice">Source controls require a tenant administrator or the source's dedicated connector operator. A space administrator can manage access to that space. Ask a tenant administrator to open Source availability for the affected source and its recovery steps.</p>
          : <>
            <p className="ws-helper">{details.visibility === 'tenant' ? 'Showing source issues across this organization.' : 'Showing source issues controlled by your connector identity.'} Paused sources remain paused until an administrator explicitly resumes them.</p>
            {details.items.length ? <div className="ws-table-wrap"><table className="ws-table">
              <thead><tr><th>Source</th><th>Current status</th><th>Recovery</th></tr></thead>
              <tbody>{details.items.map(item => <tr key={item.space_id}>
                <td>{connectors.find(connector => connector.id === item.connector_id)?.name ?? item.provider}
                  <small className="ws-helper">Space <code>{item.space_id}</code></small>
                  <small className="ws-helper">Operator <code>{item.operator_id}</code></small>
                </td>
                <td>{item.reasons.map(reason => <div key={reason}>{reasonNames[reason] ?? 'Source needs attention'}</div>)}
                  {!!item.skipped_documents && <small className="ws-helper">{item.skipped_documents} unreadable files</small>}
                </td>
                <td><p>{recovery[item.recovery] ?? 'Open source controls to review current access.'}</p>
                  {connectors.some(connector => connector.id === item.connector_id) && <button type="button" className="ws-link" onClick={() => select(item.connector_id)}>Open source controls</button>}
                </td>
              </tr>)}</tbody>
            </table></div> : <p>No issues in the sources you can control.</p>}
            <div className="ws-actions">
              {after && <button type="button" className="ws-button" disabled={query.isFetching} onClick={() => setAfter(undefined)}>First page</button>}
              {details.next_cursor && <button type="button" className="ws-button" disabled={query.isFetching} onClick={() => setAfter(details.next_cursor!)}>More sources</button>}
            </div>
          </>}
      </>}
  </section>;
}
