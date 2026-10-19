import { useState, type FormEvent } from 'react';
import { Download, ExternalLink, LockKeyhole } from 'lucide-react';
import type { RecoveryDirectoryRecord } from '@mnemion/client';
import { exportRecoveryKit } from './recovery-kit';
import './recovery-directory.css';

const materialNames = { database_backup: 'Database backup', recovery_ledger: 'Access & deletion ledger', source_mirror: 'Source mirror · tracked documents only' };
const when = (value: string) => new Date(value).toLocaleString();
function ReferenceLink({ href, children }: { href: string | null; children: string }) {
  return href ? <a className="ws-link" href={href} target="_blank" rel="noreferrer noopener">{children}<ExternalLink size={13} /></a> : null;
}

export function RecoveryReferences({ record }: { record: RecoveryDirectoryRecord }) {
  const directory = record.directory;
  return <div className="recovery-references">
    {directory.instructions && <p className="recovery-text">{directory.instructions}</p>}
    <ReferenceLink href={directory.independent_url}>Open independent recovery page</ReferenceLink>
    <h4>Hosts & operator access</h4>
    {!directory.hosts.length && <p className="ws-helper">No host references have been recorded.</p>}
    {directory.hosts.map(host => <article key={host.id} className="recovery-entry">
      <h4>{host.name}</h4><p className="ws-helper">{host.role} · {host.platform}{host.operator && ` · ${host.operator}`}</p>
      {host.workspace_url && <p className="recovery-text">{host.workspace_url}</p>}
      {host.notes && <p className="recovery-text">{host.notes}</p>}
      <div className="recovery-links"><ReferenceLink href={host.operator_url}>Open host console</ReferenceLink><ReferenceLink href={host.workspace_url}>Open workspace address</ReferenceLink></div>
    </article>)}
    <h4>Recovery material</h4>
    {directory.materials.map(material => <article key={material.id} className="recovery-entry">
      <h4>{material.name}</h4><p className="ws-helper">{materialNames[material.kind]}</p><p className="recovery-text">{material.location}</p>
      <p className="ws-helper">{material.reported_verified_at ? `Verification reported ${when(material.reported_verified_at)}` : 'No verification has been reported.'}</p>
      {material.notes && <p className="recovery-text">{material.notes}</p>}
      <ReferenceLink href={material.access_url}>Open storage access page</ReferenceLink>
    </article>)}
    <h4>Independent contacts</h4>
    {directory.contacts.map(contact => <article key={contact.id} className="recovery-entry"><h4>{contact.name}</h4><p className="recovery-text">{contact.channel}</p>{contact.responsibility && <p className="ws-helper">{contact.responsibility}</p>}</article>)}
    <p className="ws-helper">Entries are administrator-provided references. Sign in separately at the host or storage provider. A source mirror does not include every memory, user, permission or deletion.</p>
  </div>;
}

export function RecoveryKitForm({ record, endpoint, name }: { record: RecoveryDirectoryRecord; endpoint: string; name: string }) {
  const [password, setPassword] = useState(''), [repeat, setRepeat] = useState('');
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [done, setDone] = useState(false);
  const exportKit = async (event: FormEvent) => {
    event.preventDefault(); setError(''); setDone(false);
    if (password !== repeat) { setError('The two passphrases do not match.'); return; }
    setBusy(true);
    try { await exportRecoveryKit(record, password, endpoint, name); setPassword(''); setRepeat(''); setDone(true); }
    catch (error) { setError(error instanceof Error ? error.message : 'The kit could not be created.'); }
    finally { setBusy(false); }
  };
  return <section className="recovery-panel" aria-label="Independent encrypted recovery kit">
    <h3><LockKeyhole size={18} /> Keep an independent recovery kit</h3>
    <p>Download one encrypted HTML file that opens on another device without the memory server. Store it outside the original host, or serve it from your organization’s own HTTPS site.</p>
    <p className="ws-helper">The kit exports only this directory. Keep logins, backup keys and memory data in their separate stores. Use a separate passphrase, keep it separately, and refresh the kit when the setup changes. Existing copies cannot be remotely revoked.</p>
    <form onSubmit={exportKit} data-update-pending={password || repeat || busy ? '' : undefined}>
      <fieldset disabled={busy}><div className="recovery-grid">
        <label>Kit passphrase<input data-update-safe type="password" autoComplete="new-password" value={password} maxLength={1024} minLength={15} required onChange={event => setPassword(event.target.value)} /></label>
        <label>Repeat kit passphrase<input data-update-safe type="password" autoComplete="new-password" value={repeat} maxLength={1024} minLength={15} required onChange={event => setRepeat(event.target.value)} /></label>
      </div><p className="ws-helper">At least 15 characters; several unrelated words work well.</p>
      <button className="ws-button ws-primary" type="submit" disabled={!record.revision}><Download size={15} />{busy ? 'Encrypting…' : 'Download encrypted recovery kit'}</button></fieldset>
      {error && <div className="ws-notice ws-error" role="alert">{error}</div>}
      {done && <div className="ws-notice" role="status">The kit was encrypted locally and sent to your downloads. Open it and verify the passphrase before relying on it.</div>}
    </form>
  </section>;
}
