import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, Plus, RefreshCw } from "lucide-react";
import { MnemionClient, MnemionError, type Connector, type ConnectorProposal } from "@mnemion/client";

const providers = [
  ["filesystem", "Obsidian / folder"], ["git", "Git repository"],
  ["gdrive", "Google Drive"], ["slack", "Slack"], ["rclone", "Other cloud storage (rclone)"],
];
const failure = (error: unknown) => error instanceof Error ? error.message : "The request failed.";
const when = (value: string | null) => value ? new Date(value).toLocaleString() : "Not yet synced";

function configuration(connection: Connector, endpoint: string, members: string[]) {
  const publication = { scope_id: "selected-source", name: connection.name, members,
    publish_to_mapped_members: true };
  const sources: Record<string, unknown> = {
    filesystem: { type: "filesystem", path: "./selected-vault", ...publication },
    git: { type: "git", path: "./repository", ref: "HEAD", ...publication },
    rclone: { type: "rclone", remote: "company:Knowledge", ...publication },
    slack: { type: "slack", token: { env: "SLACK_ACCESS_TOKEN" }, team_id: "REPLACE_WITH_TEAM_ID", channels: ["REPLACE_WITH_CHANNEL_ID"], include_threads: true },
    gdrive: { type: "gdrive", token: { file: "./private/google-access.token" }, folder_ids: ["REPLACE_WITH_FOLDER_ID"], recursive: true },
  };
  return JSON.stringify({ version: 1, service_url: endpoint, connector_id: connection.id,
    service_token: { env: "MNEMION_CONNECTOR_KEY" }, provider: sources[connection.provider] }, null, 2);
}

