import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import BrandMark from '../components/BrandMark'
import type { TelemetryStatus } from '../../../shared/product-telemetry'
import { choiceKey, telemetryConfigure, telemetryStatus } from './telemetry-policy'
import { needsTelemetrySetup, telemetrySetupChoice } from './telemetry-setup'
import './telemetry-setup.css'

/** First-time disclosure is local, optional and independent of workspace access. */
export default function TelemetrySetup({ onDone }: { onDone: () => void }) {
  const [status, setStatus] = useState<TelemetryStatus>()
  const [enabled, setEnabled] = useState(true)
  const [busy, setBusy] = useState(false)
  const [checking, setChecking] = useState(false)
  const [error, setError] = useState<string>()
  const dialog = useRef<HTMLDialogElement>(null)
  const heading = useRef<HTMLHeadingElement>(null)
  const lifetime = useRef(0)
  const mounted = useRef(false)
  const reading = useRef(false)
  const pendingRead = useRef(false)
  const saving = useRef(false)

  const refresh = useCallback(async () => {
    // Focus/storage bursts share one in-flight read. A current-generation
    // compare-and-set remains mandatory when the user later saves a choice.
    if (saving.current || !mounted.current) return
    if (reading.current) { pendingRead.current = true; return }
    reading.current = true
    const current = lifetime.current
    setChecking(true)
    try {
      const value = await telemetryStatus()
      if (current === lifetime.current) {
        setStatus(value)
        if (!needsTelemetrySetup(value)) onDone()
      }
    } catch {
      if (current === lifetime.current) {
        setError('Privacy settings could not be checked. Open privacy controls to review them.')
      }
    } finally {
      reading.current = false
      if (current === lifetime.current) setChecking(false)
      if (pendingRead.current && mounted.current) { pendingRead.current = false; void refresh() }
    }
  }, [onDone])

  useEffect(() => {
    mounted.current = true
    void refresh()
    const changed = (event: StorageEvent) => { if (event.key === choiceKey || event.key === null) void refresh() }
    window.addEventListener('focus', refresh)
    window.addEventListener('storage', changed)
    return () => {
      mounted.current = false; pendingRead.current = false; lifetime.current++
      window.removeEventListener('focus', refresh); window.removeEventListener('storage', changed)
    }
  }, [refresh])

  const show = Boolean(status && needsTelemetrySetup(status))
  useEffect(() => {
    const element = dialog.current
    if (!show || !element) return
    element.showModal()
    heading.current?.focus({ preventScroll: true })
    return () => element.close()
  }, [show])

  async function choose(value: boolean) {
    if (!status || checking || reading.current || saving.current) return
    const input = telemetrySetupChoice(status, value)
    if (!input) return
    const current = lifetime.current
    saving.current = true
    setBusy(true); setError(undefined)
    try {
      // Only this explicit action acknowledges the disclosure. Opening,
      // dismissing or following the details link never creates a preference.
      const saved = await telemetryConfigure(input)
      if (current === lifetime.current) {
        setStatus(saved)
        if (!needsTelemetrySetup(saved)) onDone()
      }
    } catch {
      if (current === lifetime.current) {
        setError('Your privacy choice could not be saved. Review the latest settings and try again.')
        try {
          const latest = await telemetryStatus()
          if (current === lifetime.current) {
            setStatus(latest)
            if (!needsTelemetrySetup(latest)) onDone()
          }
        } catch { /* Keep the explicit failure and the original privacy fence. */ }
      }
    } finally {
      saving.current = false
      if (current === lifetime.current) setBusy(false)
    }
  }

  if (!show || !status) return null
  return <dialog ref={dialog} className="telemetry-setup-dialog" aria-labelledby="telemetry-setup-heading"
    aria-describedby="telemetry-setup-purpose" onCancel={event => { if (saving.current) event.preventDefault(); else onDone() }}>
    <div className="telemetry-setup-brand"><BrandMark /><span>Mnemion · Perseus XR</span></div>
    <h2 id="telemetry-setup-heading" ref={heading} tabIndex={-1}>Your privacy choice</h2>
    <p id="telemetry-setup-purpose">{status.disclosure.purpose}</p>
    <dl>
      <dt>Included</dt><dd>{status.disclosure.includes.join(', ')}.</dd>
      <dt>Never included</dt><dd>{status.disclosure.excludes.join(', ')}.</dd>
      <dt>Sent to</dt><dd>{status.disclosure.destination}</dd>
      <dt>Limit</dt><dd>{Math.floor(status.disclosure.limits.wire_bytes_per_day / 1024)} KiB per day; sending pauses on constrained connections or hardware.</dd>
    </dl>
    <form onSubmit={event => { event.preventDefault(); void choose(enabled) }}>
      <label className="telemetry-setup-choice"><input type="checkbox" checked={enabled} disabled={busy || checking}
        onChange={event => setEnabled(event.target.checked)} /> Share anonymous product statistics</label>
      <p className="telemetry-setup-note">On by default after you save this choice. Applies to {status.disclosure.choice_scope}.
        Change it at any time in Privacy & product telemetry. Your organization can restrict collection; it cannot override your opt-out.</p>
      {error && <p className="telemetry-setup-error" role="alert">{error}</p>}
      <div className="telemetry-setup-actions">
        <button type="submit" className="telemetry-setup-button primary" disabled={busy || checking}>{busy ? 'Saving…' : 'Save and continue'}</button>
        <button type="button" className="telemetry-setup-button" disabled={busy || checking} onClick={() => void choose(false)}>Disable product telemetry</button>
      </div>
    </form>
    <div className="telemetry-setup-footer">
      <Link to="/privacy" aria-disabled={busy} onClick={event => { if (saving.current) event.preventDefault(); else onDone() }}>Review full privacy controls</Link>
      <button type="button" disabled={busy} onClick={onDone}>Not now</button>
    </div>
    <p className="telemetry-setup-note">Not now leaves this disclosure unacknowledged. You can use Mnemion without sharing statistics.</p>
  </dialog>
}
