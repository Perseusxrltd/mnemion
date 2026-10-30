/** Case-boundary handshake for the installed resource controller.

The parent keeps the controller stdin pipe open until after process.wait.
resume() references that socket, so every settlement must pause and unref it
or the controller stays alive after its final acknowledgement. The listener
is attached before the boundary is written; a prompt acknowledgement would
otherwise arrive while stdin is flowing with no listener.
*/

const ACK_TIMEOUT_MS = 60000
const ACK_BYTE_LIMIT = 256

let pending = ''
let active = null

function releaseInput(onData, onEnd, onError) {
  process.stdin.pause()
  process.stdin.off('data', onData)
  process.stdin.off('end', onEnd)
  process.stdin.off('error', onError)
  if (typeof process.stdin.unref === 'function') process.stdin.unref()
}

function armCaseAck(label) {
  if (active) throw new Error('resource_case_ack_failed')
  let settled = false
  let accept = false
  let timer = null
  let resolveAck
  let rejectAck
  const promise = new Promise((resolve, reject) => {
    resolveAck = resolve
    rejectAck = reject
  })
  promise.catch(() => {})

  function finish(settle) {
    if (settled) return
    settled = true
    if (timer !== null) clearTimeout(timer)
    releaseInput(onData, onEnd, onError)
    active = null
    settle()
  }

  function onData(chunk) {
    pending += chunk.toString('utf8')
    if (pending.length > ACK_BYTE_LIMIT) {
      finish(() => rejectAck(new Error('resource_case_ack_malformed')))
      return
    }
    if (!accept) {
      const preexisting = pending.lastIndexOf('\n')
      if (preexisting >= 0) pending = pending.slice(preexisting + 1)
      return
    }
    const end = pending.indexOf('\n')
    if (end < 0) return
    const line = pending.slice(0, end).trim()
    pending = pending.slice(end + 1)
    if (line !== `RESOURCE_CASE_ACK ${label}`) finish(() => rejectAck(new Error('resource_case_ack_mismatch')))
    else finish(() => resolveAck())
  }

  function onEnd() {
    finish(() => rejectAck(new Error('resource_case_ack_eof')))
  }

  function onError() {
    finish(() => rejectAck(new Error('resource_case_ack_failed')))
  }

  const preexisting = pending.lastIndexOf('\n')
  if (preexisting >= 0) pending = pending.slice(preexisting + 1)
  const waiter = {
    get settled() { return settled },
    beginAccept() { accept = true },
    startTimer() {
      if (settled || timer !== null) return
      timer = setTimeout(() => {
        finish(() => rejectAck(new Error('resource_case_ack_timeout')))
      }, ACK_TIMEOUT_MS)
    },
    cancel(error) {
      finish(() => rejectAck(error))
    },
    promise,
  }
  active = waiter
  process.stdin.on('data', onData)
  process.stdin.on('end', onEnd)
  process.stdin.on('error', onError)
  if (typeof process.stdin.ref === 'function') process.stdin.ref()
  process.stdin.resume()
  return waiter
}

export async function publishResourceCase(summary) {
  const line = 'RESOURCE_CASE ' + JSON.stringify({
    label: summary.label,
    condition: summary.condition,
    attempts: summary.telemetry_attempts,
    reserved_bytes: summary.telemetry_reserved_bytes,
    present: summary.telemetry_present,
    memory_cycles: summary.memory_cycles,
    memory_results_verified: summary.memory_results_verified,
    memory_api_operations: summary.memory_api_operations,
    inspected_body_hex: summary.inspected_body_hex,
  })
  if (Buffer.byteLength(line) > 2048) throw new Error('resource_case_malformed')
  const waiter = armCaseAck(summary.label)
  waiter.beginAccept()
  try {
    await new Promise((resolve, reject) => {
      process.stdout.write(line + '\n', error => error ? reject(error) : resolve())
    })
  } catch (error) {
    if (!waiter.settled) waiter.cancel(error)
    throw error
  }
  if (!waiter.settled) waiter.startTimer()
  await waiter.promise
}
