import { useEffect, useRef, useState, type CSSProperties, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, Check, ChevronLeft, ChevronRight, Code2, Copy, FileJson, FlaskConical, GitCompareArrows, Layers, ListChecks, LoaderCircle, Play, Plus, RefreshCw, ShieldCheck, Square, Trash2, Upload, X } from "lucide-react";
import type { AssessmentLabel, EvaluationCase, EvaluationComparison, EvaluationDataset, EvaluationDatasetInput, EvaluationMode, EvaluationResult, EvaluationRun, EvaluationSplit, MnemionClient } from "@mnemion/client";
import { Bars, DataTable, EmptyChart, ExportButton, Panel, Stat, download, duration, label, number, palette, percent, when } from "./Charts";

const busy = <div className="ws-loading"><LoaderCircle size={17} className="ws-spin" />Reading evaluation data…</div>;
const errorText = (error: unknown) => error instanceof Error ? error.message : "The action could not be completed.";
const active = (run: EvaluationRun) => ["queued", "running"].includes(run.state);
const pct = (value: number) => percent(value);

function editorPayload(value: unknown): EvaluationDatasetInput {
  if (!value || typeof value !== "object") throw new Error("A test set must be a JSON object.");
  const data = value as Record<string, unknown>;
  if (typeof data.name !== "string" || (data.description !== undefined && typeof data.description !== "string") || !Array.isArray(data.cases) || !data.cases.length || data.cases.length > 1000) throw new Error("Use a name and an array of 1 to 1,000 questions.");
  for (const item of data.cases) {
    if (!item || typeof item !== "object" || typeof item.id !== "string" || typeof item.query !== "string"
      || (item.category !== undefined && typeof item.category !== "string")
      || (item.split !== undefined && !["development", "held_out"].includes(item.split))
      || (item.unanswerable !== undefined && typeof item.unanswerable !== "boolean")
      || ["known_at", "valid_at"].some(key => item[key] != null && typeof item[key] !== "string")
      || (item.references !== undefined && (!Array.isArray(item.references) || item.references.length > 50 || item.references.some((ref: unknown) => {
        if (!ref || typeof ref !== "object") return true;
        const reference = ref as Record<string, unknown>;
        return typeof reference.memory_id !== "string" || (reference.revision_id != null && typeof reference.revision_id !== "string")
          || (reference.grade !== undefined && (!Number.isInteger(reference.grade) || ![1, 2, 3].includes(reference.grade as number)));
      })))) throw new Error("Each question needs a string ID and query, a valid split, timestamp strings and reference memory IDs with optional grades 1–3.");
  }
  return value as EvaluationDatasetInput;
}