export function Connections({ client, administrator, endpoint, selectSpace }: {
  client: MnemionClient; administrator: boolean; endpoint: string; selectSpace: (id: string) => void;
}) {
  const cache = useQueryClient();
  const connections = useQuery({ queryKey: ["connectors"], queryFn: () => client.connectors() });
  const people = useQuery({ queryKey: ["principals"], queryFn: () => client.principals(), enabled: administrator });
  const [selected, setSelected] = useState("");
  const connection = connections.data?.items.find(item => item.id === selected) ?? connections.data?.items[0];
  const [name, setName] = useState("");
  const [provider, setProvider] = useState("filesystem");
  const [application, setApplication] = useState("");
  const [publication, setPublication] = useState(false);
  const [external, setExternal] = useState("");
  const [person, setPerson] = useState("");
  const [role, setRole] = useState<"reader" | "reviewer">("reader");
  const [cursor, setCursor] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const bindings = useQuery({ queryKey: ["connector-bindings", connection?.id], queryFn: () => client.connectorBindings(connection!.id), enabled: !!connection });
  const scopes = useQuery({ queryKey: ["connector-scopes", connection?.id, cursor], queryFn: () => client.connectorScopes(connection!.id, cursor), enabled: !!connection, refetchInterval: 15000 });
  const syncStatus = useQuery({ queryKey: ["connector-sync", connection?.id], queryFn: async () => {
    try { return await client.connectorSyncStatus(connection!.id); }
    catch (error) { if (error instanceof MnemionError && [404, 405].includes(error.status)) return null; throw error; }
  }, enabled: !!connection, retry: false, refetchInterval: 15000 });
  const published = !["gdrive", "slack"].includes(provider);
  async function act(work: () => Promise<unknown>) {
    setBusy(true); setError(undefined);
    try { await work(); await cache.invalidateQueries(); } catch (error) { setError(error); }
    finally { setBusy(false); }
  }
  async function create(event: FormEvent) {
    event.preventDefault();
    await act(async () => {
      const result = await client.createConnector({ name, provider, principal_id: application, access_mode: published ? "published" : "provider" });
      setSelected(result.id); setName(""); setCursor(undefined);
    });
  }
  const config = connection ? configuration(connection, endpoint, [...new Set(bindings.data?.items.map(item => item.external_id) ?? [])]) : "";
  function download() {
    const url = URL.createObjectURL(new Blob([config], { type: "application/json" }));
    const anchor = document.createElement("a"); anchor.href = url; anchor.download = "connector.json"; anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 10000);
  }
  return <div className="ws-page">
    <header className="ws-page-heading"><div><div className="ws-eyebrow">Sources</div><h1>Connect company knowledge</h1><p>Bring repositories, vaults and conversations into shared memory with their access boundaries intact.</p></div></header>
    {[error, connections.error, people.error, bindings.error, scopes.error, syncStatus.error].filter(Boolean).map((value, i) => <div className="ws-notice ws-error" role="alert" key={i}>{failure(value)}</div>)}
    {administrator && <details className="ws-card" open={!connections.data?.items.length}>
      <summary><strong>Add a connection</strong></summary>
      <form onSubmit={create} className="ws-connector-form">
        <label>Name<input value={name} onChange={e => setName(e.target.value)} required maxLength={200} placeholder="Engineering knowledge" /></label>
        <label>Source<select value={provider} onChange={e => { setProvider(e.target.value); setPublication(false); }}>{providers.map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select></label>
        <label>Dedicated application<select value={application} onChange={e => setApplication(e.target.value)} required><option value="">Choose an application</option>{people.data?.items.filter(person => person.kind === "application" && !person.administrator && !person.disabled_at).map(person => <option key={person.id} value={person.id}>{person.name}</option>)}</select></label>
        <p className="ws-helper">Create a dedicated application and its key in <Link className="ws-link" to="/workspace/team">People & apps</Link>. Each connection uses its own application.</p>
        {published && <label className="ws-checkbox"><input type="checkbox" checked={publication} onChange={e => setPublication(e.target.checked)} required />Use the mapped audience as this source’s sharing policy.</label>}
        {published ? <p className="ws-helper">Folder, Git and rclone access is published explicitly. These adapters cannot infer the provider’s effective permissions.</p> : <p className="ws-helper">Only mapped users with current provider access can read imported material. Unmapped identities and unsupported group grants remain excluded.</p>}
        <button className="ws-button ws-primary" disabled={busy || (published && !publication)}><Plus size={16} />Register connection</button>
      </form>
    </details>}
    {!connections.isPending && !connections.data?.items.length && <div className="ws-empty"><h2>No connections yet</h2><p>An administrator can register a source adapter and map its audience here.</p></div>}
    {connection && <>
      <div className="ws-card ws-connector-heading"><label>Connection<select value={connection.id} onChange={e => { setSelected(e.target.value); setCursor(undefined); }}>{connections.data?.items.map(item => <option key={item.id} value={item.id}>{item.name} · {item.provider}</option>)}</select></label>
        <span className="ws-badge">{connection.disabled_at ? "Disabled" : "Registered"}</span>
        {administrator && <button className="ws-button" disabled={busy} onClick={() => act(() => connection.disabled_at ? client.enableConnector(connection.id) : client.disableConnector(connection.id))}>{connection.disabled_at ? "Enable and recheck access" : "Disable connection"}</button>}
      </div>
      <section className="ws-card"><h2>Who can use this source?</h2><p>Map provider identities to people and applications. Removing a mapping suspends source access until the adapter checks current permissions.</p>
        {administrator && <form className="ws-connector-form" onSubmit={event => { event.preventDefault(); void act(async () => { await client.putConnectorBinding(connection.id, { external_id: external, principal_id: person, role }); setExternal(""); }); }}>
          <label>Source identity<input value={external} onChange={e => setExternal(e.target.value)} maxLength={512} required placeholder={connection.provider === "slack" ? "slack-user:U12345678" : connection.provider === "gdrive" ? "google-user:PERMISSION_ID" : "employee:alice"} /></label>
          <label>Mnemion identity<select value={person} onChange={e => setPerson(e.target.value)} required><option value="">Choose a person or application</option>{people.data?.items.filter(p => !p.disabled_at && p.id !== connection.principal_id).map(p => <option key={p.id} value={p.id}>{p.name} · {p.kind}</option>)}</select></label>
          <label>Role<select value={role} onChange={e => setRole(e.target.value as typeof role)}><option value="reader">Read memory</option><option value="reviewer">Read and review changes</option></select></label>
          <button className="ws-button" disabled={busy || !!connection.disabled_at}>Add mapping</button>
        </form>}
        <div className="ws-table-wrap"><table className="ws-table"><thead><tr><th>Source identity</th><th>Person or application</th><th>Role</th><th>Action</th></tr></thead><tbody>{bindings.data?.items.map(binding => <tr key={binding.external_id + binding.principal_id}><td><code>{binding.external_id}</code></td><td>{people.data?.items.find(p => p.id === binding.principal_id)?.name ?? binding.principal_id}</td><td>{binding.role}</td><td>{administrator && <button className="ws-link" disabled={busy} onClick={() => act(() => client.removeConnectorBinding(connection.id, binding))}>Remove</button>}</td></tr>)}</tbody></table></div>
        {!bindings.data?.items.length && <p className="ws-helper">No audience is mapped. Imported content remains available only to the dedicated connector identity.</p>}
      </section>
      <section className="ws-card"><div className="ws-section-title"><h2>Source status</h2><button className="ws-button" onClick={() => scopes.refetch()}><RefreshCw size={14} />Refresh</button></div>
        {syncStatus.data && <div className="ws-connector-heading">
          <div><p>{syncStatus.data.pending ? `Sync requested ${when(syncStatus.data.requested_at)}. Waiting for a complete scan.` : syncStatus.data.last_attempt_at ? (syncStatus.data.last_successful ? "Source scan complete." : "The last source scan was incomplete.") : "No scan reported yet."}</p>
            {syncStatus.data.last_attempt_at && <p className="ws-helper">Last report {when(syncStatus.data.last_attempt_at)} · {syncStatus.data.last_changed} changed · {syncStatus.data.last_removed} removed · {syncStatus.data.last_unchanged} unchanged · {syncStatus.data.last_duration_seconds?.toFixed(1)} seconds{syncStatus.data.last_successful === false ? ". Counts cover completed scopes." : ""}</p>}
            {connection.provider === "git" && (syncStatus.data.scanned_commit ? <p className="ws-helper">Last complete Git snapshot · {when(syncStatus.data.scanned_at ?? null)}<br /><code style={{ overflowWrap: "anywhere" }}>{syncStatus.data.scanned_commit}</code></p> : <p className="ws-helper">The scanned Git commit will appear after a complete scan with runner 4.3.2 or later.</p>)}
            {syncStatus.data.pending && <p className="ws-helper">The source runner must be running and connected. Requests do not change source permissions.</p>}
          </div>
          <button className="ws-button" disabled={busy || !!connection.disabled_at} onClick={() => void act(async () => {
            try { await client.requestConnectorSync(connection.id, syncStatus.data!.requested_generation); }
            finally { await syncStatus.refetch(); }
          })}><RefreshCw size={14} />Sync now</button>
        </div>}
        {syncStatus.data === null && <p className="ws-helper">Upgrade the memory server and source runner to 4.0.5 or later to request and monitor scans here.</p>}
        <div className="ws-table-wrap"><table className="ws-table"><thead><tr><th>Source</th><th>Access</th><th>Last complete scan</th>{administrator && <th>Control</th>}</tr></thead><tbody>{scopes.data?.items.map(scope => <tr key={scope.space_id}><td><Link className="ws-link" to="/workspace/memories" onClick={() => selectSpace(scope.space_id)}>{scope.name || scope.external_id}</Link><small className="ws-helper">{scope.external_id}</small></td><td>{connection.disabled_at ? "Disabled" : scope.operator_paused ? "Paused by an administrator" : scope.suspended_at ? "Needs permission recheck" : scope.access_current ? `Checked until ${when(scope.access_valid_until)}` : "Access expired"}</td><td>{when(scope.completed_at)}</td>{administrator && <td><button className="ws-link" disabled={busy || !!connection.disabled_at} onClick={() => act(() => scope.operator_paused ? client.resumeConnectorScope(scope.space_id) : client.pauseConnectorScope(scope.space_id))}>{scope.operator_paused ? "Resume and recheck" : "Pause source"}</button></td>}</tr>)}</tbody></table></div>
        {!scopes.data?.items.length && <p className="ws-helper">Run the adapter to discover sources and verify access.</p>}
        {scopes.data?.next_cursor && <button className="ws-button" onClick={() => setCursor(scopes.data!.next_cursor!)}>Next sources</button>}{cursor && <button className="ws-button" onClick={() => setCursor(undefined)}>First sources</button>}
      </section>
      <section className="ws-card"><h2>Run the adapter</h2><p>Run this configuration on a machine with access to the source. Set the dedicated Mnemion key and provider credentials there, then replace the source paths or IDs in the template.</p>
        <pre className="ws-code ws-connector-config">{config}</pre>
        <button className="ws-button" onClick={download}><Download size={16} />Download configuration template</button>
        <pre className="ws-code">mnemion-connect --config connector.json --inspect{"\n"}mnemion-connect --config connector.json --watch</pre>
        <p className="ws-helper">Inspect shows source IDs and memberships without importing. The template contains credential references; it does not contain a bearer token. Read the connector guide for provider scopes, file limits, and group-permission support.</p>
      </section>
    </>}
  </div>;
}

