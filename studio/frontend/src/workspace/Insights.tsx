import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Activity, ArrowRight, BarChart3, BookOpenCheck, CheckCircle2, Clock3, Cpu, Database, FlaskConical, Gauge, Layers, LoaderCircle, RefreshCw, ShieldCheck, Workflow } from "lucide-react";
import type { Insights, MetricGroup, MetricOrigin, MetricValues, MnemionClient, RuntimeInsights } from "@mnemion/client";
import { Bars, Composition, DataTable, EmptyChart, ExportButton, Panel, Ring, Stat, TimeChart, bytes, download, duration, label, number, palette, percent, when, type LinePoint } from "./insights/Charts";
import "./insights/insights.css";

const Evaluations = lazy(() => import("./insights/Evaluations"));
const views = [
  { id: "overview", label: "Overview", icon: Gauge },
  { id: "memory", label: "Memory health", icon: Layers },
  { id: "retrieval", label: "Retrieval", icon: Activity },
  { id: "pipeline", label: "Sources & pipeline", icon: Workflow },
  { id: "models", label: "Models & resources", icon: Cpu },
  { id: "evaluations", label: "Evaluations", icon: FlaskConical },
];
const stages: Record<string, string> = { recall: "Search", context: "Context", index: "Indexing", purge: "Erasure" };

function sum(groups: MetricGroup[]) {
  const total = { calls: 0, failures: 0, duration_ms: 0, output_tokens: 0, input_bytes: 0, output_bytes: 0, records: 0, chunks: 0, empty_results: 0, fallbacks: 0, incomplete_index: 0, latency_histogram: Array<number>(18).fill(0) };
  for (const group of groups) {
    for (const key of Object.keys(total).filter(key => key !== "latency_histogram") as (keyof Omit<typeof total, "latency_histogram">)[]) total[key] += group[key];
    group.latency_histogram.forEach((value, i) => { total.latency_histogram[i] += value; });
  }
  return total;
}
function quantile(histogram: number[], bounds: (number | null)[], q: number) {
  const target = Math.ceil(histogram.reduce((a, b) => a + b, 0) * q);
  if (!target) return null;
  let total = 0;
  for (let i = 0; i < histogram.length; i++) { total += histogram[i]; if (total >= target) return bounds[i]; }
  return null;
}
function seriesPoints(data: Insights, field: keyof MetricValues, transform = (value: number) => value) {
  const points = new Map<string, LinePoint>();
  for (const row of data.metrics.series) {
    const point = points.get(row.at) || { at: row.at, values: {} };
    point.values[row.stage] = typeof row[field] === "number" ? transform(row[field] as number) : null;
    points.set(row.at, point);
  }
  return [...points.values()];
}

