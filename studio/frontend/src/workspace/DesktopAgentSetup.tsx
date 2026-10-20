import { useState, type FormEvent } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { Check, FolderOpen, PlugZap, RefreshCw, Trash2 } from 'lucide-react';
import type { AgentInstallation, AgentPreview, AgentSetupResult } from '../../../shared/desktop-agents';
import type { Connection } from './connection-types';

export const desktopAgentNames: Record<string, string> = {
  codex: 'Codex', 'grok-build': 'Grok Build', 'claude-code': 'Claude Code',
  'claude-desktop': 'Claude Desktop', cursor: 'Cursor', 'gemini-cli': 'Gemini CLI',
  zed: 'Zed', devin: 'Devin Desktop · Cascade', windsurf: 'Windsurf · legacy Cascade', generic: 'Another MCP client',
};
const failure = (error: unknown) => error instanceof Error ? error.message : 'Agent setup could not finish.';

export function DesktopAgentInstallations() {
  const native = window.mnemion, cache = useQueryClient();
  const query = useQuery({ queryKey: ['desktop-agent-setups'], queryFn: () => native!.agentSetupStatus!(), enabled: !!native?.agentSetupStatus, refetchInterval: 30000 });
  const [remove, setRemove] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  if (!native?.agentSetupStatus || (!query.error && !query.data?.installations.length)) return null;
  async function uninstall(item: AgentInstallation) {
    setBusy(true); setError(undefined);
    try {
      await native!.agentSetupRemove!({ id: item.id, configuration_hash: item.configuration_hash, confirm: true });
      await query.refetch(); setRemove(undefined);
    } catch (error) { setError(failure(error)); await cache.invalidateQueries({ queryKey: ['desktop-agent-setups'] }); }
    finally { setBusy(false); }
  }
  return <details className="ws-device-settings ws-local-sources" data-update-pending={busy || remove ? '' : undefined}>
    <summary><PlugZap size={18} /> Agent connections on this computer{query.data ? ` · ${query.data.installations.length}` : ''}</summary>
    <p>Review installed configuration, or remove this computer’s setup while signed out. Agent tools still use the workspace’s permissions.</p>
    {query.data?.runtime_version && <p className="ws-helper">Private agent runtime {query.data.runtime_version}. Studio refreshes it automatically; open agent sessions keep their current runtime until reopened.</p>}
    {query.data?.runtime_attention && <p className="ws-notice" role="alert">{query.data.runtime_attention}</p>}
    {(error || query.error) && <p className="ws-notice ws-error" role="alert">{error ?? failure(query.error)}</p>}
    {query.data?.installations.map(item => <section className="ws-card" key={item.id}>
      <div className="ws-section-title"><h3>{desktopAgentNames[item.client] ?? item.client} · {item.server_name}</h3><span className="ws-badge">{{ installed: 'Configuration installed', key_missing: 'Private key file missing', replaced: 'Entry changed in agent', removed: 'Entry absent', unverified: 'Needs inspection' }[item.state]}</span></div>
      <p className="ws-helper" style={{ overflowWrap: 'anywhere' }}>{item.endpoint}<br />{item.config_path}</p>
      <p className="ws-helper">Reopen the agent after configuration changes. Installed configuration does not prove that the agent has loaded its tools.</p>
      <button type="button" className="ws-button" disabled={busy || item.state === 'unverified'} onClick={() => setRemove(item.id)}><Trash2 size={15} />Remove this setup</button>
      {remove === item.id && <div className="ws-notice"><p>Remove this installed entry and its private key file? Manually copied configurations that reference this same file will stop working. An entry changed outside Mnemion is preserved. The server key remains revocable in People & apps.</p><button className="ws-button" disabled={busy} onClick={() => void uninstall(item)}>Confirm removal</button><button className="ws-button" disabled={busy} onClick={() => setRemove(undefined)}>Cancel</button></div>}
    </section>)}
    <Link className="ws-link" to="/help?doc=docs%2Fservice%2Fdesktop-agents.md">Agent installation guide</Link>
  </details>;
}

