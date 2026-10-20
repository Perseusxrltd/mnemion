import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { BookOpenCheck, Play, RefreshCw, Settings2, Undo2 } from "lucide-react";
import { MnemionError, type MnemionClient, type LibrarianChoice, type LibrarianMode,
  type LibrarianProposal, type LibrarianProposalState, type LibrarianSettings,
  type LibrarianSettingsInput } from "@mnemion/client";
import "./librarian.css";

const failure = (error: unknown) => error instanceof Error ? error.message : "The request could not be completed.";
const denied = (error: unknown) => error instanceof MnemionError && [401, 403, 404].includes(error.status);
const display = (value: unknown) => value == null ? "Not set" : typeof value === "string" ? value : JSON.stringify(value);

function ModelSettings({ settings, choices, busy, save }: {
  settings: LibrarianSettings; choices: LibrarianChoice[]; busy: boolean;
  save: (command: LibrarianSettingsInput) => void;
}) {
  const [profile, setProfile] = useState(settings.profile_id ?? "");
  const [enabled, setEnabled] = useState(settings.enabled);
  const [approval, setApproval] = useState(false);
  const [mode, setMode] = useState<LibrarianMode>(settings.mode);
  const [batch, setBatch] = useState(settings.max_memories);
  const [budget, setBudget] = useState(settings.max_calls_per_day);
  const [schedule, setSchedule] = useState(settings.interval_minutes !== null);
  const [interval, setInterval] = useState(settings.interval_minutes ?? 1440);
  const selected = choices.find(choice => choice.id === profile);
  const submit = (event: FormEvent) => {
    event.preventDefault();
    save({ expected_version: settings.version, profile_id: profile, enabled,
      approve_network_egress: approval, mode, max_memories: batch, max_calls_per_day: budget,
      interval_minutes: schedule ? interval : null });
  };
  return <details className="ws-card librarian-settings" open={!settings.profile_id}>
    <summary><Settings2 size={18} /> Model, schedule & limits</summary>
    <form className="ws-form" onSubmit={submit}>
      <label className="ws-field"><span>Model approved by your server operator</span>
        <select value={profile} onChange={event => { setProfile(event.target.value); setApproval(false); }} required>
          <option value="">Choose a model</option>
          {choices.map(choice => <option key={choice.id} value={choice.id}>{choice.label}</option>)}
        </select></label>
      {!choices.length && <p className="ws-notice">No librarian model is configured. {window.mnemion?.localModels && <><Link to="/workspace/setup" className="ws-link">Configure models hosted on this computer</Link>, or </>}ask your server operator to add an approved endpoint. See the <Link to="/workspace/help?doc=docs/service/librarian.md" className="ws-link">librarian guide</Link>.</p>}
      {selected && <div className="librarian-provider"><strong>{selected.model}</strong><p>{selected.endpoint_origin}</p>
        <p>{selected.context_budget.toLocaleString()} {selected.token_count_unit === "utf8_bytes" ? "UTF-8 bytes of context budget" : "context tokens"} · Up to {selected.max_output_tokens.toLocaleString()} output tokens · {selected.timeout_seconds}s request limit</p>
        <code>{selected.fingerprint}</code></div>}
      <label className="ws-checkbox"><input type="checkbox" checked={enabled} onChange={event => setEnabled(event.target.checked)} />Enable model processing for this space</label>
      {enabled && selected?.network_egress && <label className="ws-checkbox"><input type="checkbox" checked={approval} onChange={event => setApproval(event.target.checked)} required />
        I approve sending selected memories to {selected.endpoint_origin}. The provider may charge for these calls.</label>}
      <div className="librarian-fields">
        <label className="ws-field"><span>Memories per run</span><input type="number" min={1} max={12} step={1} required value={Number.isFinite(batch) ? batch : ""} onChange={event => setBatch(event.target.valueAsNumber)} /></label>
        <label className="ws-field"><span>Maximum model calls per UTC day</span><input type="number" min={1} max={1000} step={1} required value={Number.isFinite(budget) ? budget : ""} onChange={event => setBudget(event.target.valueAsNumber)} /></label>
      </div>
      <label className="ws-checkbox"><input type="checkbox" checked={schedule} onChange={event => setSchedule(event.target.checked)} />Run a scheduled sweep of new or changed memories</label>
      {schedule && <div className="librarian-fields">
        <label className="ws-field"><span>Schedule</span><select value={interval} onChange={event => setInterval(Number(event.target.value))}>
          {[60, 360, 1440, 10080].includes(interval) ? null : <option value={interval}>Every {interval} minutes</option>}
          <option value={60}>Hourly</option><option value={360}>Every six hours</option><option value={1440}>Daily</option><option value={10080}>Weekly</option></select></label>
        <label className="ws-field"><span>Scheduled task</span><select value={mode} onChange={event => setMode(event.target.value as LibrarianMode)}>
          <option value="organize">Titles, tags & summaries</option><option value="review">Links, duplicates & inconsistencies</option></select></label>
      </div>}
      <p className="ws-helper">Organization uses one independent call per memory. A review compares a bounded batch in one call. Oversized inputs are skipped without sending them. Failed or interrupted calls count toward the daily cap and are not retried automatically.</p>
      <button className="ws-button ws-primary" disabled={busy || !selected || (enabled && selected.network_egress && !approval)}>Save librarian settings</button>
    </form>
  </details>;
}

