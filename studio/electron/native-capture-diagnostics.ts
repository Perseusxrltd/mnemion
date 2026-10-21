/** Bounded diagnostics ONLY for the empty, disposable native-preview fixture.
 * Never use this to publish errors from a real source or conversation capture.
 */
export function isolatedPreviewDiagnostic(line: string, environment: NodeJS.ProcessEnv, privateValues: string[]): string {
  let value = line
  // Redact before truncating: otherwise a cut credential can escape matching.
  const hidden = [...Object.values(environment), ...privateValues]
    .filter((item): item is string => typeof item === 'string' && item.length >= 4)
    .sort((left, right) => right.length - left.length)
  for (const item of hidden) value = value.split(item).join('[private]')
  value = value
    .replace(/\u001b\[[0-?]*[ -/]*[@-~]/g, '')
    .replace(/\b[a-z][a-z0-9+.-]*:\/\/[^\s"'<>]+/gi, '[url]')
    .replace(/\bBearer\s+[^\s"'<>]+/gi, 'Bearer [private]')
    .replace(/\bmnm_[A-Za-z0-9_-]+/g, '[credential]')
    .replace(/(?:[A-Za-z]:[\\/]|\/)[^\s"'<>\r\n]+/g, '[path]')
    .replace(/[A-Za-z0-9_+\/-]{40,}={0,2}/g, '[opaque]')
    .replace(/[\u0000-\u001f\u007f]/g, ' ')
  return value.slice(0, 600)
}