export function DesktopAgentSetup({ connection }: { connection: Connection }) {
  const native = window.mnemion, cache = useQueryClient();
  const status = useQuery({ queryKey: ['desktop-agent-setups'], queryFn: () => native!.agentSetupStatus!(), enabled: !!native?.agentSetupStatus });
  const people = useQuery({ queryKey: ['principals'], queryFn: () => connection.client.principals(), enabled: connection.me.administrator });
  const [client, setClient] = useState('codex');
  const [principal, setPrincipal] = useState('');
  const [name, setName] = useState('mnemion');
  const [path, setPath] = useState('');
  const [key, setKey] = useState('');
  const [preview, setPreview] = useState<AgentPreview>();
  const [replace, setReplace] = useState(false);
  const [approved, setApproved] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const [result, setResult] = useState<AgentSetupResult>();
  const profile = status.data?.profiles.find(item => item.client === client);
  const applications = people.data?.items.filter(item => item.kind === 'application' && !item.administrator && !item.disabled_at) ?? [];
  if (!native?.agentSetupStatus) return null;
  function changed() { setDirty(true); setPreview(undefined); setApproved(false); setReplace(false); setResult(undefined); }
  async function review(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(undefined); setResult(undefined);
    try {
      setPreview(await native!.agentSetupPreview!({ client, server_name: name, ...(path ? { config_path: path } : {}),
        endpoint: connection.endpoint, tenant_id: connection.me.tenant_id, principal_id: principal }));
      setApproved(false); setReplace(false); setDirty(true);
    } catch (error) { setError(failure(error)); }
    finally { setBusy(false); }
  }
  async function install() {
    if (!preview || !approved) return;
    setBusy(true); setError(undefined);
    let createdKey: string | undefined;
    try {
      const current = await native!.agentSetupStatus!();
      cache.setQueryData(['desktop-agent-setups'], current);
      if (current.installations.some(item => item.id === preview.setup.id)) {
        setPreview(undefined); setApproved(false); setReplace(false);
        throw new Error('This setup already has a private installation record. Review its status below before installing another connection.');
      }
      let credential = key;
      if (!credential) {
        const issued = await connection.client.createKey(principal, `${desktopAgentNames[client]} · ${name}`.slice(0, 200));
        credential = issued.api_key; createdKey = issued.id;
      }
      setResult(await native!.agentSetupInstall!({ setup: preview.setup, configuration_hash: preview.configuration_hash,
        credential, confirm: true, replace_existing: replace }));
      setPreview(undefined); setKey(''); setDirty(false); setApproved(false); setReplace(false);
      await cache.invalidateQueries({ queryKey: ['desktop-agent-setups'] });
    } catch (error) {
      let message = failure(error);
      if (createdKey) {
        try {
          const observed = await native!.agentSetupStatus!(); cache.setQueryData(['desktop-agent-setups'], observed);
          // A settings write can finish before its reply is lost. Revoke only
          // when the private installation record definitely does not exist.
          if (!observed.installations.some(item => item.id === preview.setup.id)) await connection.client.revokeKey(createdKey);
          else {
            setPreview(undefined); setApproved(false); setReplace(false);
            message += ' Review this installation before retrying or revoking its key.';
          }
        } catch { message += ' Check this application’s keys in People & apps before creating another key.'; }
      }
      setError(message);
    } finally { setBusy(false); }
  }
  return <>
    <section className="ws-card ws-agent-native-setup" data-update-pending={busy || dirty || key || preview ? '' : undefined}>
      <div className="ws-section-title"><h2><PlugZap size={18} /> Connect an agent on this computer</h2><button type="button" className="ws-button" disabled={busy} onClick={() => void status.refetch()}><RefreshCw size={15} />Refresh</button></div>
      <p>Choose the agent and its dedicated application. Review the exact configuration before installing it. Studio prepares a private copy of its included engine that connects independently when Studio is closed; no separate Python installation is needed.</p>
      <p className="ws-helper">Create an application and grant its intended spaces in <Link className="ws-link" to="/workspace/team">People & apps</Link>. Administrator identities cannot be installed as background agent keys. Workspaces with different permissions can use different connection names.</p>
      {(error || status.error || people.error) && <p className="ws-notice ws-error" role="alert">{error ?? failure(status.error ?? people.error)}</p>}
      {result && <div className="ws-notice" role="status"><p><Check size={16} /> Configuration saved. Reopen {desktopAgentNames[result.installation.client]} and check that its memory tools are available.</p><p className="ws-helper">{result.installation.config_path}</p>{result.backup && <p className="ws-helper" style={{ overflowWrap: 'anywhere' }}>Previous settings backup: {result.backup}</p>}</div>}
      <form className="ws-connector-form" onSubmit={event => void review(event)}>
        <label>Agent<select data-update-safe value={client} disabled={busy} onChange={event => { setClient(event.target.value); setPath(''); changed(); }}>{Object.entries(desktopAgentNames).map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select></label>
        {connection.me.administrator ? <label>Application<select data-update-safe value={principal} disabled={busy} onChange={event => { setPrincipal(event.target.value); changed(); }} required><option value="">Choose an application</option>{applications.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label> : <label>Application ID<input data-update-safe value={principal} disabled={busy} onChange={event => { setPrincipal(event.target.value); changed(); }} required placeholder="The dedicated application's ID" /></label>}
        <label>Connection name<input data-update-safe value={name} disabled={busy} maxLength={64} pattern="[A-Za-z]([A-Za-z0-9_]|-){0,63}" onChange={event => { setName(event.target.value); changed(); }} required /></label>
        <label>Agent configuration file<input data-update-safe value={path || profile?.config_path || ''} readOnly placeholder="Choose the agent’s configuration file" /></label>
        <button type="button" className="ws-button" disabled={busy} onClick={async () => {
          try { const selected = await native!.agentSetupChoose!(client); if (selected) { setPath(selected); changed(); } }
          catch (error) { setError(failure(error)); }
        }}><FolderOpen size={15} />Choose another file</button>
        <label>{connection.me.administrator ? 'Existing application key (optional)' : 'Dedicated application key'}<input data-update-safe type="password" autoComplete="new-password" value={key} disabled={busy} onChange={event => { setKey(event.target.value); setDirty(true); }} required={!connection.me.administrator} /></label>
        {connection.me.administrator && <p className="ws-helper">Leave the key blank to create one for the selected application when you install.</p>}
        <button className="ws-button ws-primary" disabled={busy || !principal || !name || !(path || profile?.config_path)}>Review connection</button>
      </form>
      {preview && <div className="ws-notice"><h3>Review {desktopAgentNames[client]} setup</h3><p style={{ overflowWrap: 'anywhere' }}>{preview.setup.config_path}</p><pre className="ws-code">{preview.snippet}</pre>
        <p>The agent’s key is stored in a private file for your OS account. It is not encrypted with Studio’s keychain, so the agent can connect without Studio running. Configuration contains the file path, never the key. Keep this computer’s setup files out of shared folders and backups without encryption.</p>
        {preview.replacing && <label className="ws-checkbox"><input data-update-safe type="checkbox" checked={replace} onChange={event => setReplace(event.target.checked)} />Replace the existing {preview.setup.server_name} entry. Other agent settings and servers remain.</label>}
        <label className="ws-checkbox"><input data-update-safe type="checkbox" checked={approved} onChange={event => setApproved(event.target.checked)} />I have closed the agent and reviewed this application’s permissions and configuration.</label>
        <button type="button" className="ws-button ws-primary" disabled={busy || !approved || (preview.replacing && !replace)} onClick={() => void install()}><PlugZap size={16} />Install connection</button>
      </div>}
      {dirty && <button type="button" className="ws-button" disabled={busy} onClick={() => { setPreview(undefined); setKey(''); setDirty(false); setApproved(false); setReplace(false); setError(undefined); }}>Discard setup</button>}
      <p className="ws-helper">This sets up memory tools. Conversation capture stays separate in Connections. WSL and Windows have separate agent profiles; use the app on the side where the agent runs.</p>
    </section>
    <DesktopAgentInstallations />
  </>;
}
