import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Copy, Download, Eye, EyeOff, KeyRound, LoaderCircle, Plus, RefreshCw, ShieldCheck, Trash2, Upload } from 'lucide-react';
import { supportsKeePass, type VaultEntry, type VaultEnvelope } from '@mnemion/client';
import type { Connection } from './connection-types';
import { downloadVault, newVaultKey } from './vault-utils';
import './vault.css';
import KeepassTransfer from './KeepassTransfer';
import VaultAuditors from './VaultAuditors';

const message = (error: unknown) => error instanceof Error ? error.message : 'The vault request could not be completed.';
const date = (value: string) => new Date(value).toLocaleString();
type Editor = { id: string; name: string; value: string; version: number; rename: boolean };

export default function SecretsVault({ connection }: { connection: Connection }) {
  const identity = useMemo(() => crypto.randomUUID(), [connection.client, connection.me.tenant_id, connection.me.principal_id, connection.me.administrator]);
  return <VaultContents key={identity} connection={connection} identity={identity} />;
}

function VaultContents({ connection, identity }: { connection: Connection; identity: string }) {
  const { client, me } = connection, cache = useQueryClient();
  const scope = ['vault', identity];
  const status = useQuery({ queryKey: [...scope, 'status'], queryFn: () => client.vaultStatus(), retry: false, gcTime: 0 });
  const metadataAvailable = !status.isError && (status.data?.metadata_available ?? status.data?.available);
  const auditAccess = !status.isError && (status.data?.audit_access ?? me.administrator);
  const [offset, setOffset] = useState(0), [auditOffset, setAuditOffset] = useState(0), [tab, setTab] = useState<'credentials' | 'audit' | 'auditors'>('credentials');
  const entries = useQuery({ queryKey: [...scope, 'entries', offset], queryFn: () => client.vaultEntries(offset), enabled: !!metadataAvailable, gcTime: 0, retry: false });
  const [selected, setSelected] = useState(''), [filter, setFilter] = useState(''), [chosen, setChosen] = useState<string[]>([]);
  const selectedEntry = entries.isError ? undefined : entries.data?.items.find(item => item.id === selected);
  const grants = useQuery({ queryKey: [...scope, selected, 'grants'], queryFn: () => client.vaultGrants(selected), enabled: !!metadataAvailable && me.administrator && !!selected, gcTime: 0 });
  const people = useQuery({ queryKey: [...scope, 'people'], queryFn: () => client.principals(), enabled: me.administrator && !!metadataAvailable, gcTime: 0 });
  const keys = useQuery({ queryKey: [...scope, 'keys'], queryFn: () => client.keys(), enabled: me.administrator && !!metadataAvailable, gcTime: 0 });
  const audit = useQuery({ queryKey: [...scope, 'audit', auditOffset], queryFn: () => client.vaultAudit(auditOffset), enabled: !!auditAccess && tab === 'audit', gcTime: 0, retry: false });
  const [revealed, setRevealed] = useState<{ id: string; value: string; version: number } | null>(null);
  const [editor, setEditor] = useState<Editor | null>(null), [showDraft, setShowDraft] = useState(false), [deleting, setDeleting] = useState<VaultEntry | null>(null);
  const [subject, setSubject] = useState(''), [canRead, setCanRead] = useState(false), [canWrite, setCanWrite] = useState(false);
  const [transfer, setTransfer] = useState<'export' | 'import' | null>(null), [transferIds, setTransferIds] = useState<string[]>([]);
  const [transferKey, setTransferKey] = useState(''), [showKey, setShowKey] = useState(false), [keySaved, setKeySaved] = useState(false);
  const [archive, setArchive] = useState<VaultEnvelope | null>(null), [fileName, setFileName] = useState('');
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [notice, setNotice] = useState('');
  const [keepassActive, setKeepassActive] = useState(false);
  const live = useRef(true), generation = useRef(0);
  useEffect(() => { live.current = true; return () => { live.current = false; generation.current++; }; }, []);
  useEffect(() => {
    const hide = () => { generation.current++; setRevealed(null); setShowDraft(false); setShowKey(false); };
    window.addEventListener('blur', hide); document.addEventListener('visibilitychange', hide);
    const timer = revealed ? setTimeout(hide, 60000) : undefined;
    return () => { window.removeEventListener('blur', hide); document.removeEventListener('visibilitychange', hide); clearTimeout(timer); };
  }, [revealed]);
  const pending = busy || !!editor || !!transfer || !!deleting || !!subject || keepassActive;
  async function refresh() { await cache.invalidateQueries({ queryKey: scope }); }
  async function run(action: () => Promise<void>) {
    setBusy(true); setError(''); setNotice('');
    try { await action(); if (live.current) await refresh(); }
    catch (error) { if (live.current) setError(message(error)); }
    finally { if (live.current) setBusy(false); }
  }
  function select(id: string) { generation.current++; setRevealed(null); setSelected(id); setSubject(''); setCanRead(false); setCanWrite(false); setNotice(''); }
  function closeTransfer() { setTransfer(null); setTransferKey(''); setShowKey(false); setKeySaved(false); setArchive(null); setFileName(''); }
  function beginTransfer(mode: 'export' | 'import') { closeTransfer(); setTransfer(mode); setTransferIds([...chosen]); setError(''); setNotice(''); }
  async function copy(value: string) {
    try { await navigator.clipboard.writeText(value); if (live.current) setNotice('Copied to your clipboard.'); }
    catch { if (live.current) setError('Clipboard access was unavailable. Reveal and select the value to copy it manually.'); }
  }
  async function reveal(entry: VaultEntry) {
    const ticket = ++generation.current; setRevealed(null);
    await run(async () => {
      const result = await client.vaultValue(entry.id);
      if (live.current && ticket === generation.current) setRevealed({ id: entry.id, value: result.value, version: result.version });
    });
  }
  async function save(event: FormEvent) {
    event.preventDefault(); if (!editor) return;
    const current = editor;
    await run(async () => {
      const saved = await client.putVaultValue(current.id, { name: current.name, value: current.value, expected_version: current.version });
      if (live.current) { setEditor(null); setShowDraft(false); setRevealed(null); setSelected(saved.id); setNotice('Credential encrypted and saved.'); }
    });
  }
  async function grant(remove = false, existing?: { subject_kind: 'person' | 'key'; subject_id: string }) {
    if (!grants.data || !selectedEntry) return;
    const [kind, id] = subject.split(':');
    await run(async () => {
      await client.grantVault(selectedEntry.id, { expected_access_version: grants.data!.access_version,
        subject_kind: existing?.subject_kind ?? kind as 'person' | 'key', subject_id: existing?.subject_id ?? id,
        read: canRead, write: canWrite, remove });
      if (live.current) { setSubject(''); setCanRead(false); setCanWrite(false); setRevealed(null); setNotice(remove ? 'Credential access revoked.' : 'Credential access saved.'); }
    });
  }
  const unavailable = status.error ? ((status.error as { status?: number }).status === 404
    ? 'Update this workspace server to use the encrypted credentials vault.' : message(status.error))
    : status.data?.error_code === 'vault_disabled' ? 'The host operator has not enabled credential access for this workspace.'
    : status.data?.error_code ? 'The host needs its matching vault encryption key. Existing encrypted credentials are retained.' : '';
  return <div className="ws-page ws-vault" data-update-pending={pending ? '' : undefined}>
    <header className="ws-page-heading"><div><p className="ws-eyebrow">Private credentials</p><h1>Secrets</h1><p>One shared credential vault, with explicit access for each person and agent key.</p></div><KeyRound size={30} /></header>
    <div className="ws-vault-summary"><span><ShieldCheck size={16} />Encrypted at rest</span><span>Excluded from memory search</span><span>Every value read is audited</span><span>MCP {status.data?.mcp_enabled ? 'value tools enabled' : status.data?.mcp_metadata_enabled ? 'metadata only' : 'disabled'}</span></div>
    <div className="ws-setup-actions"><button className="ws-button ws-quiet" disabled={pending} onClick={() => void refresh()}><RefreshCw size={14} />Refresh</button>
      <button className="ws-button ws-quiet" disabled={pending} onClick={() => setTab('credentials')}>Credentials</button>
      {auditAccess && <button className="ws-button ws-quiet" disabled={pending} onClick={() => setTab('audit')}>Access log</button>}
      {me.administrator && metadataAvailable && status.data?.metadata_available !== undefined && <button className="ws-button ws-quiet" disabled={pending} onClick={() => setTab('auditors')}>Metadata auditors</button>}
      <Link className="ws-link" to="/workspace/help?doc=docs%2Fservice%2Fsecrets-vault.md">Vault guide</Link></div>
    {error && <p className="ws-notice ws-error" role="alert">{error}</p>}{notice && <p className="ws-notice" role="status">{notice}</p>}
    {busy && <p className="ws-helper" role="status"><LoaderCircle size={15} className="ws-spin" /> Working…</p>}
    {status.isPending && <p role="status">Checking the vault…</p>}
    {unavailable && tab === 'credentials' && <div className="ws-notice"><p>{unavailable}</p><p>For a workspace hosted on this computer, open <Link to="/workspace/setup">Setup & this device</Link> and choose Encrypted credentials vault. For a remote workspace, its host operator controls the key and exposure settings.</p></div>}
    {tab === 'auditors' && me.administrator && metadataAvailable && <VaultAuditors client={client} scope={scope} keys={keys.data?.items ?? []} mcpEnabled={status.data?.mcp_metadata_enabled ?? false} />}
    {tab === 'audit' && auditAccess && <section className="ws-vault-panel"><h2>Credential access log</h2><p>Names and values stay out of this log. Events identify the person, connection key, credential ID, action and result. Auditor changes identify the target key.</p>
      {audit.error && <p role="alert" className="ws-notice ws-error">{message(audit.error)}</p>}
      <div className="ws-vault-table"><table><thead><tr><th>When</th><th>Actor</th><th>Action</th><th>Result</th><th>Credential</th></tr></thead><tbody>{!audit.isError && audit.data?.items.map(event => <tr key={event.id}><td>{date(event.occurred_at)}</td><td>{people.data?.items.find(person => person.id === event.principal_id)?.name ?? event.principal_id.slice(0, 8)}<small>Key {event.key_id.slice(0, 8)}</small></td><td>{event.action}</td><td>{event.outcome}</td><td>{event.entry_id?.slice(0, 8) ?? 'Vault'}</td></tr>)}</tbody></table></div>
      {!audit.isPending && !audit.data?.items.length && <p>No credential access events yet.</p>}
      <div className="ws-setup-actions"><button className="ws-button ws-quiet" disabled={!auditOffset} onClick={() => setAuditOffset(Math.max(0, auditOffset - 100))}>Previous events</button><button className="ws-button ws-quiet" disabled={audit.data?.next_offset == null} onClick={() => setAuditOffset(audit.data!.next_offset!)}>Older events</button></div>
    </section>}
    {tab === 'credentials' && metadataAvailable && <>
      {status.data?.available && <div className="ws-setup-actions">{me.administrator && <><button className="ws-button ws-primary" disabled={pending} onClick={() => { setEditor({ id: crypto.randomUUID(), name: '', value: '', version: 0, rename: true }); setError(''); }}><Plus size={15} />Add credential</button><button className="ws-button" disabled={pending} onClick={() => beginTransfer('import')}><Upload size={15} />Restore encrypted export</button></>}
        <button className="ws-button" disabled={pending || !chosen.length} onClick={() => beginTransfer('export')}><Download size={15} />Export selected{chosen.length ? ` (${chosen.length})` : ''}</button>{!!chosen.length && <button className="ws-button ws-quiet" disabled={pending} onClick={() => setChosen([])}>Clear selection</button>}</div>}
      {status.data?.available && supportsKeePass(me.service_version) && <KeepassTransfer client={client} administrator={me.administrator} selected={chosen}
        disabled={busy || !!editor || !!transfer || !!deleting || !!subject} onActive={setKeepassActive}
        onDone={message => { setNotice(message); setChosen([]); setOffset(0); void refresh(); }} />}
      {entries.error && <p className="ws-notice ws-error" role="alert">{message(entries.error)}</p>}
      <div className="ws-vault-columns"><section className="ws-vault-panel"><h2>Credentials available to you</h2><label className="ws-field"><span>Filter this page by name</span><input data-update-safe value={filter} onChange={event => setFilter(event.target.value)} maxLength={120} autoComplete="off" /></label>
        <ul className="ws-vault-entries">{!entries.isError && entries.data?.items.filter(item => item.name.toLocaleLowerCase().includes(filter.toLocaleLowerCase())).map(entry => <li key={entry.id} className={selected === entry.id ? 'selected' : ''}>
          <input type="checkbox" data-update-safe aria-label={`Select ${entry.name} for encrypted export`} disabled={!status.data?.available || !entry.permissions.read || pending || (!chosen.includes(entry.id) && chosen.length >= 100)} checked={chosen.includes(entry.id)} onChange={event => setChosen(current => event.target.checked ? [...current, entry.id] : current.filter(id => id !== entry.id))} />
          <button type="button" disabled={pending} onClick={() => select(entry.id)}><strong>{entry.name}</strong><small>Version {entry.version} · {entry.permissions.read ? 'Read' : 'List'}{entry.permissions.write ? ' · Write' : ''}{entry.permissions.manage ? ' · Manage' : ''}</small></button>
        </li>)}</ul>
        {!entries.isPending && !entries.data?.items.length && <p>{me.administrator ? 'Add a credential, then choose who can use it.' : 'No credentials have been shared with this connection.'}</p>}
        <div className="ws-setup-actions"><button className="ws-button ws-quiet" disabled={pending || !offset} onClick={() => { select(''); setOffset(Math.max(0, offset - 100)); }}>Previous</button><button className="ws-button ws-quiet" disabled={pending || entries.data?.next_offset == null} onClick={() => { select(''); setOffset(entries.data!.next_offset!); }}>Next</button></div>
      </section><section className="ws-vault-panel" aria-label="Selected credential">
        {!selectedEntry ? <><KeyRound size={28} /><h2>Choose a credential</h2><p>Values stay hidden until you explicitly read them. An administrator can manage access without automatically reading a credential.</p></> : <>
          <h2>{selectedEntry.name}</h2><p className="ws-helper">Updated {date(selectedEntry.updated_at)} · version {selectedEntry.version}</p>
          <div className="ws-setup-actions">{status.data?.available && selectedEntry.permissions.read && <button className="ws-button" disabled={pending} onClick={() => revealed?.id === selectedEntry.id ? setRevealed(null) : void reveal(selectedEntry)}>{revealed ? <EyeOff size={15} /> : <Eye size={15} />}{revealed ? 'Hide value' : 'Read credential'}</button>}
            {status.data?.available && selectedEntry.permissions.write && <button className="ws-button" disabled={pending} onClick={() => { setRevealed(null); setEditor({ id: selectedEntry.id, name: selectedEntry.name, value: '', version: selectedEntry.version, rename: me.administrator }); }}>Replace value</button>}
            {status.data?.available && me.administrator && <button className="ws-button ws-quiet" disabled={pending} onClick={() => { setRevealed(null); setDeleting(selectedEntry); }}><Trash2 size={14} />Delete</button>}</div>
          {revealed?.id === selectedEntry.id && <div className="ws-vault-revealed"><label className="ws-field"><span>Credential value · version {revealed.version}</span><textarea readOnly value={revealed.value} rows={4} autoComplete="off" spellCheck={false} data-update-safe /></label><button className="ws-button ws-quiet" onClick={() => void copy(revealed.value)}><Copy size={14} />Copy value</button><small>Hidden after one minute or when this window loses focus.</small></div>}
          {!selectedEntry.permissions.read && <p>This connection cannot read the value.{selectedEntry.permissions.write ? ' Its write grant lets you replace it without reading the existing credential.' : ''}</p>}
          {me.administrator && <div className="ws-vault-grants"><h3>Who can use this credential</h3><p>Person grants cover their signed-in devices. Agent keys need their own explicit grants.</p>{grants.error && <p className="ws-error" role="alert">{message(grants.error)}</p>}
            <ul>{grants.data?.items.map(item => <li key={`${item.subject_kind}:${item.subject_id}`}><div><strong>{item.name}</strong><small>{item.subject_kind === 'person' ? 'Person' : 'Key'} · {item.read ? 'Read' : 'List'}{item.write ? ' · Write' : ''}{!item.active ? ' · Inactive' : ''}</small></div><button className="ws-button ws-quiet" disabled={!status.data?.available || pending} onClick={() => void grant(true, item)}>Revoke</button></li>)}</ul>
            <form onSubmit={event => { event.preventDefault(); void grant(); }}><fieldset disabled={!status.data?.available || busy || !!editor || !!transfer || !!deleting || !grants.data}>
              <label className="ws-field"><span>Grant or change access</span><select value={subject} required onChange={event => { setSubject(event.target.value); setCanRead(false); setCanWrite(false); }}><option value="">Choose a person or key</option>
                <optgroup label="People · signed-in devices">{people.data?.items.filter(person => person.kind === 'human' && !person.disabled_at).map(person => <option key={person.id} value={`person:${person.id}`}>{person.name}</option>)}</optgroup>
                <optgroup label="Individual keys">{status.data && <option value={`key:${status.data.current_key_id}`}>This connection</option>}{keys.data?.items.filter(key => !key.revoked_at && key.id !== status.data?.current_key_id).map(key => <option key={key.id} value={`key:${key.id}`}>{key.name} · {key.prefix}</option>)}</optgroup></select></label>
              <div className="ws-setup-actions"><label className="ws-checkbox"><input type="checkbox" checked={canRead} onChange={event => setCanRead(event.target.checked)} />Read value</label><label className="ws-checkbox"><input type="checkbox" checked={canWrite} onChange={event => setCanWrite(event.target.checked)} />Write value</label></div><small>With neither permission selected, this grants names-only access.</small>
              <div className="ws-setup-actions"><button className="ws-button" disabled={!subject}>Save access</button>{subject && <button className="ws-button ws-quiet" type="button" onClick={() => { setSubject(''); setCanRead(false); setCanWrite(false); }}>Cancel</button>}</div>
            </fieldset></form></div>}
        </>}
      </section></div>
      {editor && <section className="ws-vault-panel"><h2>{editor.version ? 'Replace credential value' : 'Add a credential'}</h2><form onSubmit={save}><fieldset disabled={busy}>
        <label className="ws-field"><span>Name · do not put a password here</span><input required value={editor.name} disabled={!editor.rename} maxLength={120} autoComplete="off" onChange={event => setEditor({ ...editor, name: event.target.value })} /></label>
        <label className="ws-field"><span>{editor.version ? 'New value' : 'Credential value'}</span>{showDraft ? <textarea required rows={5} value={editor.value} maxLength={65536} autoComplete="off" spellCheck={false} onChange={event => setEditor({ ...editor, value: event.target.value })} /> : <input required type="password" value={editor.value} maxLength={65536} autoComplete="new-password" onChange={event => setEditor({ ...editor, value: event.target.value })} />}</label>
        <label className="ws-checkbox"><input type="checkbox" checked={showDraft} onChange={event => setShowDraft(event.target.checked)} />Show value and enable multiline editing</label>
        <p>{editor.version ? 'This replaces the current value. A stale version is refused; previous values are not available in ordinary vault history.' : 'Only your current person or key receives initial read/write access. Add other grants after saving.'}</p>
        <div className="ws-setup-actions"><button className="ws-button ws-primary"><ShieldCheck size={15} />Encrypt & save</button><button className="ws-button ws-quiet" type="button" onClick={() => { setEditor(null); setShowDraft(false); }}>Cancel & clear</button></div>
      </fieldset></form></section>}
      {deleting && <section className="ws-vault-panel"><h2>Delete {deleting.name}?</h2><p>The current encrypted value and grants will be removed. A deletion record prevents an older database backup from restoring it when reconciled with the current recovery ledger.</p><div className="ws-setup-actions"><button className="ws-button" disabled={busy} onClick={() => void run(async () => {
        await client.deleteVault(deleting.id, deleting.version); if (live.current) { setChosen(current => current.filter(id => id !== deleting.id)); setDeleting(null); select(''); setNotice('Credential deleted.'); }
      })}>Delete credential</button><button className="ws-button ws-quiet" disabled={busy} onClick={() => setDeleting(null)}>Cancel</button></div></section>}
      {transfer && <section className="ws-vault-panel"><h2>{transfer === 'export' ? `Encrypted export · ${transferIds.length} credentials` : 'Restore an encrypted export'}</h2><form onSubmit={event => {
        event.preventDefault(); void run(async () => {
          if (transfer === 'export') {
            const result = await client.exportVault(transferIds, transferKey);
            if (live.current) { downloadVault(result); closeTransfer(); setNotice('Encrypted export downloaded. Keep its key separately.'); }
          } else if (archive) {
            const result = await client.importVault(archive, transferKey);
            if (live.current) { closeTransfer(); setOffset(0); setNotice(`${result.items.length} credentials restored with new identifiers and access granted only to you.`); }
          }
        });
      }}><fieldset disabled={busy}>
        <p>{transfer === 'export' ? 'Only credentials you can read are included. Use a separate generated key for this export, then save the encrypted file in your chosen backup or cloud folder.' : 'Choose the encrypted JSON export and its original recovery key. Existing names are never overwritten; historical access grants are not restored.'}</p>
        {transfer === 'import' && <label className="ws-field"><span>Encrypted vault export</span><input type="file" accept="application/json,.json" required onChange={async event => {
          const file = event.target.files?.[0]; setArchive(null); setFileName(''); if (!file) return;
          if (file.size > 1500000) { setError('This export exceeds the 1.5 MB portable-file limit.'); return; }
          try { const value = JSON.parse(await file.text()); if (!value || value.format !== 'mnemion-vault-export' || value.version !== 1) throw new Error(); if (live.current) { setArchive(value); setFileName(file.name); setError(''); } }
          catch { if (live.current) setError('Choose a supported encrypted Mnemion vault export.'); }
        }} />{fileName && <small>{fileName}</small>}</label>}
        {transfer === 'export' && <button type="button" className="ws-button ws-quiet" onClick={() => { setTransferKey(newVaultKey()); setKeySaved(false); }}>Generate export key</button>}
        <label className="ws-field"><span>{transfer === 'export' ? 'Export encryption key' : 'Export recovery key'}</span><input required type={showKey ? 'text' : 'password'} value={transferKey} maxLength={47} autoComplete="off" spellCheck={false} onChange={event => { setTransferKey(event.target.value.trim()); setKeySaved(false); }} /></label>
        <div className="ws-setup-actions"><button type="button" className="ws-button ws-quiet" onClick={() => setShowKey(value => !value)}>{showKey ? 'Hide' : 'Show'} key</button>{transfer === 'export' && <button type="button" className="ws-button ws-quiet" disabled={!transferKey} onClick={() => void copy(transferKey)}><Copy size={14} />Copy key</button>}</div>
        {transfer === 'export' && <label className="ws-checkbox"><input type="checkbox" checked={keySaved} onChange={event => setKeySaved(event.target.checked)} required />I saved this export key independently.</label>}
        <div className="ws-setup-actions"><button className="ws-button ws-primary" disabled={!transferKey || (transfer === 'export' ? !keySaved : !archive)}>{transfer === 'export' ? 'Download encrypted export' : 'Verify & restore credentials'}</button><button className="ws-button ws-quiet" type="button" onClick={closeTransfer}>Cancel & clear</button></div>
      </fieldset></form></section>}
    </>}
  </div>;
}
