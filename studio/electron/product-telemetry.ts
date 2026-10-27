import type { SourceCall } from './desktop-sources.js'
import { desktopAction } from './desktop-actions.js'

export const telemetryMessages: Record<string, string> = {
  telemetry_invalid_request: 'Choose a documented product telemetry control.',
  telemetry_invalid_choice: 'Choose whether to share anonymous product statistics.',
  telemetry_choice_changed: 'Your privacy choice changed in another process. Refresh before enabling telemetry.',
  telemetry_disclosure_unavailable: 'Collection is not available in this build. Your privacy choice can still be saved.',
  telemetry_storage_unavailable: 'Privacy settings could not be read or saved. Product telemetry stays off.',
  telemetry_busy: 'Another privacy operation is finishing. Refresh its status before changing this choice.',
  telemetry_invalid_review: 'Use the current report-review settings and report token.',
  telemetry_review_changed: 'The report changed in another process. Inspect its current state again.',
  telemetry_review_not_paused: 'Choose manual report review before inspecting or approving a report.',
  telemetry_review_unavailable: 'Report review is unavailable. No report was approved; refresh its status.',
  telemetry_review_clock_unavailable: 'The report age could not be verified. No report was approved.',
}

/** App and native agent use the same offline kernel, independent of workspace state. */
export class ProductTelemetry {
  constructor(private readonly call: SourceCall, private readonly userDisabled?: () => void) {}

  async execute(action: string, input: Record<string, unknown> = {}, signal?: AbortSignal) {
    if (!['telemetry.status', 'telemetry.configure', 'telemetry.schema', 'telemetry.preview', 'telemetry.review_status',
      'telemetry.review_mode', 'telemetry.inspect_report', 'telemetry.approve_report', 'telemetry.discard_report'].includes(action)) {
      throw new Error(telemetryMessages.telemetry_invalid_request)
    }
    desktopAction(action, input)
    if (Buffer.byteLength(JSON.stringify(input)) > 8192) throw new Error(telemetryMessages.telemetry_invalid_request)
    const result = await this.call({ action: action.slice('telemetry.'.length), ...input }, signal)
    if ((action === 'telemetry.status' || action === 'telemetry.configure') &&
        result.schema_version === 1 && result.user_enabled === false && !signal?.aborted) {
      // This notification can only suppress optional samples. It conveys no
      // permission or private fields and must not alter the control result.
      try { this.userDisabled?.() } catch { /* Optional negative hint. */ }
    }
    return result
  }
}