export function SourceProposals({ client, space }: { client: MnemionClient; space: string }) {
  const query = useQuery({ queryKey: ["connector-proposals", space], queryFn: () => client.connectorProposals(space) });
  return <section className="ws-card"><h2>Incoming source changes</h2><p>Upstream edits wait here when a memory has a human correction or review decision.</p>
    {query.error && <div className="ws-notice ws-error" role="alert">{failure(query.error)}</div>}
    {!query.isPending && !query.data?.items.length && <p className="ws-helper">No source conflicts in this space.</p>}
    {query.data?.items.map(proposal => <SourceProposal key={proposal.memory_id} proposal={proposal} client={client} />)}
  </section>;
}

function SourceProposal({ client, proposal }: { client: MnemionClient; proposal: ConnectorProposal }) {
  const cache = useQueryClient();
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  async function resolve(resolution: "accept" | "keep_local") {
    setBusy(true); setError(undefined);
    try { await client.resolveConnectorProposal(proposal.memory_id, { expected_version: proposal.version, proposal_hash: proposal.proposal_hash, resolution, reason }); await cache.invalidateQueries(); }
    catch (error) { setError(error); } finally { setBusy(false); }
  }
  return <details className="ws-details"><summary>{proposal.payload.memory?.subject || proposal.payload.memory?.source?.title || "Source update"}</summary>
    <Link className="ws-link" to={`/workspace/memory/${proposal.memory_id}`}>Inspect current memory and history</Link>
    <h3>Incoming evidence</h3><pre className="ws-prose">{proposal.payload.memory?.content}</pre>
    <label className="ws-field">Review reason<input value={reason} onChange={event => setReason(event.target.value)} maxLength={1000} required /></label>
    {!!error && <div className="ws-notice ws-error" role="alert">{failure(error)}</div>}
    <div className="ws-actions"><button className="ws-button ws-primary" disabled={busy || !reason.trim()} onClick={() => resolve("accept")}>Accept source update</button><button className="ws-button" disabled={busy || !reason.trim()} onClick={() => resolve("keep_local")}>Keep local correction</button></div>
    <p className="ws-helper">Accepting updates the evidence revision. Quarantined memories remain quarantined until a separate review decision.</p>
  </details>;
}
