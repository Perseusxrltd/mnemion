import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { Building2, Check, Copy, LoaderCircle, Plus, RefreshCw } from 'lucide-react';
import type { CompanyChange, CompanyDiscoveryResult, CompanyProviderSettings, LocalStatus } from '../../../shared/local-workspace';
import { localError } from './LocalSetup';

export default function CompanyProviderSetup({ status, onStatus, connected = false }: {
  status: LocalStatus; onStatus: (status: LocalStatus) => void; connected?: boolean;
}) {
  const desktop = window.mnemion;
  const saved = status.info?.company_access, settings = status.info?.settings, remote = status.info?.remote_access;
  const [draft, setDraft] = useState<CompanyProviderSettings | null>(null);
  const [revision, setRevision] = useState(''), [remoteRevision, setRemoteRevision] = useState('');
  const [secret, setSecret] = useState(''), [clearSecret, setClearSecret] = useState(false);
  const [caPem, setCaPem] = useState(''), [clearCa, setClearCa] = useState(false);
  const [discovered, setDiscovered] = useState<CompanyDiscoveryResult | null>(null);
  const [manual, setManual] = useState(false), [reviewed, setReviewed] = useState(false);
  const [remove, setRemove] = useState<string | null>(null), [reset, setReset] = useState(false);
  const [busy, setBusy] = useState(false), [error, setError] = useState<unknown>(), [notice, setNotice] = useState('');
  const [formKey, setFormKey] = useState(0);
  const live = useRef(true);
  useEffect(() => { live.current = true; return () => { live.current = false; }; }, []);
  useEffect(() => { clear(); }, [settings?.workspace_id]);
  if (!desktop?.localCompany || !desktop.localCompanyDiscover || !saved || !settings || !remote) return null;
  const working = busy || ['starting', 'stopping'].includes(status.state);
  const stale = !!(draft || remove || reset) && (revision !== saved.revision || remoteRevision !== remote.revision);
  const previous = saved.providers.find(item => item.id === draft?.id);
  const base = { workspace_id: settings.workspace_id, expected_revision: revision, expected_remote_revision: remoteRevision };

  function clear() {
    setDraft(null); setSecret(''); setClearSecret(false); setCaPem(''); setClearCa(false);
    setDiscovered(null); setManual(false); setReviewed(false); setRemove(null); setReset(false);
    setError(undefined); setFormKey(key => key + 1);
  }
  function begin(provider?: CompanyProviderSettings) {
    clear(); setNotice(''); setRevision(saved!.revision); setRemoteRevision(remote!.revision);
    let id = 'company';
    for (let index = 2; saved!.providers.some(item => item.id === id); index++) id = `company-${index}`;
    setDraft(provider ? { id: provider.id, name: provider.name, issuer: provider.issuer,
      authorization_url: provider.authorization_url, token_url: provider.token_url, jwks_url: provider.jwks_url,
      client_id: provider.client_id, session_seconds: provider.session_seconds } : {
      id, name: 'Company account', issuer: '', authorization_url: '', token_url: '', jwks_url: '', client_id: '', session_seconds: 28800,
    });
    setManual(!!provider);
  }
  function edit(patch: Partial<CompanyProviderSettings>) {
    setDraft(current => current ? { ...current, ...patch } : null); setReviewed(false); setError(undefined); setNotice('');
    if (patch.issuer !== undefined) setDiscovered(null);
  }
  async function refresh() {
    setBusy(true); setError(undefined);
    try { const next = await desktop!.localStatus!(); if (live.current) onStatus(next); }
    catch (error) { if (live.current) setError(error); }
    finally { if (live.current) setBusy(false); }
  }
  async function discover() {
    if (!draft) return;
    setBusy(true); setError(undefined); setReviewed(false); setDiscovered(null);
    try {
      const result = await desktop!.localCompanyDiscover!({ ...base, issuer: draft.issuer.trim(),
        ...(clearCa ? { ca_pem: null } : caPem ? { ca_pem: caPem } : {}) });
      if (live.current) {
        setDiscovered(result);
        setDraft(current => current ? { ...current, issuer: result.issuer, authorization_url: result.authorization_url, token_url: result.token_url, jwks_url: result.jwks_url } : null);
        setNotice('Provider settings read. Review the addresses and finish its client registration before saving.');
      }
    } catch (error) { if (live.current) setError(error); }
    finally { if (live.current) setBusy(false); }
  }
  async function save(change: CompanyChange) {
    setBusy(true); setError(undefined); setNotice('');
    try {
      const next = await desktop!.localCompany!(change);
      if (live.current) {
        onStatus(next); clear();
        setNotice(next.state === 'starting' ? 'Company settings saved. The local workspace is restarting.' : 'Company settings saved. Start this workspace to apply them.');
      }
    } catch (error) { if (live.current) setError(error); }
    finally { if (live.current) setBusy(false); }
  }
  const pending = !!(draft || remove || reset);
  return <section className="ws-device-settings ws-company-setup" aria-labelledby="company-setup-title">
    <div className="ws-memory-heading"><h2 id="company-setup-title"><Building2 size={20} />Company sign-in setup</h2><span className="ws-badge">{saved.state === 'external' ? 'Host managed' : `${saved.providers.length} ${saved.providers.length === 1 ? 'provider' : 'providers'}`}</span></div>
    <p>Connect your organization’s existing identity provider to <strong>{settings.workspace_name}</strong>, hosted on this computer.</p>
    <p className={`ws-notice${saved.state === 'configuration_error' ? ' ws-error' : ''}`} role="status">{saved.message}</p>
    {!saved.callback_uri && saved.state !== 'external' && <p className="ws-notice">First enable an HTTPS address in <strong>Remote access</strong> above. Mnemion will then show the callback address to register with your identity provider.</p>}
    {saved.callback_uri && <div className="ws-notice"><strong>Register this callback address with your provider</strong><p className="ws-local-path">{saved.callback_uri}</p><button type="button" className="ws-button ws-quiet" onClick={async () => {
      try { await navigator.clipboard.writeText(saved.callback_uri!); setNotice('Callback address copied.'); }
      catch { setNotice('Select the callback address above and copy it manually.'); }
    }}><Copy size={14} />Copy callback address</button><p>Use an OpenID Connect client with authorization code and PKCE (S256). A confidential client uses HTTP Basic client authentication; a public client needs no secret.</p></div>}
    {!!error && <p className="ws-notice ws-error" role="alert">{localError(error)}</p>}
    {notice && <p className="ws-notice" role="status">{notice}</p>}
    {!!saved.providers.length && <ul className="ws-company-provider-list">{saved.providers.map(provider => <li key={provider.id}>
      <strong>{provider.name}</strong><span className="ws-local-path">{provider.issuer}</span><small>{provider.session_seconds / 60} minute sessions · {provider.has_client_secret ? 'Confidential client' : 'Public client'}</small>
      <div className="ws-setup-actions"><button type="button" className="ws-button ws-quiet" disabled={working || pending} onClick={() => begin(provider)}>Edit</button><button type="button" className="ws-button ws-quiet" disabled={working || pending} onClick={() => {
        clear(); setRemove(provider.id); setRevision(saved.revision); setRemoteRevision(remote.revision); setNotice('');
      }}>Remove</button></div>
    </li>)}</ul>}
    {remove && <div className="ws-notice"><p>Remove <strong>{saved.providers.find(item => item.id === remove)?.name ?? remove}</strong> and its saved client secret? Company connections using this provider cannot authenticate while it is removed. Revoke its identity links in Account & sessions if it is being retired permanently.</p><button type="button" className="ws-button" disabled={working || stale} onClick={() => void save({ ...base, action: 'remove', provider_id: remove })}>Remove provider and restart</button><button type="button" className="ws-button ws-quiet" disabled={working} onClick={clear}>Cancel</button></div>}
    {saved.state === 'configuration_error' && saved.repairable && <div className="ws-notice"><p>Reset retains a private copy of the damaged settings. You will need to configure providers again; memory, workspace members and personal logins are retained.</p><label className="ws-checkbox"><input type="checkbox" checked={reset} disabled={working} onChange={event => { setReset(event.target.checked); setRevision(saved.revision); setRemoteRevision(remote.revision); }} /><span>I understand that company providers will be cleared.</span></label><button type="button" className="ws-button" disabled={!reset || working || stale} onClick={() => void save({ ...base, action: 'reset' })}>Reset company settings</button></div>}
    {!pending && saved.state !== 'configuration_error' && <button type="button" className="ws-button" disabled={working || !saved.repairable || !saved.callback_uri || saved.providers.length >= 32} onClick={() => begin()}><Plus size={15} />Add company provider</button>}
    {draft && <form key={formKey} onSubmit={event => {
      event.preventDefault();
      if (!reviewed || stale || (!discovered && !manual)) return;
      void save({ ...base, action: 'save', provider: draft, ...(secret ? { client_secret: secret } : {}), clear_client_secret: clearSecret,
        ...(clearCa ? { ca_pem: null } : caPem ? { ca_pem: caPem } : {}) });
    }} aria-busy={busy}>
      <fieldset disabled={working || stale} className="ws-setup-fields">
        <h3>{previous ? `Edit ${previous.name}` : 'Add your company provider'}</h3>
        <label className="ws-field"><span>Button label</span><input value={draft.name} onChange={event => edit({ name: event.target.value })} maxLength={100} required /></label>
        <label className="ws-field"><span>Company issuer address</span><input type="url" value={draft.issuer} onChange={event => edit({ issuer: event.target.value })} placeholder="https://login.your-company.com" autoComplete="off" spellCheck={false} maxLength={2048} required /></label>
        <small>Use the exact issuer supplied by your identity administrator, including a realm or tenant path when required.</small>
        <details className="ws-setup-advanced"><summary>Company certificate authority</summary><p>For a private provider, paste its trusted PEM certificates. These trust roots apply to every company provider on this host. Leave blank to retain {saved.has_custom_ca ? 'the saved company certificates' : 'system certificate trust'}.</p><label className="ws-field"><span>Trusted CA certificates (PEM)</span><textarea value={caPem} disabled={clearCa} onChange={event => { setCaPem(event.target.value); setDiscovered(null); setReviewed(false); }} maxLength={8192} rows={5} autoComplete="off" spellCheck={false} /></label>{saved.has_custom_ca && <label className="ws-checkbox"><input type="checkbox" checked={clearCa} onChange={event => { setClearCa(event.target.checked); setCaPem(''); setDiscovered(null); setReviewed(false); }} /><span>Remove custom certificates and use system trust</span></label>}</details>
        <button type="button" className="ws-button" disabled={!draft.issuer} onClick={() => void discover()}>{busy ? <LoaderCircle className="ws-spin" size={15} /> : <RefreshCw size={15} />}Read provider settings</button>
        <label className="ws-field"><span>Client ID</span><input value={draft.client_id} onChange={event => edit({ client_id: event.target.value })} autoComplete="off" spellCheck={false} maxLength={512} required /></label>
        <label className="ws-field"><span>Client secret (confidential clients only)</span><input type="password" value={secret} disabled={clearSecret} onChange={event => { setSecret(event.target.value); setReviewed(false); }} placeholder={previous?.has_client_secret ? 'Saved — leave blank to retain it' : 'Leave blank for a public client'} maxLength={2048} autoComplete="off" spellCheck={false} /></label>
        <small>The secret stays in this host’s private operator files and is never shown in saved settings.</small>
        {previous?.has_client_secret && <label className="ws-checkbox"><input type="checkbox" checked={clearSecret} onChange={event => { setClearSecret(event.target.checked); setSecret(''); setReviewed(false); }} /><span>Remove the saved secret and use a public client</span></label>}
        <label className="ws-field"><span>Maximum session length (minutes)</span><input type="number" min={15} max={1440} step={1} value={draft.session_seconds / 60} onChange={event => edit({ session_seconds: event.target.valueAsNumber * 60 })} required /></label>
        <small>The default is 8 hours. Refreshing an assistant connection does not extend this maximum.</small>
        {(discovered || manual) && <div className="ws-notice"><strong>Review the provider endpoints</strong>{(['authorization_url', 'token_url', 'jwks_url'] as const).map(field => <p key={field}><small>{field === 'authorization_url' ? 'Sign-in page' : field === 'token_url' ? 'Token exchange' : 'Signing keys'}</small><span className="ws-local-path">{draft[field]}</span></p>)}</div>}
        <details className="ws-setup-advanced"><summary>Manual provider settings</summary><label className="ws-checkbox"><input type="checkbox" checked={manual} onChange={event => { setManual(event.target.checked); setReviewed(false); }} /><span>Enter provider endpoints manually</span></label>{manual && <>{(['authorization_url', 'token_url', 'jwks_url'] as const).map(field => <label className="ws-field" key={field}><span>{field === 'authorization_url' ? 'Authorization URL' : field === 'token_url' ? 'Token URL' : 'Signing keys URL'}</span><input type="url" value={draft[field]} onChange={event => edit({ [field]: event.target.value })} maxLength={2048} autoComplete="off" spellCheck={false} required /></label>)}<small>Provider identifier: {draft.id}. Keep it stable for existing company identity links.</small></>}</details>
        {previous && <p className="ws-notice">Changing the issuer, client, endpoints, public/confidential mode or session duration requires an administrator to approve identity links again. Changing only the label or rotating an existing secret preserves them.</p>}
        <label className="ws-checkbox"><input type="checkbox" checked={reviewed} onChange={event => setReviewed(event.target.checked)} required /><span>I registered the callback address and reviewed this provider and its endpoints.</span></label>
      </fieldset>
      <p>Saving briefly restarts a running local workspace. Team and assistant connections resume when it is ready.</p>
      <div className="ws-setup-actions"><button type="submit" className="ws-button ws-primary" disabled={working || stale || !reviewed || (!discovered && !manual) || !saved.callback_uri}><Check size={15} />Save company provider</button><button type="button" className="ws-button ws-quiet" disabled={working} onClick={() => { clear(); setNotice(''); }}>Cancel edits</button></div>
    </form>}
    {stale && <p className="ws-notice" role="status">Another operator changed company or remote settings. Cancel these edits and review the current configuration before saving.</p>}
    <div className="ws-setup-actions"><button type="button" className="ws-button ws-quiet" disabled={working} onClick={() => void refresh()}><RefreshCw size={14} />Refresh company status</button>{connected && <Link className="ws-button ws-quiet" to="/workspace/account">Invite people & manage identity links</Link>}</div>
    <p>Only invited or explicitly linked people can sign in. Provider registration alone does not admit everyone in your company.</p>
    <Link className="ws-link" to="/workspace/help?doc=docs%2Fservice%2Fcompany-sign-in.md">Company sign-in and agent setup guide</Link>
  </section>;
}
