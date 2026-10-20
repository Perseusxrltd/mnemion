import { useQuery } from "@tanstack/react-query";
import { Download } from "lucide-react";
import { MnemionError, type LibrarianCoverage as Coverage, type LibrarianModeCoverage, type MnemionClient } from "@mnemion/client";

const number = (value: number) => value.toLocaleString();
const date = (value: string | null) => value ? new Date(value).toLocaleString() : "None recorded";

function ModeCoverage({ item }: { item: LibrarianModeCoverage }) {
  const portions = [
    { key: "checked", label: "Checked", value: item.checked },
    { key: "skipped", label: "Skipped", value: item.skipped },
    { key: "attempted", label: "Attempted", value: item.attempted },
    { key: "pending", label: "Waiting", value: item.pending },
  ];
  let offset = 0;
  const summary = portions.map(part => `${number(part.value)} ${part.label.toLowerCase()}`).join(", ");
  return <article className="librarian-coverage-mode">
    <div className="ws-section-title"><h3>{item.mode === "organize" ? "Organization" : "Review"}</h3>
      <strong>{item.eligible ? `${(100 * item.checked / item.eligible).toFixed(1)}% checked` : "No eligible memories"}</strong></div>
    <svg viewBox="0 0 320 16" className="librarian-coverage-bar" role="img" aria-label={summary}>
      <rect width="320" height="16" className="coverage-empty" />
      {portions.map(part => {
        const width = item.eligible ? 320 * part.value / item.eligible : 0;
        const x = offset; offset += width;
        return <rect key={part.key} x={x} width={width} height="16" className={`coverage-${part.key}`} />;
      })}
    </svg>
    <dl className="librarian-coverage-legend">{portions.map(part => <div key={part.key}>
      <dt><i className={`coverage-${part.key}`} aria-hidden="true" />{part.label}</dt><dd>{number(part.value)}</dd>
    </div>)}</dl>
    <p className="ws-helper">Waiting: {number(item.unseen)} without an observation · {number(item.changed)} changed since the last observation.</p>
    <p className="ws-helper">Oldest waiting revision: {date(item.oldest_pending_at)}<br />Last observation: {date(item.last_observed_at)}</p>
  </article>;
}

function exportCoverage(data: Coverage) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2) + "\n"], { type: "application/json" }));
  const anchor = document.createElement("a");
  anchor.href = url; anchor.download = `mnemion-librarian-coverage-${data.space_id}.json`;
  anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export default function LibrarianCoverage({ client, space }: { client: MnemionClient; space: string }) {
  const query = useQuery({ queryKey: ["librarian", space, "coverage"],
    queryFn: () => client.librarianCoverage(space), staleTime: 30000, refetchInterval: 30000,
    refetchOnWindowFocus: false, retry: false });
  if (query.error) return <section className="ws-card"><h2>Coverage and processing</h2>
    <p className="ws-notice">{query.error instanceof MnemionError && query.error.status === 404
      ? "Coverage is unavailable on this server. Update the workspace service or check your current reviewer access."
      : "Coverage could not be read with your current connection. Refresh to try again."}</p></section>;
  const data = query.data;
  if (!data) return <p role="status">Loading librarian coverage…</p>;
  const usage = data.recent;
  return <section className="ws-card librarian-coverage" aria-label="Librarian coverage and processing">
    <div className="ws-section-title"><h2>Coverage and processing</h2>
      <button className="ws-button" onClick={() => exportCoverage(data)}><Download size={15} />Export data</button></div>
    <p>{number(data.active_memories)} active memories · {number(data.excluded_memories)} withheld by review state.</p>
    {!data.profile_id ? <p className="ws-notice">Choose a librarian model to measure coverage under its saved configuration.</p> : <>
      <p className="ws-helper">Current memory revisions under the saved model profile. Checked means a completed model response; it does not certify correctness. Skipped and attempted memories do not count as checked.</p>
      <div className="librarian-coverage-grid">{data.modes.map(item => <ModeCoverage key={item.mode} item={item} />)}</div>
      <div className="ws-stats" aria-label="Librarian usage over the past 30 days">
        <div><span>Calls completed · 30 days</span><strong>{number(usage.calls_completed)} / {number(usage.calls_reserved)}</strong><small>Reserved calls can include interrupted or active work</small></div>
        <div><span>Model traffic · 30 days</span><strong>{((usage.request_bytes + usage.response_bytes) / 1024).toLocaleString(undefined, { maximumFractionDigits: 1 })} KiB</strong><small>Reported request and response bytes</small></div>
        <div><span>Provider time · 30 days</span><strong>{(usage.provider_latency_ms / 1000).toLocaleString(undefined, { maximumFractionDigits: 1 })}s</strong><small>Recorded model request time</small></div>
        <div><span>Runs · 30 days</span><strong>{number(usage.runs)}</strong><small>{number(usage.active_runs)} active · {number(usage.failed_runs)} failed · {number(usage.cancelled_runs)} cancelled</small></div>
      </div>
      <p className="ws-helper">Attempted means processing was reserved without a completed or skipped outcome; it may still be running. Inspect run history before retrying. Waiting matches the automatic selection rules and does not predict input-size admission or completion time.</p>
    </>}
    <details><summary>Measurement details</summary><p className="ws-helper">Observed {date(data.observed_at)}. Coverage uses one database snapshot, the saved profile fingerprint and each memory's current version. It excludes deleted memories and never reads memory text. Changing profiles starts a separate coverage history. The JSON export contains these counts and profile identifiers.</p>
      <code>{data.profile_fingerprint ?? "No profile assigned"}</code></details>
  </section>;
}
