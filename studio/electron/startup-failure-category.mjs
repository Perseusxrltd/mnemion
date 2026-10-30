/** Bounded startup classes. The raw exception never leaves this function. */

const PAIRS = [
  ['Hosting validation requires an isolated profile and evidence directory', 'isolated_profile'],
  ['Invalid telemetry resource configuration', 'invalid_resource_config'],
  ['Invalid hosting validation configuration', 'invalid_hosting_config'],
  ['Telemetry resource fixture refused a non-loopback destination', 'non_loopback_destination'],
  ['Session-only native connection required', 'session_connection'],
  ['The packaged workspace bridge is unavailable', 'workspace_bridge'],
  ['Renderer received a workspace key instead of a handle', 'workspace_handle'],
  ['The packaged memory client did not start', 'memory_client'],
  ['Installed telemetry resource workload requires the packaged application', 'not_packaged'],
  ['Canonical memory cycles require the real client', 'memory_client'],
  ['Real save failed', 'memory_save'],
  ['Real fetch changed content', 'memory_fetch'],
  ['Real recall omitted the saved memory', 'memory_recall'],
  ['Canonical memory workload did not complete', 'workload_incomplete'],
  ['Installed delivery settlement is only available to the packaged hosting probe', 'delivery_settlement'],
  ['Resource evidence contained private fixture material', 'private_evidence'],
  ['Disposable profile required', 'disposable_profile'],
]

export const STARTUP_FAILURE_CATEGORIES = Object.freeze([
  ...new Set(PAIRS.map(([, category]) => category)),
  'unclassified',
])

function matchLine(line) {
  for (const [sentence, category] of PAIRS) {
    if (line === sentence || line.startsWith(`${sentence}:`) || line.startsWith(`${sentence}.`) || line.startsWith(`${sentence} `)) {
      return category
    }
  }
  if (line.length <= 400) {
    for (const [sentence, category] of PAIRS) {
      const at = line.indexOf(sentence)
      if (at < 0) continue
      const after = line[at + sentence.length]
      if (after === undefined || after === ':' || after === '.' || after === ' ') return category
    }
  }
  return 'unclassified'
}

export function startupFailureCategory(error) {
  if (error == null) return null
  let line = typeof error === 'string' ? error : (typeof error.message === 'string' ? error.message : '')
  line = line.split(/\r?\n/, 1)[0].trim()
  for (let depth = 0; depth < 3 && line.startsWith('Error: '); depth += 1) line = line.slice(7).trim()
  if (!line || line.length > 500) return 'unclassified'
  return matchLine(line)
}
