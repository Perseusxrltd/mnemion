import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowLeft, ShieldCheck } from 'lucide-react'
import BrandMark from '../components/BrandMark'
import TelemetryCoverage from './TelemetryCoverage'
import type { TelemetryConnectionMode, TelemetryPreview, TelemetryReview, TelemetryReviewAction, TelemetryStatus } from '../../../shared/product-telemetry'
import { choiceKey, telemetryConfigure, telemetryPreview, telemetryReviewAction, telemetryReviewStatus, telemetryStatus } from './telemetry-policy'
import { connectionEditDisclosureVersion } from './telemetry-setup'
import { budgetKey } from './telemetry-budget'
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
  const [review, setReview] = useState<TelemetryReview>()
  const [error, setError] = useState<string>()
  const [busy, setBusy] = useState(false)
  const [pendingChoice, setPendingChoice] = useState<boolean>()
  const previewRequest = useRef(0)
  const clearPreview = useCallback(() => {
    previewRequest.current++
    setPreview(undefined)
    setReview(value => value ? { ...value, packet: null } : undefined)
  }, [])
  const refresh = useCallback(async () => {
    clearPreview()
    const request = previewRequest.current
    try {
      // One coherent response also avoids launching two native control
      // processes for every initial/focus refresh.
      const report = await telemetryReviewStatus()
      if (request === previewRequest.current) { setStatus(report.status); setReview(report); setError(undefined) }
    }
    catch (error) {
      if (request === previewRequest.current) setError(error instanceof Error ? error.message : 'Privacy settings are unavailable.')
    }
  }, [clearPreview])
  useEffect(() => {
    void refresh()
    const changed = (event: StorageEvent) => { if (event.key === choiceKey || event.key === budgetKey || event.key === null) void refresh() }
    window.addEventListener('storage', changed)
    window.addEventListener('focus', refresh)
    return () => { previewRequest.current++; window.removeEventListener('storage', changed); window.removeEventListener('focus', refresh) }
  }, [refresh])
  async function choose(enabled: boolean, connectionMode?: TelemetryConnectionMode) {
    if (!status || busy) return
    clearPreview()
    const request = previewRequest.current
    setBusy(true); setPendingChoice(enabled); setError(undefined)
    try {
      const saved = await telemetryConfigure({ enabled, expected_revision: status.revision,
        expected_generation: status.store_generation,
        // Editing a connection setting never acknowledges an unseen disclosure.
        disclosure_version: connectionMode === undefined
          ? enabled && status.collection_available ? status.required_disclosure_version : 0
          : connectionEditDisclosureVersion(status),
        ...(connectionMode === undefined ? {} : { connection_mode: connectionMode }) })
      const report = await telemetryReviewStatus()
      if (request === previewRequest.current) { setStatus(saved); setReview(report) }
    } catch (error) {
      if (request === previewRequest.current) {
        setError(error instanceof Error ? error.message : 'The privacy choice could not be saved.')
        try {
          const latest = await telemetryStatus()
          if (request === previewRequest.current) setStatus(latest)
        } catch { /* Keep the explicit failure visible. */ }
      }
    } finally { setPendingChoice(undefined); setBusy(false) }
  }
  async function controlReport(action: TelemetryReviewAction, mode?: 'automatic' | 'review') {
    if (!status || !review?.review || busy) return
    const input = { expected_revision: status.revision, expected_generation: status.store_generation,
      expected_review_token: review.review.token, ...(mode === undefined ? {} : { mode }) }
    clearPreview()
    const request = previewRequest.current
    setBusy(true); setError(undefined)
    try {
      const result = await telemetryReviewAction(action, input)
      if (request === previewRequest.current) { setReview(result); setStatus(result.status) }
    } catch (error) {
      if (request === previewRequest.current) {
        setError(error instanceof Error ? error.message : 'The report could not be changed.')
        try {
          const latest = await telemetryReviewStatus()
          if (request === previewRequest.current) { setReview(latest); setStatus(latest.status) }
        } catch { /* Keep the failure visible. */ }
      }
    } finally { setBusy(false) }
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
        <details><summary>Telemetry connection settings</summary>
          <label className="ws-field" htmlFor="telemetry-connection-mode"><span>Connection for sending statistics</span>
          <select id="telemetry-connection-mode" value={status.connection_mode ?? 'auto'}
            disabled={busy || status.storage === 'unreadable'}
            onChange={event => void choose(status.user_enabled, event.target.value as TelemetryConnectionMode)}>
            <option value="auto">Automatic detection</option>
            <option value="unmetered">This connection is unmetered</option>
            <option value="metered">Metered connection — pause sending</option>
          </select></label>
          <p><small>Automatic sending may use a connection whose data cost cannot be detected. Sending pauses when available signals report metering, data saving or resource pressure. Some browsers cannot report these signals. Existing traffic limits still apply; unknown cost is not a guarantee of free network use. No network name or address is saved.</small></p>
        </details>
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
        <h2 id="telemetry-preview-heading">Inspect the report format</h2>
        <p>View a fixed, synthetic example of the report body. Viewing it does not send statistics or change your privacy choice.</p>
        <button className="ws-button" disabled={busy} onClick={async () => {
          const request = ++previewRequest.current
          setPreview(undefined)
          try {
            const value = await telemetryPreview()
            if (request === previewRequest.current) { setPreview(value); setError(undefined) }
          } catch (error) {
            if (request === previewRequest.current) setError(error instanceof Error ? error.message : 'The preview is unavailable.')
          }
        }}>Show report format</button>
        {preview && <><p>{preview.message}</p>
          {preview.illustrative_packet && <>
            <p><strong>Synthetic example:</strong> {preview.illustrative_packet.body_bytes} body bytes, shown below as Base64.</p>
            <pre className="ws-code">{preview.illustrative_packet.body_base64}</pre>
            <details><summary>Format and privacy parameters</summary><pre className="ws-code">{JSON.stringify(preview.illustrative_packet, null, 2)}</pre></details>
          </>}
          <p>No actual outgoing packet was inspected. The example is not a queued or sent report. Network headers, encryption and connection overhead add bytes beyond the report body.</p>
          <p><small>{preview.transport_available ? 'A collector route is configured. Actual sending still depends on your choice, company policy and resource limits.' : 'This build has no configured collector route.'}</small></p>
          {preview.measurement_catalog && <details><summary>Workflow coverage and exclusions</summary>
            <p>{preview.measurement_catalog.ownership.measured}</p>
            {preview.workflow_coverage ? <TelemetryCoverage coverage={preview.workflow_coverage} />
              : <p>This app version does not provide a coverage inventory. The category catalog alone does not establish which measurements are implemented.</p>}
            <h3>Excluded from product collection</h3>
            <ul>{Object.entries(preview.measurement_catalog.ownership.exclusions).map(([key, description]) => <li key={key}>{description}</li>)}</ul>
          </details>}
          {!!preview.local_aggregates?.length && <details><summary>Private local aggregate preview</summary>
            <p>Snapshot of coarse local counts when this preview was opened. Refresh the preview to see current counts. These are not an outbound report or an event history.</p>
            <pre className="ws-code">{JSON.stringify(preview.local_aggregates, null, 2)}</pre>
          </details>}
        </>}
      </section>
      <section className="ws-panel" aria-labelledby="telemetry-review-heading">
        <h2 id="telemetry-review-heading">Review reports before sending</h2>
        <p>Optionally pause every report until you approve it. You can select this before enabling collection.</p>
        <p>Reviewed reports have a fixed body within your permitted metric groups and contribute only to overall report volume. They contain no categorical measurement. Feature statistics use automatic reports.</p>
        <label className="ws-check"><input type="checkbox" checked={review?.review?.mode === 'review'}
          disabled={busy || !review?.review || status.storage === 'unreadable'}
          onChange={event => void controlReport('review_mode', event.target.checked ? 'review' : 'automatic')} />
          Pause reports for manual review</label>
        {!status.effective_enabled && <p>No new report can be prepared until collection is permitted under the current disclosure.</p>}
        {review?.review && <p role="status">{review.review.mode === 'automatic' ? 'Automatic delivery is selected.'
          : review.review.outcome === 'approved' ? 'This report is approved for one eligible attempt. Later reports remain paused.'
          : review.review.outcome === 'consumed' ? 'The report was claimed for an attempt. This does not confirm delivery; later reports remain paused.'
          : review.review.outcome === 'expired' ? 'The review expired. Reports remain paused.'
          : review.review.outcome === 'invalidated' ? 'The earlier report is no longer valid. Reports remain paused.'
          : review.review.outcome === 'discarded' ? 'The report was discarded. Reports remain paused.'
          : 'Sending is paused. Inspect a report when local observations are available.'}</p>}
        {review && ['no_report', 'no_observations'].includes(review.message) && <p>No real report is available yet.</p>}
        {review?.message === 'delivery_not_ready' && <p>The delivery allowance is not ready. A report can be prepared when its next attempt is eligible.</p>}
        {review?.message === 'transport_unavailable' && <p>This build has no configured collector route.</p>}
        <div className="ws-actions">
          <button className="ws-button" disabled={busy || review?.review?.mode !== 'review' || !status.effective_enabled}
            onClick={() => void controlReport('inspect_report')}>Inspect next report</button>
          <button className="ws-button ws-primary" disabled={busy || !review?.packet || review.review?.outcome !== 'held'}
            onClick={() => void controlReport('approve_report')}>Approve this report</button>
          <button className="ws-button" disabled={busy || !review?.review?.report_available || review.review.mode !== 'review'}
            onClick={() => void controlReport('discard_report')}>Discard report</button>
        </div>
        {review?.packet && <>
          <p><strong>Exact report:</strong> {review.packet.body_bytes} bytes, shown as Base64. Approval allows these bytes once; it does not generate a replacement.</p>
          <pre className="ws-code" aria-label="Exact report bytes">{review.packet.body_base64}</pre>
          <p>Review expires by {new Date(review.review!.expires_ms!).toLocaleTimeString()}. Its age and permissions are checked again on approval and sending.</p>
          <details><summary>Report fields</summary><pre className="ws-code">{JSON.stringify(review.packet, null, 2)}</pre></details>
        </>}
        <p><small>Review lasts at most 15 minutes and can end sooner. Expired or discarded reports are lost; they never restore an allowance. Leaving manual review clears the held report and resumes automatic delivery. Closing all browser tabs prevents reuse of that review.</small></p>
        <p><small>Stored status is a snapshot. Refresh or inspect again after another user, agent or process changes it. Approval cannot override your privacy choice, company policy, connection limits or resource pressure.</small></p>
      </section>
      <Link className="ws-link" to="/help?doc=docs%2Fservice%2Fprivacy.md">Privacy & data handling documentation</Link>
    </>}
  </main></div>
}