export default function InsightsView({ client, space, reviewer, administrator }: {
  client: MnemionClient; space: string; reviewer: boolean; administrator: boolean;
}) {
  const [params, setParams] = useSearchParams();
  const page = useRef<HTMLDivElement>(null);
  const view = views.some(item => item.id === params.get("view")) ? params.get("view")! : "overview";
  const selectedRun = params.get("run");
  const [online, setOnline] = useState(() => navigator.onLine);
  useEffect(() => {
    const update = () => setOnline(navigator.onLine);
    window.addEventListener("online", update); window.addEventListener("offline", update);
    return () => { window.removeEventListener("online", update); window.removeEventListener("offline", update); };
  }, []);
  useEffect(() => {
    page.current?.closest("main")?.scrollTo({ top: 0, behavior: "instant" });
    window.scrollTo({ top: 0, behavior: "instant" });
  }, [view, selectedRun, space]);
  const parsedHours = Number(params.get("hours"));
  const hours = [1, 6, 24, 168, 720].includes(parsedHours) ? parsedHours : 24;
  const [origin, setOrigin] = useState<MetricOrigin>("all");
  const [live, setLive] = useState(true);
  const change = (key: string, value: string) => setParams(previous => { const next = new URLSearchParams(previous); next.set(key, value); return next; }, { replace: true });
  const query = useQuery({
    queryKey: ["insights", client.baseUrl, space, hours, origin],
    queryFn: ({ signal }) => client.insights(space, { hours, origin, signal }),
    enabled: reviewer && view !== "evaluations", staleTime: 30000,
    refetchInterval: live && view !== "evaluations" ? 60000 : false,
    refetchIntervalInBackground: false, retry: 1,
  });
  const runtime = useQuery({
    queryKey: ["insights-runtime", client.baseUrl], queryFn: ({ signal }) => client.runtimeInsights(signal),
    enabled: reviewer && administrator && view === "models", staleTime: 10000,
    refetchInterval: live && view === "models" ? 15000 : false, refetchIntervalInBackground: false, retry: 1,
  });
  if (!reviewer) return <div className="ws-page"><h1>Insights & evaluations</h1><p className="ws-notice">Reviewer access to this space is required to inspect shared diagnostics.</p></div>;
  return <div ref={page} className="ws-page ins-page">
    <header className="ins-heading"><div><p className="ws-eyebrow">Measure your memory</p><h1>Insights & evaluations</h1><p>Follow the evidence. Understand performance. Test every change.</p></div>
      {view !== "evaluations" && <div className="ins-heading-actions"><span className={`ins-live ${online && !query.isError && live ? "on" : ""}`}><i />{!online ? "Offline" : query.isError ? "Unavailable" : live ? "Live · 60 s" : "Manual"}</span>
        <ExportButton disabled={!online || !query.data || query.isError} onClick={() => download(JSON.stringify(query.data, null, 2), `mnemion-insights-${space}-${new Date().toISOString().slice(0, 10)}.json`)} />
      </div>}
    </header>
    <nav className="ins-tabs" aria-label="Insights views">{views.map(item => <button key={item.id} className={view === item.id ? "active" : ""} aria-current={view === item.id ? "page" : undefined} onClick={() => change("view", item.id)}><item.icon size={16} />{item.label}</button>)}</nav>
    {!online && <p className="ws-notice" role="status">Connection is offline. Automatic updates pause; displayed results are the last observed data. Reconnect to refresh measurements or run evaluations.</p>}
    {view === "evaluations" ? <Suspense fallback={<div className="ws-loading"><LoaderCircle className="ws-spin" size={18} />Loading evaluations…</div>}><Evaluations client={client} space={space} /></Suspense> : <>
      <div className="ins-toolbar"><div className="ins-window" role="group" aria-label="Time window">{[[1, "1 hour"], [6, "6 hours"], [24, "24 hours"], [168, "7 days"], [720, "30 days"]].map(([value, title]) => <button key={value} aria-pressed={hours === value} onClick={() => change("hours", String(value))}>{title}</button>)}</div>
        <label className="ins-select"><span>Traffic</span><select value={origin} onChange={event => setOrigin(event.target.value as MetricOrigin)}><option value="all">All activity</option><option value="interactive">Applications</option><option value="background">Background work</option><option value="evaluation">Evaluations</option></select></label>
        <label className="ins-live-control"><input type="checkbox" checked={live} onChange={event => setLive(event.target.checked)} />Auto refresh</label>
        <button className="ws-button ws-quiet" aria-label="Refresh insights" disabled={query.isFetching} onClick={() => { void query.refetch(); if (administrator && view === "models") void runtime.refetch(); }}><RefreshCw size={15} className={query.isFetching ? "ws-spin" : ""} /></button>
      </div>
      {query.isError ? <div className="ws-notice ws-error" role="alert">{query.error.message}</div> : query.isPending ? online ? <div className="ws-loading"><LoaderCircle className="ws-spin" size={18} />Reading scoped measurements…</div> : <EmptyChart>Reconnect to load measurements.</EmptyChart> : <>
        <div className="ins-observation"><span><ShieldCheck size={13} />Current space · reviewer access</span><span>Observed {when(query.data.observed_at)}</span><span>{number(query.data.metrics.recorded_calls)} recorded calls · {query.data.metrics.bucket_seconds / 60} min chart buckets</span></div>
        {query.data.metrics.truncated && <p className="ws-notice">This window contains more metric groups than can be displayed. Choose a shorter window or traffic filter.</p>}
        {view === "overview" && <Overview data={query.data} />}
        {view === "memory" && <MemoryHealth data={query.data} />}
        {view === "retrieval" && <Retrieval data={query.data} />}
        {view === "pipeline" && <Pipeline data={query.data} />}
        {view === "models" && <Models data={query.data} runtime={runtime.isError ? undefined : runtime.data} error={runtime.error?.message} administrator={administrator} live={live} />}
        <details className="ins-definitions"><summary><BookOpenCheck size={15} />Measurement notes & data provenance</summary>
          {query.data.notices.map(note => <p key={note}>{note}</p>)}<p>Counts reflect a snapshot taken at {when(query.data.snapshot_at)}, cached for at most {query.data.snapshot_cache_seconds} seconds. Numeric telemetry is retained for {query.data.metrics.retention_days} days. Automatic refresh pauses in a background tab.</p>
          <p>First recorded sample in this window: {when(query.data.metrics.first_sample_at)}. Last: {when(query.data.metrics.last_sample_at)}.</p>
        </details>
      </>}
    </>}
  </div>;
}

