import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowLeft, ShieldCheck } from 'lucide-react'
import BrandMark from '../components/BrandMark'
import type { TelemetryPreview, TelemetryStatus } from '../../../shared/product-telemetry'
import { choiceKey, telemetryConfigure, telemetryPreview, telemetryStatus } from './telemetry-policy'
import './workspace.css'

const reasons: Record<TelemetryStatus['reason'], string> = {
  enabled: 'Anonymous product telemetry is on.',
  user_disabled: 'Product telemetry is off by your choice.',
  browser_privacy: 'Your browser’s Global Privacy Control keeps product telemetry off.',
  company_policy: 'Your organization’s policy keeps product telemetry off.',
  storage_unavailable: 'Privacy settings could not be read. Product telemetry stays off.',
  coordination_unavailable: 'This browser cannot coordinate privacy settings between tabs. Product telemetry stays off.',
  disclosure_required: 'No product telemetry is collected until you have reviewed the current disclosure.',
  collection_unavailable: 'Product telemetry is not available in this build.',
}

export default function Privacy() {
  const [status, setStatus] = useState<TelemetryStatus>()
  const [preview, setPreview] = useState<TelemetryPreview>()
  const [error, setError] = useState<string>()
  const [busy, setBusy] = useState(false)
  const [pendingChoice, setPendingChoice] = useState<boolean>()
  const refresh = useCallback(async () => {
    try { setStatus(await telemetryStatus()); setError(undefined) }
    catch (error) { setError(error instanceof Error ? error.message : 'Privacy settings are unavailable.') }
  }, [])
  useEffect(() => {
    void refresh()
    const changed = (event: StorageEvent) => { if (event.key === choiceKey || event.key === null) void refresh() }
    window.addEventListener('storage', changed)
    window.addEventListener('focus', refresh)
    return () => { window.removeEventListener('storage', changed); window.removeEventListener('focus', refresh) }
  }, [refresh])
  async function choose(enabled: boolean) {
    if (!status || busy) return
    setBusy(true); setPendingChoice(enabled); setError(undefined)
    try {
      setStatus(await telemetryConfigure({ enabled, expected_revision: status.revision,
        disclosure_version: enabled && status.collection_available ? status.required_disclosure_version : 0 }))
      setPreview(undefined)
    } catch (error) {
      setError(error instanceof Error ? error.message : 'The privacy choice could not be saved.')
      try { setStatus(await telemetryStatus()) } catch { /* Keep the explicit failure visible. */ }
    } finally { setPendingChoice(undefined); setBusy(false) }
  }
  return <div className="workspace"><main className="ws-page ws-privacy" aria-labelledby="privacy-heading">
    <Link className="ws-link" to="/workspace"><ArrowLeft size={16} /> Back to workspaces</Link>
    <div className="ws-brand"><BrandMark /> mnemion<span>studio</span></div>
    <h1 id="privacy-heading"><ShieldCheck size={24} /> Privacy & product telemetry</h1>
    <p>Help Perseus XR improve Mnemion with anonymous product statistics. Your memories and private workspace diagnostics stay separate.</p>
    {error && <p className="ws-error" role="alert">{error}</p>}
    {!status ? <>{!error && <p role="status">Loading your privacy choice…</p>}
      <button className="ws-button" onClick={() => void refresh()}>Retry privacy status</button></> : <>
      <section className="ws-panel" aria-labelledby="telemetry-choice-heading">
        <h2 id="telemetry-choice-heading">Your choice</h2>
        <p role="status">{reasons[status.reason]}</p>
        {!status.collection_available && <p>No product statistics are sent by this build. Your preference is saved; enabling collection in a later build will require its current disclosure.</p>}
        <label className="ws-check"><input type="checkbox" checked={pendingChoice ?? status.user_enabled}
          disabled={busy || status.storage === 'unreadable'} onChange={event => void choose(event.target.checked)} />
          Share anonymous product statistics</label>
        <p><small>Enabled by default after disclosure. Change this at any time. This choice applies to {status.disclosure.choice_scope} and never changes memory features or access.</small></p>
        <div className="ws-actions">
          {status.collection_available && status.reason === 'disclosure_required' && <button className="ws-button ws-primary" disabled={busy} onClick={() => void choose(true)}>Keep product telemetry on</button>}
          <button className="ws-button" disabled={busy || status.storage === 'unreadable'} onClick={() => void choose(false)}>{busy ? 'Saving…' : 'Disable product telemetry'}</button>
          <button className="ws-button ws-quiet" disabled={busy} onClick={() => void refresh()}>Refresh privacy status</button>
        </div>
        {status.company_policy.state !== 'unmanaged' && <p><small>Your organization can restrict collection. It cannot override your opt-out.</small></p>}
      </section>
      <section className="ws-panel" aria-labelledby="telemetry-measurements-heading">
        <h2 id="telemetry-measurements-heading">{status.collection_available ? 'What is measured' : 'Planned measurements'}</h2>
        <p>{status.disclosure.includes.join('; ')}.</p>
        <h3>What stays private</h3><p>{status.disclosure.excludes.join('; ')}.</p>
        <p>{status.disclosure.operational_records}</p>
        <p>{status.disclosure.disable}</p>
        <p><strong>Destination:</strong> {status.disclosure.destination ?? 'No collector is active.'}</p>
        {!window.mnemion?.productTelemetry && <p><small>Clearing this site’s browser storage removes this preference and requires fresh disclosure. Global Privacy Control is respected. Other browsers and installations have their own choices.</small></p>}
      </section>
      <section className="ws-panel" aria-labelledby="telemetry-preview-heading">
        <h2 id="telemetry-preview-heading">Inspect the next request</h2>
        <p>Check the exact outgoing body. Transport metadata and its handling are described in the privacy documentation.</p>
        <button className="ws-button" disabled={busy} onClick={async () => {
          try { setPreview(await telemetryPreview()); setError(undefined) }
          catch (error) { setError(error instanceof Error ? error.message : 'The preview is unavailable.') }
        }}>Show payload preview</button>
        {preview && <><p>{preview.message}</p><pre className="ws-code">{preview.outbound_body ?? 'No request is queued.'}</pre><p>{preview.outbound_bytes} outgoing payload bytes.</p>
          {preview.measurement_catalog && <details><summary>Workflow coverage and exclusions</summary>
            <p>{preview.measurement_catalog.ownership.measured}</p>
            <p>These are the supported measurement categories. Collection remains subject to your choice and the availability shown above.</p>
            <dl>{Object.entries(preview.measurement_catalog.workflows).map(([family, operations]) => <div key={family}>
              <dt><strong>{family}</strong></dt><dd>{operations.join(', ')}</dd></div>)}</dl>
            <h3>Excluded from product collection</h3>
            <ul>{Object.entries(preview.measurement_catalog.ownership.exclusions).map(([key, description]) => <li key={key}>{description}</li>)}</ul>
          </details>}
          {!!preview.local_aggregates?.length && <details><summary>Private local aggregate preview</summary>
            <p>Coarse counts waiting locally. These are not an outbound report or an event history.</p>
            <pre className="ws-code">{JSON.stringify(preview.local_aggregates, null, 2)}</pre>
          </details>}
        </>}
      </section>
      <Link className="ws-link" to="/help?doc=docs%2Fservice%2Fprivacy.md">Privacy & data handling documentation</Link>
    </>}
  </main></div>
}
