import { useEffect, useState } from 'react';
import { Activity, Cpu, LoaderCircle, PauseCircle, RefreshCw, ShieldCheck } from 'lucide-react';
import type { LocalResources, LocalStatus, MemoryOptions, MemorySnapshot } from '../../../shared/local-workspace';

export const memorySize = (bytes: number) => bytes >= 1024 ** 3
  ? `${(bytes / 1024 ** 3).toFixed(1)} GiB`
  : `${Math.round(bytes / 1024 ** 2)} MiB`;
export const validMemory = (value: MemoryOptions) => value.mode === 'auto' ||
  (Number.isInteger(value.limit_mib) && value.limit_mib >= 256 && value.limit_mib <= 1048576);

export function MemoryFields({ value, onChange, resources, disabled = false }: {
  value: MemoryOptions; onChange: (value: MemoryOptions) => void; resources: LocalResources; disabled?: boolean;
}) {
  return <fieldset className="ws-memory-fields" disabled={disabled}>
    <legend>RAM budget</legend>
    <div className="ws-memory-modes">
      <label className={value.mode === 'auto' ? 'selected' : ''}><input type="radio" name="memory-mode" value="auto" checked={value.mode === 'auto'} onChange={() => onChange({ mode: 'auto', limit_mib: null })} /><span><strong>Automatic</strong><small>Adapt to this computer and leave room for other apps.</small></span></label>
      <label className={value.mode === 'manual' ? 'selected' : ''}><input type="radio" name="memory-mode" value="manual" checked={value.mode === 'manual'} onChange={() => onChange({ mode: 'manual', limit_mib: Math.max(256, Math.round(resources.recommended_budget_bytes / 1024 ** 2)) })} /><span><strong>Set my own budget</strong><small>Choose how much memory Mnemion should work within.</small></span></label>
    </div>
    {value.mode === 'manual' && <label className="ws-field ws-memory-limit"><span>Budget in MiB</span><div><input type="number" min={256} max={1048576} step={1} required value={Number.isFinite(value.limit_mib) ? value.limit_mib : ''} onChange={event => onChange({ mode: 'manual', limit_mib: event.target.valueAsNumber })} /><span>{Number.isFinite(value.limit_mib) ? memorySize(value.limit_mib * 1024 ** 2) : 'Enter a budget'}</span></div></label>}
    <p className="ws-memory-caption">{memorySize(resources.effective_memory_bytes)} available to this environment · {memorySize(resources.effective_available_memory_bytes)} currently free. Automatic mode currently targets about {memorySize(resources.recommended_budget_bytes)}.</p>
    <small>This is a working budget. Mnemion adjusts batches and pauses model work when needed; an active calculation finishes safely before memory is released.</small>
  </fieldset>;
}

