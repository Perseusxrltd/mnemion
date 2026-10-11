import { useEffect, useRef, useState } from 'react';
import { ArrowLeft, ArrowRight, Check, Cpu, Database, LoaderCircle, Play, ShieldCheck } from 'lucide-react';
import type { LocalOptions, LocalStatus } from '../../../shared/local-workspace';
import type { WorkspaceSession } from './connection-types';
import { LiveMemory, MemoryFields, memorySize, validMemory } from './MemoryControls';

export const localError = (error: unknown) => (error instanceof Error ? error.message : 'The local workspace could not complete this step.')
  .replace(/^Error invoking remote method '[^']+': (?:Error: )?/, '');

const stages = [
  ['database', 'Private database'], ['access', 'Workspace and permissions'], ['model', 'Memory model'],
  ['service', 'Background service'], ['verification', 'Save and search checks'],
];

export default function LocalSetup({ initial, onOpen, onBack, autoContinue = false }: {
  initial?: LocalStatus; onOpen: (session: WorkspaceSession) => void; onBack: () => void; autoContinue?: boolean;
}) {
  const desktop = window.mnemion!;
  const [status, setStatus] = useState(initial);
  const [step, setStep] = useState(0);
  const [options, setOptions] = useState<LocalOptions>({ workspace_name: 'My workspace', owner_name: 'You', embedding_profile: 'e5-small', threads: 2, port: 7892, memory: { mode: 'auto', limit_mib: null } });
  const [error, setError] = useState<unknown>();
  const [busy, setBusy] = useState(false);
  const initialized = useRef(false);
  const autoOpened = useRef(false);
  const autoStarted = useRef(false);
  const active = useRef(true);

  useEffect(() => {
    active.current = true;
    void desktop.localStatus!().then(value => { if (active.current) setStatus(value); }).catch(error => { if (active.current) setError(error); });
    const unsubscribe = desktop.onLocalStatus?.(value => { if (active.current) setStatus(value); });
    return () => { active.current = false; unsubscribe?.(); };
  }, [desktop]);
  useEffect(() => {
    if (initialized.current || !status?.info) return;
    initialized.current = true;
    const resources = status.info.resources;
    setOptions(status.info.settings || { workspace_name: 'My workspace', owner_name: 'You', embedding_profile: resources.recommended_profile, threads: Math.min(2, resources.cpu_threads), port: 7892, memory: { mode: 'auto', limit_mib: null } });
  }, [status?.info]);

  async function perform(action: () => Promise<unknown>) {
    setBusy(true); setError(undefined);
    try { await action(); } catch (error) { if (active.current) setError(error); }
    finally { if (active.current) setBusy(false); }
  }
  async function open() { const session = await desktop.localOpen!(); if (active.current) onOpen(session); }
  useEffect(() => {
    if (autoContinue && status?.info?.configured && ['new', 'stopped'].includes(status.state) && !autoStarted.current) {
      autoStarted.current = true;
      void perform(async () => setStatus(await desktop.localStart!()));
    }
    if (autoContinue && status?.state === 'running' && !autoOpened.current) {
      autoOpened.current = true;
      void perform(open);
    }
  }, [autoContinue, status?.state, status?.info?.configured]);

  const resources = status?.info?.resources;
  const working = status?.state === 'starting' || status?.state === 'stopping';
  const configured = status?.info?.configured;
  const stepIndex = stages.findIndex(([id]) => id === status?.stage);

  return <section className="ws-local-setup" aria-label="Create a local workspace">
    <button type="button" className="ws-button ws-quiet" disabled={busy} onClick={onBack}><ArrowLeft size={15} />Choose another workspace</button>
    <div className="ws-local-intro"><span className="ws-local-symbol"><Database size={23} /></span><div><h3>{configured ? status.info?.settings?.workspace_name : 'Your memory, on this computer'}</h3><p>Mnemion manages the database, model and background service for you.</p></div></div>
    {!!error && <div className="ws-notice ws-error" role="alert">{localError(error)}</div>}
    {!status && !error && <p role="status"><LoaderCircle className="ws-spin" size={16} />Checking this computer…</p>}
    {status && !status.available && <div className="ws-notice">This installation does not include the local engine. Use a complete desktop installer, or join an existing workspace.</div>}
    {status?.state === 'error' && <div className="ws-notice ws-error" role="alert"><p>{status.message}</p><small>Your saved data has been retained.</small></div>}
    {working && <div className="ws-setup-progress" aria-live="polite">
      <p><LoaderCircle className="ws-spin" size={18} />{status.message}</p>
      {status.state === 'starting' && <ol>{stages.map(([id, label], index) => <li key={id} className={index < stepIndex ? 'complete' : index === stepIndex ? 'current' : ''}><span>{index < stepIndex ? <Check size={13} /> : index + 1}</span>{label}</li>)}</ol>}
      <small>The first model download needs an internet connection. A paused setup resumes from its saved files.</small>
      <button className="ws-button ws-quiet" disabled={busy || status.state === 'stopping'} onClick={() => void perform(() => desktop.localStop!())}>Pause setup</button>
    </div>}
    {status?.state === 'running' && <div className="ws-local-ready"><ShieldCheck size={28} /><h3>Your workspace is ready</h3><p>{status.memory?.indexing_paused ? 'You can save and search memories now. Semantic indexing will resume when the RAM budget has room for the model.' : 'Your private workspace is running and its save and search checks passed.'}</p><button className="ws-button ws-primary" disabled={busy} onClick={() => void perform(open)}>{busy ? <LoaderCircle className="ws-spin" size={16} /> : <ArrowRight size={16} />}Open workspace</button></div>}
    {configured && !working && status?.state !== 'running' && <div className="ws-local-resume"><p>Continue with your saved settings and downloaded model files.</p><button className="ws-button ws-primary" disabled={busy} onClick={() => void perform(async () => setStatus(await desktop.localStart!()))}><Play size={16} />Resume local workspace</button></div>}
    {resources && status?.available && !configured && !working && status.state !== 'running' && <form onSubmit={event => {
      event.preventDefault();
      if (step < 2) { setStep(step + 1); return; }
      void perform(async () => setStatus(await desktop.localCreate!(options)));
    }}>
      <div className="ws-setup-steps" aria-label={`Setup step ${step + 1} of 3`}>{['Workspace', 'Computer', 'Create'].map((name, index) => <span key={name} className={step === index ? 'current' : step > index ? 'complete' : ''}><b>{index + 1}</b>{name}</span>)}</div>
      {step === 0 && <div className="ws-setup-fields"><label className="ws-field"><span>Workspace name</span><input value={options.workspace_name} onChange={event => setOptions({ ...options, workspace_name: event.target.value })} maxLength={200} required autoComplete="organization" /></label><label className="ws-field"><span>Your display name</span><input value={options.owner_name} onChange={event => setOptions({ ...options, owner_name: event.target.value })} maxLength={200} required autoComplete="name" /></label><div className="ws-notice"><ShieldCheck size={16} />You start with a private space. Add team spaces and give each person or agent only the access they need.</div></div>}
      {step === 1 && <div className="ws-setup-fields"><label className="ws-field"><span>Embedding model</span><select value={options.embedding_profile} onChange={event => setOptions({ ...options, embedding_profile: event.target.value as LocalOptions['embedding_profile'] })}>{resources.profiles.map(profile => <option key={profile.id} value={profile.id}>{profile.label} · {profile.languages}</option>)}</select></label><small><Cpu size={14} />Both run locally on the CPU. No graphics card or paid account is required.</small><MemoryFields value={options.memory} resources={resources} onChange={memory => setOptions({ ...options, memory })} /><details className="ws-setup-advanced"><summary>Advanced settings</summary><label className="ws-field"><span>Model CPU threads</span><input type="number" min={1} max={Math.min(8, resources.cpu_threads)} value={options.threads} onChange={event => setOptions({ ...options, threads: event.target.valueAsNumber })} /></label><label className="ws-field"><span>Local service port</span><input type="number" min={1024} max={65535} value={options.port} onChange={event => setOptions({ ...options, port: event.target.valueAsNumber })} /></label></details></div>}
      {step === 2 && <div className="ws-setup-review"><h3>Ready to create {options.workspace_name}</h3><dl><dt>Model</dt><dd>{resources.profiles.find(profile => profile.id === options.embedding_profile)?.label}</dd><dt>RAM</dt><dd>{options.memory.mode === 'auto' ? 'Automatically managed' : memorySize(options.memory.limit_mib * 1024 ** 2)}</dd><dt>Data folder</dt><dd className="ws-local-path">{status.info?.data_directory}</dd><dt>Free disk space</dt><dd>{memorySize(resources.available_disk_bytes)}</dd><dt>Access</dt><dd>Private to this OS account; agents need a workspace key.</dd></dl><p>The model downloads once. Mnemion checks the database, creates your workspace, then saves a welcome memory and tests search.</p>{resources.available_disk_bytes < resources.minimum_free_disk_bytes && <p className="ws-notice ws-error" role="alert">Free at least 2 GiB on this drive before continuing.</p>}</div>}
      <div className="ws-setup-actions">{step > 0 && <button type="button" className="ws-button ws-quiet" disabled={busy} onClick={() => setStep(step - 1)}>Back</button>}<button className="ws-button ws-primary" disabled={busy || !options.workspace_name.trim() || !options.owner_name.trim() || !validMemory(options.memory) || (step === 2 && resources.available_disk_bytes < resources.minimum_free_disk_bytes)}>{busy ? <LoaderCircle className="ws-spin" size={16} /> : <ArrowRight size={16} />}{step === 2 ? 'Create workspace' : 'Continue'}</button></div>
    </form>}
    {status?.memory && <LiveMemory value={status.memory} />}
  </section>;
}
