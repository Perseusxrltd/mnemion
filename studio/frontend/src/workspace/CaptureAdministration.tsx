import { useEffect, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import type { Connector, MnemionClient } from '@mnemion/client';
import type { CapturePolicy } from '../../../shared/desktop-sources';

type Source = {
  source_id: string; name: string; namespace: string; version: number; policy_version: number;
  capture_mode: 'messages' | 'complete'; capture_policy: CapturePolicy | null; revoked_at: string | null;
};
type Device = { grant_id: string; device_key_id: string; device_name: string; policy_version: number; created_at: string; active: boolean };
type Review = { source: Source; review_token: string; unrevoked_grants: number; active_grants: number; devices: Device[]; next_cursor: string | null };
type PolicyVersion = Pick<Source, 'policy_version' | 'capture_mode' | 'capture_policy'> & { created_at: string; previous_grants: 'retain' | 'revoke' | null; affected_grants: number | null };
type Change = { expected_version: number; review_token: string; capture_policy: CapturePolicy; previous_grants: 'retain' | 'revoke'; confirm: true };
const failure = (error: unknown) => error instanceof Error ? error.message : 'The operation was not confirmed. Refresh its status before making another change.';
const policyFor = (source: Source): CapturePolicy => source.capture_policy ?? {
  format: 'mnemion-capture-policy-v1', preset: source.capture_mode === 'messages' ? 'conversation' : 'detailed',
  capture_mode: source.capture_mode, include: ['*.jsonl'], exclude: [], retention: 'until_deleted',
  max_file_bytes: 1_000_000_000, max_record_bytes: 2_000_000,
};

export default function CaptureAdministration({ client, connection, endpoint }: {
  client: MnemionClient; connection: Connector; endpoint: string;
}) {
  const [after, setAfter] = useState<string>(), [selected, setSelected] = useState('');
  const capability = useQuery({ queryKey: ['capture-policy-capability', endpoint],
    queryFn: () => client.request<{ capture_policy_versions?: string }>('GET', '/health/live'), retry: false });
  const supported = capability.data?.capture_policy_versions === 'v1';
  const sources = useQuery({ queryKey: ['capture-admin-sources', endpoint, connection.id, after], enabled: supported,
    queryFn: () => client.request<{ items: Source[]; next_cursor: string | null }>('GET',
      `/v1/connectors/${connection.id}/capture-sources?limit=100${after ? `&after=${after}` : ''}`) });
  if (!supported && !capability.error) return capability.isPending ? null : <p className="ws-helper">Update this workspace server to manage retained capture policies and device authorizations here.</p>;
  const source = sources.data?.items.find(item => item.source_id === selected) ?? sources.data?.items[0];
  return <section className="ws-card" data-capture-administration="ready">
    <div className="ws-section-title"><h2>Retained conversation capture</h2><button className="ws-button" onClick={() => void sources.refetch()}>Refresh sources</button></div>
    <p>Manage this workspace’s capture permissions from any connected computer. Each device authorization retains the policy it was approved to use.</p>
    {(capability.error || sources.error) && <p className="ws-notice ws-error" role="alert">{failure(capability.error || sources.error)}</p>}
    {!sources.isPending && !source && <p className="ws-helper">No retained source is configured on this connection. Choose a conversation folder in Studio, or use the headless capture guide to enroll an agent.</p>}
    {source && <>
      <label className="ws-field"><span>Retained source</span><select data-update-safe value={source.source_id} onChange={event => setSelected(event.target.value)}>
        {sources.data?.items.map(item => <option key={item.source_id} value={item.source_id}>{item.name} · {item.namespace}{item.revoked_at ? ' · retired' : ''}</option>)}
      </select></label>
      <SourcePolicy key={source.source_id} source={source} client={client} connection={connection} endpoint={endpoint} />
    </>}
    <div className="ws-actions">
      {sources.data?.next_cursor && <button className="ws-button" onClick={() => { setAfter(sources.data!.next_cursor!); setSelected(''); }}>Next sources</button>}
      {after && <button className="ws-button" onClick={() => { setAfter(undefined); setSelected(''); }}>First sources</button>}
    </div>
  </section>;
}

function SourcePolicy({ source, client, connection, endpoint }: {
  source: Source; client: MnemionClient; connection: Connector; endpoint: string;
}) {
  const cache = useQueryClient(), route = `/v1/connectors/${connection.id}/capture-sources/${source.source_id}`;
  const [deviceAfter, setDeviceAfter] = useState<string>(), [policyAfter, setPolicyAfter] = useState(0);
  const [policy, setPolicy] = useState(() => policyFor(source));
  const [include, setInclude] = useState(policy.include.join('\n')), [exclude, setExclude] = useState(policy.exclude.join('\n'));
  const [treatment, setTreatment] = useState<'retain' | 'revoke'>('retain');
  const [dirty, setDirty] = useState(false), [busy, setBusy] = useState(false), [confirmed, setConfirmed] = useState(false);
  const [error, setError] = useState<string>(), [notice, setNotice] = useState<string>(), [retiring, setRetiring] = useState<string>();
  const [candidate, setCandidate] = useState<{ id: string; review: Review; command: Change }>();
  const reviewKey = ['capture-policy-review', endpoint, source.source_id];
  const review = useQuery({ queryKey: [...reviewKey, deviceAfter],
    queryFn: () => client.request<Review>('GET', route + `/policy-review?limit=100${deviceAfter ? `&after=${deviceAfter}` : ''}`) });
  const historyKey = ['capture-policy-history', endpoint, source.source_id];
  const history = useQuery({ queryKey: [...historyKey, policyAfter],
    queryFn: () => client.request<{ items: PolicyVersion[]; next_cursor: number | null }>('GET', route + `/policies?limit=100&after=${policyAfter}`) });
  const current = review.data?.source ?? source;
  useEffect(() => {
    if (!dirty) {
      const selected = policyFor(current);
      setPolicy(selected); setInclude(selected.include.join('\n')); setExclude(selected.exclude.join('\n'));
    }
  }, [current.version, dirty]);
  function editing() { setDirty(true); setCandidate(undefined); setConfirmed(false); setNotice(undefined); }
  async function act(work: () => Promise<void>) {
    setBusy(true); setError(undefined);
    try { await work(); } catch (error) { setError(failure(error)); } finally { setBusy(false); }
  }
  async function refresh() {
    await Promise.all([cache.invalidateQueries({ queryKey: reviewKey }), cache.invalidateQueries({ queryKey: historyKey }),
      cache.invalidateQueries({ queryKey: ['capture-admin-sources', endpoint, connection.id] })]);
  }
  return <div data-capture-policy-source={source.source_id} data-update-pending={busy || dirty || retiring ? '' : undefined}>
    <p><strong>{current.revoked_at ? 'Source retired' : `Policy ${current.policy_version} for new device authorizations`}</strong> · {current.capture_policy?.preset ?? current.capture_mode}</p>
    <p className="ws-helper">The source identity and its accepted memories stay the same when its default changes. Sharing is controlled by the mapped audience above. Revoking a capture authorization does not delete memories.</p>
    {[error, review.error && failure(review.error), history.error && failure(history.error)].filter(Boolean).map((value, index) => <p className="ws-notice ws-error" role="alert" key={index}>{value}</p>)}
    {notice && <p className="ws-notice" role="status">{notice}</p>}
    {review.data && <>
      <div className="ws-section-title"><h3>Device authorizations</h3><button className="ws-button" disabled={busy} onClick={() => void act(refresh)}>Refresh permissions</button></div>
      <p>{review.data.unrevoked_grants.toLocaleString()} unrevoked authorizations · {review.data.active_grants.toLocaleString()} can currently authenticate</p>
      <div className="ws-table-wrap"><table className="ws-table"><thead><tr><th>Device key</th><th>Approved policy</th><th>Access</th><th>Action</th></tr></thead>
        <tbody>{review.data.devices.map(device => <tr key={device.grant_id}>
          <td>{device.device_name}<small className="ws-helper" title={device.grant_id}>Authorization {device.grant_id.slice(0, 8)}</small></td>
          <td>Policy {device.policy_version}{device.policy_version !== current.policy_version ? ' · earlier approval' : ''}</td>
          <td>{device.active ? 'Active' : 'Key or source unavailable'}</td>
          <td><button className="ws-link" disabled={busy || !!current.revoked_at} onClick={() => setRetiring(device.grant_id)}>Revoke</button></td>
        </tr>)}</tbody></table></div>
      {!review.data.devices.length && <p className="ws-helper">No unrevoked authorizations on this page.</p>}
      <div className="ws-actions">
        {review.data.next_cursor && <button className="ws-button" disabled={busy} onClick={() => setDeviceAfter(review.data!.next_cursor!)}>Next authorizations</button>}
        {deviceAfter && <button className="ws-button" disabled={busy} onClick={() => setDeviceAfter(undefined)}>First authorizations</button>}
      </div>
    </>}
    {retiring && <div className="ws-notice">
      <p>Revoke authorization <code>{retiring}</code>? Its server deliveries will stop. Offline evidence stays on its device; recovering it requires a newly approved authorization.</p>
      <div className="ws-actions"><button className="ws-button" disabled={busy} onClick={() => void act(async () => {
        await client.request('DELETE', `/v1/capture-grants/${retiring}`);
        setRetiring(undefined); setCandidate(undefined); setConfirmed(false); await refresh();
        setNotice('Device authorization revoked. Existing server memories are retained.');
      })}>Confirm revocation</button><button className="ws-button" disabled={busy} onClick={() => setRetiring(undefined)}>Cancel</button></div>
    </div>}
    {!current.revoked_at && !connection.disabled_at && <details className="ws-details">
      <summary>Change the policy for new device authorizations</summary>
      <form className="ws-form" onSubmit={event => { event.preventDefault(); void act(async () => {
        const fresh = await client.request<Review>('GET', route + '/policy-review');
        const selected: CapturePolicy = { ...policy, include: include.split('\n').map(value => value.trim()).filter(Boolean),
          exclude: exclude.split('\n').map(value => value.trim()).filter(Boolean) };
        setCandidate({ id: crypto.randomUUID(), review: fresh, command: { expected_version: fresh.source.version,
          review_token: fresh.review_token, capture_policy: selected, previous_grants: treatment, confirm: true } });
        setConfirmed(false);
      }); }}>
        <p>These rules apply when a new device is authorized. Existing devices keep their own approved capture settings unless you revoke their authorizations below. Their local settings and queued content are not rewritten.</p>
        <label className="ws-field"><span>Capture preset</span><select data-update-safe disabled={busy} value={policy.preset} onChange={event => {
          const preset = event.target.value as CapturePolicy['preset']; editing();
          setPolicy({ ...policy, preset, capture_mode: preset === 'conversation' ? 'messages' : preset === 'detailed' ? 'complete' : policy.capture_mode });
        }}><option value="conversation">User and assistant messages</option><option value="detailed">All available exported event fields</option><option value="selected">Custom selection</option></select></label>
        {policy.preset === 'selected' && <label className="ws-field"><span>Content</span><select data-update-safe disabled={busy} value={policy.capture_mode} onChange={event => { editing(); setPolicy({ ...policy, capture_mode: event.target.value as CapturePolicy['capture_mode'] }); }}><option value="messages">User and assistant messages</option><option value="complete">Available exported event fields</option></select></label>}
        <label className="ws-field"><span>Included session paths, one pattern per line</span><textarea data-update-safe disabled={busy} required maxLength={32768} value={include} onChange={event => { editing(); setInclude(event.target.value); }} /></label>
        <label className="ws-field"><span>Excluded session paths, one pattern per line</span><textarea data-update-safe disabled={busy} maxLength={32768} value={exclude} onChange={event => { editing(); setExclude(event.target.value); }} /></label>
        <details className="ws-details"><summary>Read limits</summary>
          <label className="ws-field"><span>Maximum file size (MB)</span><input type="number" data-update-safe disabled={busy} min={0.001} max={1000000} step={0.001} value={policy.max_file_bytes / 1_000_000} onChange={event => { editing(); setPolicy({ ...policy, max_file_bytes: Math.round(Number(event.target.value) * 1_000_000) }); }} /></label>
          <label className="ws-field"><span>Maximum event record (KB)</span><input type="number" data-update-safe disabled={busy} min={0.001} max={16000} step={0.001} value={policy.max_record_bytes / 1000} onChange={event => { editing(); setPolicy({ ...policy, max_record_bytes: Math.round(Number(event.target.value) * 1000) }); }} /></label>
        </details>
        <p className="ws-helper">Accepted memories remain until explicitly deleted. Default private-file exclusions remain in force. This page does not read producer files; each new device still previews and approves its selected folder. Hidden model reasoning and attachment binaries are not available through this capture policy.</p>
        <label className="ws-field"><span>Existing device authorizations</span><select data-update-safe disabled={busy} value={treatment} onChange={event => { editing(); setTreatment(event.target.value as typeof treatment); }}>
          <option value="retain">Keep their previously approved policies</option><option value="revoke">Revoke every existing authorization</option>
        </select></label>
        <button className="ws-button" disabled={busy || !dirty}>Review policy change</button>
      </form>
      {candidate && <div className="ws-notice" data-capture-policy-review="ready">
        <p>Change the default from policy {candidate.review.source.policy_version} ({candidate.review.source.capture_mode}) to <strong>{candidate.command.capture_policy.capture_mode === 'messages' ? 'user and assistant messages' : 'all available exported event fields'}</strong>.</p>
        <p>{candidate.command.previous_grants === 'retain'
          ? `Keep all ${candidate.review.unrevoked_grants} existing authorizations on their approved policies, including their permission to collect new content.`
          : `Revoke all ${candidate.review.unrevoked_grants} existing authorizations. Pending deliveries from those grants will be refused until an administrator approves recovery.`}</p>
        <p>Captured memories, deletion records, the source identity and its mapped audience are retained.</p>
        <label className="ws-checkbox"><input type="checkbox" data-update-safe disabled={busy} checked={confirmed} onChange={event => setConfirmed(event.target.checked)} />I approve these rules and this treatment of existing authorizations.</label>
        <div className="ws-actions"><button className="ws-button ws-primary" disabled={busy || !confirmed} onClick={() => void act(async () => {
          const result = await client.request<{ source: Source; transition: PolicyVersion }>('PUT', route + `/policy-transitions/${candidate.id}`, { body: candidate.command });
          setCandidate(undefined); setConfirmed(false); setDirty(false); setPolicy(policyFor(result.source));
          await refresh(); setNotice(`Policy ${result.transition.policy_version} approved. Existing authorizations were ${result.transition.previous_grants === 'revoke' ? 'revoked' : 'retained on their original policies'}.`);
        })}>Approve policy change</button><button className="ws-button" disabled={busy} onClick={() => { setCandidate(undefined); setConfirmed(false); }}>Cancel review</button></div>
      </div>}
    </details>}
    <details className="ws-details"><summary>Approved policy history</summary>
      {history.data?.items.map(item => <details className="ws-details" key={item.policy_version}>
        <summary>Policy {item.policy_version} · {item.capture_policy?.preset ?? item.capture_mode}{item.policy_version === current.policy_version ? ' · current default' : ''}</summary>
        <p>Approved {new Date(item.created_at).toLocaleString()}{item.previous_grants ? ` · ${item.affected_grants} earlier authorizations ${item.previous_grants === 'retain' ? 'retained' : 'revoked'}` : ' · original approval'}.</p>
        {item.capture_policy ? <><p>Include: {item.capture_policy.include.join(', ')}</p><p>Exclude: {item.capture_policy.exclude.join(', ') || 'Default exclusions only'}</p><p>File limit {item.capture_policy.max_file_bytes.toLocaleString()} bytes · record limit {item.capture_policy.max_record_bytes.toLocaleString()} bytes</p></> : <p>The original mode-only approval is preserved. No later selection rules are assumed.</p>}
      </details>)}
      <div className="ws-actions">{history.data?.next_cursor && <button className="ws-button" disabled={busy} onClick={() => setPolicyAfter(history.data!.next_cursor!)}>Next policies</button>}{policyAfter > 0 && <button className="ws-button" disabled={busy} onClick={() => setPolicyAfter(0)}>First policies</button>}</div>
    </details>
  </div>;
}
