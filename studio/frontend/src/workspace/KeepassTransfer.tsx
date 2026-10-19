import { useEffect, useRef, useState } from 'react';
import { Download, Eye, EyeOff, KeyRound, LoaderCircle, Upload } from 'lucide-react';
import { type KeepassPreview, type KeepassPreviewInput, type MnemionClient } from '@mnemion/client';

async function encodeFile(file: File, limit: number): Promise<string> {
  if (!file.size || file.size > limit) throw new Error(`Choose a file no larger than ${limit.toLocaleString()} bytes.`);
  const data = new Uint8Array(await file.arrayBuffer());
  let binary = '';
  for (let start = 0; start < data.length; start += 16384) binary += String.fromCharCode(...data.subarray(start, start + 16384));
  return btoa(binary);
}
function password(): string {
  return btoa(String.fromCharCode(...crypto.getRandomValues(new Uint8Array(24)))).replace(/\+/g, '-').replace(/\//g, '_');
}
async function download(file: string, expected: string): Promise<void> {
  if (file.length > 1333336) throw new Error('The KeePass export exceeds the supported download size.');
  const data = Uint8Array.from(atob(file), value => value.charCodeAt(0));
  const digest = new Uint8Array(await crypto.subtle.digest('SHA-256', data));
  if ([...digest].map(value => value.toString(16).padStart(2, '0')).join('') !== expected) throw new Error('The downloaded file did not match its checksum. Retry the export.');
  const url = URL.createObjectURL(new Blob([data], { type:'application/x-keepass2' }));
  const link = document.createElement('a'); link.href = url; link.download = `mnemion-vault-${new Date().toISOString().slice(0, 10)}.kdbx`;
  link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export default function KeepassTransfer({ client, administrator, selected, disabled, onActive, onDone }: {
  client: MnemionClient; administrator: boolean; selected: string[]; disabled: boolean;
  onActive: (active:boolean) => void; onDone: (message:string) => void;
}) {
  const [mode, setMode] = useState<'import' | 'export' | null>(null);
  const [file, setFile] = useState(''), [keyFile, setKeyFile] = useState(''), [secret, setSecret] = useState('');
  const [noPassword, setNoPassword] = useState(false), [show, setShow] = useState(false);
  const [prefix, setPrefix] = useState('keepass'), [masked, setMasked] = useState(true);
  const [preview, setPreview] = useState<KeepassPreview | null>(null), [approved, setApproved] = useState(false);
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [copyNotice, setCopyNotice] = useState('');
  const alive = useRef(true), fileGeneration = useRef(0), keyGeneration = useRef(0);
  useEffect(() => { alive.current = true; return () => { alive.current = false; fileGeneration.current++; keyGeneration.current++; }; }, []);
  useEffect(() => { onActive(mode !== null || busy); return () => onActive(false); }, [mode, busy, onActive]);
  useEffect(() => { const hide = () => setShow(false); window.addEventListener('blur', hide); return () => window.removeEventListener('blur', hide); }, []);
  function edit() { setPreview(null); setApproved(false); setError(''); }
  function clear() {
    fileGeneration.current++; keyGeneration.current++;
    setFile(''); setKeyFile(''); setSecret(''); setNoPassword(false); setShow(false);
    setPreview(null); setApproved(false); setMode(null); setError(''); setCopyNotice('');
  }
  const input = (): KeepassPreviewInput => ({ file, password:noPassword ? null : secret,
    key_file:keyFile || null, namespace:prefix, mask_names:masked });
  async function run(task: () => Promise<void>) {
    setBusy(true); setError('');
    try { await task(); } catch (failure) { if (alive.current) setError(failure instanceof Error ? failure.message : 'The KeePass operation could not finish.'); }
    finally { if (alive.current) setBusy(false); }
  }
  async function readFile(value: File | undefined, key: boolean) {
    const generation = key ? keyGeneration : fileGeneration, ticket = ++generation.current;
    edit(); if (key) setKeyFile(''); else setFile('');
    if (!value) return;
    try { const encoded = await encodeFile(value, key ? 65536 : 1000000);
      if (alive.current && ticket === generation.current) { if (key) setKeyFile(encoded); else setFile(encoded); }
    } catch (failure) { if (alive.current && ticket === generation.current) setError((failure as Error).message); }
  }
  if (!mode) return <div className="ws-setup-actions">
    {administrator && <button type="button" className="ws-button ws-quiet" disabled={disabled} onClick={() => { clear(); setMode('import'); }}><Upload size={14} />Import KeePass</button>}
    <button type="button" className="ws-button ws-quiet" disabled={disabled || selected.length === 0} onClick={() => { clear(); setMode('export'); }}><Download size={14} />Export selected to KeePass</button>
  </div>;
  return <section className="ws-vault-panel ws-keepass" data-update-pending>
    <h2><KeyRound size={19} />{mode === 'import' ? 'Import from KeePass' : `Export ${selected.length} credentials to KeePass`}</h2>
    <p>{mode === 'import' ? 'Choose a KDBX 4 file, review the mapped names, then import its current fields. Your workspace host decrypts it in memory; no plaintext file is created.' : 'Download a password-protected KDBX 4.1 file. Only selected credentials you can read are included. Imported fields retain their original grouping when available.'}</p>
    {error && <p className="ws-notice ws-error" role="alert">{error}</p>}
    <form className="ws-form" onSubmit={event => { event.preventDefault(); void run(async () => {
      if (mode === 'export') {
        const result = await client.exportKeePass(selected, secret);
        if (alive.current) { await download(result.file, result.sha256); clear(); onDone('Encrypted KeePass download requested. Keep its password separately.'); }
      } else if (preview && approved) {
        const result = await client.importKeePass({ ...input(), expected_plan:preview.plan, import_current_values:true });
        if (alive.current) { clear(); onDone(result.already_imported ? 'This file was already imported; no credentials were changed.' : `${result.items.length} credential fields imported. Only your current person or key has initial access.`); }
      } else {
        const result = await client.previewKeePass(input()); if (alive.current) { setPreview(result); setApproved(false); }
      }
    }); }}><fieldset className="ws-form" disabled={busy}>
      {mode === 'import' && <>
        <label className="ws-field"><span>KeePass file · up to 1 MB</span><input type="file" accept=".kdbx" required onChange={event => void readFile(event.target.files?.[0], false)} /></label>
        <details className="ws-details"><summary>Optional key file</summary>
          <label className="ws-field"><span>Key file · up to 64 KiB</span><input type="file" onChange={event => void readFile(event.target.files?.[0], true)} /></label>
          <label className="ws-checkbox"><input type="checkbox" checked={noPassword} onChange={event => { edit(); setNoPassword(event.target.checked); }} />This database uses a key file without a password component</label>
        </details>
      </>}
      {!noPassword && <label className="ws-field"><span>{mode === 'import' ? 'KeePass master password' : 'Password for this encrypted export'}</span><input type={show ? 'text' : 'password'} value={secret} required={mode === 'export'} minLength={mode === 'export' ? 12 : undefined} maxLength={1024} autoComplete={mode === 'export' ? 'new-password' : 'off'} spellCheck={false} onChange={event => { edit(); setSecret(event.target.value); setCopyNotice(''); }} /></label>}
      <div className="ws-setup-actions">
        {!noPassword && <button type="button" className="ws-button ws-quiet" onClick={() => setShow(value => !value)}>{show ? <EyeOff size={14} /> : <Eye size={14} />}{show ? 'Hide password' : 'Show password'}</button>}
        {mode === 'export' && <><button type="button" className="ws-button ws-quiet" onClick={() => { setSecret(password()); setApproved(false); setCopyNotice(''); }}>Generate password</button>
          <button type="button" className="ws-button ws-quiet" disabled={!secret} onClick={() => void navigator.clipboard.writeText(secret).then(() => setCopyNotice('Export password copied.'), () => setError('Clipboard is unavailable. Reveal the password and save it separately.'))}>Copy password</button></>}
      </div>
      {copyNotice && <p role="status">{copyNotice}</p>}
      {mode === 'import' && <>
        <label className="ws-field"><span>Name prefix</span><input value={prefix} pattern={'[A-Za-z0-9_\\-]{1,24}'} maxLength={24} required onChange={event => { edit(); setPrefix(event.target.value); }} /><small>Use a different prefix to keep separate imports apart.</small></label>
        <label className="ws-checkbox"><input type="checkbox" checked={masked} onChange={event => { edit(); setMasked(event.target.checked); }} />Mask account, group and custom-field names in the credential list</label>
        {preview && <div className="ws-keepass-preview">
          <h3>{preview.credentials} credential fields from {preview.entries} KeePass entries</h3>
          <p>Empty fields retained: {preview.empty_fields}. Names and field context are never indexed as memory.</p>
          <p>Left out — previous versions: {preview.omitted.history_entries}; attachments: {preview.omitted.attachments}; recycled or deleted entries: {preview.omitted.recycled_entries}.</p>
          <details className="ws-details"><summary>Review {preview.names.length} credential names</summary><ul>{preview.names.map(name => <li key={name}>{name}</li>)}</ul></details>
          {!preview.can_import && <p className="ws-notice ws-error">Existing names conflict or this import has changed. Choose a different prefix and preview again.</p>}
          {preview.already_imported && <p className="ws-notice">This exact import is already present. Repeating it will not create duplicates.</p>}
        </div>}
      </>}
      {(mode === 'export' || preview) && <label className="ws-checkbox"><input type="checkbox" required checked={approved} onChange={event => setApproved(event.target.checked)} />{mode === 'export' ? 'I saved this export password independently.' : 'I reviewed the names and want to import current credential values, without history, recycled entries or attachments.'}</label>}
      <div className="ws-setup-actions"><button className="ws-button ws-primary" disabled={busy || (mode === 'export' ? !secret || !approved : !file || (noPassword && !keyFile) || !!preview && (!approved || !preview.can_import))}>
        {busy && <LoaderCircle size={15} className="ws-spin" />}{busy ? 'Working…' : mode === 'export' ? 'Download encrypted KeePass file' : preview ? 'Import reviewed credentials' : 'Verify file & preview names'}</button>
        <button type="button" className="ws-button ws-quiet" onClick={clear}>Cancel & clear</button></div>
    </fieldset></form>
  </section>;
}
