import type { CaptureIndexProgress } from '../../../shared/desktop-sources';
import './capture-status.css';

const stamp = (value: string) => new Date(value).toLocaleString();

export default function CaptureIndexStatus({ progress }: { progress?: CaptureIndexProgress }) {
  const sweep = progress?.completed ?? progress?.active;
  if (!sweep) return <p className="ws-helper">Index observations: {progress?.status === 'unsupported' ? 'update the workspace server to report indexing progress' : progress?.status === 'unavailable' ? 'workspace observation unavailable; readiness remains unknown' : 'not yet observed'}. Librarian consolidation progress is not yet available.</p>;
  const c = sweep.counts;
  return <section aria-label="Workspace source index observations">
    <p><strong>{progress?.completed ? 'Last completed source index sweep' : 'Partial source index sweep'}</strong> · {c.events.toLocaleString()} accepted events observed</p>
    <div className="ws-capture-index-metrics">
      <div><strong>{c.lexical_indexed.toLocaleString()}</strong><span>Text indexed</span></div>
      <div><strong>{c.vector_indexed.toLocaleString()}</strong><span>Vectors indexed</span></div>
      <div><strong>{c.waiting.toLocaleString()}</strong><span>Awaiting vectors</span></div>
    </div>
    {(c.failed > 0 || c.withheld > 0 || c.forgotten > 0 || c.unknown > 0) && <p>{c.failed.toLocaleString()} failed · {c.withheld.toLocaleString()} withheld from ordinary search · {c.forgotten.toLocaleString()} forgotten · {c.unknown.toLocaleString()} unknown</p>}
    {sweep.inference_paused && <p>Inference was paused at the last observation.</p>}
    {progress?.active && progress.completed && <p className="ws-helper">A new sweep has observed {progress.active.counts.events.toLocaleString()} events so far. Its partial results have not replaced the completed sweep.</p>}
    {(progress?.status === 'unavailable' || progress?.status === 'unsupported') && <p>Fresh index observations are {progress.status === 'unsupported' ? 'not supported by the current workspace server' : 'unavailable'}. These are saved results.</p>}
    <p className="ws-helper">Observed {stamp(sweep.started_at)} to {stamp(sweep.observed_at)} · model generation <code title={sweep.generation_id}>{sweep.generation_id.slice(0, 12)}</code>.</p>
    <p className="ws-helper">Covers this shared source across its devices. Counts describe stored indices; permissions, review and search filters still apply. Records can change during a sweep and appear in the next one. Librarian consolidation progress is not yet available.</p>
  </section>;
}