export function RepairMemory({ status, onStatus, disabled = false }: {
  status: LocalStatus; onStatus: (status: LocalStatus, repaired?: boolean) => void; disabled?: boolean;
}) {
  const info = status.info!;
  const recovery = info.memory_recovery!;
  const live = status.memory || info.memory;
  const [options, setOptions] = useState<MemoryOptions>(() => live?.mode === 'manual' && live.requested_limit_mib
    ? { mode: 'manual', limit_mib: live.requested_limit_mib } : { mode: 'auto', limit_mib: null });
  const [token, setToken] = useState(recovery.repair_token);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const changed = token !== recovery.repair_token;
  async function refresh() {
    setBusy(true); setError('');
    try {
      const next = await window.mnemion!.localStatus!();
      setToken(next.info?.memory_recovery?.repair_token ?? null);
      onStatus(next);
    } catch (error) { setError(error instanceof Error ? error.message.replace(/^Error invoking remote method '[^']+': (?:Error: )?/, '') : 'Could not refresh the RAM policy.'); }
    finally { setBusy(false); }
  }
  return <section className="ws-device-settings ws-memory-repair" aria-label="Repair RAM budget">
    <h3>Repair your RAM budget</h3>
    <div className="ws-notice ws-error" role="alert"><p>{recovery.message}</p><p>New model work stays paused. Your memories are retained.</p></div>
    {recovery.repair_token && <form onSubmit={async event => {
      event.preventDefault();
      if (!token || changed) return;
      setBusy(true); setError('');
      try { onStatus(await window.mnemion!.localMemory!({ ...options, repair_token: token }), true); }
      catch (error) { setError(error instanceof Error ? error.message.replace(/^Error invoking remote method '[^']+': (?:Error: )?/, '') : 'The policy could not be repaired. Refresh before retrying.'); }
      finally { setBusy(false); }
    }}>
      <p>Choose the budget to use from now on. {recovery.code === 'memory_policy_missing' ? 'Repair saves your chosen budget in the missing policy file.' : 'Repair preserves a private copy of the damaged settings before saving your choice.'} It does not change your stored memories.</p>
      <MemoryFields value={options} onChange={setOptions} resources={info.resources} disabled={busy || disabled} />
      <button className="ws-button ws-primary" disabled={busy || disabled || changed || !validMemory(options)}>{busy ? <LoaderCircle className="ws-spin" size={16} /> : <ShieldCheck size={16} />}Repair and save RAM budget</button>
      <p className="ws-memory-caption">{status.state === 'running' ? 'The running engine adopts the repaired budget within a few seconds. Its other memory limits still apply.' : 'After repair, resume the local workspace to apply this budget.'}</p>
    </form>}
    {changed && <p className="ws-notice" role="status">The saved policy changed in another session. Refresh its status before repairing it. Your budget choice is retained.</p>}
    {!!error && <p className="ws-notice ws-error" role="alert">{error}</p>}
    <button type="button" className="ws-button ws-quiet" disabled={busy || disabled} onClick={() => void refresh()}><RefreshCw size={15} />Refresh RAM policy</button>
  </section>;
}

const reasons: Record<string, string> = {
  model_exceeds_budget: 'The selected model needs more RAM than this budget allows.',
  system_pressure: 'Other software is using the memory this computer needs to keep free.',
  working_set_over_budget: 'Mnemion is releasing idle models and waiting for memory to become available.',
  measurement_unavailable: 'Memory measurements are unavailable. New model work is paused.',
  policy_unavailable: 'The saved RAM policy needs attention. Your previous limit is retained.',
};

export function LiveMemory({ value }: { value: MemorySnapshot }) {
  const [history, setHistory] = useState<number[]>([]);
  useEffect(() => { setHistory(previous => [...previous.slice(-29), value.used_bytes]); }, [value]);
  const ceiling = Math.max(value.target_bytes, ...history, 1);
  const points = history.map((sample, index) => `${index * 300 / 29},${70 - sample / ceiling * 62}`).join(' ');
  return <section className="ws-live-memory" aria-label="Live memory usage">
    <div className="ws-memory-heading"><span><Activity size={17} />Memory on this computer</span><span className={`ws-budget-state ${value.state}`}>{value.indexing_paused ? 'Indexing paused' : value.state === 'constrained' ? 'Smaller batches' : 'Within budget'}</span></div>
    <div className="ws-memory-totals"><div><strong>{memorySize(value.used_bytes)}</strong><span>Measured use</span></div><div><strong>{memorySize(value.target_bytes)}</strong><span>Current budget</span></div><svg viewBox="0 0 300 80" role="img" aria-label="Recent memory use while this page is open"><line x1="0" y1={70 - value.target_bytes / ceiling * 62} x2="300" y2={70 - value.target_bytes / ceiling * 62} className="ws-memory-target" /><polyline points={points} fill="none" className="ws-memory-line" /></svg></div>
    <div className="ws-memory-parts"><span><Cpu size={14} />Engine <b>{memorySize(value.engine_bytes)}</b></span><span>Database <b>{memorySize(value.database_bytes)}</b></span><span>App <b>{memorySize(value.desktop_bytes)}</b></span></div>
    {value.reason && <p className="ws-budget-explanation" role="status"><PauseCircle size={17} /><span>{reasons[value.reason] || 'Model work is waiting for memory capacity.'} Saved memories and keyword search remain available.</span></p>}
    <details><summary>Measurement details</summary><p>Usage adds the resident memory of the engine, its database and the desktop app. Shared pages can be counted more than once. The chart shows recent samples from this page; it is not a historical performance report.</p><p>Current model batch: {value.batch_size} chunks. Idle models released: {value.model_evictions}. System headroom: {memorySize(value.system_reserve_bytes)}.{value.os_memory_limit_bytes ? ` Operating-system limit: ${memorySize(value.os_memory_limit_bytes)}.` : ' No operating-system RAM limit is reported.'}</p><p>The budget does not reserve RAM or terminate the process at an exact byte count. External model servers have their own memory settings.</p></details>
  </section>;
}