function Proposal({ proposal, busy, decide }: {
  proposal: LibrarianProposal; busy: boolean; decide: (action: "accept" | "reject" | "undo") => void;
}) {
  const suggestion = proposal.suggestion;
  return <article className="ws-card librarian-proposal">
    <div className="ws-section-title"><h3>{suggestion?.kind === "organize" ? "Organization proposal" : suggestion ? suggestion.kind.charAt(0).toUpperCase() + suggestion.kind.slice(1) + " finding" : "Source unavailable"}</h3>
      <span className="ws-badge">{proposal.state}</span></div>
    {!suggestion ? <p>Generated text was removed because its source evidence is no longer available.</p> : <>
      <Link className="ws-link librarian-id" to={"/workspace/memory/" + proposal.memory_id}>Open source memory</Link>
      <p>{suggestion.rationale}</p><p className="ws-helper">Model confidence: {suggestion.confidence}. This is a suggestion, not a verified fact.</p>
      {suggestion.changes && <div className="librarian-diff">
        {(["subject", "tags", "summary"] as const).filter(field => suggestion.changes?.[field] != null).map(field => <div key={field}>
          <h4>{field === "subject" ? "Title" : field === "tags" ? "Tags to add" : "Summary"}</h4>
          <div><p><span>Before proposal</span>{display(proposal.before?.[field])}</p><p><span>Proposed</span>{display(suggestion.changes?.[field])}</p></div>
        </div>)}
      </div>}
      <details><summary>Source evidence ({proposal.references.length} {proposal.references.length === 1 ? "memory" : "memories"})</summary>
        <p className="ws-helper">These are the exact memory revisions supplied to the model, including context it did not quote.</p>
        {proposal.references.map(reference => <div className="librarian-reference" key={reference.memory_id}>
          <Link className="ws-link" to={"/workspace/memory/" + reference.memory_id}>Memory {reference.memory_id} · version {reference.memory_version}</Link>
          <small>Revision {reference.revision_id}</small>
          {suggestion.evidence.some(evidence => evidence.memory_id === reference.memory_id)
            ? suggestion.evidence.filter(evidence => evidence.memory_id === reference.memory_id).map((evidence, index) => <blockquote key={index}><p>{evidence.quote}</p></blockquote>)
            : <p className="ws-helper">Supplied as context; no direct quotation.</p>}
        </div>)}
      </details>
      {proposal.unavailable_reason === "revision_changed" && ["pending", "accepted"].includes(proposal.state) && <p className="ws-notice">A source memory has changed since this proposal. Generate a new proposal to use its latest revision.</p>}
      <div className="ws-actions">
        {proposal.state === "pending" && <><button className="ws-button ws-primary" disabled={busy || !proposal.applicable} onClick={() => decide("accept")}>
          {suggestion.kind === "organize" ? "Apply organization" : "Acknowledge finding"}</button>
          <button className="ws-button" disabled={busy} onClick={() => decide("reject")}>Reject</button></>}
        {proposal.state === "accepted" && <button className="ws-button" disabled={busy || !proposal.applicable} onClick={() => decide("undo")}><Undo2 size={15} />Undo decision</button>}
      </div>
    </>}
  </article>;
}

