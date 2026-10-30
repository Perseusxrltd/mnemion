/** One finite Firefox or WebKit journey. No app controls and no second attempt. */
import assert from 'node:assert/strict'
import { readFileSync, writeFileSync, existsSync } from 'node:fs'
import { pathToFileURL } from 'node:url'
import { setTimeout as delay } from 'node:timers/promises'

const inputPath = process.env.MNEMION_BROWSER_JOURNEY_INPUT
if (!inputPath) throw new Error('MNEMION_BROWSER_JOURNEY_INPUT is required')
const input = JSON.parse(readFileSync(inputPath, 'utf8'))
const redact = text => String(text ?? '').split(input.memory.api_key).join('[redacted]')

const CHECKS = [
  'disclosure_acknowledged',
  'manual_review_configured',
  'memory_saved',
  'memory_fetched',
  'lexical_recall',
  'inspected_25_byte_report',
  'approved_exact_body',
  'received_matching_report',
  'spent_budget_preserved',
  'opt_out_persisted',
  'manual_review_persisted',
  'canary_absent_from_origin_storage',
  'canary_absent_from_reviewed_body',
]

function sensor(present) {
  return present ? 'present' : 'unavailable'
}

async function journey() {
  assert.equal(input.engine === 'firefox' || input.engine === 'webkit', true)
  const playwrightPath = process.env.MNEMION_PROBE_PLAYWRIGHT
  if (!playwrightPath) throw new Error('MNEMION_PROBE_PLAYWRIGHT is required')
  const playwright = await import(pathToFileURL(playwrightPath).href)
  const engine = playwright[input.engine]
  if (!engine) throw new Error('Playwright does not expose this engine')
  let context
  let page
  let stage = 'starting'
  const phases = []
  const checks = {}
  const pageErrors = []
  const result = {
    schema_version: 1,
    engine: input.engine,
    attempts: 1,
    phases,
    checks,
    page_errors: pageErrors,
    native_safari_acceptance: false,
    webkit_engine_evidence: input.engine === 'webkit',
    acceptance: input.engine === 'webkit' ? 'webkit_engine_evidence_not_native_safari' : 'firefox_engine',
    resource_acceptance: false,
    production_collection_available: false,
    loopback_tls_exception: 'playwright_ignoreHTTPSErrors',
  }
  const phase = name => {
    stage = name
    phases.push(name)
    console.log(JSON.stringify({ stage: name }))
  }
  const fail = (path, error) => {
    let dom = ''
    return page?.locator('body').ariaSnapshot({ timeout: 3000 }).then(value => { dom = value }).catch(() => {}).then(() => {
      writeFileSync(path, JSON.stringify({
        stage, phases, checks, page_errors: pageErrors, error: redact(error && error.stack || error), dom: redact(dom),
      }, null, 2) + '\n')
    })
  }
  try {
    phase('launching')
    // Browser fetch cannot install the baked route CA. Accept only this disposable certificate.
    context = await engine.launchPersistentContext(input.profile, {
      headless: true,
      ignoreHTTPSErrors: true,
      viewport: { width: 1440, height: 1000 },
      timeout: 30000,
    })
    page = context.pages()[0] || await context.newPage()
    page.setDefaultTimeout(20000)
    page.setDefaultNavigationTimeout(30000)
    page.on('pageerror', error => pageErrors.push(error.name))
    const browser = context.browser()
    result.browser_version = browser?.version() || ''
    assert.match(result.browser_version, /\d/, 'The engine did not report a version')
    await page.goto(input.origin + '/workspace')
    result.user_agent = await page.evaluate(() => navigator.userAgent)
    result.sensors = await page.evaluate(() => ({
      pressure_observer: typeof PressureObserver === 'undefined' ? 'unavailable' : 'present',
      heap_memory: 'memory' in performance ? 'present' : 'unavailable',
      network_information: 'connection' in navigator ? 'present' : 'unavailable',
    }))
    for (const name of ['pressure_observer', 'heap_memory', 'network_information']) {
      assert.equal(sensor(result.sensors[name] === 'present'), result.sensors[name])
      assert.notEqual(result.sensors[name], 0)
    }
    phase('disclosure')
    const dialog = page.getByRole('dialog', { name: 'Your privacy choice', exact: true })
    await dialog.waitFor()
    assert.equal(await dialog.getByRole('checkbox', { name: 'Share anonymous product statistics', exact: true }).isChecked(), true)
    await dialog.getByRole('button', { name: 'Save and continue', exact: true }).click()
    await dialog.waitFor({ state: 'hidden' })
    await page.getByRole('link', { name: 'Privacy & product telemetry', exact: true }).click()
    await page.getByRole('heading', { name: 'Privacy & product telemetry' }).waitFor()
    await page.getByText('Anonymous product telemetry is on.', { exact: true }).waitFor()
    checks.disclosure_acknowledged = true
    phase('manual_review')
    // This controlled checkbox is persisted asynchronously. One user click,
    // followed by the saved-state status below, works across browser engines.
    await page.getByRole('checkbox', { name: 'Pause reports for manual review' }).click()
    await page.getByText('Sending is paused. Inspect a report when local observations are available.', { exact: true }).waitFor()
    checks.manual_review_configured = true
    phase('join')
    await page.getByRole('link', { name: 'Back to workspaces', exact: true }).click()
    await page.getByRole('heading', { name: 'Welcome to Mnemion' }).waitFor()
    const joinChoice = page.getByRole('button', { name: /Join a workspace/ })
    if (await joinChoice.isVisible()) await joinChoice.click()
    await page.getByRole('group', { name: 'Choose how to join', exact: true }).waitFor()
    await page.getByRole('button', { name: 'Workspace key', exact: true }).click()
    const form = page.getByRole('form', { name: 'Connect a workspace' })
    await form.getByLabel('Workspace address', { exact: true }).fill(input.memory.base_url)
    await form.getByLabel('Workspace key', { exact: true }).fill(input.memory.api_key)
    await form.getByRole('button', { name: 'Open workspace', exact: true }).click()
    await page.getByRole('link', { name: 'Save memory', exact: true }).waitFor()
    phase('save')
    await page.getByRole('link', { name: 'Save memory', exact: true }).click()
    await page.getByLabel('Subject', { exact: true }).fill(input.canary)
    await page.getByLabel('Memory type', { exact: true }).selectOption('procedure')
    const content = (`${input.query} postgres backup billing procedure. `).repeat(20) + input.canary
    await page.getByLabel('Memory content', { exact: true }).fill(content)
    await page.getByRole('button', { name: 'Save memory', exact: true }).click()
    await page.waitForURL(/\/workspace\/memory\//)
    const savedMemory = page.url().match(/\/workspace\/memory\/([a-f0-9-]{36})(?:[/?#]|$)/)?.[1]
    assert.ok(savedMemory, 'The saved memory did not expose its canonical detail URL')
    checks.memory_saved = true
    phase('fetch')
    await page.getByText(input.query, { exact: false }).first().waitFor()
    await page.getByText(input.canary, { exact: false }).first().waitFor()
    checks.memory_fetched = true
    phase('recall')
    await page.getByRole('link', { name: 'Search & context', exact: true }).click()
    await page.getByLabel('Search method', { exact: true }).selectOption('lexical')
    await page.getByLabel('Search shared memory', { exact: true }).fill(input.query)
    await page.getByRole('button', { name: 'Search', exact: true }).click()
    const recalledMemory = page.locator('article').filter({
      has: page.locator(`a[href$="/workspace/memory/${savedMemory}"]`),
    })
    await recalledMemory.getByText('Why this result?', { exact: true }).click()
    await recalledMemory.getByText(/Exact-text rank \d+/).waitFor()
    checks.lexical_recall = true
    await page.waitForFunction(() => {
      const raw = localStorage.getItem('mnemion.product-telemetry.pending.v1')
      if (!raw) return false
      const pending = JSON.parse(raw)
      return Array.isArray(pending.entries) && pending.entries.length > 0
    })
    phase('inspect')
    await page.getByRole('link', { name: 'Privacy & product telemetry', exact: true }).click()
    await page.getByRole('button', { name: 'Refresh privacy status', exact: true }).click()
    await page.getByRole('button', { name: 'Inspect next report', exact: true }).click()
    const bytes = page.getByLabel('Exact report bytes', { exact: true })
    await bytes.waitFor()
    const shown = (await bytes.textContent())?.trim() ?? ''
    const body = Buffer.from(shown, 'base64')
    assert.equal(body.length, 25)
    assert.equal(body.toString('base64'), shown)
    assert.equal(body.includes(Buffer.from(input.canary)), false)
    result.approved_body_base64 = shown
    result.approved_body_hex = body.toString('hex')
    checks.inspected_25_byte_report = true
    checks.canary_absent_from_reviewed_body = true
    phase('approve')
    await page.getByRole('button', { name: 'Approve this report', exact: true }).click()
    await page.getByText('This report is approved for one eligible attempt. Later reports remain paused.', { exact: true }).waitFor()
    checks.approved_exact_body = true
    phase('receive')
    const deadline = Date.now() + 20000
    let received = null
    while (Date.now() < deadline && !received) {
      if (existsSync(input.received_flag)) {
        received = JSON.parse(readFileSync(input.received_flag, 'utf8'))
        break
      }
      await delay(200)
    }
    assert.equal(received?.body_hex, result.approved_body_hex)
    checks.received_matching_report = true
    phase('opt_out')
    await page.getByRole('button', { name: 'Disable product telemetry', exact: true }).click()
    await page.getByText('Product telemetry is off by your choice.', { exact: true }).waitFor()
    phase('reload')
    await page.reload()
    await page.getByText('Product telemetry is off by your choice.', { exact: true }).waitFor()
    assert.equal(await page.getByRole('checkbox', { name: 'Share anonymous product statistics' }).isChecked(), false)
    assert.equal(await page.getByRole('checkbox', { name: 'Pause reports for manual review' }).isChecked(), true)
    const stored = await page.evaluate(() => ({
      choice: localStorage.getItem('mnemion.product-telemetry.choice.v1'),
      budget: localStorage.getItem('mnemion.product-telemetry.budget.v1'),
      queue: localStorage.getItem('mnemion.product-telemetry.pending.v1'),
      joined: Object.values(localStorage).join('\n'),
    }))
    const choice = JSON.parse(stored.choice)
    const budget = JSON.parse(stored.budget)
    assert.equal(choice.enabled, false)
    assert.equal(budget.review.mode, 'review')
    assert.equal(budget.attempts.length, 1)
    assert.equal(stored.joined.includes(input.canary), false)
    result.budget_attempts_after_reload = budget.attempts.length
    checks.spent_budget_preserved = true
    checks.opt_out_persisted = true
    checks.manual_review_persisted = true
    checks.canary_absent_from_origin_storage = true
    phase('closed')
    assert.deepEqual(pageErrors, [])
    for (const name of CHECKS) assert.equal(checks[name], true, name)
  } catch (error) {
    result.original_failure = redact(error && error.message || error)
    await fail(input.failure, error)
    throw error
  } finally {
    if (context) await context.close().catch(() => {})
    writeFileSync(input.result, JSON.stringify(result, null, 2) + '\n')
  }
}

await journey().catch(error => {
  console.error(redact(error && error.stack || error))
  process.exitCode = 1
})
