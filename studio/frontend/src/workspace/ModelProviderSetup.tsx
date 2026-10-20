import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { Check, Cpu, LoaderCircle, Plus, RefreshCw } from 'lucide-react';
import type { LocalStatus } from '../../../shared/local-workspace';
import type { EmbeddingProviderSettings, LibrarianProviderSettings, ModelDefinition, ModelKind, ModelsChange, SavedModelProvider } from '../../../shared/local-models';
import { localError } from './LocalSetup';
import './model-provider-setup.css';

function address(kind: ModelKind, connection: string) {
  if (connection === 'ollama') return `http://127.0.0.1:11434/api/${kind === 'embedding' ? 'embed' : 'chat'}`;
  if (connection === 'compatible') return `http://127.0.0.1:1234/v1/${kind === 'embedding' ? 'embeddings' : 'chat/completions'}`;
  return '';
}

export default function ModelProviderSetup({ status, onStatus, connected = false }: {
  status: LocalStatus; onStatus: (status: LocalStatus) => void; connected?: boolean;
}) {
  const desktop = window.mnemion, saved = status.info?.model_access, settings = status.info?.settings;
  const [draft, setDraft] = useState<ModelDefinition | null>(null), [editing, setEditing] = useState(false);
  const [revision, setRevision] = useState(''), [connection, setConnection] = useState('ollama');
  const [apiKey, setApiKey] = useState(''), [clearKey, setClearKey] = useState(false);
  const [ca, setCa] = useState(''), [clearCa, setClearCa] = useState(false);
  const [reviewed, setReviewed] = useState(false), [approved, setApproved] = useState(false);
  const [remove, setRemove] = useState<SavedModelProvider | null>(null), [reset, setReset] = useState(false);
  const [busy, setBusy] = useState(false), [error, setError] = useState<unknown>(), [notice, setNotice] = useState('');
  const live = useRef(true);
  useEffect(() => { live.current = true; return () => { live.current = false; }; }, []);
  useEffect(() => { clear(); }, [settings?.workspace_id]);
  if (!desktop?.localModels || !saved || !settings) return null;
  const working = busy || ['starting', 'stopping'].includes(status.state);
  const pending = !!(draft || remove || reset), stale = pending && saved.revision !== revision;
  const previous = saved.providers.find(p => p.kind === draft?.kind && p.profile.id === draft.profile.id);
  const base = { workspace_id: settings.workspace_id, expected_revision: revision };

  function clear() {
    setDraft(null); setEditing(false); setApiKey(''); setClearKey(false); setCa(''); setClearCa(false);
    setReviewed(false); setApproved(false); setRemove(null); setReset(false); setError(undefined);
  }
  function begin(kind: ModelKind, provider?: SavedModelProvider) {
    clear(); setNotice(''); setRevision(saved!.revision); setConnection('ollama'); setEditing(!!provider);
    let id: string = kind;
    for (let index = 2; saved!.providers.some(p => p.kind === kind && p.profile.id === id); index++) id = `${kind}-${index}`;
    const common = { id, label: kind === 'embedding' ? 'My embedding model' : 'My librarian',
      protocol: 'ollama' as const, endpoint: address(kind, 'ollama'), model: '', revision: '' };
    setDraft(provider ? structuredClone({ kind: provider.kind, profile: provider.profile }) as ModelDefinition : kind === 'embedding'
      ? { kind, profile: { ...common, dimensions: 0 } }
      : { kind, profile: { ...common, context_budget: 8192, max_output_tokens: 1024 } });
  }
  function edit(patch: Partial<EmbeddingProviderSettings & LibrarianProviderSettings>) {
    setDraft(current => current ? { ...current, profile: { ...current.profile, ...patch } } as ModelDefinition : null);
    setReviewed(false); setApproved(false); setError(undefined); setNotice('');
  }
  async function refresh() {
    setBusy(true); setError(undefined);
    try { const next = await desktop!.localStatus!(); if (live.current) onStatus(next); }
    catch (error) { if (live.current) setError(error); }
    finally { if (live.current) setBusy(false); }
  }
  async function save(change: ModelsChange) {
    setBusy(true); setError(undefined); setNotice('');
    try {
      const next = await desktop!.localModels!(change);
      if (live.current) {
        onStatus(next); clear();
        setNotice(next.state === 'starting' ? 'Model settings saved. The local workspace is restarting; then choose the model for each space.' : 'Model settings saved. Resume this workspace to make the profiles available.');
      }
    } catch (error) { if (live.current) setError(error); }
    finally { if (live.current) { setBusy(false); setApiKey(''); } }
  }
  function submit(event: FormEvent) {
    event.preventDefault();
    if (!draft) return;
    if (!reviewed) { setReviewed(true); return; }
    if (!approved) return;
    void save({ ...base, action: 'save', provider: draft,
      ...(apiKey ? { api_key: apiKey } : {}), ...(clearKey ? { clear_api_key: true } : {}),
      ...(clearCa ? { ca_pem: null } : ca ? { ca_pem: ca } : {}) });
  }
  const fields = (items: Array<[string, number, number, number, string]>) => items.map(([key, min, max, fallback, title]) =>
    <label className="ws-field" key={key}><span>{title}</span><input type="number" min={min} max={max} step={1} required
      value={Number.isFinite((draft!.profile as Record<string, unknown>)[key] ?? fallback) ? Number((draft!.profile as Record<string, unknown>)[key] ?? fallback) : ''}
      onChange={event => edit({ [key]: event.target.valueAsNumber })} /></label>);

  return <section id="model-providers" className="ws-device-settings ws-company-setup ws-model-providers" aria-labelledby="model-providers-title" data-update-pending={pending || busy ? '' : undefined}>
    <div className="ws-memory-heading"><h2 id="model-providers-title"><Cpu size={20} />Your model providers</h2><span className="ws-badge">{saved.state === 'external' ? 'Host managed' : `${saved.providers.length} profiles`}</span></div>
    <p>Configure embedding and librarian models for <strong>{settings.workspace_name}</strong> on this computer. The built-in CPU embedding models stay available.</p>
    <p className={`ws-notice${saved.state === 'configuration_error' ? ' ws-error' : ''}`} role="status">{saved.message}</p>
    {!!error && <p className="ws-notice ws-error" role="alert">{localError(error)}</p>}
    {notice && <p className="ws-notice" role="status">{notice}</p>}
    {!!saved.providers.length && <ul className="ws-company-provider-list">{saved.providers.map(provider => <li key={`${provider.kind}/${provider.profile.id}`}>
      <strong>{provider.profile.label}</strong><span>{provider.kind === 'embedding' ? 'Embedding' : 'Librarian'} · {provider.profile.model}</span>
      <span className="ws-local-path">{provider.profile.endpoint}</span>
      <small>{provider.network_egress ? 'Network provider · space approval required' : 'Local provider'} · {provider.has_api_key ? 'Private key saved' : 'No API key'}{provider.has_custom_ca ? ' · Custom certificate trust' : ''}</small>
      <details><summary>Profile identity</summary><p>Profile {provider.profile.id} · Revision {provider.profile.revision}</p><code className="ws-local-path">{provider.fingerprint}</code></details>
      <div className="ws-setup-actions"><button type="button" className="ws-button ws-quiet" disabled={working || pending} onClick={() => begin(provider.kind, provider)}>Edit</button><button type="button" className="ws-button ws-quiet" disabled={working || pending} onClick={() => { clear(); setRemove(provider); setRevision(saved.revision); setNotice(''); }}>Remove</button></div>
    </li>)}</ul>}
    {remove && <div className="ws-notice"><p>Remove <strong>{remove.profile.label}</strong> and its saved key? Spaces using this profile will pause its processing until an available model is selected. Memories and existing indexes are retained.</p><div className="ws-setup-actions"><button type="button" className="ws-button" disabled={working || stale} onClick={() => void save({ ...base, action: 'remove', kind: remove.kind, profile_id: remove.profile.id })}>Remove profile</button><button type="button" className="ws-button ws-quiet" disabled={working} onClick={clear}>Cancel</button></div></div>}
    {saved.state === 'configuration_error' && saved.repairable && <div className="ws-notice"><p>Reset keeps a private copy of the damaged file. Recreate the model profiles afterward; workspace members and memories are retained.</p><label className="ws-checkbox"><input type="checkbox" checked={reset} disabled={working} onChange={event => { setReset(event.target.checked); setRevision(saved.revision); }} />I understand the custom profiles will be cleared.</label><button type="button" className="ws-button" disabled={working || !reset || stale} onClick={() => void save({ ...base, action: 'reset' })}>Reset model settings</button></div>}
    {saved.repairable && !pending && saved.state !== 'configuration_error' && <div className="ws-setup-actions">{(['embedding', 'librarian'] as const).map(kind => <button type="button" key={kind} className="ws-button" disabled={working || saved.providers.filter(p => p.kind === kind).length >= 8} onClick={() => begin(kind)}><Plus size={15} />Add {kind} model</button>)}</div>}
    {draft && <form className="ws-form" onSubmit={submit}><fieldset disabled={working}>
      <legend>{editing ? 'Edit' : 'Add'} {draft.kind} model</legend>
      {!editing && <label className="ws-field"><span>Connection</span><select value={connection} onChange={event => { setConnection(event.target.value); edit({ protocol: event.target.value === 'ollama' ? 'ollama' : 'openai', endpoint: address(draft.kind, event.target.value) }); }}><option value="ollama">Ollama on this computer</option><option value="compatible">Compatible local server</option><option value="cloud">Cloud or organization endpoint</option></select></label>}
      <div className="ws-model-fields"><label className="ws-field"><span>Display name</span><input value={draft.profile.label} maxLength={200} required onChange={event => edit({ label: event.target.value })} /></label><label className="ws-field"><span>Profile ID</span><input value={draft.profile.id} readOnly={editing} pattern="[a-z]([a-z0-9]|-)*" maxLength={64} required onChange={event => edit({ id: event.target.value })} /></label></div>
      <label className="ws-field"><span>Complete API endpoint</span><input type="url" value={draft.profile.endpoint} maxLength={2000} required placeholder={`https://provider.example/v1/${draft.kind === 'embedding' ? 'embeddings' : 'chat/completions'}`} onChange={event => edit({ endpoint: event.target.value })} /></label>
      <div className="ws-model-fields"><label className="ws-field"><span>Model name</span><input value={draft.profile.model} maxLength={300} required placeholder="Exact model name from your provider" onChange={event => edit({ model: event.target.value })} /></label><label className="ws-field"><span>Model revision</span><input value={draft.profile.revision} maxLength={300} required placeholder="Fixed revision or installed model digest" onChange={event => edit({ revision: event.target.value })} /></label></div>
      {draft.kind === 'embedding' && <label className="ws-field"><span>Embedding dimensions</span><input type="number" value={draft.profile.dimensions > 0 ? draft.profile.dimensions : ''} min={1} max={4096} step={1} required placeholder="From your model documentation" onChange={event => edit({ dimensions: event.target.valueAsNumber })} /></label>}
      <p className="ws-helper">Install and start a local model server first, or use an endpoint your organization provides. Mnemion does not download or start external models. The revision identifies what you approved; changing a mutable provider model requires updating its revision and reviewing the index.</p>
      <label className="ws-field"><span>{previous?.has_api_key ? 'Replacement API key (leave blank to retain)' : 'API key (if required)'}</span><input type="password" autoComplete="new-password" value={apiKey} maxLength={4096} disabled={clearKey} onChange={event => { setApiKey(event.target.value); setReviewed(false); setApproved(false); }} /></label>
      {previous?.has_api_key && <label className="ws-checkbox"><input type="checkbox" checked={clearKey} onChange={event => { setClearKey(event.target.checked); setApiKey(''); setReviewed(false); setApproved(false); }} />Remove the saved API key</label>}
      <details className="ws-setup-advanced"><summary>Protocol, capacity & certificate settings</summary>
        <p className="ws-helper">Embedding requests share one queue. Its capacity is the smallest approved profile limit and the host’s own limit (16 by default). External model-server RAM is managed by that server.</p>
        <div className="ws-model-fields"><label className="ws-field"><span>API protocol</span><select value={draft.profile.protocol} onChange={event => edit({ protocol: event.target.value as 'openai' | 'ollama' })}><option value="ollama">Ollama</option><option value="openai">OpenAI compatible</option></select></label><label className="ws-field"><span>Key header</span><select value={draft.profile.api_key_header ?? 'Authorization'} onChange={event => edit({ api_key_header: event.target.value as 'Authorization' | 'api-key' })}><option value="Authorization">Authorization: Bearer</option><option value="api-key">api-key (Azure and compatible)</option></select></label></div>
        <label className="ws-field"><span>Expected response model (optional)</span><input value={draft.profile.response_model ?? ''} maxLength={300} onChange={event => edit({ response_model: event.target.value || null })} /></label>
        <div className="ws-model-fields">{fields([['timeout_seconds', 1, draft.kind === 'embedding' ? 120 : 90, draft.kind === 'embedding' ? 30 : 45, 'Request timeout (seconds)'], ['server_threads', 1, draft.kind === 'embedding' ? 32 : 8, 2, 'Ollama CPU threads'], ['keep_alive_seconds', 0, draft.kind === 'embedding' ? 600 : 60, draft.kind === 'embedding' ? 30 : 0, 'Ollama keep loaded (seconds)']])}</div>
        {draft.kind === 'embedding' ? <>
          <div className="ws-model-fields">{fields([['chunk_tokens', 32, 8192, 512, 'Chunk budget (UTF-8 bytes)'], ['overlap_tokens', 0, 4096, 64, 'Overlap budget (UTF-8 bytes)'], ['max_input_tokens', 64, 32768, 4096, 'Provider input limit (UTF-8 bytes)'], ['max_query_tokens', 32, 32768, 2048, 'Query limit (UTF-8 bytes)'], ['batch_size', 1, 32, 8, 'Inputs per request'], ['max_queued', 0, 64, 4, 'Waiting request limit'], ['document_timeout_seconds', 1, 600, 120, 'Whole-document timeout (seconds)']])}</div>
          <label className="ws-field"><span>Query prefix (optional)</span><textarea rows={2} value={draft.profile.query_prefix ?? ''} maxLength={2000} onChange={event => edit({ query_prefix: event.target.value })} /></label>
          <label className="ws-field"><span>Document prefix (optional)</span><textarea rows={2} value={draft.profile.document_prefix ?? ''} maxLength={2000} onChange={event => edit({ document_prefix: event.target.value })} /></label>
          <label className="ws-checkbox"><input type="checkbox" checked={draft.profile.send_dimensions ?? false} onChange={event => edit({ send_dimensions: event.target.checked })} />Send the dimensions parameter (only if supported)</label>
        </> : <>
          <div className="ws-model-fields">{fields([['context_budget', 2048, 32768, 8192, 'Context budget (UTF-8 bytes)'], ['max_output_tokens', 256, 8192, 1024, 'Maximum output tokens']])}</div>
          <label className="ws-field"><span>Output limit parameter</span><select value={draft.profile.output_token_parameter ?? 'max_completion_tokens'} onChange={event => edit({ output_token_parameter: event.target.value as 'max_tokens' | 'max_completion_tokens' })}><option value="max_completion_tokens">max_completion_tokens</option><option value="max_tokens">max_tokens</option></select></label>
          <label className="ws-checkbox"><input type="checkbox" checked={draft.profile.json_mode ?? true} onChange={event => edit({ json_mode: event.target.checked })} />Request JSON mode (OpenAI-compatible servers)</label>
        </>}
        <label className="ws-field"><span>{previous?.has_custom_ca ? 'Replacement PEM CA certificates (blank retains trust)' : 'Private organization CA certificates (optional PEM)'}</span><textarea rows={3} maxLength={8192} value={ca} disabled={clearCa} onChange={event => { setCa(event.target.value); setReviewed(false); setApproved(false); }} /></label>
        {previous?.has_custom_ca && <label className="ws-checkbox"><input type="checkbox" checked={clearCa} onChange={event => { setClearCa(event.target.checked); setCa(''); setReviewed(false); setApproved(false); }} />Return to system certificate trust</label>}
      </details>
      {reviewed && <div className="ws-notice" role="status"><strong>Review {draft.profile.label}</strong><p className="ws-local-path">{draft.profile.endpoint}</p><p>{draft.profile.model} · {draft.profile.revision}</p><p>Saving restarts this local workspace if it is running. It makes the profile available; selecting it and authorizing cloud processing remain separate steps. Cloud providers may charge when you enable processing.</p><label className="ws-checkbox"><input type="checkbox" checked={approved} onChange={event => setApproved(event.target.checked)} />I have checked this provider and its model settings.</label></div>}
      <div className="ws-setup-actions"><button className="ws-button ws-primary" disabled={working || stale || (reviewed && !approved)}>{working ? <LoaderCircle className="ws-spin" size={15} /> : <Check size={15} />}{reviewed ? 'Save model profile' : 'Review model profile'}</button><button type="button" className="ws-button ws-quiet" disabled={working} onClick={clear}>Cancel edits</button></div>
    </fieldset></form>}
    {stale && <p className="ws-notice" role="status">Another operator changed the profiles. Cancel these edits and review the current settings before saving.</p>}
    <div className="ws-setup-actions"><button type="button" className="ws-button ws-quiet" disabled={working} onClick={() => void refresh()}><RefreshCw size={14} />Refresh model status</button>{connected && <><Link className="ws-button ws-quiet" to="/workspace/models">Choose a space’s embedding model</Link><Link className="ws-button ws-quiet" to="/workspace/librarian">Assign its librarian</Link></>}</div>
    <p className="ws-helper">Credentials stay in this OS account’s private host settings and never enter memories. Local-server RAM is controlled by that server; Mnemion’s own RAM controls remain in Setup.</p>
    <Link className="ws-link" to="/workspace/help?doc=docs%2Fservice%2Fdesktop-models.md">Model setup, recovery and agent controls</Link>
  </section>;
}
