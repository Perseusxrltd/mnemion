import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import test from 'node:test'
const helperHref = new URL('./resource-case-boundary.mjs', import.meta.url).href

const childSource = `
import { publishResourceCase } from ${JSON.stringify(helperHref)}
const summaries = [
  {
    label: 'r1-unavailable',
    condition: 'unavailable',
    telemetry_attempts: 0,
    telemetry_reserved_bytes: 0,
    telemetry_present: false,
    memory_cycles: 0,
    memory_results_verified: 0,
    memory_api_operations: 0,
    inspected_body_hex: '',
  },
  {
    label: 'r1-opted_out',
    condition: 'opted_out',
    telemetry_attempts: 0,
    telemetry_reserved_bytes: 0,
    telemetry_present: false,
    memory_cycles: 0,
    memory_results_verified: 0,
    memory_api_operations: 0,
    inspected_body_hex: '',
  },
]
for (const summary of summaries) await publishResourceCase(summary)
process.stdout.write('CONTROLLER_DONE\\n')
`

test('controller exits after two prompt acknowledgements while parent stdin stays open', async () => {
  const child = spawn(process.execPath, ['--input-type=module', '-e', childSource], {
    stdio: ['pipe', 'pipe', 'pipe'],
    windowsHide: true,
  })
  const lines = []
  let stdout = ''
  let stderr = ''
  let openAtCompletion = null
  child.stderr.setEncoding('utf8')
  child.stderr.on('data', chunk => { stderr += chunk })
  child.stdout.on('data', chunk => {
    stdout += chunk.toString('utf8')
    let end = stdout.indexOf('\n')
    while (end >= 0) {
      const line = stdout.slice(0, end)
      stdout = stdout.slice(end + 1)
      lines.push(line)
      if (line === 'CONTROLLER_DONE') {
        openAtCompletion = {
          destroyed: child.stdin.destroyed,
          writableEnded: child.stdin.writableEnded,
        }
      }
      if (line.startsWith('RESOURCE_CASE ')) {
        const payload = JSON.parse(line.slice('RESOURCE_CASE '.length))
        child.stdin.write(`RESOURCE_CASE_ACK ${payload.label}\n`)
      }
      end = stdout.indexOf('\n')
    }
  })

  let stillAlive = false
  const result = await new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      stillAlive = true
      child.kill()
    }, 5000)
    child.once('error', error => {
      clearTimeout(timer)
      reject(error)
    })
    child.once('exit', (code, signal) => {
      clearTimeout(timer)
      if (stillAlive) {
        reject(new Error('controller_still_alive'))
        return
      }
      resolve({
        code,
        signal,
        writableEnded: child.stdin.writableEnded,
        stderr,
      })
    })
  })

  assert.equal(result.code, 0, result.stderr)
  assert.equal(result.signal, null)
  assert.deepEqual(
    lines.filter(line => line.startsWith('RESOURCE_CASE ')).map(line => JSON.parse(line.slice('RESOURCE_CASE '.length)).label),
    ['r1-unavailable', 'r1-opted_out'],
  )
  assert.equal(lines.at(-1), 'CONTROLLER_DONE')
  // Completion is observed before this parent ends or destroys stdin.
  // Node then marks the pipe destroyed inside the exit event because the
  // child has gone away; writableEnded stays false because stdin was not ended.
  assert.deepEqual(openAtCompletion, { destroyed: false, writableEnded: false })
  assert.equal(result.writableEnded, false)
})
