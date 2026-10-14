import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { Copy, ExternalLink, Globe, LoaderCircle, RefreshCw, ShieldCheck } from 'lucide-react';
import type { LocalStatus, RemoteChange, RemoteMode } from '../../../shared/local-workspace';
import { localError } from './LocalSetup';

const labels = { disabled: 'Off', unchecked: 'Not checked', stopped: 'Host stopped', configuration_error: 'Needs repair', connecting: 'Connecting', online: 'Last check passed', unavailable: 'Connection unavailable' };

export default function RemoteAccess({ status, onStatus, connected = false }: {
  status: LocalStatus; onStatus: (status: LocalStatus) => void; connected?: boolean;
}) {
  const desktop = window.mnemion;
  const saved = status.info?.remote_access;
  const settings = status.info?.settings;
  const [mode, setMode] = useState<RemoteMode>('disabled');
  const [address, setAddress] = useState('');
  const [personal, setPersonal] = useState(true);
  const [token, setToken] = useState('');
  const [revision, setRevision] = useState('not-configured');
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const [notice, setNotice] = useState('');
  const [copied, setCopied] = useState('');
  const [formKey, setFormKey] = useState(0);
  const active = useRef(true);
  useEffect(() => { active.current = true; return () => { active.current = false; }; }, []);
  useEffect(() => {
    if (!saved || dirty) return;
    setMode(saved.mode); setAddress(saved.public_url ?? ''); setPersonal(saved.personal_sign_in);
    setRevision(saved.revision); setToken('');
  }, [saved?.revision, dirty]);
  if (!desktop?.localRemote || !saved || !settings) return null;

  const working = busy || ['starting', 'stopping'].includes(status.state);
  const stale = dirty && revision !== saved.revision;
  function edit() { setDirty(true); setNotice(''); setError(undefined); }
  async function refresh() {
    setBusy(true); setError(undefined);
    try { const next = await desktop!.localStatus!(); if (active.current) onStatus(next); }
    catch (error) { if (active.current) setError(error); }
    finally { if (active.current) setBusy(false); }
  }
  async function copy(value: string) {
    try { await navigator.clipboard.writeText(value); setCopied(value); }
    catch { setNotice('Select the address and copy it manually; clipboard access is unavailable.'); }
  }
  async function save() {
    setBusy(true); setError(undefined); setNotice('');
    const change: RemoteChange = { workspace_id: settings!.workspace_id, expected_revision: revision,
      mode, public_url: mode === 'disabled' ? null : address.trim(), personal_sign_in: personal,
      ngrok_authtoken: mode === 'ngrok' && token ? token : null };
    try {
      const next = await desktop!.localRemote!(change);
      if (active.current) {
        onStatus(next); setDirty(false); setToken(''); setFormKey(key => key + 1);
        setNotice(next.state === 'starting' ? 'Settings saved. The local host is restarting and will check the connection.' : 'Settings saved. Start this local workspace to apply them.');
      }
    } catch (error) { if (active.current) setError(error); }
    finally { if (active.current) setBusy(false); }
  }

  return <section className="ws-device-settings ws-remote-access" aria-labelledby="remote-access-title">
    <div className="ws-memory-heading"><h2 id="remote-access-title"><Globe size={20} />Remote access</h2><span className="ws-badge" aria-live="polite">{labels[saved.state]}</span></div>
    <p>Share <strong>{settings.workspace_name}</strong>, hosted on this computer, with your team and agents. Each connection still needs its own permitted login or key.</p>
    <div className={`ws-notice${saved.state === 'configuration_error' || saved.state === 'unavailable' ? ' ws-error' : ''}`} role="status">
      <p>{saved.message}</p>{saved.provider_code && <small>Provider code: {saved.provider_code}</small>}
      {saved.verified_at && <small>Last successful route check: {new Date(saved.verified_at).toLocaleString()}</small>}
      {saved.mode !== 'disabled' && <small>Automatic route checks run every 15 minutes. Use Check now after a network change.</small>}
    </div>
    {!!error && <p className="ws-notice ws-error" role="alert">{localError(error)}</p>}
    <form key={formKey} onSubmit={event => { event.preventDefault(); void save(); }} aria-busy={busy}>
      <fieldset disabled={working || !saved.repairable} className="ws-setup-fields">
        <label className="ws-field"><span>Connection method</span><select value={mode} onChange={event => { edit(); setMode(event.target.value as RemoteMode); setToken(''); }}>
          <option value="disabled">Off</option><option value="ngrok">Managed ngrok connection</option><option value="proxy">Existing HTTPS proxy or private network</option>
        </select></label>
        {mode === 'ngrok' && <div className="ws-remote-provider"><p>Use the authtoken and assigned domain from your own ngrok account. Mnemion opens and maintains the connection; no separate tunnel program is needed. A free account is supported within its limits.</p>
          <a className="ws-link" href="https://dashboard.ngrok.com/get-started/your-authtoken" target="_blank" rel="noreferrer">Get your account authtoken<ExternalLink size={13} /></a>
          <a className="ws-link" href="https://dashboard.ngrok.com/domains" target="_blank" rel="noreferrer">Find your assigned domain<ExternalLink size={13} /></a>
          <label className="ws-field"><span>ngrok authtoken</span><input type="password" autoComplete="off" spellCheck={false} maxLength={256} value={token} placeholder={saved.has_ngrok_authtoken ? 'Saved — enter a new token to replace it' : 'Paste your account authtoken'} onChange={event => { edit(); setToken(event.target.value); }} required={!saved.has_ngrok_authtoken} /></label>
          <small>Kept in the host’s private operator files. The app never displays the saved token.</small>
          <small>The free plan currently includes 20,000 HTTP requests and 1 GB of outbound traffic per month. Routine checks use about 2,880 requests in 30 days. <a href="https://ngrok.com/docs/pricing-limits/free-plan-limits" target="_blank" rel="noreferrer">Provider limits</a></small>
        </div>}
        {mode !== 'disabled' && <label className="ws-field"><span>HTTPS address</span><input type="url" value={address} onChange={event => { edit(); setAddress(event.target.value); }} placeholder={mode === 'ngrok' ? 'https://your-domain.ngrok-free.dev' : 'https://memory.your-company.com'} maxLength={2048} required spellCheck={false} autoComplete="url" /></label>}
        {mode === 'proxy' && <div className="ws-notice"><p>Point your existing HTTPS proxy at <code>http://127.0.0.1:{settings.port}</code> on this computer. Forward the full site, including <code>/mcp</code>, <code>/v1</code>, <code>/oauth</code> and <code>/.well-known</code>, and preserve its public Host header.</p><p>Mnemion checks the route. Your network operator manages the proxy, its certificate and its availability.</p></div>}
        {mode !== 'disabled' && <label className="ws-checkbox"><input type="checkbox" checked={personal} onChange={event => { edit(); setPersonal(event.target.checked); }} /><span>Allow hosted agents to request personal sign-in and consent (OAuth)</span></label>}
        {mode === 'disabled' && saved.mode === 'ngrok' && <p>The managed tunnel will close and its saved authtoken will be removed. Workspace memories, logins and grants are retained.</p>}
        {mode === 'disabled' && saved.mode === 'proxy' && <p>Also remove forwarding in your proxy to disconnect it. Mnemion cannot shut down a separately managed proxy.</p>}
      </fieldset>
      {stale && <p className="ws-notice" role="status">Another operator changed these settings. Review the saved version before applying your edits.</p>}
      <div className="ws-setup-actions"><button className="ws-button ws-primary" disabled={working || !saved.repairable || !dirty || stale} type="submit">{busy ? <LoaderCircle size={15} className="ws-spin" /> : <ShieldCheck size={15} />}{status.state === 'running' ? 'Save & restart local host' : 'Save settings'}</button>
        <button className="ws-button ws-quiet" type="button" disabled={working} onClick={() => void refresh()}><RefreshCw size={14} />Refresh status</button>
        {saved.mode !== 'disabled' && desktop.localRemoteCheck && <button className="ws-button ws-quiet" type="button" disabled={working || dirty || status.state !== 'running'} onClick={async () => {
          setBusy(true); setError(undefined);
          try {
            const next = await desktop.localRemoteCheck!({ workspace_id: settings.workspace_id, expected_revision: saved.revision });
            if (active.current) { onStatus(next); setNotice('Route check requested. Results appear here shortly; checks are limited to once every 30 seconds.'); }
          } catch (error) { if (active.current) setError(error); }
          finally { if (active.current) setBusy(false); }
        }}>Check now</button>}
        {dirty && <button className="ws-button ws-quiet" type="button" disabled={working} onClick={() => { setDirty(false); setToken(''); setError(undefined); setFormKey(key => key + 1); }}>Use saved settings</button>}
      </div>
      {status.state === 'running' && dirty && <p className="ws-remote-hint">Saving briefly restarts this local host. Connected clients can reconnect to the same workspace afterwards.</p>}
    </form>
    {notice && <p className="ws-memory-saved" role="status">{notice}</p>}
    {!['running', 'starting', 'stopping'].includes(status.state) && !status.info?.memory_recovery && <button className="ws-button" disabled={busy || dirty} onClick={async () => {
      setBusy(true); setError(undefined);
      try { const next = await desktop.localStart!(); if (active.current) onStatus(next); }
      catch (error) { if (active.current) setError(error); }
      finally { if (active.current) setBusy(false); }
    }}>Start local host</button>}
    {saved.public_url && <div className="ws-remote-addresses">
      {[[saved.public_url, 'Workspace address'], [saved.public_url + '/mcp', 'MCP server']].map(([value, label]) => <label className="ws-field" key={label}><span>{label}</span><div><input readOnly data-update-safe value={value} aria-label={label} /><button type="button" className="ws-button ws-quiet" onClick={() => void copy(value)}><Copy size={14} />{copied === value ? 'Copied' : 'Copy'}</button></div></label>)}
      {connected ? <p><Link className="ws-link" to="/workspace/account">Create personal invitation links</Link><Link className="ws-link" to="/workspace/agents">Connect an agent</Link></p> : <p>Open this workspace to create invitations in <strong>Account & sessions</strong> and set up scoped connections in <strong>Agents</strong>.</p>}
    </div>}
    <p className="ws-remote-hint">This computer must remain running and connected. Background mode and startup keep Mnemion independent of an agent’s model quota; they cannot wake a powered-off host. Remote traffic passes through your selected provider.</p>
  </section>;
}
