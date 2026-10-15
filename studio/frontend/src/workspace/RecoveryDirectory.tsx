import { useEffect, useState, type FormEvent } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Plus, RefreshCw, Save, ShieldCheck, Trash2 } from 'lucide-react';
import type { RecoveryDirectory as Directory, RecoveryDirectoryRecord } from '@mnemion/client';
import { recoveryRecord } from '../../../electron/workspace-recovery';
import type { Connection } from './connection-types';
import { RecoveryKitForm, RecoveryReferences } from './RecoveryReferences';
import './recovery-directory.css';

const empty = (): Directory => ({ instructions: '', independent_url: null, hosts: [], materials: [], contacts: [] });
const message = (error: unknown) => error instanceof Error ? error.message.replace(/^Error invoking remote method '[^']+': (?:Error: )?/, '') : 'The recovery directory could not be updated.';
const localDate = (value: string | null) => { if (!value) return ''; const date = new Date(value); return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16); };
const utcDate = (value: string) => value && Number.isFinite(Date.parse(value)) ? new Date(value).toISOString() : null;

export default function RecoveryDirectory({ connection }: { connection: Connection }) {
  const { client, me, endpoint } = connection, cache = useQueryClient();
  const key = ['recovery-directory', endpoint, me.tenant_id, me.principal_id];
  const query = useQuery({ queryKey: key, queryFn: async () => recoveryRecord(await client.recoveryDirectory(), me.tenant_id), enabled: me.administrator });
  const [baseline, setBaseline] = useState<RecoveryDirectoryRecord>(), [draft, setDraft] = useState<Directory>(empty);
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [notice, setNotice] = useState('');
  const dirty = !!baseline && JSON.stringify(draft) !== JSON.stringify(baseline.directory);
  const bytes = new TextEncoder().encode(JSON.stringify(draft)).length;
  useEffect(() => {
    if (query.data && (!baseline || (!dirty && query.data.revision > baseline.revision))) {
      setBaseline(query.data); setDraft(structuredClone(query.data.directory));
    }
  }, [query.data, baseline, dirty]);
  const change = (edit: (next: Directory) => void) => { setDraft(previous => { const next = structuredClone(previous); edit(next); return next; }); setNotice(''); };
  const save = async (event: FormEvent) => {
    event.preventDefault(); if (!baseline) return; setBusy(true); setError(''); setNotice('');
    try {
      const saved = recoveryRecord(await client.configureRecoveryDirectory(baseline.revision, draft), me.tenant_id);
      cache.setQueryData(key, saved); setBaseline(saved); setDraft(structuredClone(saved.directory));
      if (connection.refreshRecovery) {
        try { await connection.refreshRecovery(); setNotice('Saved for the organization and in this device’s protected offline copy.'); }
        catch (error) { setNotice('Saved for the organization. The local copy could not be refreshed: ' + message(error)); }
      } else setNotice('Saved for the organization. Download an independent kit, and remember an administrator connection to keep a protected desktop copy.');
    } catch (error) { setError(message(error)); }
    finally { setBusy(false); }
  };
  const reload = async () => {
    setBusy(true); setError('');
    try { const fresh = recoveryRecord(await client.recoveryDirectory(), me.tenant_id); cache.setQueryData(key, fresh); setBaseline(fresh); setDraft(structuredClone(fresh.directory)); setNotice('Loaded the currently saved directory.'); }
    catch (error) { setError(message(error)); }
    finally { setBusy(false); }
  };
  if (!me.administrator) return <div className="ws-page"><h1>Recovery directory</h1><p>Use an organization administrator account to manage recovery references.</p></div>;
  if (query.error) return <div className="ws-page"><h1>Recovery directory</h1><div role="alert" className="ws-notice ws-error">{(query.error as { status?: number }).status === 404 ? 'Update this workspace server to use its recovery directory. Existing memory connections still work.' : message(query.error)}</div><button className="ws-button" onClick={() => void query.refetch()}>Retry</button></div>;
  if (!baseline) return <div className="ws-page" role="status">Loading the organization’s recovery directory…</div>;
  return <div className="ws-page recovery-directory">
    <header className="ws-page-heading"><div><p className="ws-eyebrow">Organization continuity</p><h1>Recovery directory</h1><p>Keep host access, recovery locations and independent contacts available when an agent or server is offline.</p></div><ShieldCheck size={26} /></header>
    <p className="ws-notice">Only organization administrators can read or change this directory. Record where to sign in and where recovery material lives; keep passwords and keys in your separate credential store. Entries do not grant host access.</p>
    {baseline.updated_at && <p className="ws-helper">Saved {new Date(baseline.updated_at).toLocaleString()} · revision {baseline.revision}</p>}
    {query.data && query.data.revision !== baseline.revision && <p className="ws-notice" role="status">The server has a different saved revision. Reload and review it before replacing another administrator’s changes.</p>}
    {error && <div className="ws-notice ws-error" role="alert">{error}</div>}{notice && <div className="ws-notice" role="status">{notice}</div>}
    <form onSubmit={save} data-update-pending={dirty || busy}>
      <fieldset disabled={busy}>
        <section className="recovery-panel"><h2>Independent entry point</h2>
          <label>Recovery instructions<textarea rows={4} maxLength={2000} value={draft.instructions} onChange={event => change(next => { next.instructions = event.target.value; })} placeholder="Who can restart the host, where their separate access is held, and what to verify before recovering." /></label>
          <label>Independent recovery page (optional)<input type="url" value={draft.independent_url ?? ''} maxLength={2048} placeholder="https://recovery.company.example" onChange={event => change(next => { next.independent_url = event.target.value || null; })} /></label>
          <p className="ws-helper">Use an HTTPS entry address without login tokens or query parameters. Hosting an encrypted kit on a different system keeps it reachable when the memory host stops.</p>
        </section>
        <section className="recovery-panel"><h2>Hosts & operator access</h2><p className="ws-helper">Record primary, recovery and ingestion computers. Provider or operating-system sign-in remains separate from Mnemion membership.</p>
          {draft.hosts.map((host, i) => <div key={host.id} className="recovery-entry"><div className="recovery-grid">
            <label>Host name<input required maxLength={120} value={host.name} onChange={event => change(next => { next.hosts[i].name = event.target.value; })} /></label>
            <label>Purpose<select value={host.role} onChange={event => change(next => { next.hosts[i].role = event.target.value as typeof host.role; })}><option value="primary">Primary memory host</option><option value="recovery">Recovery computer</option><option value="ingestion">Ingestion host</option></select></label>
            <label>System<select value={host.platform} onChange={event => change(next => { next.hosts[i].platform = event.target.value as typeof host.platform; })}>{(['windows','macos','linux','managed','other'] as const).map(value => <option key={value} value={value}>{({windows:'Windows',macos:'macOS',linux:'Linux',managed:'Managed cloud',other:'Other'})[value]}</option>)}</select></label>
            <label>Responsible operator<input maxLength={200} value={host.operator} onChange={event => change(next => { next.hosts[i].operator = event.target.value; })} /></label>
            <label>Workspace address (optional)<input type="url" maxLength={2048} value={host.workspace_url ?? ''} onChange={event => change(next => { next.hosts[i].workspace_url = event.target.value || null; })} /></label>
            <label>Host console address (optional)<input type="url" maxLength={2048} value={host.operator_url ?? ''} onChange={event => change(next => { next.hosts[i].operator_url = event.target.value || null; })} /></label>
          </div><label>Host notes<textarea rows={2} maxLength={600} value={host.notes} onChange={event => change(next => { next.hosts[i].notes = event.target.value; })} /></label><button type="button" className="ws-button ws-quiet" aria-label={`Remove host ${host.name || i + 1}`} onClick={() => change(next => { next.hosts.splice(i,1); })}><Trash2 size={14} />Remove host</button></div>)}
          <button className="ws-button" type="button" disabled={draft.hosts.length >= 16} onClick={() => change(next => { next.hosts.push({id:crypto.randomUUID(),name:'',role:next.hosts.length ? 'recovery' : 'primary',platform:'other',workspace_url:null,operator_url:null,operator:'',notes:''}); })}><Plus size={15} />Add host</button>
        </section>
        <section className="recovery-panel"><h2>Backups, ledgers & source mirrors</h2><p className="ws-helper">A complete workspace recovery needs a verified database backup and current access/deletion ledger. A Git or cloud source mirror recovers its tracked documents.</p>
          {draft.materials.map((material,i) => <div key={material.id} className="recovery-entry"><div className="recovery-grid">
            <label>Recovery location name<input required maxLength={120} value={material.name} onChange={event => change(next => { next.materials[i].name = event.target.value; })} /></label>
            <label>Material<select value={material.kind} onChange={event => change(next => { next.materials[i].kind = event.target.value as typeof material.kind; })}><option value="database_backup">Database backup</option><option value="recovery_ledger">Access & deletion ledger</option><option value="source_mirror">Source mirror · documents only</option></select></label>
            <label>Location or path<input required maxLength={1024} value={material.location} placeholder="Company drive / backups, a local path, or an object-storage location" onChange={event => change(next => { next.materials[i].location = event.target.value; })} /></label>
            <label>Storage access page (optional)<input type="url" maxLength={2048} value={material.access_url ?? ''} onChange={event => change(next => { next.materials[i].access_url = event.target.value || null; })} /></label>
            <label>Verification reported at (optional)<input type="datetime-local" value={localDate(material.reported_verified_at)} onChange={event => change(next => { next.materials[i].reported_verified_at = utcDate(event.target.value); })} /></label>
          </div><label>Recovery material notes<textarea rows={2} maxLength={600} value={material.notes} onChange={event => change(next => { next.materials[i].notes = event.target.value; })} /></label><p className="ws-helper">This date is your reported observation. Registering a location does not verify its contents or upload a backup.</p><button className="ws-button ws-quiet" type="button" aria-label={`Remove recovery location ${material.name || i + 1}`} onClick={() => change(next => { next.materials.splice(i,1); })}><Trash2 size={14} />Remove location</button></div>)}
          <button className="ws-button" type="button" disabled={draft.materials.length >= 16} onClick={() => change(next => { next.materials.push({id:crypto.randomUUID(),name:'',kind:'database_backup',location:'',access_url:null,reported_verified_at:null,notes:''}); })}><Plus size={15} />Add recovery location</button>
        </section>
        <section className="recovery-panel"><h2>Independent contacts</h2>
          {draft.contacts.map((contact,i) => <div key={contact.id} className="recovery-entry"><div className="recovery-grid">
            <label>Contact name<input required maxLength={120} value={contact.name} onChange={event => change(next => { next.contacts[i].name = event.target.value; })} /></label>
            <label>Contact channel<input required maxLength={300} value={contact.channel} placeholder="Help desk, email, phone or company messaging channel" onChange={event => change(next => { next.contacts[i].channel = event.target.value; })} /></label>
          </div><label>Responsibility<input maxLength={300} value={contact.responsibility} onChange={event => change(next => { next.contacts[i].responsibility = event.target.value; })} /></label><button className="ws-button ws-quiet" type="button" aria-label={`Remove contact ${contact.name || i + 1}`} onClick={() => change(next => { next.contacts.splice(i,1); })}><Trash2 size={14} />Remove contact</button></div>)}
          <button className="ws-button" type="button" disabled={draft.contacts.length >= 16} onClick={() => change(next => { next.contacts.push({id:crypto.randomUUID(),name:'',channel:'',responsibility:''}); })}><Plus size={15} />Add contact</button>
        </section>
        <div className="recovery-actions"><button type="submit" className="ws-button ws-primary" disabled={!dirty || bytes > 6144}><Save size={15} />{busy ? 'Saving…' : 'Save recovery directory'}</button><button type="button" className="ws-button" onClick={() => void reload()}><RefreshCw size={15} />{dirty ? 'Discard edits & reload saved directory' : 'Reload saved directory'}</button></div>
        <p className="ws-helper">{(bytes / 1024).toFixed(1)} / 6 KiB. Keep this portable directory concise and link to longer runbooks.</p>
        {bytes > 6144 && <p className="ws-notice ws-error" role="alert">Shorten the directory before saving; use the independent page for longer instructions.</p>}
      </fieldset>
    </form>
    {connection.refreshRecovery && <button type="button" className="ws-button" disabled={busy || dirty} onClick={async () => { setBusy(true); setError(''); try { await connection.refreshRecovery!(); setNotice('The protected copy on this device was refreshed from the server.'); } catch (error) { setError(message(error)); } finally { setBusy(false); } }}><RefreshCw size={15} />Refresh protected offline copy</button>}
    {!!baseline.revision && <><details className="recovery-panel"><summary>Preview the saved recovery references</summary><RecoveryReferences record={baseline} /></details>{dirty ? <p className="ws-notice">Save or discard your edits before exporting a recovery kit.</p> : <RecoveryKitForm record={baseline} endpoint={endpoint} name={me.tenant_name} />}</>}
  </div>;
}
