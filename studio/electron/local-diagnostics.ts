/** Structured diagnostics only: never exception text, paths, arguments or stderr. */
import type { LocalDiagnostic, LocalProcessExit } from '../shared/local-workspace.js'

const signals = new Set([
  'SIGABRT', 'SIGALRM', 'SIGBREAK', 'SIGBUS', 'SIGCHLD', 'SIGCLD', 'SIGCONT', 'SIGEMT',
  'SIGFPE', 'SIGHUP', 'SIGILL', 'SIGINFO', 'SIGINT', 'SIGIO', 'SIGIOT', 'SIGKILL',
  'SIGLOST', 'SIGPIPE', 'SIGPOLL', 'SIGPROF', 'SIGPWR', 'SIGQUIT', 'SIGSEGV',
  'SIGSTKFLT', 'SIGSTOP', 'SIGSYS', 'SIGTERM', 'SIGTRAP', 'SIGTSTP', 'SIGTTIN',
  'SIGTTOU', 'SIGUNUSED', 'SIGURG', 'SIGUSR1', 'SIGUSR2', 'SIGVTALRM', 'SIGWINCH',
  'SIGXCPU', 'SIGXFSZ',
])

function validExit(value: LocalProcessExit): boolean {
  return !!value && typeof value === 'object' && !Array.isArray(value) &&
    Object.keys(value).sort().join(',') === 'code,signal' &&
    (value.code === null || (Number.isInteger(value.code) && value.code >= -2147483648 && value.code <= 4294967295)) &&
    (value.signal === null || (typeof value.signal === 'string' && signals.has(value.signal))) &&
    !(value.code !== null && value.signal !== null)
}

export function localDiagnostic(input: unknown): LocalDiagnostic | undefined {
  if (input === undefined) return undefined
  if (!input || typeof input !== 'object' || Array.isArray(input)) throw new Error('Invalid setup diagnostic')
  const value = input as LocalDiagnostic
  if (Object.keys(value).some(key => !['category', 'locations', 'errno', 'winerror', 'sqlstate', 'database_reason', 'exit'].includes(key)) ||
      !['unexpected', 'memory', 'dependency', 'operating_system', 'timeout', 'database', 'process_exit'].includes(value.category) ||
      [value.errno, value.winerror].some(code => code !== undefined && (!Number.isInteger(code) || code < 0 || code > 4294967295)) ||
      (value.sqlstate !== undefined && (typeof value.sqlstate !== 'string' || !/^[A-Z0-9]{5}$/.test(value.sqlstate))) ||
      (value.database_reason !== undefined && (value.category !== 'database' ||
        !['authentication', 'timeout', 'connection_refused', 'connection_closed', 'tls', 'other'].includes(value.database_reason))) ||
      (value.exit !== undefined && !validExit(value.exit)) || (value.category === 'process_exit' && !value.exit) ||
      !Array.isArray(value.locations) || value.locations.length > 8 || value.locations.some(location =>
        !location || typeof location !== 'object' || Array.isArray(location) || Object.keys(location).sort().join(',') !== 'function,line,module' ||
        typeof location.module !== 'string' || !/^mnemion(?:\.[a-z_][a-z0-9_]{0,63}){1,4}$/.test(location.module) ||
        typeof location.function !== 'string' || !/^[A-Za-z_][A-Za-z0-9_]{0,63}$/.test(location.function) ||
        !Number.isInteger(location.line) || location.line < 1 || location.line > 1000000)) throw new Error('Invalid setup diagnostic')
  return structuredClone(value)
}

export function processExitDiagnostic(code: number | null, signal: NodeJS.Signals | null,
  previous?: LocalDiagnostic): LocalDiagnostic {
  // A future OS termination value must not throw from the child-close handler.
  // Unknown metadata stays null; arbitrary signal text is never forwarded.
  const knownSignal = signal && signals.has(signal) ? signal : null
  const knownCode = !knownSignal && Number.isInteger(code) && code! >= -2147483648 && code! <= 4294967295 ? code : null
  return localDiagnostic({ ...(previous ?? { category: 'process_exit', locations: [] }), exit: { code: knownCode, signal: knownSignal } })!
}