function RunItems({ client, space, run, active }: {
  client: MnemionClient; space: string; run: string; active: boolean;
}) {
  const [open, setOpen] = useState(false);
  const query = useQuery({ queryKey: ["librarian", space, "run-items", run],
    queryFn: () => client.librarianRunItems(space, run), enabled: open,
    refetchInterval: open && active ? 6000 : false });
  return <details open={open} onToggle={event => setOpen(event.currentTarget.open)}>
    <summary>Selected memories & outcomes</summary>
    {open && (denied(query.error) ? <p className="ws-notice">Current reviewer access is required to view this run.</p> : <>
      {query.error && <p className="ws-notice" role="alert">{failure(query.error)}</p>}
      {query.isPending && <p role="status">Loading selected memories…</p>}
      {query.data && !query.data.items.length && <p>No new or changed memories were selected.</p>}
      {query.data?.items.map(item => <div className="librarian-reference" key={item.position}>
        <Link className="ws-link" to={"/workspace/memory/" + item.memory_id}>Memory {item.memory_id} · version {item.memory_version}</Link>
        <small>Revision {item.revision_id}</small>
        <p>{item.state === "pending" && !active ? "Not processed" : item.state === "completed" ? "Checked" : item.state === "skipped" ? "Skipped" : "Waiting"}
          {item.reason ? " · " + item.reason.replaceAll("_", " ") : ""}</p>
      </div>)}
    </>)}
  </details>;
}

