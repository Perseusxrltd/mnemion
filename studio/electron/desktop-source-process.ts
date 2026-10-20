/** Bounded native process protocol. Keys stay off argv, disk, logs and env. */
import { spawn } from 'node:child_process'
import type { SourceCall } from './desktop-sources.js'

const messages: Record<string, string> = {
  source_identity_mismatch: 'Use this connection’s dedicated application key in the expected workspace.',
  source_connection_unavailable: 'Enable this connection and check its application.',
  source_settings_changed: 'Source settings changed. Refresh before retrying.',
  source_memory_limit: 'The scan reached its RAM allowance. Increase the source allowance or narrow the source folder, then retry.',
  private_location: 'Source settings must stay private to this OS account.',
  unsafe_location: 'Choose an ordinary source folder, separate from private app settings.',
  damaged_state: 'Saved source settings could not be read. The existing file has been retained.',
}

export function sourceProcess(options: { executable: string; root: string; privateRoots: string[];
  environment: NodeJS.ProcessEnv; prefix?: string[] }): SourceCall {
  return (request, signal, resources) => new Promise((resolve, reject) => {
    let input: string
    try { input = JSON.stringify(request) } catch { reject(new Error('Invalid source settings.')); return }
    if (Buffer.byteLength(input) > 256 * 1024 || signal?.aborted) { reject(new Error('The source request was cancelled or is too large.')); return }
    const child = spawn(options.executable, [...(options.prefix ?? []), 'desktop-source', '--root', options.root,
      ...options.privateRoots.flatMap(path => ['--private-root', path])],
    { stdio: ['pipe', 'pipe', 'pipe'], windowsHide: true, env: options.environment })
    let buffer = '', result: Record<string, unknown> | undefined, failure: Error | undefined
    const fail = (message: string) => { failure ??= new Error(message); child.kill() }
    const abort = () => fail('The source operation was cancelled. Its next scan will reconcile saved progress.')
    signal?.addEventListener('abort', abort, { once: true })
    const timer = setTimeout(() => fail('The source operation timed out. Check its saved status before retrying.'), request.operation === 'scan' ? 600_000 : 45_000)
    child.stdin.on('error', () => fail('The source helper could not receive its private request.'))
    child.stdin.end(input)
    child.stderr.resume()
    child.stdout.setEncoding('utf8')
    child.stdout.on('data', (chunk: string) => {
      if (failure) return
      buffer += chunk
      if (Buffer.byteLength(buffer) > 256 * 1024) { fail('The source helper returned an oversized response.'); return }
      let end: number
      while ((end = buffer.indexOf('\n')) >= 0) {
        const line = buffer.slice(0, end); buffer = buffer.slice(end + 1)
        try {
          const value = JSON.parse(line)
          if (value.event === 'resources' && !result && Number.isSafeInteger(value.rss_bytes) && value.rss_bytes >= 0 && value.rss_bytes <= 16 * 1024 ** 3) resources?.(value.rss_bytes)
          else if (value.event === 'result' && !result) result = value
          else throw new Error()
        } catch { fail('The source helper returned an invalid response.'); return }
      }
    })
    child.on('error', () => { failure ??= new Error('The source helper could not start. Repair or update the app.'); })
    child.on('close', code => {
      clearTimeout(timer); signal?.removeEventListener('abort', abort); resources?.(0)
      if (failure) { reject(failure); return }
      if (buffer.trim() || !result || code !== 0 || result.ok !== true || !result.result || typeof result.result !== 'object' || Array.isArray(result.result)) {
        reject(new Error(messages[String(result?.error)] ?? 'The source could not be read or reached. Check its folder, dedicated key, workspace and network.')); return
      }
      resolve(result.result as Record<string, unknown>)
    })
    if (signal?.aborted) abort()
  })
}
