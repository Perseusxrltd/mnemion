import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Cpu, FlaskConical, Pause, Play, RefreshCw, Search } from "lucide-react";
import type { EmbeddingSettings, MnemionClient, Recall, ReindexAction } from "@mnemion/client";
import "./embedding-models.css";

const failure = (error: unknown) => error instanceof Error ? error.message : "The request failed.";

export default function EmbeddingModels({ client, space, administrator }: {
  client: MnemionClient; space: string; administrator: boolean;
}) {
  const cache = useQueryClient();
  const key = ["embedding-settings", client.baseUrl, space];
  const status = useQuery({ queryKey: key, queryFn: () => client.embeddingSettings(space),
    enabled: administrator, refetchInterval: query => query.state.data?.candidate ? 10000 : false,
    refetchIntervalInBackground: false, retry: 1 });
  const [selected, setSelected] = useState("");
  const [approval, setApproval] = useState(false);
  const [activeApproval, setActiveApproval] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [preview, setPreview] = useState<Recall | null>(null);
  const data = status.data;
  const active = data?.profiles.find(p => p.generation_id === data.active_generation_id);
  const candidate = data?.candidate;
  const chosen = data?.profiles.find(p => p.id === selected);
  const target = data?.profiles.find(p => p.generation_id === candidate?.generation_id);
  const needsApproval = Boolean(target?.network_egress && !candidate?.network_egress_approved && !approval);
  const percent = candidate?.revisions ? Math.min(100, Math.round(candidate.indexed_revisions / candidate.revisions * 100)) : candidate?.scan_complete ? 100 : 0;

  const act = async (action: () => Promise<EmbeddingSettings>) => {
    setBusy(true); setError(""); setPreview(null);
    try {
      cache.setQueryData(key, await action());
      await cache.invalidateQueries({ queryKey: ["insights"] });
    } catch (error) { setError(failure(error)); await status.refetch(); }
    finally { setBusy(false); }
  };
  const control = (action: ReindexAction) => {
    if (data && candidate) void act(() => client.controlReindex(space, candidate.id, action, data.version, approval));
  };
  const inspect = async (event: FormEvent) => {
    event.preventDefault();
    if (!candidate) return;
    setBusy(true); setError(""); setPreview(null);
    try { setPreview(await client.search({ query, space_ids: [space], mode: "semantic", limit: 5,
      embedding_generation: candidate.generation_id })); }
    catch (error) { setError(failure(error)); }
    finally { setBusy(false); }
  };
  if (!administrator) return <div className="ws-page"><h1>Embedding models</h1><p className="ws-notice">A space administrator can choose models and approve where this space's text is processed.</p></div>;
  return <div className="ws-page model-settings">
    <header className="ws-page-heading"><div><p className="ws-eyebrow">Intelligence for this space</p><h1>Embedding models</h1><p>Choose a model, measure its retrieval, and activate a complete index.</p></div>
      <button className="ws-button" disabled={status.isFetching || busy} onClick={() => void status.refetch()}><RefreshCw size={16} />Refresh</button></header>
    {(error || status.isError) && <p className="ws-notice ws-error" role="alert">{error || failure(status.error)}</p>}
    {status.isPending && <p role="status">Loading model settings…</p>}
    {data && <>
      <section className="ws-card"><div className="ws-section-title"><h2><Cpu size={20} /> Active model</h2><span className="ws-badge">In use</span></div>
        <h3>{active?.label ?? "Configured model unavailable on this server"}</h3>
        <p>{active ? `${active.dimensions} dimensions · ${active.execution === "local_cpu" ? "CPU on the memory server" : active.endpoint_origin}` : "Lexical memory remains available. Restore the registered profile to resume semantic processing."}</p>
        <code className="model-fingerprint">{data.active_generation_id}</code>
        {data.inference_paused && <div className="ws-notice"><p>Endpoint processing is paused after recovery. Review the destination before resuming. You can also build and activate a local candidate.</p>
          {active?.network_egress && <label className="ws-checkbox"><input type="checkbox" checked={activeApproval} onChange={event => setActiveApproval(event.target.checked)} />I reapprove sending this space's text to {active.endpoint_origin}.</label>}
          <button className="ws-button" disabled={busy || !active || (active.network_egress && !activeApproval)} onClick={() => void act(() => client.resumeEmbeddingProcessing(space, data.version, activeApproval))}>Resume active model processing</button></div>}
        <p className="ws-helper">Desktop clients use the organization's memory server. They do not need to load this embedding model.</p>
      </section>
      {!candidate && <form className="ws-card ws-form" onSubmit={event => {
        event.preventDefault();
        if (chosen) void act(() => client.startReindex(space, { profile_id: chosen.id,
          expected_version: data.version, approve_network_egress: chosen.network_egress && approval }));
      }}><h2>Build a candidate index</h2><label className="ws-field"><span>Model</span><select value={selected} onChange={event => { setSelected(event.target.value); setApproval(false); }} required>
        <option value="">Choose an approved model</option>{data.profiles.filter(p => p.generation_id !== data.active_generation_id).map(p => <option key={p.id} value={p.id} disabled={!p.registered}>{p.label} · {p.dimensions} dimensions{!p.registered ? " · registration required" : ""}</option>)}</select></label>
        {chosen && <><p>{chosen.model} · {chosen.token_count_unit === "utf8_bytes" ? "Explicit UTF-8 byte budgets" : "Pinned model tokenizer"}</p>
          {chosen.endpoint_origin && <p>Text is processed at <strong>{chosen.endpoint_origin}</strong>.</p>}
          {chosen.network_egress && <label className="ws-checkbox"><input type="checkbox" checked={approval} onChange={event => setApproval(event.target.checked)} required />I approve sending this space's retained revisions, new memories and search queries to this endpoint. Its provider may charge for processing.</label>}
          <details><summary>Model configuration</summary><pre className="ws-code model-json">{JSON.stringify(chosen.configuration, null, 2)}</pre></details></>}
        <p className="ws-helper">The active index keeps serving searches while the candidate builds. Memory text, source evidence, permissions and Obsidian files stay attached to the same records.</p>
        <button className="ws-button ws-primary" disabled={busy || !chosen || !chosen.registered || (chosen.network_egress && !approval)}><Play size={16} />Build candidate</button>
      </form>}
      {candidate && <section className="ws-card model-candidate" aria-label="Candidate index">
        <div className="ws-section-title"><h2>{target?.label ?? "Candidate model"}</h2><span className="ws-badge">{candidate.state === "paused" ? "Paused" : candidate.ready_to_activate ? "Ready to review" : "Building"}</span></div>
        <div className="model-progress-caption"><strong>{percent}% indexed</strong><span>{candidate.indexed_revisions.toLocaleString()} / {candidate.revisions.toLocaleString()} retained revisions</span></div>
        <progress aria-label="Candidate indexing coverage" value={percent} max={100} />
        <p className="ws-helper">{candidate.scan_complete ? "History scan complete." : "The worker is scanning history in small, resumable batches."} New revisions join the candidate queue. {candidate.state === "paused" ? "No new indexing starts while paused; an in-flight document may finish." : "Progress refreshes every 10 seconds while this page is visible."}</p>
        <div className="ws-stats">{candidate.jobs.map(row => <div key={row.state}><span>{row.state}</span><strong>{row.count.toLocaleString()}</strong></div>)}</div>
        <div className="ws-actions">
          <button className="ws-button" disabled={busy || (candidate.state === "paused" && needsApproval)} onClick={() => control(candidate.state === "paused" ? "resume" : "pause")}>{candidate.state === "paused" ? <Play size={15} /> : <Pause size={15} />}{candidate.state === "paused" ? "Resume" : "Pause"}</button>
          {candidate.jobs.some(j => j.state === "failed") && <button className="ws-button" disabled={busy} onClick={() => control("retry")}><RefreshCw size={15} />Retry failed work</button>}
          <button className="ws-button" disabled={busy} onClick={() => control("cancel")}>Cancel candidate</button>
          <button className="ws-button ws-primary" disabled={busy || !candidate.ready_to_activate || !target || needsApproval} onClick={() => control("activate")}><CheckCircle2 size={16} />Activate complete index</button>
        </div>
        {target?.network_egress && !candidate.network_egress_approved && <label className="ws-checkbox"><input type="checkbox" checked={approval} onChange={event => setApproval(event.target.checked)} />I reapprove sending this space's text to {target.endpoint_origin} when I resume or activate this candidate.</label>}
        <p className="ws-helper">Activation checks current coverage again. Previous vectors remain available; selecting the previous model rebuilds only missing revisions before a controlled rollback.</p>
        <form className="ws-form" onSubmit={inspect}><h3>Preview candidate retrieval</h3><label className="ws-field"><span>Search query</span><input value={query} onChange={event => setQuery(event.target.value)} required maxLength={4000} /></label>
          <button className="ws-button" disabled={busy || !query.trim() || !candidate.indexed_revisions}><Search size={15} />Search candidate</button></form>
        {preview && <div aria-live="polite"><p>{preview.hits.length} matches · {preview.timing_ms.toFixed(1)} ms{preview.warnings.length ? ` · ${preview.warnings.join(", ")}` : ""}</p>
          {preview.hits.map(hit => <article className="model-preview-hit" key={hit.memory_id}><Link className="ws-link" to={`/workspace/memory/${hit.memory_id}`}>{hit.evidence.title}</Link><p>{hit.text}</p></article>)}</div>}
        <Link className="ws-link" to={`/workspace/insights?view=evaluations&generation=${candidate.generation_id}`}><FlaskConical size={16} />Evaluate this candidate on a versioned test set</Link>
      </section>}
      <p className="ws-helper">Operators add local CPU or compatible Ollama/OpenAI endpoint profiles on the server, then register them. Credentials stay there. <Link className="ws-link" to="/workspace/help?doc=docs%2Fservice%2Fembeddings.md">Model configuration & resource guide</Link></p>
    </>}
  </div>;
}
