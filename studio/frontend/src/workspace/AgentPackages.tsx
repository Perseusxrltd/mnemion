import { useEffect, useRef, useState } from 'react';
import { Download } from 'lucide-react';
import { MnemionError, type AgentPackageProvider, type MnemionClient } from '@mnemion/client';
import { Link } from 'react-router-dom';

const providers: { id: AgentPackageProvider; label: string; kind: string }[] = [
  { id: 'openai', label: 'OpenAI / Codex', kind: 'plugin' },
  { id: 'claude', label: 'Claude Code', kind: 'plugin' },
  { id: 'grok-build', label: 'Grok Build', kind: 'plugin' },
  { id: 'hermes', label: 'Hermes', kind: 'configuration' },
  { id: 'openclaw', label: 'OpenClaw', kind: 'configuration' },
  { id: 'grokbot', label: 'Grok Bot', kind: 'guide' },
];

export function AgentPackages({ client, address }: { client: MnemionClient; address: string }) {
  const [provider, setProvider] = useState<AgentPackageProvider>('openai');
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [message, setMessage] = useState('');
  const generation = useRef(0);
  useEffect(() => { generation.current++; setBusy(false); setError(''); setMessage(''); return () => { generation.current++; }; }, [client, address]);
  const selected = providers.find(item => item.id === provider)!;
  async function download() {
    if (busy) return;
    const ticket = ++generation.current, expected = provider;
    setBusy(true); setError(''); setMessage('');
    try {
      const file = await client.agentPackage(expected);
      if (ticket !== generation.current) return;
      if (file.author !== 'Perseus XR' || file.provider !== expected || file.contains_credentials !== false || file.content_base64.length > 180000 || !/^mnemion-[a-z-]+-\d+\.\d+\.\d+\.zip$/.test(file.filename)) throw new Error('The connection package did not match this download. Retry or contact your host operator.');
      const data = Uint8Array.from(atob(file.content_base64), value => value.charCodeAt(0));
      const digest = new Uint8Array(await crypto.subtle.digest('SHA-256', data));
      if ([...digest].map(value => value.toString(16).padStart(2, '0')).join('') !== file.sha256) throw new Error('The connection package checksum did not match. Retry the download.');
      if (ticket !== generation.current) return;
      const url = URL.createObjectURL(new Blob([data], { type: 'application/zip' }));
      const link = document.createElement('a'); link.href = url; link.download = file.filename;
      document.body.appendChild(link); link.click(); link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      setMessage('Download requested. Open README.md in the package for the connection steps.');
    } catch (failure) {
      if (ticket === generation.current) setError(failure instanceof MnemionError && failure.status === 404 ? 'Update this workspace’s server to download connection packages. You can use the MCP address above now.' : failure instanceof Error ? failure.message : 'The connection package could not be downloaded.');
    } finally { if (ticket === generation.current) setBusy(false); }
  }
  return <div className="ws-agent-package" data-update-pending={busy ? '' : undefined}>
    <h3>Get your agent’s connection package</h3>
    <p>Prepared for this workspace by Perseus XR. Sign in through the agent after installation.</p>
    <label className="ws-field"><span>Agent</span><select value={provider} disabled={busy} onChange={event => { setProvider(event.target.value as AgentPackageProvider); setMessage(''); setError(''); }}>{providers.map(item => <option key={item.id} value={item.id}>{item.label} · {item.kind === 'guide' ? 'connection guide' : item.kind}</option>)}</select></label>
    {selected.kind === 'configuration' && <p className="ws-helper">Includes native settings to merge into the selected agent profile. Keep its other settings and connections.</p>}
    {selected.kind === 'guide' && <p className="ws-helper">Includes the workspace address and supported connection steps. Grok Bot’s available connectors depend on your account; this guide is not a marketplace plugin.</p>}
    <button type="button" className="ws-button" disabled={busy} onClick={() => void download()}><Download size={15} />{busy ? 'Preparing…' : `Download ${selected.kind === 'guide' ? 'connection guide' : selected.kind}`}</button>
    {message && <p role="status">{message}</p>}
    {error && <p className="ws-notice ws-error" role="alert">{error}</p>}
    <p className="ws-helper">No password or API key is included. <Link className="ws-link" to="/workspace/help?doc=docs%2Fservice%2Fagent-packages.md">Setup and supported clients</Link></p>
  </div>;
}