function Traffic({ data, title = "Work moving through memory" }: { data: Insights; title?: string }) {
  return <Panel title={title} subtitle="Measured calls per minute · gaps mean no recorded sample">
    <TimeChart name={title} points={seriesPoints(data, "calls", value => value * 60 / data.metrics.bucket_seconds)}
      series={[{ key: "recall", label: "Search" }, { key: "context", label: "Context" }, { key: "index", label: "Indexing" }]}
      unit="calls / min" format={v => number(v, 2)} since={data.metrics.since} until={data.metrics.until} bucketSeconds={data.metrics.bucket_seconds} />
  </Panel>;
}

function Overview({ data }: { data: Insights }) {
  const queries = sum(data.metrics.groups.filter(group => ["recall", "context"].includes(group.stage)));
  const pending = data.queue.filter(row => ["pending", "leased"].includes(row.state)).reduce((n, row) => n + row.count, 0);
  const failed = data.queue.find(row => row.state === "failed")?.count ?? 0;
  const p95 = quantile(queries.latency_histogram, data.metrics.histogram_upper_bounds_ms, .95);
  const issues = [
    ...(failed ? [{ label: `${number(failed)} failed indexing jobs`, detail: "Review errors and retry recoverable operations.", to: "/workspace/operations", tone: "bad" }] : []),
    ...(data.memory.quarantined ? [{ label: `${number(data.memory.quarantined)} memories in review`, detail: "Quarantined evidence is excluded from ordinary retrieval.", to: "/workspace/review", tone: "warm" }] : []),
    ...(data.memory.duplicate_copies ? [{ label: `${number(data.memory.duplicate_copies)} exact duplicate copies`, detail: "Inspect shared evidence before proposing a merge.", to: "/workspace/knowledge", tone: "" }] : []),
    ...(data.memory.eligible > data.memory.indexed ? [{ label: `${number(data.memory.eligible - data.memory.indexed)} memories awaiting search coverage`, detail: "Lexical retrieval remains available while indexing completes.", to: "/workspace/operations", tone: "warm" }] : []),
  ];
  return <>
    <div className="ins-stat-grid"><Stat title="Active memories" value={number(data.memory.active)} detail={`${number(data.memory.sources)} sources · ${number(data.memory.revisions)} revisions`} icon={<Layers size={16} />} />
      <Stat title="Semantic coverage" value={data.memory.eligible ? percent(data.memory.indexed / data.memory.eligible) : "—"} detail={`${number(data.memory.indexed)} / ${number(data.memory.eligible)} eligible`} tone="mint" icon={<CheckCircle2 size={16} />} />
      <Stat title="Retrieval p95" value={queries.calls && p95 == null ? "> 5 min" : p95 == null ? "—" : `≤ ${duration(p95)}`} detail={`${number(queries.calls)} recorded search & context calls`} icon={<Activity size={16} />} />
      <Stat title="Work waiting" value={number(pending)} detail={failed ? `${number(failed)} failed jobs need attention` : "Durable indexing & erasure queue"} tone={failed ? "bad" : ""} icon={<Workflow size={16} />} /></div>
    <div className="ins-grid ins-grid-wide"><Traffic data={data} /><Panel title="Ready to recall" subtitle="Current evidence eligible for retrieval"><Ring value={data.memory.indexed} total={data.memory.eligible} title="indexed" />
      <div className="ins-mini-numbers"><span><b>{number(data.memory.quarantined)}</b>In review</span><span><b>{number(data.memory.expired)}</b>Past validity</span><span><b>{number(data.memory.future)}</b>Future validity</span></div>
    </Panel></div>
    <div className="ins-grid"><Panel title="Evidence states" subtitle="Workflow labels on current memory revisions"><Composition name="Claim states" values={(data.memory.distributions.claim || []).map(row => ({ ...row, label: label(row.label) }))} />
      <p className="ins-footnote">A verified label records a review decision. It is not a probability of truth.</p></Panel>
      <Panel title="Things to inspect" subtitle="Concrete conditions with a path to investigate">{issues.length ? <div className="ins-issues">{issues.map(issue => <Link key={issue.label} to={issue.to} className={issue.tone}><i /><div><strong>{issue.label}</strong><p>{issue.detail}</p></div><ArrowRight size={16} /></Link>)}</div> : <div className="ins-clear"><ShieldCheck size={32} /><strong>No queue or review conditions flagged</strong><p>{data.memory.active ? "Run an evaluation to measure whether your memories answer the questions that matter." : "Connect a source or save memories to begin collecting evidence and measurements."}</p><Link to={data.memory.active ? "/workspace/insights?view=evaluations" : "/workspace/new"} className="ws-button">{data.memory.active ? "Open evaluations" : "Save a memory"}<ArrowRight size={14} /></Link></div>}</Panel></div>
    <div className="ins-note-strip"><FlaskConical size={19} /><div><strong>Make a change. Measure its effect.</strong><p>Version your test questions, compare retrieval modes, inspect citations and keep reproducible results.</p></div><Link to="/workspace/insights?view=evaluations" className="ws-button">Evaluation lab<ArrowRight size={14} /></Link></div>
  </>;
}

