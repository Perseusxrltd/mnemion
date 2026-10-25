import { spawn } from 'node:child_process'

async function bounded(promise, milliseconds, message) {
  let timer
  try {
    return await Promise.race([promise, new Promise((_, reject) => {
      timer = setTimeout(() => reject(new Error(message)), milliseconds)
    })])
  } finally { clearTimeout(timer) }
}

/** Own disposable Python helpers until their pipes close, before removing SQLite fixtures. */
export class TelemetryFixtureChildren {
  children = new Map()
  constructor(python, environment) { this.python = python; this.environment = environment }

  start(arguments_) {
    const child = spawn(this.python, arguments_, {
      env: this.environment, stdio: ['pipe', 'pipe', 'pipe'], timeout: 20000,
    })
    const state = { closed: false }
    // Readiness reports startup errors; this listener also prevents an unhandled
    // error if a test fails before it begins waiting for the helper.
    child.on('error', () => {})
    state.finished = new Promise(resolve => child.once('close', code => {
      state.closed = true; resolve(code)
    }))
    this.children.set(child, state)
    return child
  }

  exited(child) {
    return bounded(this.children.get(child).finished, 20000, 'Python fixture did not exit')
  }

  async close() {
    await Promise.all([...this.children].map(async ([child, state]) => {
      if (!state.closed) child.kill('SIGKILL')
      try { await bounded(state.finished, 5000, 'Python fixture cleanup did not finish') }
      finally { child.stdin.destroy(); child.stdout.destroy(); child.stderr.destroy() }
    }))
    this.children.clear()
  }
}

/** Pipes may split a record anywhere; Python emits CRLF on Windows. */
export function waitForTelemetryFixture(child) {
  return new Promise((resolve, reject) => {
    let received = ''
    const finish = error => {
      clearTimeout(timer)
      child.stdout.off('data', data)
      child.off('error', failed)
      child.off('close', closed)
      if (error) reject(error); else resolve()
    }
    const failed = () => finish(new Error('Python fixture failed before readiness'))
    const closed = () => finish(new Error('Python fixture exited before readiness'))
    const data = chunk => {
      received += chunk.toString('utf8')
      if (received.length > 64) return finish(new Error('Python fixture readiness exceeded its bound'))
      const newline = received.indexOf('\n')
      if (newline >= 0) {
        const record = received.slice(0, newline)
        finish(record === 'ready' || record === 'ready\r' ? null : new Error('Unexpected Python fixture readiness'))
      }
    }
    const timer = setTimeout(() => finish(new Error('Python fixture readiness timed out')), 5000)
    child.stdout.on('data', data)
    child.once('error', failed)
    child.once('close', closed)
    if (child.exitCode !== null || child.signalCode !== null) closed()
  })
}
