import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { Copy, KeyRound, LoaderCircle, ShieldCheck } from 'lucide-react';
import type { LocalStatus } from '../../../shared/local-workspace';
import { localError } from './LocalSetup';
import { newVaultKey } from './vault-utils';

export default function VaultSetup({ status, onStatus }: { status: LocalStatus; onStatus: (value: LocalStatus) => void }) {
  const saved = status.info?.vault_access, settings = status.info?.settings, desktop = window.mnemion;
  const [editing, setEditing] = useState(false), [restoring, setRestoring] = useState(false);
  const [enabled, setEnabled] = useState(false), [mcp, setMcp] = useState(false), [revision, setRevision] = useState('');
  const [key, setKey] = useState(''), [keySaved, setKeySaved] = useState(false), [visible, setVisible] = useState(false);
  const [revealed, setRevealed] = useState(''), [busy, setBusy] = useState(false), [error, setError] = useState<unknown>();
  const [notice, setNotice] = useState('');
  const live = useRef(true), generation = useRef(0);
  useEffect(() => { live.current = true; return () => { live.current = false; generation.current++; }; }, []);
  useEffect(() => { cancel(); setNotice(''); }, [settings?.workspace_id]);
  useEffect(() => {
    const clear = () => { generation.current++; setRevealed(''); setVisible(false); };
    window.addEventListener('blur', clear); document.addEventListener('visibilitychange', clear);
    const timer = revealed ? setTimeout(clear, 60000) : undefined;
    return () => { window.removeEventListener('blur', clear); document.removeEventListener('visibilitychange', clear); clearTimeout(timer); };
  }, [revealed]);
  if (!saved || !settings || !desktop?.localVault) return null;
  const working = busy || ['starting', 'stopping'].includes(status.state);
  const stale = editing && revision !== saved.revision;
  function cancel() { generation.current++; setEditing(false); setRestoring(false); setKey(''); setKeySaved(false); setVisible(false); setRevealed(''); setError(undefined); }
  function begin(restore = false) {
    cancel(); setNotice(''); setRevision(saved!.revision); setEditing(true); setRestoring(restore);
    setEnabled(saved!.key_id ? saved!.enabled : true); setMcp(saved!.mcp_enabled);
  }
  async function copy(value: string) {
    try { await navigator.clipboard.writeText(value); setNotice('Key copied. Keep its recovery copy separate from the encrypted backup.'); }
    catch { setError(new Error('Copy was unavailable. Reveal and select the key to copy it manually.')); }
  }
  async function reveal() {
    if (!desktop?.localVaultKey || !saved || !settings) return;
    const ticket = ++generation.current; setBusy(true); setError(undefined);
    try {
      const value = await desktop.localVaultKey({ workspace_id: settings.workspace_id, expected_revision: saved.revision });
      if (live.current && ticket === generation.current) setRevealed(value.recovery_key);
    } catch (error) { if (live.current) setError(error); }
    finally { if (live.current) setBusy(false); }
  }
  return <section className="ws-device-settings ws-vault-setup" aria-labelledby="vault-setup-title" data-update-pending={editing || busy ? '' : undefined}>
    <div className="ws-memory-heading"><h2 id="vault-setup-title"><KeyRound size={20} />Encrypted credentials vault</h2><span className="ws-badge">{saved.enabled ? 'Enabled' : 'Disabled'}</span></div>
    <p>Store credentials for <strong>{settings.workspace_name}</strong>, hosted on this computer. People and agent keys receive specific grants in Secrets.</p>
    <p className={`ws-notice${saved.state === 'configuration_error' ? ' ws-error' : ''}`}>{saved.message}</p>
    {!!error && <p className="ws-notice ws-error" role="alert">{localError(error)}</p>}{notice && <p className="ws-notice" role="status">{notice}</p>}
    {!editing && saved.repairable && <div className="ws-setup-actions">
      {saved.state !== 'configuration_error' && <button type="button" className="ws-button" disabled={working} onClick={() => begin()}>{saved.key_id ? 'Change vault access' : 'Set up vault'}</button>}
      <button type="button" className="ws-button ws-quiet" disabled={working} onClick={() => begin(true)}>Restore an existing key</button>
      {saved.key_id && desktop.localVaultKey && <button type="button" className="ws-button ws-quiet" disabled={working} onClick={() => void reveal()}>Show host recovery key</button>}
    </div>}
    {revealed && <div className="ws-notice"><strong>Private host recovery key</strong><p>This key opens the encrypted credentials in workspace database backups. Keep it independently; the display clears after one minute or when this window loses focus.</p><input aria-label="Host vault recovery key" readOnly value={revealed} autoComplete="off" spellCheck={false} className="ws-local-path" /><div className="ws-setup-actions"><button type="button" className="ws-button ws-quiet" onClick={() => void copy(revealed)}><Copy size={14} />Copy key</button><button type="button" className="ws-button ws-quiet" onClick={() => setRevealed('')}>Hide</button></div></div>}
    {editing && <form onSubmit={async event => {
      event.preventDefault(); if (stale) return; setBusy(true); setError(undefined); setRevealed('');
      try {
        const next = await desktop.localVault!({ workspace_id: settings.workspace_id, expected_revision: revision,
          action: restoring ? 'restore' : 'configure', enabled, mcp_enabled: mcp,
          ...(key ? { recovery_key: key, key_saved: keySaved } : {}) });
        if (live.current) { onStatus(next); cancel(); setNotice(next.state === 'starting' ? 'Vault settings saved. The workspace is restarting.' : 'Vault settings saved. Start the workspace to use them.'); }
      } catch (error) { if (live.current) setError(error); }
      finally { if (live.current) setBusy(false); }
    }}><fieldset disabled={working || stale} className="ws-setup-fields">
      <label className="ws-checkbox"><input type="checkbox" checked={enabled} onChange={event => setEnabled(event.target.checked)} /><span>Enable credential access in the app and API</span></label>
      <label className="ws-checkbox"><input type="checkbox" checked={mcp} onChange={event => setMcp(event.target.checked)} /><span>Also enable the vault MCP tools for explicitly granted agents</span></label>
      <small>MCP reads send the requested credential to that client or model. Ordinary memory search, context and automatic capture never include vault values. Disabling app/API access also disables the vault tools.</small>
      {(!saved.key_id || restoring) && <><h3>{restoring ? 'Restore the original key' : 'Create and save your recovery key'}</h3>
        <p>{restoring ? 'Use the key that encrypted your existing credentials. Previous private key files are retained; supplying a new key does not re-encrypt old values.' : 'Keep an independent copy before continuing. Workspace backups contain encrypted values; they do not include this host key.'}</p>
        {!restoring && <button type="button" className="ws-button ws-quiet" onClick={() => { setKey(newVaultKey()); setKeySaved(false); }}>Generate a vault key</button>}
        <label className="ws-field"><span>Vault recovery key</span><input type={visible ? 'text' : 'password'} value={key} onChange={event => { setKey(event.target.value.trim()); setKeySaved(false); }} required autoComplete="off" spellCheck={false} maxLength={47} /></label>
        <div className="ws-setup-actions"><button type="button" className="ws-button ws-quiet" onClick={() => setVisible(value => !value)}>{visible ? 'Hide' : 'Show'} key</button><button type="button" className="ws-button ws-quiet" disabled={!key} onClick={() => void copy(key)}><Copy size={14} />Copy key</button></div>
        <label className="ws-checkbox"><input type="checkbox" checked={keySaved} onChange={event => setKeySaved(event.target.checked)} required /><span>I saved an independent recovery copy of this key.</span></label></>}
      <p>Saving briefly restarts a running workspace. Existing encrypted values and grants are retained.</p>
      <div className="ws-setup-actions"><button type="submit" className="ws-button ws-primary" disabled={working || stale || ((!saved.key_id || restoring) && (!key || !keySaved))}>{busy ? <LoaderCircle className="ws-spin" size={15} /> : <ShieldCheck size={15} />}Save vault settings</button><button type="button" className="ws-button ws-quiet" disabled={busy} onClick={cancel}>Cancel</button></div>
    </fieldset></form>}
    {stale && <p className="ws-notice" role="status">Vault settings changed. Cancel these edits and review the latest configuration.</p>}
    <Link className="ws-link" to="/workspace/help?doc=docs%2Fservice%2Fsecrets-vault.md">Vault access, backups and recovery guide</Link>
  </section>;
}
