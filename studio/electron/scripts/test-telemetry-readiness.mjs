import test from 'node:test'
import assert from 'node:assert/strict'
import vm from 'node:vm'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { telemetryReadinessError, telemetrySnapshotDecision } from '../telemetry-readiness.mjs'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const probe = readFileSync(resolve(root, 'native-telemetry-delivery-probe.ts'), 'utf8')
const build = readFileSync(resolve(root, 'scripts/build.mjs'), 'utf8')
const leaked = 'C:\\Users\\secret\\report.json'
const manual = {
  status: { effective_enabled: true, pending_records: 2, connection_mode: 'unmetered', user_enabled: true,
    delivery_budget: { attempts_in_rolling_week: 0 }, endpoint: leaked, credential: leaked },
  review: { mode: 'review', outcome: 'paused', report_available: false, token: leaked, detail: leaked },
  packet: null,
  message: 'paused',
  path: leaked,
}

function isolated(fn) {
  return vm.runInNewContext(`(${fn.toString()})`, Object.create(null))
}

function observationsReady(snapshot) {
  if (snapshot.review.mode !== 'review') return 'review_not_paused'
  if (snapshot.status?.effective_enabled !== true) return 'collection_pending'
  if (!(snapshot.status?.pending_records > 0)) return 'no_observations'
  return true
}

test('a null control or review snapshot is not a pass and drops arbitrary text', () => {
  const decide = isolated(telemetrySnapshotDecision)
  const fail = isolated(telemetryReadinessError)
  let called = false
  const missing = decide(null, () => { called = true; return true })
  assert.equal(called, false)
  assert.equal(missing.ready, false)
  assert.equal(missing.gate, 'control_unavailable')
  const unread = decide({ status: { pending_records: 4, connection_mode: 'unmetered' }, review: null, message: leaked, error: leaked }, () => { called = true; return true })
  assert.equal(called, false)
  assert.equal(unread.ready, false)
  assert.equal(unread.gate, 'review_unavailable')
  const unavailable = decide({ review: null, message: 'unavailable', status: { endpoint: leaked } }, () => true)
  assert.equal(unavailable.gate, 'unavailable')
  for (const text of [fail('memory_observations', unread.gate), fail('before_permission', leaked), fail('../' + leaked, 'no_observations')]) {
    assert.equal(text.includes('secret'), false)
    assert.equal(text.includes('Users'), false)
    assert.equal(text.includes('report.json'), false)
    assert.match(text, /^Installed telemetry was not ready: phase=[a-z_]+ gate=[a-z_]+$/)
  }
  assert.equal(fail('memory_observations', 'no_observations'), 'Installed telemetry was not ready: phase=memory_observations gate=no_observations')
})

test('pending observations are not a held report', () => {
  const decide = isolated(telemetrySnapshotDecision)
  const waiting = decide(manual, observationsReady)
  assert.equal(waiting.ready, true)
  assert.equal(waiting.snapshot.review.report_available, false)
  const empty = decide({ ...manual, status: { ...manual.status, pending_records: 0 } }, observationsReady)
  assert.equal(empty.ready, false)
  assert.equal(empty.gate, 'no_observations')
  const alreadyHeld = decide({
    ...manual,
    status: { ...manual.status, pending_records: 0 },
    review: { ...manual.review, outcome: 'held', report_available: true },
  }, observationsReady)
  assert.equal(alreadyHeld.ready, false)
  assert.equal(alreadyHeld.gate, 'no_observations')
  const held = decide({
    ...manual,
    review: { ...manual.review, outcome: 'held', report_available: true },
    packet: null,
  }, snapshot => snapshot.review.outcome === 'held' && snapshot.review.report_available === true ? true : 'report_not_held')
  assert.equal(held.ready, true)
})

test('the installed journey inspects only after pending observations', () => {
  const cycleStart = probe.indexOf('async function memoryCycle()')
  const stageStart = probe.indexOf('async function stageHeld()')
  assert.ok(cycleStart > 0 && stageStart > cycleStart)
  const cycle = probe.slice(cycleStart, stageStart)
  assert.equal(cycle.includes('report_available'), false)
  assert.equal(cycle.includes('Inspect next report'), false)
  const stage = probe.slice(stageStart, probe.indexOf('const initial = await control', stageStart))
  const pending = stage.indexOf("return 'no_observations'")
  const refresh = stage.indexOf("click('Refresh privacy status')")
  const inspect = stage.indexOf("click('Inspect next report'")
  assert.ok(pending > 0 && pending < refresh && refresh < inspect)
  assert.equal(probe.includes('The packaged app recorded no real report after the memory actions'), false)
  assert.equal(probe.includes('await review()'), false)
  assert.equal(probe.includes('review().review'), false)
  assert.equal(probe.includes('.review.mode'), true)
  assert.match(probe, /reviewStatus = \(\) =>/)
  assert.match(build, /telemetry-readiness\.mjs/)
})