function MemoryHealth({ data }: { data: Insights }) {
  const m = data.memory, vectors = data.generations.reduce((n, generation) => n + generation.vector_bytes, 0);
  const stored = m.revision_bytes + m.source_bytes + m.attachment_bytes + vectors;
  const changes = useMemo(() => { const map = new Map<string, LinePoint>(); for (const row of data.changes) { const point = map.get(row.at) || { at: row.at, values: {} }; point.values[row.action] = row.count; map.set(row.at, point); } return [...map.values()]; }, [data.changes]);
  return <><div className="ins-stat-grid"><Stat title="Current content" value={bytes(m.content_bytes)} detail={`${number(m.active)} active memory records`} icon={<Database size={16} />} />
    <Stat title="Stored values" value={bytes(stored)} detail="Memory history, source text, attachments & vectors" /><Stat title="Exact duplicate copies" value={number(m.duplicate_copies)} detail="Matching current content hashes" tone={m.duplicate_copies ? "warm" : ""} /><Stat title="Deleted memories" value={number(m.deleted)} detail="Tombstones remain for durable erasure" /></div>
    <div className="ins-grid"><Panel title="Memory types" subtitle="Current active records"><Composition name="Memory kinds" values={(m.distributions.kind || []).map(row => ({ ...row, label: label(row.label) }))} /></Panel>
      <Panel title="Age since last update" subtitle="Age is a review signal, not proof of staleness"><Bars name="Memory age distribution" values={["under_1_day", "1_to_7_days", "7_to_30_days", "30_to_90_days", "over_90_days"].map(key => ({ label: label(key), value: m.distributions.age?.find(row => row.label === key)?.count ?? 0 }))} /></Panel></div>
    <div className="ins-grid"><Panel title="Logical storage composition" subtitle="Database indexes, backups and filesystem overhead are excluded"><Bars name="Logical storage" format={bytes} values={[
      { label: "Memory revisions", value: m.revision_bytes }, { label: "Source revisions", value: m.source_bytes }, { label: "Original attachments", value: m.attachment_bytes }, { label: "Vector values", value: vectors },
    ]} /><div className="ins-mini-numbers"><span><b>{m.content_bytes ? `${number(stored / m.content_bytes, 1)}×` : "—"}</b>Stored / current content</span><span><b>{number(m.source_revisions)}</b>Source revisions</span></div></Panel>
      <Panel title="Document sizes" subtitle="UTF-8 bytes in current memory content"><Bars name="Document size distribution" values={["under_1_KiB", "1_to_4_KiB", "4_to_16_KiB", "over_16_KiB"].map(key => ({ label: label(key), value: m.distributions.size?.find(row => row.label === key)?.count ?? 0 }))} /></Panel></div>
    <Panel title="Memory changes" subtitle="Durable audit events in the selected window"><TimeChart name="Memory changes over time" points={changes} series={[{ key: "memory.created", label: "Created" }, { key: "memory.revised", label: "Revised" }, { key: "memory.reviewed", label: "Reviewed" }, { key: "memory.deleted", label: "Deleted", color: palette[4] }]} unit="events / bucket" since={data.metrics.since} until={data.metrics.until} bucketSeconds={data.metrics.bucket_seconds} /></Panel>
  </>;
}

