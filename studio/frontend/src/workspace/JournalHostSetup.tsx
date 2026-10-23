import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { GitBranch, RefreshCw } from 'lucide-react';
import type { JournalChange, JournalDestination, LocalStatus } from '../../../shared/local-workspace';
import { localError } from './LocalSetup';

type Draft = { action: 'save'; destination: JournalDestination } | { action: 'remove'; space_id: string } | { action: 'reset' };

export default function JournalHostSetup({ endpoint, space, label }: { endpoint: string; space: string; label: string }) {
  const desktop = window.mnemion;
  const cache = useQueryClient();
  const [status, setStatus] = useState<LocalStatus>();
  const [error, setError] = useState<unknown>();
  const [notice, setNotice] = useState('');
  const [draft, setDraft] = useState<Draft | null>(null);
  const [revision, setRevision] = useState('');
  const [reviewed, setReviewed] = useState(false);
  const [busy, setBusy] = useState(false);
  const live = useRef(true), refreshAfterRestart = useRef(false);
  const saved = status?.info?.journal_access, settings = status?.info?.settings;
  useEffect(() => {
    live.current = true;
    if (desktop?.localJournal) void desktop.localStatus?.().then(value => { if (live.current) setStatus(value); }).catch(failure => { if (live.current) setError(failure); });
    const unsubscribe = desktop?.localJournal ? desktop.onLocalStatus?.(value => { if (live.current) setStatus(value); }) : undefined;
    return () => { live.current = false; unsubscribe?.(); };
  }, [desktop]);
  // Reset identity-bound drafts before exposing this host's controls. A passive
  // effect can otherwise discard a form opened just as the first status arrives.
  useLayoutEffect(() => { setDraft(null); setReviewed(false); setNotice(''); }, [settings?.workspace_id, space, endpoint]);
  useEffect(() => {
    if (status?.state === 'running' && refreshAfterRestart.current) {
      refreshAfterRestart.current = false;
      void cache.invalidateQueries({ queryKey: ['journal', space] });
    }
  }, [status?.state, cache, space]);
  let sameHost = false;
  try { sameHost = new URL(endpoint).origin === `http://127.0.0.1:${settings?.port}`; } catch { /* The workspace connection validates addresses. */ }
  if (!desktop?.localJournal || !sameHost || !saved || !settings || !status) return null;
  const current = saved.destinations.find(item => item.space_id === space);
  const working = busy || ['starting', 'stopping'].includes(status.state);
  const stale = !!draft && revision !== saved.revision;
  function begin(value: Draft) {
    setDraft(value); setRevision(saved!.revision); setReviewed(false); setError(undefined); setNotice('');
  }
  function edit(patch: Partial<JournalDestination>) {
    setDraft(value => value?.action === 'save' ? { action: 'save', destination: { ...value.destination, ...patch } } : value);
    setReviewed(false); setError(undefined);
  }
  async function chooseSsh(kind: 'identity' | 'known_hosts') {
    if (draft?.action !== 'save' || !draft.destination.ssh || !desktop?.localJournalChoose) return;
    setBusy(true); setError(undefined);
    try {
      const path = await desktop.localJournalChoose(kind);
      if (path && live.current) edit({ ssh: { ...draft.destination.ssh, [kind === 'identity' ? 'identity_file' : 'known_hosts_file']: path } });
    } catch (failure) { if (live.current) setError(failure); }
    finally { if (live.current) setBusy(false); }
  }
  async function refresh() {
    setBusy(true); setError(undefined);
    try { const next = await desktop!.localStatus!(); if (live.current) setStatus(next); }
    catch (failure) { if (live.current) setError(failure); }
    finally { if (live.current) setBusy(false); }
  }
  async function save() {
    if (!draft || !reviewed || stale) return;
    setBusy(true); setError(undefined); setNotice('');
    try {
      const next = await desktop!.localJournal!({ workspace_id: settings!.workspace_id, expected_revision: revision, ...draft } as JournalChange);
      if (live.current) {
        refreshAfterRestart.current = true;
        setStatus(next); setDraft(null); setReviewed(false);
        setNotice(next.state === 'starting'
          ? 'Destination saved. The workspace is restarting; review its publication settings below when it returns.'
          : 'Destination saved. Start this local workspace, then review its publication settings.');
      }
    } catch (failure) { if (live.current) setError(failure); }
    finally { if (live.current) setBusy(false); }
  }
  return <section className="ws-card ws-journal-host" aria-labelledby="journal-host-title">
    <div className="ws-memory-heading"><h2 id="journal-host-title"><GitBranch size={20} />Repository on this host</h2>
      <button type="button" className="ws-button ws-quiet" disabled={working} onClick={() => void refresh()}><RefreshCw size={14} />Refresh host</button></div>
    <p>Choose the Git destination for <strong>{label}</strong>, hosted on this computer. Mnemion manages its private registration and restarts the workspace to apply changes.</p>
    <p className={`ws-notice${saved.state === 'configuration_error' ? ' ws-error' : ''}`} role="status">{saved.message}</p>
    {!saved.git_found && <p className="ws-notice">Git was not found on this computer. <a href="https://git-scm.com/downloads" target="_blank" rel="noreferrer">Install Git for free</a>, then restart Mnemion.</p>}
    <p className="ws-helper">Use an existing repository with Git credential-manager sign-in, or its own SSH deploy key and verified host keys. Registration does not test repository access or publish memories; approve publication separately below. Passwords and tokens do not belong in the repository address.</p>
    {!!error && <p className="ws-notice ws-error" role="alert">{localError(error)}</p>}
    {notice && <p className="ws-notice" role="status">{notice}</p>}
    {current && !draft && <p className="ws-helper">{current.remote} · {current.branch} · {current.prefix}</p>}
    {saved.repairable && saved.state !== 'configuration_error' && !draft && <div className="ws-setup-actions">
      <button type="button" className="ws-button" disabled={working} onClick={() => begin({ action: 'save', destination: current ? { ...current } : {
        space_id: space, label, remote: '', branch: 'main', prefix: `memory/native-buffer/${space}`, personal_data_scan: true,
      } })}>{current ? 'Change repository registration' : 'Register a repository'}</button>
      {current && <button type="button" className="ws-button ws-quiet" disabled={working} onClick={() => begin({ action: 'remove', space_id: space })}>Remove registration</button>}
    </div>}
    {saved.repairable && saved.state === 'configuration_error' && !draft && <button type="button" className="ws-button" disabled={working} onClick={() => begin({ action: 'reset' })}>Repair registrations</button>}
    {draft && <form className="ws-form" onSubmit={event => { event.preventDefault(); void save(); }}>
      <fieldset className="ws-form" disabled={working}>
        {stale && <p className="ws-notice" role="alert">Registrations changed on this host. Cancel and review the current values before saving.</p>}
        {draft.action === 'save' && <>
          <label className="ws-field"><span>Destination name</span><input required maxLength={200} value={draft.destination.label} onChange={event => edit({ label: event.target.value })} /></label>
          <label className="ws-field"><span>Connection</span><select value={draft.destination.ssh ? 'ssh' : 'https'} onChange={event => edit({ remote: '', ssh: event.target.value === 'ssh' ? { identity_file: '', known_hosts_file: '' } : undefined })}>
            <option value="https">HTTPS · Git credential manager</option><option value="ssh">SSH · repository deploy key</option></select></label>
          <label className="ws-field"><span>Repository address</span><input type="url" required maxLength={2048} autoComplete="off" placeholder={draft.destination.ssh ? 'ssh://git@github.com/your-team/memories.git' : 'https://github.com/your-team/memories.git'} value={draft.destination.remote} onChange={event => edit({ remote: event.target.value })} /></label>
          {draft.destination.ssh && <>
            <label className="ws-field"><span>Private deploy key file</span><input required maxLength={4096} autoComplete="off" spellCheck={false} value={draft.destination.ssh.identity_file} onChange={event => edit({ ssh: { ...draft.destination.ssh!, identity_file: event.target.value } })} /></label>
            {desktop.localJournalChoose && <button type="button" className="ws-button ws-quiet" onClick={() => void chooseSsh('identity')}>Choose deploy key</button>}
            <label className="ws-field"><span>Verified known-hosts file</span><input required maxLength={4096} autoComplete="off" spellCheck={false} value={draft.destination.ssh.known_hosts_file} onChange={event => edit({ ssh: { ...draft.destination.ssh!, known_hosts_file: event.target.value } })} /></label>
            {desktop.localJournalChoose && <button type="button" className="ws-button ws-quiet" onClick={() => void chooseSsh('known_hosts')}>Choose host keys</button>}
            <p className="ws-helper">Both files must belong to this OS account and be readable only by it. Use a dedicated deploy key with write access to this repository. Verify the server’s host keys through its provider or administrator before saving. Background publishing cannot ask for a key passphrase and does not use an SSH agent.</p>
          </>}
          <label className="ws-field"><span>Branch</span><input required maxLength={200} value={draft.destination.branch} onChange={event => edit({ branch: event.target.value })} /></label>
          <label className="ws-field"><span>Journal folder</span><input required maxLength={200} value={draft.destination.prefix} onChange={event => edit({ prefix: event.target.value })} /></label>
          <p className="ws-helper">Choose an unused folder or this space’s existing native journal. An older external buffer needs separate migration. Pending changes use the newly approved destination; previously published Git history stays in its original repository.</p>
          <label className="ws-checkbox"><input type="checkbox" checked={draft.destination.personal_data_scan} onChange={event => edit({ personal_data_scan: event.target.checked })} />Check recognizable personal-data patterns before journaling</label>
          <p className="ws-helper">Secret checks always remain enabled. These checks cannot recognize every sensitive detail.</p>
        </>}
        {draft.action === 'remove' && <p className="ws-notice">Removing the destination keeps its private queue and Git history. If publication was enabled, further journal-backed saves require re-registration and approval. Use <strong>Pause publication</strong> below for an ordinary pause.</p>}
        {draft.action === 'reset' && <p className="ws-notice">Repair preserves the damaged registration file and clears this host’s destination choices. Re-register each affected space before resuming its journal. Existing memories and Git history remain.</p>}
        <label className="ws-checkbox"><input type="checkbox" required checked={reviewed} onChange={event => setReviewed(event.target.checked)} />Save this change and briefly restart the local workspace</label>
        <div className="ws-setup-actions"><button className="ws-button ws-primary" disabled={!reviewed || stale}>{busy ? 'Saving…' : 'Save host registration'}</button>
          <button type="button" className="ws-button ws-quiet" onClick={() => { setDraft(null); setReviewed(false); setError(undefined); }}>Cancel</button></div>
      </fieldset>
    </form>}
  </section>;
}
