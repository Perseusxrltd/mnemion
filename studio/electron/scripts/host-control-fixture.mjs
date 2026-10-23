/** Private loopback peer. Its source Python process is never a product dependency. */
import { spawn } from 'node:child_process'
import { randomBytes } from 'node:crypto'
import { createInterface } from 'node:readline'

export function hostControlFixture({ python, root, cwd }) {
  if (!python) throw new Error('The native host-client gate requires the pinned fixture interpreter')
  const child = spawn(python, ['-m', 'deploy.native_host_control_fixture', '--root', root], {
    cwd, stdio: ['pipe', 'pipe', 'pipe'], windowsHide: true,
  })
  let closed = false, pending = null
  const emergencyStop = () => { if (child.exitCode === null && child.signalCode === null) child.kill() }
  process.once('exit', emergencyStop)
  const lines = createInterface({ input: child.stdout })
  const fail = () => {
    closed = true
    if (pending) { clearTimeout(pending.timer); pending.reject(new Error('The disposable SSH peer could not complete enrollment')); pending = null }
  }
  child.on('error', fail)
  child.on('close', () => { process.off('exit', emergencyStop); fail() })
  child.stdin.on('error', fail)
  child.stderr.resume()
  lines.on('line', raw => {
    if (!pending || raw.length > 4096) { child.kill(); fail(); return }
    try {
      const result = JSON.parse(raw)
      if (result.id !== pending.id || !result.connection || result.connection.hostname !== '127.0.0.1') throw new Error()
      clearTimeout(pending.timer)
      pending.resolve(result.connection); pending = null
    } catch { child.kill(); fail() }
  })
  return {
    enroll(operator) {
      if (closed || pending || child.exitCode !== null || child.signalCode !== null) return Promise.reject(new Error('The disposable SSH peer is unavailable'))
      return new Promise((resolve, reject) => {
        const id = randomBytes(16).toString('hex')
        const timer = setTimeout(() => { child.kill(); fail() }, 15000)
        pending = { id, timer, resolve, reject }
        child.stdin.write(JSON.stringify({ id, operator }) + '\n')
      })
    },
    async close() {
      if (pending) fail()
      if (child.exitCode === null && child.signalCode === null) child.stdin.end('{"action":"close"}\n')
      const end = Date.now() + 5000
      while (child.exitCode === null && child.signalCode === null && Date.now() < end) await new Promise(resolve => setTimeout(resolve, 50))
      if (child.exitCode === null && child.signalCode === null) child.kill()
      lines.close()
    },
  }
}