function Retrieval({ data }: { data: Insights }) {
  const [stage, setStage] = useState("recall");
  const [log, setLog] = useState(false);
  const groups = data.metrics.groups.filter(row => row.stage === stage), totals = sum(groups);
  const histogram = totals.latency_histogram.map((value, i) => ({ label: data.metrics.histogram_upper_bounds_ms[i] == null ? "> 5 min" : `≤ ${duration(data.metrics.histogram_upper_bounds_ms[i])}`, value }));
  const p95 = quantile(totals.latency_histogram, data.metrics.histogram_upper_bounds_ms, .95);
  return <><div className="ins-sub-toolbar"><label className="ins-select"><span>Operation</span><select value={stage} onChange={e => setStage(e.target.value)}><option value="recall">Search</option><option value="context">Context assembly</option></select></label><p>Measured behavior for the selected traffic filter. Ranking quality comes from labeled evaluations.</p></div>
    <div className="ins-stat-grid"><Stat title="Recorded calls" value={number(totals.calls)} detail={`${number(totals.failures)} failures`} /><Stat title="Mean latency" value={totals.calls ? duration(totals.duration_ms / totals.calls) : "—"} detail={totals.calls ? `p95 ${p95 == null ? "> 5 min" : `≤ ${duration(p95)}`}` : "No measured latency samples"} />
      <Stat title="Empty result rate" value={totals.calls > totals.failures ? percent(totals.empty_results / (totals.calls - totals.failures)) : "—"} detail={`${number(totals.empty_results)} successful calls with no citations / hits`} /><Stat title="Context tokens" value={number(totals.output_tokens)} detail="Reported by the configured embedding tokenizer" /></div>
    <div className="ins-grid ins-grid-wide"><Panel title="Retrieval latency over time" subtitle="Histogram p95 upper bounds; an unbounded bin is shown as a data gap"><TimeChart name="Retrieval latency" points={seriesPoints(data, "p95_upper_ms")} series={[{ key: "recall", label: "Search p95" }, { key: "context", label: "Context p95" }]} unit="ms" format={duration} since={data.metrics.since} until={data.metrics.until} bucketSeconds={data.metrics.bucket_seconds} /></Panel>
      <Panel title="Retrieval conditions" subtitle="Events to investigate"><Bars name="Retrieval conditions" values={[{ label: "Failed calls", value: totals.failures, color: palette[4] }, { label: "Empty results", value: totals.empty_results }, { label: "Lexical fallback", value: totals.fallbacks, color: palette[2] }, { label: "Index incomplete", value: totals.incomplete_index, color: palette[2] }]} /><p className="ins-footnote">Conditions can overlap. An empty result is not automatically a correct abstention.</p></Panel></div>
    <div className="ins-grid"><Panel title="Latency distribution" subtitle="Disjoint duration bins · exact sample counts" action={<label className="ins-live-control"><input type="checkbox" checked={log} onChange={e => setLog(e.target.checked)} />Log scale</label>}>{totals.calls ? <Bars name="Latency histogram" values={histogram} logarithmic={log} /> : <EmptyChart />}</Panel>
      <Panel title="Modes, origins & generations" subtitle="Inspect sample size before comparing response times"><DataTable name="Retrieval measurements" columns={["Mode", "Origin", "Generation", "Calls", "Mean", "p95 ≤", "Failures", "Output"]} rows={groups.map(group => [label(group.mode), label(group.origin), group.generation_id.slice(0, 10), number(group.calls), duration(group.mean_ms), group.p95_upper_ms == null && group.calls ? "> 5 min" : duration(group.p95_upper_ms), number(group.failures), bytes(group.output_bytes)])} />
        <Bars name="Recorded calls by retrieval mode" values={["lexical", "semantic", "hybrid"].map(mode => ({ label: label(mode), value: groups.filter(group => group.mode === mode).reduce((n, row) => n + row.calls, 0) }))} />
        <div className="ins-note"><FlaskConical size={17} /><p>Use the evaluation lab to compare recall, NDCG, citation validity and bounded context coverage on the same labeled questions.</p></div>
        <Link className="ws-button" to="/workspace/insights?view=evaluations">Compare retrieval quality<ArrowRight size={14} /></Link>
      </Panel></div>
  </>;
}