export default function Librarian({ client, space, reviewer, administrator }: {
  client: MnemionClient; space: string; reviewer: boolean; administrator: boolean;
}) {
  const cache = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [mode, setMode] = useState<LibrarianMode>("organize");
  const [ids, setIds] = useState("");
  const [filter, setFilter] = useState<LibrarianProposalState | "all">("pending");
  const [cursor, setCursor] = useState<string | undefined>();
  const [runCursor, setRunCursor] = useState<string | undefined>();
  const prefix = ["librarian", space];
  const settings = useQuery({ queryKey: [...prefix, "settings"], queryFn: () => client.librarianSettings(space), enabled: reviewer, refetchInterval: 12000 });
  const choices = useQuery({ queryKey: [...prefix, "models"], queryFn: () => client.librarianChoices(space), enabled: reviewer });
  const runs = useQuery({ queryKey: [...prefix, "runs", runCursor], queryFn: () => client.librarianRuns(space, runCursor), enabled: reviewer, refetchInterval: 6000 });
  const proposals = useQuery({ queryKey: [...prefix, "proposals", filter, cursor],
    queryFn: () => client.librarianProposals(space, filter === "all" ? undefined : filter, cursor), enabled: reviewer, refetchInterval: 12000 });
  const refresh = async () => { await cache.invalidateQueries({ queryKey: prefix }); };
  const act = async (action: () => Promise<unknown>) => {
    setBusy(true); setError("");
    try { await action(); await refresh(); await cache.invalidateQueries({ queryKey: ["memories"] }); }
    catch (cause) { setError(failure(cause)); await refresh(); }
    finally { setBusy(false); }
  };
  if (!reviewer || [settings.error, choices.error, runs.error, proposals.error].some(denied)) {
    return <div className="ws-page"><h1>Librarian</h1><p className="ws-notice">Current reviewer access is required to view or run the librarian for this space.</p></div>;
  }
  const data = settings.data;
  const active = runs.data?.items.some(run => run.state === "queued" || run.state === "running");
  const selected = choices.data?.items.find(choice => choice.id === data?.profile_id);
  const queryError = settings.error || choices.error || runs.error || proposals.error;
  const run = (event: FormEvent) => {
    event.preventDefault();
    const memoryIds = ids.trim() ? ids.trim().split(/[\s,]+/) : [];
    if (memoryIds.some(id => !/^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i.test(id))) {
      setError("Use complete memory UUIDs, separated by spaces, commas or new lines."); return;
    }
    void act(() => client.startLibrarian(space, mode, memoryIds));
  };
  return <div className="ws-page librarian-page">
    <header className="ws-page-heading"><div><p className="ws-eyebrow">Memory care</p><h1><BookOpenCheck size={26} /> Librarian</h1>
      <p>A local or cloud model proposes useful organization. Your team reviews the changes.</p></div>
      <button className="ws-button" disabled={busy || settings.isFetching} onClick={() => void refresh()}><RefreshCw size={16} />Refresh</button></header>
    {(error || queryError) && <p className="ws-notice ws-error" role="alert">{error || failure(queryError)}</p>}
    {settings.isPending && <p role="status">Loading librarian…</p>}
    {data && <>
      <section className="ws-stats" aria-label="Librarian status">
        <div><span>Model</span><strong>{selected?.label ?? "Not assigned"}</strong><small>{data.enabled && data.profile_available ? "Enabled" : data.enabled ? "Configuration needs review" : "Paused"}</small></div>
        <div><span>Calls reserved today</span><strong>{data.calls_reserved_today} / {data.max_calls_per_day}</strong><small>Resets at midnight UTC</small></div>
        <div><span>Awaiting review</span><strong>{data.pending_proposals}</strong><small>Changes require your approval</small></div>
        <div><span>Next scheduled sweep</span><strong>{data.next_run_at ? new Date(data.next_run_at).toLocaleString() : "Manual"}</strong><small>New or changed memories</small></div>
      </section>
      {data.enabled && !data.profile_available && <p className="ws-notice">The approved model configuration has changed or is unavailable. An administrator must review and save its current configuration before processing resumes.</p>}
      {administrator && <ModelSettings key={data.version} settings={data} choices={choices.data?.items ?? []} busy={busy} save={command => void act(() => client.configureLibrarian(space, command))} />}
      {administrator && data.enabled && data.profile_id && <button className="ws-button" disabled={busy} onClick={() => void act(() => client.configureLibrarian(space, {
        expected_version: data.version, profile_id: data.profile_id!, enabled: false, mode: data.mode,
        max_memories: data.max_memories, max_calls_per_day: data.max_calls_per_day, interval_minutes: null,
      }))}>Pause processing and cancel queued work</button>}
      <form className="ws-card ws-form" onSubmit={run}><h2>Generate proposals</h2>
        <label className="ws-field"><span>Task</span><select value={mode} onChange={event => setMode(event.target.value as LibrarianMode)}>
          <option value="organize">Organize titles, tags & summaries</option><option value="review">Review links, duplicates & inconsistencies</option></select></label>
        <p className="ws-helper">{mode === "organize" ? "Each memory is considered independently. Applying a proposal preserves its text, source and attachments." : "A bounded batch is compared for possible links, duplication, contradictions and stale claims. Acknowledging a finding does not merge, delete or verify memories."}</p>
        <details><summary>Select specific memories</summary><label className="ws-field"><span>Memory IDs (optional, up to {data.max_memories})</span>
          <textarea rows={3} value={ids} maxLength={1000} onChange={event => setIds(event.target.value)} placeholder="Leave blank to check new or changed memories." /></label></details>
        <button className="ws-button ws-primary" disabled={busy || active || !data.enabled || !data.profile_available || data.calls_reserved_today >= data.max_calls_per_day}><Play size={15} />Generate proposals</button>
      </form>
      <section aria-label="Librarian proposals"><div className="ws-section-title"><h2>Review proposals</h2>
        <label className="ws-field"><span>Show</span><select value={filter} onChange={event => { setFilter(event.target.value as typeof filter); setCursor(undefined); }}>
          <option value="pending">Awaiting review</option><option value="accepted">Accepted</option><option value="rejected">Rejected</option><option value="undone">Undone</option><option value="all">All decisions</option></select></label></div>
        {proposals.isPending ? <p role="status">Loading proposals…</p> : !proposals.data?.items.length ? <p className="ws-notice">No proposals in this view. Generate a run or choose another filter.</p> : proposals.data.items.map(proposal =>
          <Proposal key={proposal.id} proposal={proposal} busy={busy} decide={action => void act(() => client.decideLibrarian(space, proposal.id, action, proposal.version))} />)}
        <div className="ws-actions">{cursor && <button className="ws-button" onClick={() => setCursor(undefined)}>Newest proposals</button>}
          {proposals.data?.next_cursor && <button className="ws-button" onClick={() => setCursor(proposals.data!.next_cursor!)}>Older proposals</button>}</div>
      </section>
      <section className="ws-card"><h2>Run history & usage</h2><p className="ws-helper">Usage covers completed requests and reported failures. Reserved calls also include interrupted requests whose final usage may be unknown. Provider tokens are shown only when reported.</p>
        {!runs.data?.items.length && <p>No librarian runs yet.</p>}
        {runs.data?.items.map(job => <article className="librarian-run" key={job.id}>
          <div className="ws-section-title"><h3>{job.mode === "organize" ? "Organization" : "Review"} · {new Date(job.created_at).toLocaleString()}</h3><span className="ws-badge">{job.state}</span></div>
          <progress value={job.processed + job.skipped} max={job.selected || 1} aria-label="Memories processed or skipped" />
          <p>{job.processed} checked · {job.skipped} skipped · {job.selected} selected · {job.proposal_count} {job.proposal_count === 1 ? "proposal" : "proposals"}</p>
          <p className="ws-helper">{job.calls_completed}/{job.calls_reserved} reserved calls completed · {job.input_units.toLocaleString()} {job.configuration.token_count_unit === "utf8_bytes" ? "input budget bytes" : "input tokens"} · {job.output_tokens?.toLocaleString() ?? "Unreported"} output tokens · {((job.request_bytes + job.response_bytes) / 1024).toFixed(1)} KiB transferred · {(job.latency_ms / 1000).toFixed(1)}s provider time</p>
          {job.error_code && <p className="ws-notice">Stopped: {job.error_code.replaceAll("_", " ")}. Review the cause before starting another run.</p>}
          <RunItems client={client} space={space} run={job.id} active={job.state === "queued" || job.state === "running"} />
          <details><summary>Reproducible configuration</summary><pre className="ws-code">{JSON.stringify(job.configuration, null, 2)}</pre></details>
          {(job.state === "queued" || job.state === "running") && <button className="ws-button" disabled={busy} onClick={() => void act(() => client.cancelLibrarian(space, job.id))}>Cancel run</button>}
        </article>)}
        <div className="ws-actions">{runCursor && <button className="ws-button" onClick={() => setRunCursor(undefined)}>Newest runs</button>}
          {runs.data?.next_cursor && <button className="ws-button" onClick={() => setRunCursor(runs.data!.next_cursor!)}>Older runs</button>}</div>
      </section>
    </>}
  </div>;
}