export default function Evaluations({ client, space, serviceVersion }: { client: MnemionClient; space: string; serviceVersion?: string | null }) {
  const cache = useQueryClient();
  const [params, setParams] = useSearchParams();
  const selected = params.get("run") || "";
  const [tab, setTab] = useState<"runs" | "datasets" | "compare">("runs");
  const [draft, setDraft] = useState<EvaluationDatasetInput | null>(null);
  const [launch, setLaunch] = useState(false);
  const [error, setError] = useState<unknown>();
  const [datasetCursor, setDatasetCursor] = useState<string>();
  const [datasetPages, setDatasetPages] = useState<(string | undefined)[]>([]);
  const [runCursor, setRunCursor] = useState<string>();
  const [runPages, setRunPages] = useState<(string | undefined)[]>([]);
  const datasets = useQuery({ queryKey: ["evaluation-datasets", space, datasetCursor], queryFn: () => client.evaluationDatasets(space, { cursor: datasetCursor, limit: 50 }), staleTime: 60000, retry: 1 });
  const runs = useQuery({ queryKey: ["evaluation-runs", space, runCursor], queryFn: () => client.evaluationRuns(space, { cursor: runCursor, limit: 50 }), staleTime: 10000,
    refetchInterval: query => query.state.data?.items.some(active) ? 5000 : false, refetchIntervalInBackground: false, retry: 1 });
  const choose = (id: string) => setParams(previous => { const next = new URLSearchParams(previous); next.set("view", "evaluations"); id ? next.set("run", id) : next.delete("run"); return next; }, { replace: true });
  const refresh = async () => { await cache.invalidateQueries({ queryKey: ["evaluation-datasets", space] }); await cache.invalidateQueries({ queryKey: ["evaluation-runs", space] }); };
  if (datasets.isError || runs.isError) return <div className="ws-notice ws-error" role="alert"><p>{errorText(datasets.error || runs.error)}</p><button className="ws-button" onClick={() => { void datasets.refetch(); void runs.refetch(); }} disabled={datasets.isFetching || runs.isFetching}><RefreshCw size={14} />Retry evaluation data</button></div>;
  if (datasets.isPending || runs.isPending) return busy;
  if (selected) return <RunDetails key={selected} client={client} space={space} id={selected} back={() => choose("")} />;
  const current = runs.data.items.find(active);
  return <>
    <div className="ins-eval-heading"><div><h2>Evaluation lab</h2><p>Use your own questions and reference evidence. Keep the configuration. Compare the result.</p></div>
      <button className="ws-button ws-primary" disabled={!datasets.data.items.some(item => item.state === "active") || !!current} onClick={() => setLaunch(!launch)}><Play size={15} />New evaluation</button>
    </div>
    {current && <button className="ins-running-banner" onClick={() => choose(current.id)}><LoaderCircle size={19} className="ws-spin" /><div><strong>{current.state === "queued" ? "Evaluation queued" : "Evaluation in progress"}</strong><span>{current.progress} / {current.total} case-mode checks · {label(current.configuration.split)}</span></div><progress value={current.progress} max={current.total} /><ArrowRight size={17} /></button>}
    {!!error && <div className="ws-notice ws-error" role="alert">{errorText(error)}</div>}
    {launch && <RunForm client={client} space={space} serviceVersion={serviceVersion} datasets={datasets.data.items.filter(item => item.state === "active")} close={() => setLaunch(false)} created={run => { setLaunch(false); void refresh(); choose(run.id); }} />}
    <div className="ins-subtabs" role="group" aria-label="Evaluation sections">{[
      { key: "runs", title: "Runs", icon: FlaskConical, count: runs.data.items.length },
      { key: "datasets", title: "Test sets", icon: Layers, count: datasets.data.items.length },
      { key: "compare", title: "Compare", icon: GitCompareArrows },
    ].map(item => <button key={item.key} aria-pressed={tab === item.key} onClick={() => setTab(item.key as typeof tab)}><item.icon size={15} />{item.title}{item.count !== undefined && <span>{item.count}</span>}</button>)}
      <button className="ws-button ws-quiet ins-push" onClick={() => { void refresh(); }} aria-label="Refresh evaluations"><RefreshCw size={14} /></button>
    </div>
    {tab === "runs" && (runs.data.items.length ? <Panel title="Evaluation history" subtitle="50 runs per page · full manifests and results stay available by run ID">
      <div className="ws-table-wrap"><table className="ws-table"><thead><tr><th>Run & test set</th><th>State</th><th>Configuration</th><th>Cases</th><th>Started</th><th /></tr></thead><tbody>{runs.data.items.map(run => <tr key={run.id}>
        <td><button className="ins-text-button" onClick={() => choose(run.id)}>{datasets.data.items.find(item => item.id === run.dataset_id)?.name || "Test set"}</button><small>{run.id.slice(0, 12)} · v{run.manifest.dataset_version}</small></td>
        <td><span className={`ins-state ${run.state}`}>{label(run.state)}</span>{(run.manifest.corpus_changed || run.manifest.index_changed) && <small className="ins-warm-text">Data changed during run</small>}</td>
        <td>{run.configuration.modes.join(" · ")}<small>{label(run.configuration.split)} · {run.manifest.generation.model}</small></td>
        <td>{run.progress} / {run.total}</td><td>{when(run.started_at || run.created_at)}</td><td><button className="ws-button ws-quiet" onClick={() => choose(run.id)} aria-label={`Inspect run ${run.id}`}><ArrowRight size={15} /></button></td>
      </tr>)}</tbody></table></div></Panel> : <div className="ins-eval-empty"><div className="ins-eval-symbol"><FlaskConical size={38} /></div><h2>Build confidence with evidence</h2><p>Create a test set of questions and the memories that should answer them. Then compare retrieval modes, context coverage, citations and latency.</p><div className="ins-eval-steps"><span><b>01</b>Label reference memories</span><span><b>02</b>Run a bounded evaluation</span><span><b>03</b>Inspect & compare</span></div><button className="ws-button ws-primary" onClick={() => { setTab("datasets"); setDraft({ name: "", cases: [{ id: "question_1", query: "", category: "general", split: "development", references: [] }] }); }}><Plus size={15} />Create your first test set</button></div>)}
    {tab === "runs" && <div className="ins-pagination"><button className="ws-button ws-quiet" disabled={!runPages.length} onClick={() => { setRunCursor(runPages.at(-1)); setRunPages(runPages.slice(0, -1)); }}><ChevronLeft size={14} />Previous runs</button><span>Page {runPages.length + 1}</span><button className="ws-button ws-quiet" disabled={!runs.data.next_cursor} onClick={() => { setRunPages([...runPages, runCursor]); setRunCursor(runs.data.next_cursor!); }}>Older runs<ChevronRight size={14} /></button></div>}
    {tab === "datasets" && <div className="ins-pagination"><button className="ws-button ws-quiet" disabled={!datasetPages.length} onClick={() => { setDatasetCursor(datasetPages.at(-1)); setDatasetPages(datasetPages.slice(0, -1)); }}><ChevronLeft size={14} />Previous test sets</button><span>Page {datasetPages.length + 1}</span><button className="ws-button ws-quiet" disabled={!datasets.data.next_cursor} onClick={() => { setDatasetPages([...datasetPages, datasetCursor]); setDatasetCursor(datasets.data.next_cursor!); }}>Older test sets<ChevronRight size={14} /></button></div>}
    {tab === "datasets" && <>
      <div className="ins-section-heading"><div><h2>Versioned test sets</h2><p>Queries and labels stay outside searchable memory. Source revisions are pinned when saved.</p></div><button className="ws-button" onClick={() => setDraft({ name: "", cases: [{ id: "question_1", query: "", category: "general", split: "development", references: [] }] })}><Plus size={14} />Create or import</button></div>
      {draft && <DatasetEditor key={JSON.stringify(draft)} client={client} space={space} initial={draft} close={() => setDraft(null)} saved={() => { setDraft(null); void refresh(); }} />}
      <div className="ins-dataset-grid">{datasets.data.items.map(dataset => <article className="ins-dataset-card" key={dataset.id}><div><span className="ins-dataset-icon"><FileJson size={20} /></span><span className={`ins-state ${dataset.state === "active" ? "ready" : dataset.state}`}>{dataset.state}</span></div><h3>{dataset.name}</h3><p>{dataset.description || "No description"}</p><div className="ins-dataset-counts"><span><b>{dataset.development_count}</b>Development</span><span><b>{dataset.held_out_count}</b>Held out</span><span><b>v{dataset.version}</b>Version</span></div><code title={dataset.content_hash}>{dataset.content_hash.slice(0, 20)}…</code><small>{when(dataset.created_at)}</small>
        <footer><button className="ws-button ws-quiet" disabled={dataset.state !== "active"} onClick={async () => { try { const full = await client.evaluationDataset(space, dataset.id); setDraft({ name: full.name, description: full.description, cases: full.cases || [] }); } catch (error) { setError(error); } }}><Copy size={13} />Open as draft</button>
          <button className="ws-button ws-quiet" disabled={dataset.state === "deleted"} aria-label={`Remove test set ${dataset.name}`} onClick={async () => { if (!window.confirm("Remove this test set, its questions, reference labels, results and human assessments? Export any results you want to retain first.")) return; try { await client.removeEvaluationDataset(space, dataset.id); await refresh(); } catch (error) { setError(error); } }}><Trash2 size={14} /></button></footer>
      </article>)}</div>
      {!datasets.data.items.length && !draft && <EmptyChart>Create a test set to define what useful retrieval means for this space.</EmptyChart>}
    </>}
    {tab === "compare" && <CompareRuns client={client} space={space} runs={runs.data.items} inspect={choose} />}
    <div className="ins-note"><ShieldCheck size={19} /><p>Evaluation uses current space permissions and a single durable execution slot. Deleting reference evidence hides related test details and removes them during purge. Automated scores measure retrieval and citation behavior; human usefulness assessments remain separate.</p></div>
  </>;
}

function ReferenceIds({ references, change }: {
  references: NonNullable<EvaluationCase["references"]>;
  change: (references: NonNullable<EvaluationCase["references"]>) => void;
}) {
  const [text, setText] = useState(() => references.map(ref => ref.memory_id).join("\n"));
  const parse = (value: string) => value.split(/\r?\n/).map(id => id.trim()).filter(Boolean);
  useEffect(() => {
    // Preserve whitespace while typing; picker changes still update the field.
    if (JSON.stringify(parse(text)) !== JSON.stringify(references.map(ref => ref.memory_id))) {
      setText(references.map(ref => ref.memory_id).join("\n"));
    }
  }, [references, text]);
  return <label className="ws-field"><span>Relevant memory IDs · one per line</span><textarea rows={3} required maxLength={4096} value={text}
    onChange={event => {
      setText(event.target.value);
      change(parse(event.target.value).map(id => references.find(ref => ref.memory_id === id) || { memory_id: id }));
    }} placeholder="Select memories below, or paste their IDs" /></label>;
}