function Pipeline({ data }: { data: Insights }) {
  const totals = sum(data.metrics.groups.filter(row => row.stage === "index")), queue = data.queue.filter(row => ["pending", "leased", "failed"].includes(row.state));
  const oldest = queue.filter(row => row.state !== "failed").reduce((value, row) => Math.max(value, row.oldest_age_seconds ?? 0), 0);
  return <><div className="ins-pipeline" aria-label="Source to searchable memory pipeline">{[
    { name: "Source evidence", value: number(data.memory.sources), detail: data.source.managed ? data.source.provider || "Managed source" : "Captured or imported sources", icon: Database },
    { name: "Durable memory", value: number(data.memory.active), detail: "Canonical active records", icon: Layers },
    { name: "Indexing queue", value: number(queue.filter(row => row.state !== "failed").reduce((n, row) => n + row.count, 0)), detail: oldest ? `Oldest ${duration(oldest * 1000)}` : "No waiting jobs", icon: Workflow },
    { name: "Searchable", value: number(data.memory.indexed), detail: "Current eligible generation", icon: CheckCircle2 },
  ].map((item, i) => <div key={item.name}><item.icon size={20} /><span>{item.name}</span><strong>{item.value}</strong><small>{item.detail}</small>{i < 3 && <ArrowRight className="ins-pipeline-arrow" size={20} />}</div>)}</div>
    <div className="ins-stat-grid"><Stat title="Indexing completed" value={number(totals.records)} detail={`${number(totals.chunks)} chunks published in this window`} /><Stat title="Processed text" value={bytes(totals.input_bytes)} detail="UTF-8 memory text in successful indexing jobs" /><Stat title="Time to searchable · p50" value={duration(data.queue_latency.p50_seconds == null ? null : data.queue_latency.p50_seconds * 1000)} detail="From accepted operation to ready state" /><Stat title="Time to searchable · p95" value={duration(data.queue_latency.p95_seconds == null ? null : data.queue_latency.p95_seconds * 1000)} detail={`${number(data.queue_latency.completed_operations)} completed operations`} /></div>
    <Traffic data={data} title="Pipeline throughput" />
    <div className="ins-grid"><Panel title="Durable job queue" subtitle="Includes retries, indexing and pending erasure" action={<Link to="/workspace/operations" className="ws-button ws-quiet">Inspect jobs<ArrowRight size={13} /></Link>}>
      <div className="ws-table-wrap"><table className="ws-table"><thead><tr><th>State</th><th>Jobs</th><th>Retried</th><th>Oldest created</th></tr></thead><tbody>{data.queue.length ? data.queue.map(row => <tr key={row.state}><td><span className={`ins-state ${row.state}`}>{label(row.state)}</span></td><td>{number(row.count)}</td><td>{number(row.retried)}</td><td>{when(row.oldest_at)}</td></tr>) : <tr><td colSpan={4}>No jobs yet.</td></tr>}</tbody></table></div>
    </Panel><Panel title="Source coordination" subtitle={data.source.managed ? "Managed connector scope" : "This space uses captured or imported evidence"}>
      {data.source.managed ? <><dl className="ins-key-values"><dt>Provider</dt><dd>{data.source.provider || "Operator details restricted"}</dd><dt>Access last observed</dt><dd>{when(data.source.observed_at)}</dd><dt>Access valid until</dt><dd>{when(data.source.access_valid_until)}</dd><dt>Last complete sync</dt><dd>{when(data.source.completed_at)}</dd><dt>Operator pause</dt><dd>{data.source.operator_paused == null ? "Not available" : data.source.operator_paused ? "Paused" : "Active"}</dd></dl>
        <Composition name="Connector item states" values={data.source.items.map(row => ({ ...row, label: label(row.label) }))} /></> : <div className="ins-note"><Database size={22} /><p>Sources in this space are saved through applications, imports or direct captures. Connector access leases and sync checkpoints appear in their managed source spaces.</p></div>}
      {!data.source.operator_details_available && data.source.managed && <p className="ins-footnote">Connector administration details require the appropriate operator identity. Memory access remains scoped to this space.</p>}
    </Panel></div>
  </>;
}

