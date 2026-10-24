import type { SourceCall } from './desktop-sources.js'
import { desktopAction } from './desktop-actions.js'

export const telemetryMessages: Record<string, string> = {
  telemetry_invalid_request: 'Choose a documented product telemetry control.',
  telemetry_invalid_choice: 'Choose whether to share anonymous product statistics.',
  telemetry_choice_changed: 'Your privacy choice changed in another process. Refresh before enabling telemetry.',
  telemetry_disclosure_unavailable: 'Collection is not available in this build. Your privacy choice can still be saved.',
  telemetry_storage_unavailable: 'Privacy settings could not be read or saved. Product telemetry stays off.',
  telemetry_busy: 'Another privacy operation is finishing. Refresh its status before changing this choice.',
}

/** App and native agent use the same offline kernel, independent of workspace state. */
export class ProductTelemetry {
  constructor(private readonly call: SourceCall) {}

  async execute(action: string, input: Record<string, unknown> = {}, signal?: AbortSignal) {
    if (!['telemetry.status', 'telemetry.configure', 'telemetry.schema', 'telemetry.preview'].includes(action)) {
      throw new Error(telemetryMessages.telemetry_invalid_request)
    }
    desktopAction(action, input)
    if (Buffer.byteLength(JSON.stringify(input)) > 8192) throw new Error(telemetryMessages.telemetry_invalid_request)
    return this.call({ action: action.slice('telemetry.'.length), ...input }, signal)
  }
}