function DatasetEditor({ client, space, initial, close, saved }: { client: MnemionClient; space: string; initial: EvaluationDatasetInput; close: () => void; saved: () => void }) {
  const [draft, setDraft] = useState(initial);
  const [tab, setTab] = useState<"form" | "json">("form");
  const [raw, setRaw] = useState(JSON.stringify(initial, null, 2));
  const [selected, setSelected] = useState(0);
  const [browse, setBrowse] = useState(false);
  const [cursor, setCursor] = useState<string>();
  const [cursors, setCursors] = useState<(string | undefined)[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<unknown>();
  const memories = useQuery({ queryKey: ["evaluation-reference-picker", space, cursor], queryFn: () => client.list(space, { limit: 20, cursor }), enabled: browse, staleTime: 30000, retry: 1 });
  const current = draft.cases[selected];
  const casePage = Math.floor(selected / 40);
  const update = (values: Partial<EvaluationCase>) => setDraft(old => ({ ...old, cases: old.cases.map((item, index) => index === selected ? { ...item, ...values } : item) }));
  const switchTab = (next: "form" | "json") => { try { if (next === "json") setRaw(JSON.stringify(draft, null, 2)); else { setDraft(editorPayload(JSON.parse(raw))); setSelected(0); } setError(undefined); setTab(next); } catch (error) { setError(error); } };
  async function submit(event: FormEvent) {
    event.preventDefault(); setSubmitting(true); setError(undefined);
    try { const payload = tab === "json" ? JSON.parse(raw) : draft; await client.createEvaluationDataset(space, payload); saved(); }
    catch (error) { setError(error); } finally { setSubmitting(false); }
  }
  return <Panel title="Test-set editor" subtitle="Saving changed questions or labels creates a new version." action={<button className="ws-icon-button" onClick={close} aria-label="Close test-set editor"><X size={17} /></button>} className="ins-editor">
    <div className="ins-subtabs"><button aria-pressed={tab === "form"} onClick={() => switchTab("form")}><ListChecks size={14} />Question editor</button><button aria-pressed={tab === "json"} onClick={() => switchTab("json")}><Code2 size={14} />JSON</button>
      <label className="ws-button ws-quiet ins-file-input"><Upload size={14} />Import JSON<input type="file" accept="application/json,.json" onChange={async event => { const file = event.target.files?.[0]; if (!file) return; try { if (file.size > 1500000) throw new Error("A test set must fit within 1.5 MB."); const text = await file.text(); JSON.parse(text); setRaw(text); setTab("json"); setError(undefined); } catch (error) { setError(error); } event.target.value = ""; }} /></label>
    </div>
    <form onSubmit={submit}>
      {tab === "json" ? <label className="ws-field"><span>Test-set JSON · up to 1,000 questions and 1.5 MB</span><textarea className="ins-json-editor" value={raw} onChange={event => setRaw(event.target.value)} rows={16} spellCheck={false} maxLength={1500000} /></label> : <>
        <div className="ins-form-grid"><label className="ws-field"><span>Test-set name</span><input required maxLength={200} value={draft.name} onChange={event => setDraft({ ...draft, name: event.target.value })} placeholder="Team knowledge checks" /></label><label className="ws-field"><span>Description</span><input maxLength={4000} value={draft.description || ""} onChange={event => setDraft({ ...draft, description: event.target.value })} placeholder="What should this set help you verify?" /></label></div>
        <div className="ins-case-editor"><div className="ins-case-list"><h3>Questions <span>{draft.cases.length}</span></h3>{draft.cases.slice(casePage * 40, (casePage + 1) * 40).map((item, j) => { const i = casePage * 40 + j; return <button type="button" key={i} aria-pressed={selected === i} onClick={() => setSelected(i)}><span>{String(i + 1).padStart(2, "0")}</span><div><strong>{item.id || "Untitled"}</strong><small>{label(item.split || "development")}{item.unanswerable ? " · unanswerable" : ""}</small></div></button>; })}{draft.cases.length > 40 && <div className="ins-pagination"><button type="button" className="ws-button ws-quiet" disabled={casePage === 0} onClick={() => setSelected((casePage - 1) * 40)} aria-label="Previous questions"><ChevronLeft size={13} /></button><small>{casePage + 1} / {Math.ceil(draft.cases.length / 40)}</small><button type="button" className="ws-button ws-quiet" disabled={(casePage + 1) * 40 >= draft.cases.length} onClick={() => setSelected((casePage + 1) * 40)} aria-label="Next questions"><ChevronRight size={13} /></button></div>}<button type="button" className="ws-button ws-quiet" disabled={draft.cases.length >= 1000} onClick={() => { let index = draft.cases.length + 1; while (draft.cases.some(item => item.id === `question_${index}`)) index++; setDraft({ ...draft, cases: [...draft.cases, { id: `question_${index}`, query: "", category: "general", split: "development", references: [] }] }); setSelected(draft.cases.length); }}><Plus size={14} />Add question</button></div>
          {current && <div className="ins-case-fields"><div className="ins-form-grid"><label className="ws-field"><span>Stable question ID</span><input required pattern="[A-Za-z0-9_.\-]+" maxLength={80} value={current.id} onChange={event => update({ id: event.target.value })} /></label><label className="ws-field"><span>Category</span><input maxLength={80} required value={current.category || "general"} onChange={event => update({ category: event.target.value })} /></label></div>
            <label className="ws-field"><span>Question</span><textarea required rows={3} maxLength={4000} value={current.query} onChange={event => update({ query: event.target.value })} placeholder="Which memories should answer this question?" /></label>
            <div className="ins-form-grid"><label className="ws-field"><span>Split</span><select value={current.split || "development"} onChange={event => update({ split: event.target.value as EvaluationSplit })}><option value="development">Development · iterate here</option><option value="held_out">Held out · evaluate final choices</option></select></label><label className="ins-live-control"><input type="checkbox" checked={!!current.unanswerable} onChange={event => update({ unanswerable: event.target.checked, references: [] })} />Intentionally unanswerable</label></div>
            {current.unanswerable ? <p className="ins-footnote">This question has no supporting reference. It is excluded from recall denominators. Inspect its output before assigning any human abstention judgment.</p> : <><ReferenceIds key={selected} references={current.references || []} change={references => update({ references })} /><button type="button" className="ws-button ws-quiet" onClick={() => setBrowse(!browse)}><Layers size={14} />{browse ? "Hide memory picker" : "Browse reference memories"}</button></>}
            {browse && !current.unanswerable && <div className="ins-reference-picker">{memories.isError ? <p role="alert">{memories.error.message}</p> : memories.isPending ? busy : <>{memories.data.items.map(memory => <label key={memory.memory_id}><input type="checkbox" checked={current.references?.some(ref => ref.memory_id === memory.memory_id) || false} onChange={event => update({ references: event.target.checked ? [...(current.references || []), { memory_id: memory.memory_id }] : current.references?.filter(ref => ref.memory_id !== memory.memory_id) })} /><span><strong>{memory.subject || label(memory.kind)}</strong><small>{memory.content.slice(0, 160)}</small><code>{memory.memory_id}</code></span></label>)}<div className="ins-pagination"><button type="button" className="ws-button ws-quiet" disabled={!cursors.length} onClick={() => { setCursor(cursors.at(-1)); setCursors(cursors.slice(0, -1)); }}><ChevronLeft size={14} />Previous</button><button type="button" className="ws-button ws-quiet" disabled={!memories.data.next_cursor} onClick={() => { setCursors([...cursors, cursor]); setCursor(memories.data.next_cursor!); }}>Next<ChevronRight size={14} /></button></div></>}</div>}
            <details className="ins-inline-details"><summary>Temporal filters & relevance grades</summary><div className="ins-form-grid"><label className="ws-field"><span>Known at · ISO 8601 with timezone</span><input value={current.known_at || ""} onChange={event => update({ known_at: event.target.value || null })} placeholder="2026-10-10T09:00:00Z" /></label><label className="ws-field"><span>Valid at · ISO 8601 with timezone</span><input value={current.valid_at || ""} onChange={event => update({ valid_at: event.target.value || null })} placeholder="2026-10-10T09:00:00Z" /></label></div>
              <p className="ins-footnote">The JSON editor supports explicit historical revision IDs and relevance grades 1–3. Otherwise the current revision is pinned with grade 1 when this version is saved.</p></details>
            {draft.cases.length > 1 && <button type="button" className="ws-button ws-quiet" onClick={() => { setDraft({ ...draft, cases: draft.cases.filter((_, i) => i !== selected) }); setSelected(Math.max(0, selected - 1)); }}><Trash2 size={13} />Remove question</button>}
          </div>}
        </div>
      </>}
      {!!error && <p className="ws-notice ws-error" role="alert">{errorText(error)}</p>}
      <div className="ins-form-actions"><p>Labels are private to reviewers in this space. Development and held-out questions are scored separately.</p><button className="ws-button ws-primary" disabled={submitting}>{submitting ? <LoaderCircle size={14} className="ws-spin" /> : <Check size={14} />}Save test-set version</button></div>
    </form>
  </Panel>;
}

function RunForm({ client, space, serviceVersion, datasets, close, created }: { client: MnemionClient; space: string; serviceVersion?: string | null; datasets: EvaluationDataset[]; close: () => void; created: (run: EvaluationRun) => void }) {
  const [params] = useSearchParams();
  const [generation, setGeneration] = useState(params.get("generation") || "");
  const models = useQuery({ queryKey: ["embedding-choices", space], queryFn: () => client.embeddingChoices(space), retry: 1 });
  const selectedModel = models.data?.items.find(model => generation ? model.generation_id === generation : model.state === "active");
  const [dataset, setDataset] = useState(datasets[0]?.id || ""), [split, setSplit] = useState<EvaluationSplit>("development");
  const [modes, setModes] = useState<EvaluationMode[]>(["hybrid"]), [cutoffs, setCutoffs] = useState("5, 10, 20");
  const [context, setContext] = useState(true), [tokens, setTokens] = useState(2048), [seconds, setSeconds] = useState(300), [interval, setInterval] = useState(1);
  const [keywordFallback, setKeywordFallback] = useState(true);
  const [recencyWeight, setRecencyWeight] = useState("25"), [halfLifeDays, setHalfLifeDays] = useState("3");
  const [archiveWeight, setArchiveWeight] = useState("35"), [archiveDirectories, setArchiveDirectories] = useState("archive, archives");
  const serviceParts = serviceVersion?.match(/^(\d{1,5})\.(\d{1,5})\.(\d{1,5})$/)?.slice(1).map(Number);
  const supportsRankingOptions = !!serviceParts && (serviceParts[0] > 4 ||
    (serviceParts[0] === 4 && (serviceParts[1] > 3 || (serviceParts[1] === 3 && serviceParts[2] >= 3))));
  const [error, setError] = useState<unknown>(), [submitting, setSubmitting] = useState(false);
  const key = useRef({ body: "", key: "" });
  const chosen = datasets.find(item => item.id === dataset), count = chosen ? split === "development" ? chosen.development_count : chosen.held_out_count : 0;
  async function submit(event: FormEvent) {
    event.preventDefault(); setError(undefined); setSubmitting(true);
    try {
      const ks = cutoffs.split(",").map(value => Number(value.trim()));
      if (!ks.length || ks.length > 5 || ks.some(k => !Number.isInteger(k) || k < 1 || k > 50) || new Set(ks).size !== ks.length) throw new Error("Choose up to five distinct K values from 1 to 50.");
      const archiveSegments = archiveDirectories.split(",").map(part => part.trim()).filter(Boolean);
      if (supportsRankingOptions && (
        [recencyWeight, archiveWeight].some(value => !value.trim() || !Number.isFinite(Number(value)) || Number(value) < 0 || Number(value) > 100) ||
        !halfLifeDays.trim() || !Number.isFinite(Number(halfLifeDays)) || Number(halfLifeDays) < 1 / 24 || Number(halfLifeDays) > 36500 ||
        archiveSegments.length > 16 || archiveSegments.some(part => part.length > 128 || /[\\/\x00]/.test(part))
      )) throw new Error("Use percentages from 0 to 100, a half-life from one hour to 36,500 days, and at most 16 archive directory names without slashes.");
      const body = { dataset_id: dataset, split, modes, cutoffs: ks, context, token_budget: tokens, max_seconds: seconds, interval_seconds: interval, embedding_generation: generation || null,
        ...(supportsRankingOptions ? { keyword_fallback: keywordFallback, ranking_policy: {
          recency_weight: Number(recencyWeight) / 100, half_life_days: Number(halfLifeDays),
          archive_weight: Number(archiveWeight) / 100, archive_path_segments: archiveSegments,
        } } : {}),
      };
      const signature = JSON.stringify(body); if (key.current.body !== signature) key.current = { body: signature, key: crypto.randomUUID() };
      created(await client.startEvaluation(space, body, key.current.key));
    } catch (error) { setError(error); } finally { setSubmitting(false); }
  }
  return <Panel title="Configure evaluation" subtitle="A durable run with a fixed test set and explicit resource budget." action={<button className="ws-icon-button" onClick={close} aria-label="Close evaluation configuration"><X size={16} /></button>} className="ins-run-form"><form onSubmit={submit}>
    <label className="ws-field"><span>Embedding generation</span><select value={generation} onChange={event => setGeneration(event.target.value)} disabled={models.isPending}><option value="">Active index when this run is queued</option>{models.data?.items.map(model => <option key={model.generation_id} value={model.generation_id} disabled={!model.available}>{model.label} · {model.state} · {model.generation_id.slice(0, 10)}</option>)}</select><small>The run freezes the selected generation. Preview a candidate search first to warm up its model before measuring latency.</small></label>
    {models.isError && <p className="ws-notice ws-error" role="alert">{models.error.message}<button type="button" className="ws-link" onClick={() => void models.refetch()}>Retry model choices</button></p>}
    <div className="ins-form-grid"><label className="ws-field"><span>Test-set version</span><select value={dataset} onChange={event => setDataset(event.target.value)}>{datasets.map(item => <option key={item.id} value={item.id}>{item.name} · v{item.version} · {item.case_count} questions</option>)}</select></label><label className="ws-field"><span>Split</span><select value={split} onChange={event => setSplit(event.target.value as EvaluationSplit)}><option value="development">Development</option><option value="held_out">Held out</option></select></label></div>
    <div className="ins-form-grid"><fieldset className="ins-mode-picker"><legend>Retrieval modes</legend>{(["lexical", "semantic", "hybrid"] as EvaluationMode[]).map(mode => <label key={mode}><input type="checkbox" checked={modes.includes(mode)} onChange={event => setModes(event.target.checked ? [...modes, mode] : modes.filter(item => item !== mode))} /><span>{label(mode)}</span></label>)}</fieldset><label className="ws-field"><span>Evaluate at K</span><input value={cutoffs} onChange={event => setCutoffs(event.target.value)} placeholder="5, 10, 20" /><small>Top results to assess at each cutoff; at most 50.</small></label></div>
    <div className="ins-form-grid"><label className="ins-live-control"><input type="checkbox" checked={context} onChange={event => setContext(event.target.checked)} />Also evaluate bounded context</label><label className="ws-field"><span>Context {selectedModel?.token_count_unit === "utf8_bytes" ? "UTF-8 byte" : "token"} budget</span><input type="number" min={128} max={16000} step={1} disabled={!context} value={tokens} onChange={event => setTokens(Number(event.target.value))} /></label></div>
    {supportsRankingOptions && <details className="ins-inline-details"><summary>Ranking preferences</summary>
      <label className="ins-live-control"><input type="checkbox" checked={keywordFallback} onChange={event => setKeywordFallback(event.target.checked)} />Use key terms when a question has no complete text match</label>
      <div className="ins-form-grid">
        <label className="ws-field"><span>Recency influence (%)</span><input type="number" min={0} max={100} step={1} value={recencyWeight} onChange={event => setRecencyWeight(event.target.value)} /></label>
        <label className="ws-field"><span>Recency half-life (days)</span><input type="number" min={1 / 24} max={36500} step="any" value={halfLifeDays} onChange={event => setHalfLifeDays(event.target.value)} /></label>
        <label className="ws-field"><span>Archived match weight (%)</span><input type="number" min={0} max={100} step={1} value={archiveWeight} onChange={event => setArchiveWeight(event.target.value)} /></label>
        <label className="ws-field"><span>Archive directories (comma separated)</span><input maxLength={2063} value={archiveDirectories} onChange={event => setArchiveDirectories(event.target.value)} /></label>
      </div><p className="ins-footnote">These settings are saved with the run. Key-term support applies to hybrid search. Use 0% recency influence and 100% archived weight to assess relevance without age or archive adjustments. Compare runs on the same test set and unchanged memories.</p>
    </details>}
    {!supportsRankingOptions && <p className="ins-footnote">Configurable ranking evaluations need workspace server 4.3.3 or later. This run will use your server's existing settings.</p>}
    <details className="ins-inline-details"><summary>Execution budget</summary><div className="ins-form-grid"><label className="ws-field"><span>Maximum run duration · seconds</span><input type="number" min={10} max={3600} value={seconds} onChange={event => setSeconds(Number(event.target.value))} /></label><label className="ws-field"><span>Delay between case-mode checks · seconds</span><input type="number" min={.25} max={60} step={.25} value={interval} onChange={event => setInterval(Number(event.target.value))} /></label></div><p className="ins-footnote">One evaluation runs at a time across the deployment. Calls use the selected service model. The runner does not download or launch new local models.</p></details>
    {split === "held_out" && <p className="ins-note">Keep this split for assessing final choices. Repeated tuning on held-out results makes the evaluation less independent.</p>}
    {!!error && <p className="ws-notice ws-error" role="alert">{errorText(error)}</p>}
    <div className="ins-form-actions"><p><b>{count * modes.length}</b> case-mode checks{context ? " + context calls" : ""} · {seconds} second budget</p><button className="ws-button ws-primary" disabled={submitting || !count || !modes.length || !selectedModel?.available}>{submitting ? <LoaderCircle size={14} className="ws-spin" /> : <Play size={14} />}Start evaluation</button></div>
  </form></Panel>;
}

function RunDetails({ client, space, id, back }: { client: MnemionClient; space: string; id: string; back: () => void }) {
  const cache = useQueryClient();
  const [error, setError] = useState<unknown>();
  const [mode, setMode] = useState<EvaluationMode | "">("");
  const [cutoff, setCutoff] = useState("");
  const [cursor, setCursor] = useState(0), [pages, setPages] = useState<number[]>([]), [selected, setSelected] = useState<number | null>(null);
  const full = useRef(false);
  const run = useQuery({ queryKey: ["evaluation-run", space, id], queryFn: async () => {
    const row = await client.evaluationRun(space, id, !full.current);
    if (!active(row) && !full.current) { full.current = true; return client.evaluationRun(space, id); }
    return row;
  },
    refetchInterval: query => query.state.data && active(query.state.data) ? 5000 : false, refetchIntervalInBackground: false, retry: 1 });
  const dataset = useQuery({ queryKey: ["evaluation-dataset", space, run.data?.dataset_id], queryFn: () => client.evaluationDataset(space, run.data!.dataset_id), enabled: !!run.data && run.data.state !== "invalidated", staleTime: 60000, retry: 1 });
  // Progress polling is separate from the paginated case payload. Refresh cases
  // after a completed run or explicitly, rather than retransferring them every tick.
  const results = useQuery({ queryKey: ["evaluation-results", space, id, cursor, run.data?.state], queryFn: () => client.evaluationResults(space, id, cursor), enabled: !!run.data && run.data.state !== "invalidated", staleTime: 30000, retry: 1 });
  async function exported(format: "json" | "csv") { try { const bytes = await client.exportEvaluation(space, id, format); download(bytes, `mnemion-evaluation-${id}.${format}`, format === "json" ? "application/json" : "text/csv"); } catch (error) { setError(error); } }
  if (run.isError) return <><button className="ws-button ws-quiet" onClick={back}><ArrowLeft size={15} />All evaluations</button><div className="ws-notice ws-error" role="alert"><p>{run.error.message}</p><button className="ws-button" disabled={run.isFetching} onClick={() => void run.refetch()}><RefreshCw size={14} />Retry evaluation</button></div></>;
  if (run.isPending) return busy;
  const value = run.data;
  const modes = value.configuration.modes, selectedMode = modes.includes(mode as EvaluationMode) ? mode as EvaluationMode : modes[0];
  const selectedK = value.configuration.cutoffs.map(String).includes(cutoff) ? cutoff : String(value.configuration.cutoffs.at(-1));
  const summary = value.summary?.modes[selectedMode], scores = summary?.metrics[selectedK];
  const selectedResult = results.data?.items.find(item => item.position === selected);
  const redacted = value.state === "invalidated";
  return <><button className="ws-button ws-quiet ins-back" onClick={back}><ArrowLeft size={15} />All evaluations</button>
    <div className="ins-eval-heading"><div><p className="ws-eyebrow">Run {id.slice(0, 12)}</p><h2>{redacted ? "Evaluation evidence unavailable" : dataset.data?.name || "Evaluation results"}</h2><p>Test set v{value.manifest.dataset_version} · {label(value.configuration.split)} · {value.manifest.generation.model}</p></div><span className={`ins-state ${value.state}`}>{label(value.state)}</span></div>
    <div className="ins-run-toolbar"><span>{value.progress} / {value.total} case-mode checks</span><span>{when(value.started_at || value.created_at)}</span><div className="ins-push" />
      {active(value) && <button className="ws-button" onClick={async () => { try { await client.cancelEvaluation(space, id); await cache.invalidateQueries({ queryKey: ["evaluation-run", space, id] }); } catch (error) { setError(error); } }}><Square size={13} />Cancel run</button>}
      <ExportButton disabled={redacted} onClick={() => void exported("json")} /><ExportButton disabled={redacted} onClick={() => void exported("csv")}>Export CSV</ExportButton>
    </div>
    {active(value) && <div className="ins-progress"><progress value={value.progress} max={value.total} /><span>{percent(value.progress / value.total)} · progress refreshes every 5 seconds</span></div>}
    {!!error && <div className="ws-notice ws-error" role="alert">{errorText(error)}</div>}
    {value.error_code && <p className="ws-notice">{errorReason(value.error_code)}</p>}
    {(value.manifest.corpus_changed || value.manifest.index_changed) && <div className="ws-notice">The corpus or index changed during this run. Treat it as a diagnostic observation; it cannot establish a controlled comparison.</div>}
    {!redacted && <>
      {value.summary && <><div className="ins-sub-toolbar"><div className="ins-window" role="group" aria-label="Result retrieval mode">{modes.map(item => <button key={item} aria-pressed={selectedMode === item} onClick={() => setMode(item)}>{label(item)}</button>)}</div><label className="ins-select"><span>Cutoff</span><select value={selectedK} onChange={event => setCutoff(event.target.value)}>{value.configuration.cutoffs.map(k => <option key={k} value={k}>K = {k}</option>)}</select></label></div>
        <div className="ins-stat-grid"><Stat title={`Recall @ ${selectedK}`} value={percent(scores?.recall)} detail={`${number(scores?.n)} scored answerable cases`} tone="mint" /><Stat title={`NDCG @ ${selectedK}`} value={number(scores?.ndcg, 3)} detail="Graded, rank-discounted relevance" /><Stat title="Complete evidence" value={percent(scores?.complete_rate)} detail={`${number(scores?.complete)} / ${number(scores?.n)} answerable cases`} /><Stat title="Retrieval p95" value={duration(summary?.latency_p95_ms)} detail={`${number(summary?.successful)} successful · ${number(summary?.failed)} failed`} /></div>
        <div className="ins-grid"><Panel title={`Recall by mode @ ${selectedK}`} subtitle="Mean case recall · lines show the 95% bootstrap interval"><Bars name="Evaluation recall by retrieval mode" format={pct} total={1} values={modes.flatMap((item, i) => { const score = value.summary?.modes[item]?.metrics[selectedK]; return score?.recall == null ? [] : [{ label: label(item), value: score.recall, color: palette[i], interval: score.recall_bootstrap95 }]; })} /><p className="ins-footnote">{value.summary.uncertainty.note}</p></Panel>
          <Panel title="Evidence in the context" subtitle="Reference coverage is distinct from answer correctness"><div className="ins-context-scores"><div><strong>{percent(summary?.context_recall)}</strong><span>Context reference recall</span></div><div><strong>{percent(summary?.citation_validity)}</strong><span>Checked citations valid</span></div></div><dl className="ins-key-values"><dt>Complete context cases</dt><dd>{number(summary?.context_complete)} / {number(summary?.context_cases)}</dd><dt>Citation checks</dt><dd>{number(summary?.citations_checked)}</dd><dt>Context tokens consumed</dt><dd>{number(summary?.context_tokens)}</dd><dt>Unanswerable cases</dt><dd>{number(summary?.unanswerable)} · excluded from recall</dd></dl><p className="ins-footnote">Answer generation and automatic answer judging are not part of this retrieval run. Human usefulness judgments can be recorded per case.</p></Panel></div>
        <Panel title="Performance by category" subtitle={`${label(selectedMode)} · K = ${selectedK} · color accompanies the numerical score`}><div className="ws-table-wrap"><table className="ws-table ins-heatmap"><thead><tr><th>Category</th><th>Cases scored</th><th>Recall</th><th>NDCG</th><th>Complete</th><th>p95</th></tr></thead><tbody>{value.summary.categories.filter(row => row.mode === selectedMode).slice(0, 100).map(row => <tr key={row.category}><th scope="row">{row.category}</th><td>{row.metrics[selectedK]?.n ?? 0}</td>{(["recall", "ndcg", "complete_rate"] as const).map(metric => { const score = row.metrics[selectedK]?.[metric]; return <td key={metric} style={{ "--score": score == null ? 0 : Math.min(1, Math.max(0, score)) } as CSSProperties}><span>{score == null ? "—" : percent(score)}</span></td>; })}<td>{duration(row.latency_p95_ms)}</td></tr>)}</tbody></table></div>{value.summary.categories.filter(row => row.mode === selectedMode).length > 100 && <p className="ins-footnote">First 100 categories shown. The JSON export includes every category.</p>}</Panel>
      </>}
      <Panel title="Case explorer" subtitle="Inspect ranking, source citations and human usefulness assessments." action={<button className="ws-button ws-quiet" onClick={() => { void results.refetch(); void dataset.refetch(); }} disabled={results.isFetching || dataset.isFetching}><RefreshCw size={14} />Refresh cases</button>}>
        {results.isError || dataset.isError ? <p className="ws-notice ws-error" role="alert">{errorText(results.error || dataset.error)}</p> : results.isPending ? busy : !results.data.items.length ? <EmptyChart>Case results appear as the run progresses.</EmptyChart> : <>
          <div className="ws-table-wrap"><table className="ws-table"><thead><tr><th>Question</th><th>Mode</th><th>Recall @ {selectedK}</th><th>Context</th><th>Latency</th><th>Review</th></tr></thead><tbody>{results.data.items.map(item => <tr key={item.position} className={selected === item.position ? "ins-row-selected" : ""}><td><button className="ins-text-button" onClick={() => setSelected(item.position)}>{item.case_id}</button><small>{item.result.category}{item.result.unanswerable ? " · unanswerable" : ""}</small></td><td>{item.mode}</td><td>{item.result.status === "failed" ? "Failed" : percent(item.result.metrics[selectedK]?.recall)}</td><td>{percent(item.result.context_recall)}</td><td>{duration(item.result.recall_ms)}</td><td>{item.human_assessment ? label(item.human_assessment.label) : "Unreviewed"}</td></tr>)}</tbody></table></div>
          <div className="ins-pagination"><button className="ws-button ws-quiet" disabled={!pages.length} onClick={() => { setCursor(pages.at(-1)!); setPages(pages.slice(0, -1)); setSelected(null); }}><ChevronLeft size={14} />Previous</button><span>Cases {cursor + 1}–{cursor + results.data.items.length}</span><button className="ws-button ws-quiet" disabled={results.data.next_cursor == null} onClick={() => { setPages([...pages, cursor]); setCursor(results.data.next_cursor!); setSelected(null); }}>Next<ChevronRight size={14} /></button></div>
          {selectedResult && dataset.data?.state === "active" && <CaseDetail key={`${selectedResult.position}:${selectedResult.assessment_version}`} client={client} space={space} run={value} result={selectedResult} question={dataset.data.cases?.find(item => item.id === selectedResult.case_id)} close={() => setSelected(null)} updated={() => { void results.refetch(); }} />}
        </>}
      </Panel>
    </>}
    <details className="ins-definitions"><summary><FileJson size={15} />Reproducibility manifest & metric definitions</summary><pre className="ins-json">{JSON.stringify(value.manifest, null, 2)}</pre>{Object.entries(value.summary?.definitions || {}).map(([key, description]) => <p key={key}><b>{label(key)}.</b> {description}</p>)}</details>
  </>;
}

function errorReason(code: string) {
  const reasons: Record<string, string> = {
    model_not_ready: "The configured embedding model is not loaded. Prepare it on the service or perform an ordinary search before starting a new run. Evaluations do not download model weights.",
    access_revoked: "The initiating key or space access was revoked. Completed data remains subject to current permissions.",
    reference_unavailable: "Reference evidence was deleted, quarantined or made unavailable. Related questions and result details are hidden. Create a new test-set version with current evidence.",
    time_budget_exhausted: "The run exhausted its time budget. Partial case results are retained; create a new run with a suitable budget to complete the evaluation.",
    inference_busy: "The shared model reached its admission limit. The run stopped so normal traffic could continue; retry when capacity is available.",
    evidence_validation_failed: "A source hash or citation span failed validation. Inspect the affected evidence before relying on this result.",
    corpus_limit: "This evaluation space exceeds the 100,000-record local evaluation bound. Use a selected evaluation space or a separate benchmark runner.",
  };
  return reasons[code] || `Evaluation stopped: ${label(code)}.`;
}

function CaseDetail({ client, space, run, result, question, close, updated }: { client: MnemionClient; space: string; run: EvaluationRun; result: EvaluationResult; question?: EvaluationCase; close: () => void; updated: () => void }) {
  const section = useRef<HTMLElement>(null);
  useEffect(() => {
    section.current?.scrollIntoView({ block: "start", behavior: "instant" });
    section.current?.focus({ preventScroll: true });
  }, []);
  const [assessment, setAssessment] = useState<AssessmentLabel>(result.human_assessment?.label || "useful");
  const [note, setNote] = useState(result.human_assessment?.note || "");
  const [error, setError] = useState<unknown>(), [saving, setSaving] = useState(false), [showAll, setShowAll] = useState(false);
  const ranking = result.result.ranking || [];
  const relevant = new Set(question?.references?.map(ref => `${ref.memory_id}:${ref.revision_id}`));
  async function submit(event: FormEvent) {
    event.preventDefault(); setSaving(true); setError(undefined);
    try { await client.assessEvaluation(space, run.id, result.position, { expected_recorded_at: result.recorded_at, expected_assessment_version: result.assessment_version, label: assessment, note }); updated(); }
    catch (error) { setError(error); } finally { setSaving(false); }
  }
  return <section ref={section} tabIndex={-1} className="ins-case-detail" aria-label={`Details for ${result.case_id}`}><header><div><p className="ws-eyebrow">{result.mode} · {result.case_id}</p><h3>{question?.query || "Question unavailable"}</h3></div><button className="ws-icon-button" onClick={close} aria-label="Close case details"><X size={18} /></button></header>
    {result.result.error_code && <p className="ws-notice">{errorReason(result.result.error_code)}</p>}
    <div className="ins-case-facts"><span>{duration(result.result.recall_ms)} retrieval</span><span>{number(result.result.context_tokens)} context tokens</span><span>{number(result.result.citations_checked)} citation checks</span><span>{number(question?.references?.length)} reference revisions</span></div>
    {result.result.warnings?.length ? <p className="ws-notice">{result.result.warnings.map(label).join(" · ")}</p> : null}
    <div className="ins-grid"><div><h3>Retrieved evidence</h3><p className="ins-footnote">The bar shows normalized rank-fusion relevance, not confidence or truth.</p>
      {ranking.length ? <ol className="ins-ranking">{ranking.slice(0, showAll ? 50 : 10).map((hit, i) => <li key={`${hit.memory_id}:${i}`}><b>{i + 1}</b><div><div className="ins-ranking-label"><Link to={`/workspace/sources/${hit.source_revision_id}`}>Source {hit.source_revision_id.slice(0, 8)}<ArrowRight size={12} /></Link>{relevant.has(`${hit.memory_id}:${hit.revision_id}`) && <span className="ins-reference-tag">Reference</span>}</div><div className="ins-ranking-track"><span style={{ width: `${Math.max(0, Math.min(1, hit.relevance_score)) * 100}%` }} /></div><small>Relevance {number(hit.relevance_score, 4)} · Cosine {number(hit.ranking.cosine_similarity, 3)} · Span {hit.memory_span.start}–{hit.memory_span.end}</small><Link className="ins-memory-link" to={`/workspace/memory/${hit.memory_id}`}>Open current memory</Link></div></li>)}</ol> : <EmptyChart>No ranked memories returned.</EmptyChart>}
      {ranking.length > 10 && <button className="ws-button ws-quiet" onClick={() => setShowAll(!showAll)}>{showAll ? "Show first 10" : `Show all ${ranking.length} hits`}</button>}
    </div><form className="ins-assessment" onSubmit={submit}><h3>Human usefulness review</h3><p>Record your judgment after inspecting the source evidence. This does not replace the automated retrieval scores.</p><label className="ws-field"><span>Assessment</span><select value={assessment} onChange={event => setAssessment(event.target.value as AssessmentLabel)}>{(["useful", "partially_useful", "not_useful", "correct_abstention", "incorrect_abstention"] as AssessmentLabel[]).map(value => <option key={value} value={value}>{label(value)}</option>)}</select></label><label className="ws-field"><span>Review note</span><textarea rows={4} maxLength={2000} value={note} onChange={event => setNote(event.target.value)} placeholder="Which evidence was useful, missing or misleading?" /></label>
      {!!error && <p className="ws-notice ws-error" role="alert">{errorText(error)}</p>}<button className="ws-button ws-primary" disabled={saving}>{saving ? <LoaderCircle size={14} className="ws-spin" /> : <Check size={14} />}Save assessment</button>{result.assessed_at && <small>Last reviewed {when(result.assessed_at)} · version {result.assessment_version}</small>}
    </form></div>
    <details className="ins-inline-details"><summary>Raw case measurements</summary><pre className="ins-json">{JSON.stringify(result.result, null, 2)}</pre></details>
  </section>;
}

function CompareRuns({ client, space, runs, inspect }: { client: MnemionClient; space: string; runs: EvaluationRun[]; inspect: (id: string) => void }) {
  const completed = runs.filter(run => run.state === "completed");
  const [baseline, setBaseline] = useState(completed[1]?.id || completed[0]?.id || ""), [candidate, setCandidate] = useState(completed[0]?.id || "");
  const [comparison, setComparison] = useState<EvaluationComparison | null>(null), [error, setError] = useState<unknown>(), [working, setWorking] = useState(false);
  const [metric, setMetric] = useState("recall");
  async function compare(event: FormEvent) { event.preventDefault(); setWorking(true); setError(undefined); setComparison(null);
    try { setComparison(await client.compareEvaluations(space, baseline, candidate)); } catch (error) { setError(error); } finally { setWorking(false); } }
  if (completed.length < 2) return <div className="ins-eval-empty"><GitCompareArrows size={38} /><h2>Compare two completed runs</h2><p>Run a baseline and a candidate on the same test-set version and corpus. Comparison checks matching splits, scorer, context budget and index coverage before calculating paired changes.</p></div>;
  return <><Panel title="A controlled comparison" subtitle="A model may change; the test set, corpus and scoring settings must stay comparable."><form onSubmit={compare}><div className="ins-form-grid">{[{ title: "Baseline", value: baseline, change: setBaseline }, { title: "Candidate", value: candidate, change: setCandidate }].map(field => <label className="ws-field" key={field.title}><span>{field.title}</span><select value={field.value} onChange={event => { field.change(event.target.value); setComparison(null); }}>{completed.map(run => <option key={run.id} value={run.id}>{run.id.slice(0, 8)} · {run.manifest.generation.model} · {when(run.started_at)}</option>)}</select></label>)}</div><div className="ins-form-actions"><p>Differences use paired, successfully scored answerable cases. Confidence intervals do not prove general superiority.</p><button className="ws-button ws-primary" disabled={working || !baseline || !candidate || baseline === candidate}>{working ? <LoaderCircle size={14} className="ws-spin" /> : <GitCompareArrows size={14} />}Compare runs</button></div></form></Panel>
    {!!error && <p className="ws-notice ws-error" role="alert">{errorText(error)}</p>}
    {comparison && <>
      <div className={`ins-comparison-status ${comparison.comparable ? "good" : "warm"}`}><ShieldCheck size={23} /><div><strong>{comparison.comparable ? "Comparable inputs confirmed" : "These runs are not a controlled comparison"}</strong>{comparison.comparable ? <p>Same test version, corpus, scorer, split, cutoffs and context settings.</p> : comparison.reasons.map(reason => <p key={reason}>{reason}</p>)}</div><ExportButton onClick={() => download(JSON.stringify(comparison, null, 2), `mnemion-comparison-${baseline.slice(0, 8)}-${candidate.slice(0, 8)}.json`)} /></div>
      <div className="ins-comparison-links"><button className="ws-button ws-quiet" onClick={() => inspect(baseline)}>Inspect baseline<ArrowRight size={13} /></button><button className="ws-button ws-quiet" onClick={() => inspect(candidate)}>Inspect candidate<ArrowRight size={13} /></button></div>
      {comparison.comparable && <Panel title="Paired score changes" subtitle="Candidate minus baseline · percentage points · 95% paired bootstrap intervals" action={<label className="ins-select"><span>Metric</span><select value={metric} onChange={event => setMetric(event.target.value)}>{["recall", "precision", "ndcg", "mrr"].map(value => <option key={value} value={value}>{value.toUpperCase()}</option>)}</select></label>}>
        <div className="ins-delta-chart" role="group" aria-label="Paired evaluation differences">{comparison.deltas.filter(row => row.metric === metric).map(row => <div key={`${row.mode}:${row.cutoff}`}><span>{row.mode} @ {row.cutoff}</span><div className="ins-delta-track"><i /><b style={{ left: `${50 + Math.min(0, row.delta ?? 0) * 50}%`, width: `${Math.abs(row.delta ?? 0) * 50}%`, background: (row.delta ?? 0) < 0 ? palette[4] : palette[1] }} />{row.paired_bootstrap95 && <em style={{ left: `${50 + row.paired_bootstrap95[0] * 50}%`, width: `${(row.paired_bootstrap95[1] - row.paired_bootstrap95[0]) * 50}%` }} />}</div><strong>{row.delta == null ? "—" : `${row.delta > 0 ? "+" : ""}${number(row.delta * 100, 2)} pp`}</strong><small>{row.paired_cases} pairs · 95% {row.paired_bootstrap95 ? row.paired_bootstrap95.map(v => `${number(v * 100, 2)} pp`).join(" to ") : "unavailable"}</small></div>)}</div>
        <DataTable name="Paired run deltas" columns={["Mode", "K", "Metric", "Pairs", "Delta", "95% interval"]} rows={comparison.deltas.map(row => [row.mode, row.cutoff, row.metric, row.paired_cases, number(row.delta, 5), row.paired_bootstrap95?.map(value => number(value, 5)).join(" – ") || "—"])} />
      </Panel>}
    </>}
  </>;
}
