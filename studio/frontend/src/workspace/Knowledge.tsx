import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Download, RefreshCw } from "lucide-react";
import { MnemionClient, type Knowledge, type KnowledgeNode } from "@mnemion/client";
import MemoryMap, { compactMapDefault } from "./MemoryMap";

export function KnowledgeView({ client, space, reviewer = false, administrator = false }: { client: MnemionClient; space: string; reviewer?: boolean; administrator?: boolean }) {
  const [tab, setTab] = useState("map");
  const [live, setLive] = useState(true);
  const [mapLimit, setMapLimit] = useState(() => compactMapDefault() ? 60 : 120);
  const [subject, setSubject] = useState("");
  const [filter, setFilter] = useState("");
  const [all, setAll] = useState(false);
  const [history, setHistory] = useState(false);
  const limit = tab === "map" ? mapLimit : 250;
  const query = useQuery({ queryKey: ["knowledge", client.baseUrl, space, all, filter, history, limit],
    queryFn: ({ signal }) => client.request<Knowledge>("POST", "/v1/knowledge", { body: { ...(all ? { all_accessible: true } : { space_ids: [space] }), subject: filter || undefined, include_historical: history, limit }, signal }),
    refetchInterval: tab === "map" && live ? 20_000 : false, refetchIntervalInBackground: false,
    refetchOnWindowFocus: tab !== "map" || live, refetchOnReconnect: tab !== "map" || live, retry: 1, gcTime: 0,
  });
  // A rejected refresh must not keep rendering evidence from an older access grant.
  const result = query.error ? undefined : query.data;
  function download() {
    if (!result) return;
    const url = URL.createObjectURL(new Blob([result.markdown], { type: "text/markdown;charset=utf-8" }));
    const anchor = document.createElement("a"); anchor.href = url; anchor.download = "mnemion-evidence-wiki.md"; anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 10000);
  }
  return <div className="ws-page">
    <header className="ws-page-heading"><div><div className="ws-eyebrow">{tab === "map" ? "Connected intelligence" : "Organized knowledge"}</div><h1>{tab === "map" ? "Your memory, in perspective" : "Explore the evidence"}</h1><p>A living map and wiki built from the memories you can currently access.</p></div><button className="ws-button" onClick={() => query.refetch()} disabled={query.isFetching}><RefreshCw size={16} />Refresh</button></header>
    <details className="ws-knowledge-scope" open={tab !== "map"}><summary>Scope, subject & history{filter ? ` · ${filter}` : ""}{all ? " · all accessible spaces" : ""}{history ? " · including historical claims" : ""}</summary>
    <form className="ws-card ws-knowledge-controls" onSubmit={event => { event.preventDefault(); setFilter(subject); }}>
      <div className="ws-knowledge-filter"><label className="ws-field"><span>Subject filter</span><input type="search" value={subject} onChange={event => setSubject(event.target.value)} placeholder="Billing, product, research…" maxLength={500} /></label><button className="ws-button">Apply filter</button></div>
      <div className="ws-knowledge-options"><label className="ws-checkbox"><input data-update-safe type="checkbox" checked={all} onChange={event => setAll(event.target.checked)} />All accessible spaces</label>
      <label className="ws-checkbox"><input data-update-safe type="checkbox" checked={history} onChange={event => setHistory(event.target.checked)} />Include expired and withdrawn claims</label></div>
    </form>
    </details>
    {query.error && <div className="ws-notice ws-error" role="alert">{query.error instanceof Error ? query.error.message : "Knowledge could not be loaded."}</div>}
    {query.isPending && <p role="status">Building the evidence view…</p>}
    {result && <>
      <div className="ws-actions" role="group" aria-label="Knowledge view">{[["map", "Live memory map"], ["wiki", "Wiki"], ["graph", "Evidence graph"], ["curation", "Curation"]].map(([id, label]) => <button className={`ws-button ${tab === id ? "ws-primary" : ""}`} key={id} aria-pressed={tab === id} onClick={() => setTab(id)}>{label}</button>)}<span className="ws-helper">{result.memories.length} memories · {result.topics.length} topics</span></div>
      {result.truncated && <div className="ws-notice" role="status">This view includes the first {limit} matching memories. Narrow the subject or space to inspect a complete set.</div>}
      {tab === "map" && <MemoryMap result={result} client={client} space={space} reviewer={reviewer} administrator={administrator} live={live} setLive={setLive} limit={mapLimit} setLimit={setMapLimit} checkedAt={query.dataUpdatedAt} refreshing={query.isFetching} />}
      {tab === "wiki" && <>
        <div className="ws-section-title"><p className="ws-helper">Each passage retains its source and review status. Refresh after changing a memory.</p><button className="ws-button" onClick={download}><Download size={16} />Save Markdown</button></div>
        {result.topics.map(topic => <section className="ws-card" key={topic.id}><h2>{topic.title}</h2>{topic.memory_ids.map(id => {
          const memory = result.memories.find(record => record.memory_id === id)!;
          return <details className="ws-details" key={id} open={topic.memory_ids.length < 4}><summary><span className="ws-badge">{memory.claim_status}</span> {memory.content.split("\n")[0].slice(0, 120)}</summary><p className="ws-prose">{memory.content}</p><div className="ws-actions"><Link className="ws-link" to={`/workspace/memory/${id}`}>Memory · revision {memory.version}</Link><Link className="ws-link" to={`/workspace/sources/${memory.evidence.source_revision_id}`}>{memory.evidence.title}</Link></div></details>;
        })}</section>)}
      </>}
      {tab === "graph" && <KnowledgeGraph result={result} />}
      {tab === "curation" && <section className="ws-card"><h2>Review suggestions</h2><p>Inspect related evidence before changing it. These findings do not merge or delete memories.</p>{result.findings.map((finding, index) => <div className="ws-details" key={index}><h3>{finding.kind.replaceAll("_", " ")}</h3><p>{finding.message}</p><div className="ws-actions">{finding.memory_ids.map(id => <Link className="ws-link" key={id} to={`/workspace/memory/${id}`}>{result.memories.find(record => record.memory_id === id)?.subject || id.slice(0, 8)}</Link>)}</div></div>)}{!result.findings.length && <p className="ws-helper">No duplicate, contested or unassigned memories were found in this view.</p>}</section>}
      {!result.memories.length && <div className="ws-empty"><h2>No matching evidence yet</h2><p>Save a memory or connect a source, then refresh this view.</p></div>}
      <p className="ws-helper">Built {new Date(result.generated_at).toLocaleString()}. For a linked vault with protected personal annotations, use <Link className="ws-link" to="/workspace/obsidian">Obsidian</Link>.</p>
    </>}
  </div>;
}

