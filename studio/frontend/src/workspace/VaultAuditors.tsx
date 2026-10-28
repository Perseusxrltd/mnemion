import { useEffect, useId, useRef, useState, type FormEvent } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import type { ApiKey, MnemionClient, VaultAuditor } from '@mnemion/client';

const uuid = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i;

export default function VaultAuditors({ client, scope, keys, mcpEnabled }: {
  client: MnemionClient; scope: string[]; keys: ApiKey[]; mcpEnabled: boolean;
}) {
  const cache = useQueryClient(), suggestions = useId(), live = useRef(true);
  const [offset, setOffset] = useState(0), [key, setKey] = useState(''), [hours, setHours] = useState('168');
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [notice, setNotice] = useState('');
  const page = useQuery({ queryKey: [...scope, 'auditors', offset], queryFn: () => client.vaultAuditors(offset), gcTime: 0, retry: false });
  const selected = useQuery({ queryKey: [...scope, 'auditor-key', key], queryFn: () => client.vaultAuditors(0, 1, key), enabled: uuid.test(key), gcTime: 0, retry: false });
  useEffect(() => { live.current = true; return () => { live.current = false; }; }, []);
  async function change(keyId: string, expected: number, enabled: boolean) {
    setBusy(true); setError(''); setNotice('');
    try {
      await client.setVaultAuditor(keyId, { expected_version: expected, enabled,
        expires_at: enabled && hours !== '0' ? new Date(Date.now() + Number(hours) * 3600000).toISOString() : null });
      if (live.current) setNotice(enabled ? 'Metadata access granted to this key. Secret-value permissions are unchanged.' : 'Metadata auditor access revoked. Any separate credential grants remain in place.');
    } catch (error) { if (live.current) setError(error instanceof Error ? error.message : 'Auditor access could not be updated.'); }
    finally { await cache.invalidateQueries({ queryKey: scope }); if (live.current) setBusy(false); }
  }
  function grant(event: FormEvent) {
    event.preventDefault();
    if (selected.data && !selected.isError && !selected.isFetching && uuid.test(key)) void change(key, selected.data.items[0]?.version ?? 0, true);
  }
  function choose(item: VaultAuditor) { setKey(item.key_id); setNotice(''); setError(''); }
  return <section className="ws-vault-panel" data-update-pending={busy || key ? '' : undefined}>
    <h2>Metadata auditors</h2>
    <p>Grant a specific agent key access to all credential names, IDs, versions and the vault access log in this workspace. This role cannot read, replace, export or delete secret values, or change anyone’s permissions.</p>
    {!mcpEnabled && <p className="ws-notice">App and API access is available. The host operator must enable vault metadata in Setup before agents can use these permissions through MCP.</p>}
    <p className="ws-helper">An additional key belonging to the same agent needs its own grant. Disabling a key or its owner immediately disables its auditor access.</p>
    {[error, page.error?.message, selected.error?.message].filter(Boolean).map((text, index) => <p key={index} className="ws-notice ws-error" role="alert">{text}</p>)}
    {notice && <p className="ws-notice" role="status">{notice}</p>}
    <form onSubmit={grant}><fieldset disabled={busy} className="ws-setup-fields">
      <label className="ws-field"><span>Agent key ID</span><input list={suggestions} value={key} onChange={event => setKey(event.target.value.trim())} maxLength={36} required autoComplete="off" spellCheck={false} placeholder="Choose or paste the key’s UUID" /></label>
      <datalist id={suggestions}>{keys.filter(item => !item.revoked_at && (!item.expires_at || Date.parse(item.expires_at) > Date.now())).map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</datalist>
      <label className="ws-field"><span>Access expires</span><select value={hours} onChange={event => setHours(event.target.value)}><option value="1">In 1 hour</option><option value="24">In 1 day</option><option value="168">In 7 days</option><option value="720">In 30 days</option><option value="0">When revoked</option></select></label>
      <div className="ws-setup-actions"><button className="ws-button ws-primary" disabled={!uuid.test(key) || !selected.data || selected.isError || selected.isFetching}>Grant metadata access</button><button type="button" className="ws-button ws-quiet" onClick={() => setKey('')}>Clear</button></div>
    </fieldset></form>
    <div className="ws-vault-table"><table><thead><tr><th>Key</th><th>Status</th><th>Expiry</th><th>Access</th></tr></thead><tbody>{!page.isError && page.data?.items.map(item => <tr key={item.key_id}><td>{item.name}<small>{item.key_id}</small></td><td>{item.active ? 'Active' : item.enabled ? 'Expired or key unavailable' : 'Revoked'}</td><td>{item.expires_at ? new Date(item.expires_at).toLocaleString() : 'When revoked'}</td><td><button className="ws-button ws-quiet" disabled={busy} onClick={() => choose(item)}>Change</button><button className="ws-button ws-quiet" disabled={busy || !item.enabled} onClick={() => void change(item.key_id, item.version, false)}>Revoke</button></td></tr>)}</tbody></table></div>
    {!page.isPending && !page.isError && !page.data?.items.length && <p>No auditor grants on this page.</p>}
    <div className="ws-setup-actions"><button className="ws-button ws-quiet" disabled={busy || !offset} onClick={() => setOffset(Math.max(0, offset - 100))}>Previous</button><button className="ws-button ws-quiet" disabled={busy || page.isError || page.data?.next_offset == null} onClick={() => setOffset(page.data!.next_offset!)}>Next</button></div>
  </section>;
}