function Models({ data, runtime, error, administrator, live }: { data: Insights; runtime?: RuntimeInsights; error?: string; administrator: boolean; live: boolean }) {
  const [samples, setSamples] = useState<{ at: string; epoch: string; rss: number; cpu: number }[]>([]);
  useEffect(() => { if (runtime?.resources.available && runtime.resources.rss_bytes != null && runtime.resources.cpu_seconds != null) setSamples(previous => {
    if (previous.at(-1)?.at === runtime.observed_at) return previous;
    const kept = previous.at(-1)?.epoch === runtime.telemetry.started_at ? previous : [];
    return [...kept, { at: runtime.observed_at, epoch: runtime.telemetry.started_at, rss: runtime.resources.rss_bytes!, cpu: runtime.resources.cpu_seconds! }].slice(-120);
  }); }, [runtime]);
  const resourcePoints = samples.map(row => ({ at: row.at, values: { rss: row.rss } }));
  const previous = samples.at(-2), last = samples.at(-1);
  const cores = previous && last && +new Date(last.at) > +new Date(previous.at) ? (last.cpu - previous.cpu) / ((+new Date(last.at) - +new Date(previous.at)) / 1000) : null;
  const active = data.generations.find(row => row.active);
  const resources = runtime?.resources;
  return <><div className="ins-model-banner"><div className="ins-model-symbol"><Cpu size={28} /></div><div><span className="ws-eyebrow">Active embedding generation</span><h2>{active?.model || runtime?.model || "Configured service model"}</h2><p>{number(active?.dimensions || runtime?.dimensions)} dimensions · {number(active?.chunks ?? 0)} stored chunks · {bytes(active?.vector_bytes)}</p><code>{data.generation_id}</code></div><span className="ins-state ready">Fingerprint pinned</span></div>
    <div className="ins-grid"><Panel title="Index generations" subtitle="Separate vector spaces; stored bytes exclude database index overhead"><div className="ws-table-wrap"><table className="ws-table"><thead><tr><th>Model / generation</th><th>Dimensions</th><th>Chunks</th><th>Values</th></tr></thead><tbody>{data.generations.map(row => <tr key={row.id}><td>{row.model}{row.active && <span className="ins-inline-tag">Active</span>}<small>{row.id.slice(0, 16)}</small></td><td>{number(row.dimensions)}</td><td>{number(row.chunks)}</td><td>{bytes(row.vector_bytes)}</td></tr>)}</tbody></table></div><p className="ins-footnote">Changing a model requires a distinct generation and a verified reindex. Old and new embedding spaces are never mixed.</p></Panel>
      <Panel title="Vector and text traffic" subtitle="Recorded logical payloads, not physical hardware bandwidth"><Bars name="Pipeline byte volume" format={bytes} values={Object.entries(stages).map(([key, title]) => ({ label: `${title} output`, value: data.metrics.groups.filter(group => group.stage === key).reduce((n, row) => n + row.output_bytes, 0) }))} /><p className="ins-footnote">Provider billing, GPU counters and physical DRAM bandwidth require their own sensors. They are not inferred from these totals.</p></Panel></div>
    {!administrator ? <p className="ws-notice">Your space's index statistics are shown above. Process-wide resource and model configuration details require a tenant administrator.</p> : error ? <p className="ws-notice ws-error" role="alert">{error}</p> : !runtime ? <div className="ws-loading"><LoaderCircle size={17} className="ws-spin" />Reading API process gauges…</div> : <>
      <div className="ins-section-heading"><h2>API process resources</h2><p>Process-local counters · {resources?.platform} {resources?.architecture} · started {when(runtime.telemetry.started_at)}</p></div>
      <div className="ins-stat-grid"><Stat title="Resident memory" value={bytes(resources?.rss_bytes)} detail={resources?.memory_limit_bytes ? `Cgroup limit ${bytes(resources.memory_limit_bytes)}` : "No measured cgroup memory cap"} /><Stat title="CPU in use" value={cores == null ? "—" : `${number(cores, 2)} cores`} detail={resources?.cpu_limit_cores ? `${number(resources.cpu_limit_cores, 2)} cores allowed by cgroup` : `${number(resources?.logical_cpus)} logical CPUs reported`} />
        <Stat title="Inference admitted" value={runtime.inference ? `${runtime.inference.active} active` : "—"} detail={runtime.inference ? `${runtime.inference.queued} waiting · queue capacity ${runtime.inference.queue_capacity}` : "Provider admission counters unavailable"} /><Stat title="Capacity rejections" value={number(runtime.inference?.rejected)} detail="Retryable admission failures since process start" tone={runtime.inference?.rejected ? "warm" : ""} /></div>
      <div className="ins-grid ins-grid-wide"><Panel title="Resident memory while monitoring" subtitle={`Local observation history · up to 120 samples · ${live ? "15 second refresh" : "manual refresh"}`}><TimeChart name="API resident memory" points={resourcePoints} series={[{ key: "rss", label: "API process", color: palette[1] }]} unit="bytes" format={bytes} bucketSeconds={90} /><p className="ins-footnote">This history is collected while the view is open and resets when the API process changes. Separate workers, databases and remote model hosts are not included.</p></Panel>
        <Panel title="Collector & connection pressure" subtitle="Diagnostic overhead is bounded"><dl className="ins-key-values"><dt>Buffered metric series</dt><dd>{runtime.telemetry.buffered_series} / {runtime.telemetry.series_capacity}</dd><dt>Dropped samples</dt><dd>{number(runtime.telemetry.dropped_samples)}</dd><dt>Persisted samples</dt><dd>{number(runtime.telemetry.persisted_samples)}</dd><dt>Last flush</dt><dd>{when(runtime.telemetry.last_flush_at)}</dd><dt>DB connections</dt><dd>{number(runtime.pool.pool_size)} / {number(runtime.pool.pool_max)}</dd><dt>Waiting for DB</dt><dd>{number(runtime.pool.requests_waiting)}</dd><dt>Native threads</dt><dd>{number(resources?.threads)}</dd><dt>Model loaded</dt><dd>{runtime.model_loaded == null ? "Provider managed" : runtime.model_loaded ? "Yes" : "No"}</dd></dl></Panel></div>
      {!!runtime.models?.length && <Panel title="Models in this API process" subtitle="Cumulative provider request attempts and JSON payload bytes; excludes network overhead and provider charges"><DataTable name="Runtime embedding models" columns={["Model", "Loaded", "Requests", "Failures", "Request payload", "Response payload"]} rows={runtime.models.map(model => [model.model, model.model_loaded == null ? "Provider managed" : model.model_loaded ? "Yes" : "No", model.provider ? number(model.provider.requests) : "Local", model.provider ? number(model.provider.failed_requests) : "—", model.provider ? bytes(model.provider.request_bytes) : "—", model.provider ? bytes(model.provider.response_bytes) : "—"])} /></Panel>}
      <details className="ins-definitions"><summary>Default local model configuration</summary><pre className="ins-json">{JSON.stringify(runtime.configuration, null, 2)}</pre>{runtime.notices.map(notice => <p key={notice}>{notice}</p>)}</details>
    </>}
  </>;
}
