import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, BookOpenCheck, Cpu, Database, HardDrive, LoaderCircle, Plug, RefreshCw, ShieldCheck, Users } from 'lucide-react';
import type { LocalStatus, MemoryOptions } from '../../../shared/local-workspace';
import { LiveMemory, MemoryFields, RepairMemory, validMemory } from './MemoryControls';
import { localError } from './LocalSetup';

export default function Setup({ endpoint, administrator }: { endpoint: string; administrator: boolean }) {
  const desktop = window.mnemion;
  const [status, setStatus] = useState<LocalStatus>();
  const [options, setOptions] = useState<MemoryOptions>({ mode: 'auto', limit_mib: null });
  const [revision, setRevision] = useState<string>();
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const [saved, setSaved] = useState(false);
  const live = useRef(true);
  useEffect(() => {
    live.current = true;
    void desktop?.localStatus?.().then(value => { if (live.current) setStatus(value); }).catch(error => { if (live.current) setError(error); });
    const unsubscribe = desktop?.onLocalStatus?.(value => { if (live.current) setStatus(value); });
    return () => { live.current = false; unsubscribe?.(); };
  }, [desktop]);
  useEffect(() => {
    if (dirty || !status?.info?.memory_policy) return;
    setOptions(status.info.memory_policy.settings);
    setRevision(status.info.memory_policy.revision);
  }, [dirty, status?.info?.memory_policy]);

  const steps = [
    { to: 'agents', title: 'Connect your assistants', description: 'Create scoped keys and use the MCP and API connection guides.', icon: Plug },
    ...(administrator ? [
      { to: 'team', title: 'Organize your team', description: 'Give each person and app access to the spaces they need.', icon: Users },
      { to: 'connections', title: 'Bring in your sources', description: 'Manage source connections, permissions and synchronization.', icon: Database },
      { to: 'models', title: 'Choose your memory models', description: 'Review local and operator-approved providers for each space.', icon: Cpu },
      { to: 'librarian', title: 'Configure your librarian', description: 'Let an approved model propose memory improvements for review.', icon: BookOpenCheck },
    ] : []),
    { to: 'obsidian', title: 'Open your visual memory', description: 'Refresh an Obsidian vault with linked, traceable memories.', icon: HardDrive },
  ];
  return <div className="ws-setup-page">
    <header className="ws-page-heading"><div><p className="ws-eyebrow">Make Mnemion yours</p><h1>Setup & this device</h1><p>Your workspace, connections and local resources in one place.</p></div></header>
    <div className="ws-setup-connected"><ShieldCheck size={19} /><div><strong>Connected workspace</strong><span>{endpoint}</span></div></div>
    {!!error && <div className="ws-notice ws-error" role="alert">{localError(error)}</div>}
    {status?.info?.configured && <section className="ws-device-settings">
      <div className="ws-memory-heading"><h2>RAM on this computer</h2><span className="ws-badge">{status.state === 'running' ? 'Local workspace running' : status.state}</span></div>
      <p>These controls manage <strong>{status.info.settings?.workspace_name}</strong> on this device. A workspace hosted elsewhere uses that host’s resource settings.</p>
      {status.memory && <LiveMemory value={status.memory} />}
      {status.info.memory_recovery ? <RepairMemory status={status} onStatus={(next, repaired) => { setStatus(next); setDirty(false); setSaved(!!repaired); }} /> : <form onSubmit={async event => {
        event.preventDefault(); setBusy(true); setError(undefined); setSaved(false);
        try {
          const next = await desktop!.localMemory!({ ...options, expected_revision: revision });
          if (live.current) { setStatus(next); setDirty(false); setSaved(true); }
        } catch (error) { if (live.current) setError(error); }
        finally { if (live.current) setBusy(false); }
      }}>
        <MemoryFields value={options} resources={status.info.resources} disabled={busy} onChange={value => { setOptions(value); setDirty(true); setSaved(false); }} />
        <div className="ws-setup-actions"><button className="ws-button ws-primary" disabled={busy || !dirty || !validMemory(options)}>{busy ? <LoaderCircle className="ws-spin" size={16} /> : <CheckIcon />}Apply RAM budget</button>{dirty && <button type="button" className="ws-button ws-quiet" disabled={busy} onClick={() => { setDirty(false); setError(undefined); }}><RefreshCw size={15} />Use current settings</button>}</div>
        {saved && <p className="ws-memory-saved" role="status">{status.state === 'running' ? 'RAM budget saved. The running engine applies it within a few seconds.' : 'RAM budget saved for the next local start.'} Active calculations finish safely.</p>}
        {saved && !['running', 'starting', 'stopping'].includes(status.state) && <button type="button" className="ws-button" disabled={busy} onClick={async () => {
          setBusy(true); setError(undefined);
          try { const next = await desktop!.localStart!(); if (live.current) setStatus(next); }
          catch (error) { if (live.current) setError(error); }
          finally { if (live.current) setBusy(false); }
        }}>Resume local workspace</button>}
      </form>}
      <details className="ws-setup-advanced"><summary>Local storage & agent controls</summary><p className="ws-local-path">{status.info.data_directory}</p><p>Host agents can read the current budget with <code>mnemion-service local status --root &lt;data-folder&gt;</code> and change it through <code>local memory</code>. These are local operator commands; workspace API keys do not grant access to this computer’s settings.</p><Link className="ws-link" to="/workspace/help?doc=docs%2Fservice%2Fmemory-resources.md">RAM policy and agent examples<ArrowRight size={13} /></Link></details>
    </section>}
    {!status?.info?.configured && <div className="ws-notice">{desktop ? 'This device is connected as a client. Its workspace host controls model and database RAM. Create a local workspace from the welcome screen to manage hosting here.' : 'You are using the web app. The workspace host controls model and database RAM.'}</div>}
    <div className="ws-setup-guide">{steps.map(({ to, title, description, icon: Icon }) => <Link className="ws-setup-card" to={`/workspace/${to}`} key={to}><Icon size={21} /><div><h3>{title}</h3><p>{description}</p></div><ArrowRight size={17} /></Link>)}</div>
    <section className="ws-setup-footer"><h2>Keep it running smoothly</h2><p>Desktop startup, background mode and automatic updates are controlled in the app’s <strong>Background and updates</strong> menu. Use Insights & evaluations to check retrieval, indexing and service health.</p><div><Link className="ws-button" to="/workspace/insights">Open insights</Link><Link className="ws-button ws-quiet" to="/workspace/help">Documentation, recovery & roadmap<ArrowRight size={14} /></Link></div></section>
  </div>;
}

function CheckIcon() { return <ShieldCheck size={16} />; }