function KnowledgeGraph({ result }: { result: Knowledge }) {
  const [selected, setSelected] = useState("");
  const focus = result.nodes.find(node => node.id === selected);
  const neighbors = new Set(focus ? [focus.id, ...result.edges.filter(edge => edge.source === selected || edge.target === selected).flatMap(edge => [edge.source, edge.target])] : []);
  const kinds = ["space", "entity", "memory", "source"] as const;
  const visible = kinds.flatMap(kind => result.nodes.filter(node => node.kind === kind && (!focus || neighbors.has(node.id))).slice(0, 12));
  const points = new Map<string, { x: number; y: number }>();
  for (const [column, kind] of kinds.entries()) {
    const nodes = visible.filter(node => node.kind === kind);
    nodes.forEach((node, row) => points.set(node.id, { x: 100 + column * 220, y: 60 + (row + .5) * 430 / Math.max(1, nodes.length) }));
  }
  function choose(node: KnowledgeNode) { setSelected(node.id === selected ? "" : node.id); }
  return <section className="ws-card"><div className="ws-section-title"><h2>{focus ? focus.label : "Spaces, subjects and their evidence"}</h2>{focus && <button className="ws-button" onClick={() => setSelected("")}>Show overview</button>}</div><p className="ws-helper">Select a node to focus on its direct connections. The overview shows up to 12 nodes of each kind.</p>
    <div className="ws-graph-canvas" tabIndex={0} role="region" aria-label="Scrollable evidence graph"><svg viewBox="0 0 960 540" aria-label="Evidence relationships" role="group">
      {kinds.map((kind, column) => <text key={kind} x={100 + column * 220} y={25} className="ws-graph-column" textAnchor="middle">{{space: "Spaces", entity: "Subjects & entities", memory: "Memories", source: "Sources"}[kind]}</text>)}
      {result.edges.filter(edge => points.has(edge.source) && points.has(edge.target)).map((edge, index) => <line key={index} x1={points.get(edge.source)!.x} y1={points.get(edge.source)!.y} x2={points.get(edge.target)!.x} y2={points.get(edge.target)!.y} className="ws-graph-edge"><title>{edge.relation.replaceAll("_", " ")}</title></line>)}
      {visible.map(node => { const point = points.get(node.id)!; return <g key={node.id} role="button" tabIndex={0} aria-label={`${node.kind}: ${node.label}`} aria-pressed={selected === node.id} onClick={() => choose(node)} onKeyDown={event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); choose(node); } }} className={`ws-graph-node ws-graph-${node.kind}`} transform={`translate(${point.x},${point.y})`}><title>{node.label}</title><circle r={7} /><text x={12} y={4}>{node.label.length > 23 ? node.label.slice(0, 22) + "…" : node.label}</text></g>; })}
    </svg></div>{focus?.memory_id && <Link className="ws-link" to={`/workspace/memory/${focus.memory_id}`}>Open memory and source history</Link>}
  </section>;
}
