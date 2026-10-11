import { useEffect, useRef, useState } from 'react';
import { LoaderCircle, RefreshCw, ShieldCheck } from 'lucide-react';
import type { LocalStatus } from '../../../shared/local-workspace';

export default function LocalAddress({ status, onStatus, disabled = false }: {
  status: LocalStatus; onStatus: (status: LocalStatus) => void; disabled?: boolean;
}) {
  const settings = status.info?.settings;
  const [automatic, setAutomatic] = useState(true);
  const [port, setPort] = useState(settings?.port ?? 7892);
  const [expected, setExpected] = useState(() => ({ id: settings?.workspace_id, port: settings?.port }));
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState('');
  const [expanded, setExpanded] = useState(status.errorCode === 'port_in_use');
  const live = useRef(true);
  useEffect(() => { live.current = true; return () => { live.current = false; }; }, []);
  useEffect(() => { if (status.errorCode === 'port_in_use') setExpanded(true); }, [status.errorCode]);
  useEffect(() => {
    if (!dirty && settings) {
      setPort(settings.port);
      setExpected({ id: settings.workspace_id, port: settings.port });
    }
  }, [dirty, settings?.workspace_id, settings?.port]);
  if (!settings || !window.mnemion?.localPort) return null;
  const stopped = !['running', 'starting', 'stopping'].includes(status.state);
  const changed = expected.id !== settings.workspace_id || expected.port !== settings.port;
  const valid = automatic || (Number.isInteger(port) && port >= 1024 && port <= 65535 && port !== settings.database_port);
  async function perform(action: () => Promise<void>) {
    setBusy(true); setError('');
    try { await action(); }
    catch (error) {
      if (live.current) setError(error instanceof Error ? error.message.replace(/^Error invoking remote method '[^']+': (?:Error: )?/, '') : 'The address could not be changed. Refresh before retrying.');
    } finally { if (live.current) setBusy(false); }
  }
  return <details className="ws-setup-advanced" open={expanded} onToggle={event => setExpanded(event.currentTarget.open)}>
    <summary>Local workspace address</summary>
    <p>Current address: <code>http://127.0.0.1:{settings.port}</code></p>
    <p>If another program uses this address, choose an available port. Your workspace and keys stay the same. Agents using the old address will need the new one.</p>
    {!stopped && <p className="ws-notice">Pause this local workspace before changing its address.</p>}
    <form onSubmit={event => {
      event.preventDefault();
      if (busy || disabled || !stopped || changed || !valid || !expected.id || !expected.port) return;
      void perform(async () => {
        const next = await window.mnemion!.localPort!({ workspace_id: expected.id!, expected_port: expected.port!, port: automatic ? null : port });
        if (live.current) { setDirty(false); setSaved(true); onStatus(next); }
      });
    }}>
      <fieldset className="ws-setup-fields" disabled={busy || disabled || !stopped}>
        <legend>Choose a local port</legend>
        <label className="ws-field"><span>Port selection</span><select value={automatic ? 'auto' : 'manual'} onChange={event => { setAutomatic(event.target.value === 'auto'); setDirty(true); setSaved(false); }}><option value="auto">Automatic · choose an available port</option><option value="manual">Choose a specific port</option></select></label>
        {!automatic && <label className="ws-field"><span>Local service port</span><input type="number" min={1024} max={65535} step={1} required value={Number.isFinite(port) ? port : ''} onChange={event => { setPort(event.target.valueAsNumber); setDirty(true); setSaved(false); }} /></label>}
        {!automatic && port === settings.database_port && <p className="ws-notice ws-error" role="alert">That port belongs to the private database. Choose another port.</p>}
        <button className="ws-button" disabled={changed || !valid}>{busy ? <LoaderCircle className="ws-spin" size={16} /> : <ShieldCheck size={16} />}Save local address</button>
      </fieldset>
    </form>
    {changed && <p className="ws-notice" role="status">The address changed in another session. Refresh before saving; your choice is retained.</p>}
    {saved && <p className="ws-memory-saved" role="status">Address saved. Resume the workspace when ready.</p>}
    {!!error && <p className="ws-notice ws-error" role="alert">{error}</p>}
    <button type="button" className="ws-button ws-quiet" disabled={busy || disabled} onClick={() => void perform(async () => {
      const next = await window.mnemion!.localStatus!();
      if (live.current) {
        setExpected({ id: next.info?.settings?.workspace_id, port: next.info?.settings?.port });
        setSaved(false); onStatus(next);
      }
    })}><RefreshCw size={15} />Refresh current address</button>
  </details>;
}
