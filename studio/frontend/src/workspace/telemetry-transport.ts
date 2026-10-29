/** Existing foreground work may own one send; this module schedules no work. */
import type { BrowserTelemetry } from './telemetry-policy'
import { PreparedBrowserTelemetryReport } from './telemetry-delivery'
import { readBrowserCompanyPolicy } from './telemetry-company'
import { destinationValid } from './telemetry-capability'

type Outcome = 'delivered' | 'suppressed' | 'failed' | 'deadline'
type Client = Pick<BrowserTelemetry, 'status' | 'delivery' | 'restrictCompany'>

/** Fetch cannot expose or cap DNS/TLS/TCP/IP byte counts. The durable allowance
 * reserves the entire attempt; release qualification must measure browser wire
 * costs. Credentials, referrers, redirects, retries and keepalive are disabled. */
export async function sendBrowserTelemetry(client: Client, report: PreparedBrowserTelemetryReport,
  stop?: AbortSignal): Promise<{ outcome: Outcome }> {
  if (!(report instanceof PreparedBrowserTelemetryReport) || !report.claimTransport()) return { outcome: 'suppressed' }
  const request = new AbortController(), watching = new AbortController()
  const abort = () => request.abort()
  const clock = { expired: false }
  let releaseHandoff = () => {}
  let timer: ReturnType<typeof setTimeout> | undefined, watcher: Promise<void> | undefined
  let outcome: Outcome = 'failed'
  try {
    const status = client.status(), destination = status.disclosure.destination
    if (!status.effective_enabled || !status.collection_available || !destinationValid(destination) || stop?.aborted ||
      !await client.delivery.current(report)) return { outcome: 'suppressed' }
    const remaining = Math.min(5000, report.monotonicDeadline - performance.now())
    if (remaining <= 0) return { outcome: 'deadline' }
    stop?.addEventListener('abort', abort, { once: true })
    if (stop?.aborted) return { outcome: 'suppressed' }
    timer = setTimeout(() => { clock.expired = true; request.abort() }, remaining)
    const handoff = new Promise<void>(resolve => { releaseHandoff = resolve })
    watcher = client.delivery.watch(report, abort, watching.signal, handoff)
    const checkedAt = performance.now()
    const company = await readBrowserCompanyPolicy(request.signal,
      start => client.delivery.guardedPolicyRead(report, start), releaseHandoff)
    // A local stop or expired attempt is not a newly observed company policy.
    if (request.signal.aborted) return { outcome: clock.expired ? 'deadline' : 'suppressed' }
    client.restrictCompany(company)
    if (request.signal.aborted || !company.enabled || !report.permits(company.metric_groups) ||
        performance.now() - checkedAt >= 1000 ||
        !await client.delivery.current(report)) return { outcome: clock.expired ? 'deadline' : 'suppressed' }
    let pending: Promise<Response | null> | undefined
    const written = await client.delivery.guardedWrite(report, body => {
      if (request.signal.aborted || performance.now() - checkedAt >= 1000) return false
      // Fetch copies the BufferSource during request construction, before the
      // privacy fence erases its temporary body. No caller object is retained.
      pending = fetch(destination, { method: 'POST', body: new Uint8Array(body),
        headers: { 'Content-Type': 'application/octet-stream' }, mode: 'cors', credentials: 'omit',
        cache: 'no-store', redirect: 'error', referrerPolicy: 'no-referrer', keepalive: false, signal: request.signal,
      }).then(response => response, () => null)
      return true
    })
    releaseHandoff()
    if (!written || !pending) return { outcome: 'suppressed' }
    // The watcher covers both requests; the same owner's short Web Lock work
    // is serialized, so final handoff cannot race its own in-flight checks.
    const response = await pending
    if (request.signal.aborted) return { outcome: clock.expired ? 'deadline' : 'suppressed' }
    if (performance.now() >= report.monotonicDeadline) return { outcome: 'deadline' }
    // Chromium can expose an empty ReadableStream for HTTP 204. Do not read it
    // or mistake its presence for response content; require the fixed empty
    // collector response and discard the stream when this attempt ends.
    if (response && response.status === 204 && !response.redirected && response.url === destination &&
      response.headers.get('content-length') === '0') outcome = 'delivered'
    return { outcome }
  } catch { return { outcome: request.signal.aborted ? 'suppressed' : 'failed' } }
  finally {
    if (timer !== undefined) clearTimeout(timer)
    stop?.removeEventListener('abort', abort)
    // No response content is read. Abort discards a rejected response body and
    // stops a pending request; there is no page-exit flush or opt-out ping.
    request.abort(); watching.abort()
    releaseHandoff()
    await watcher
    await client.delivery.cancel(report)
  }
}
