/** Actual source-app review controls. Uses only the launcher's disposable fixtures. */
import assert from 'node:assert/strict'
import { writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { pathToFileURL } from 'node:url'
import { setTimeout as delay } from 'node:timers/promises'

export async function reviewController({ root, input, application, marker }) {
  assert(input.review_journey === true && input.attribution === false)
  assert(root.includes('mnemion-owned-renderer-'))
  const { _electron } = await import(pathToFileURL(process.env.MNEMION_PROBE_PLAYWRIGHT).href)
  const environment = { ...process.env }
  delete environment.ELECTRON_RUN_AS_NODE
  let electron, page, launches = 0, cycles = 0, stage = 'starting'
  const checks = {}, pageErrors = []
  const retain = async name => {
    stage = name
    writeFileSync(join(process.env.MNEMION_PROBE_ARTIFACTS, 'review-' + name + '.txt'),
      await page.locator('body').ariaSnapshot(), { flag: 'wx' })
    console.log(JSON.stringify({ stage: name }))
  }
  const launch = async () => {
    assert(launches < 2, 'Only the initial app and one restart belong to this journey')
    electron = await _electron.launch({ executablePath: process.env.MNEMION_PROBE_ELECTRON,
      args: [application], cwd: application, env: environment, timeout: 30000 })
    launches++
    marker({ phase: 'review-app-' + launches, pid: electron.process().pid })
    const deadline = Date.now() + 30000
    page = undefined
    while (!page && Date.now() < deadline) {
      page = electron.windows().find(value => value.url().startsWith('http://127.0.0.1:' + process.env.VITE_DEV_PORT + '/'))
      if (!page) await delay(25)
    }
    assert(page, 'The source app did not load its owned frontend')
    page.setDefaultTimeout(20000)
    page.on('pageerror', error => pageErrors.push(error.name))
    await page.getByRole('heading', { name: 'Welcome to Mnemion' }).waitFor()
    await electron.evaluate(({ webContents }) => {
      for (const contents of webContents.getAllWebContents()) if (contents.isDevToolsOpened()) contents.closeDevTools()
    })
  }
  const control = (action, value = {}) => page.evaluate(
    ({ action, value }) => window.mnemion.productTelemetry('telemetry.' + action, value), { action, value })
  const review = () => control('review_status')
  const request = value => ({ expected_revision: value.status.revision,
    expected_generation: value.status.store_generation, expected_review_token: value.review.token })
  const privacy = async () => {
    await page.getByRole('link', { name: 'Privacy & product telemetry', exact: true }).click()
    await page.getByRole('heading', { name: 'Privacy & product telemetry' }).waitFor()
    await page.getByRole('button', { name: 'Disable product telemetry', exact: true }).waitFor()
  }
  const settle = () => electron.evaluate(async () => globalThis.__mnemionOwnedProbe.settle())
  const refresh = async () => {
    await page.getByRole('button', { name: 'Refresh privacy status', exact: true }).click()
    await page.waitForFunction(() => [...document.querySelectorAll('.ws-privacy button')]
      .some(value => value.textContent.trim() === 'Disable product telemetry' && !value.disabled))
  }
  const memoryCycle = async () => {
    await page.evaluate(async space => {
      const probe = window.__mnemionReviewMemory
      const query = 'reviewprobe' + probe.cycles
      const content = (query + ' postgres backup billing procedure. ').repeat(20)
      const saved = await probe.client.save(space, { content, subject: 'PRIVATE_RENDERER_MEMORY_CANARY', kind: 'procedure' })
      if (!saved.lexical_ready || !saved.memory_id) throw new Error('The real save did not complete')
      const fetched = await probe.client.fetch(saved.memory_id)
      if (fetched.content !== content) throw new Error('The real fetch changed content')
      const recalled = await probe.client.search({ query, space_ids: [space], mode: 'lexical', limit: 5 })
      if (!recalled.hits.some(hit => hit.memory_id === saved.memory_id)) throw new Error('The real recall missed its saved memory')
      probe.cycles++
    }, input.memory.space_id)
    cycles++
    await settle()
  }
  const inspect = async () => {
    await refresh()
    await page.getByRole('button', { name: 'Inspect next report', exact: true }).click()
    const bytes = page.getByLabel('Exact report bytes', { exact: true })
    await bytes.waitFor()
    const shown = await bytes.textContent()
    const held = await review()
    assert.equal(held.review.outcome, 'held')
    assert.equal(held.packet, null, 'A status read must not disclose the staged body')
    assert.equal(held.status.delivery_budget.attempts_in_rolling_week, 0)
    assert.equal(Buffer.from(shown, 'base64').length, 4)
    return { shown, held }
  }
  try {
    await launch()
    await retain('onboarding')
    const initial = await control('status')
    assert.equal(initial.storage, 'new')
    assert.equal(initial.user_enabled, true)
    assert.equal(initial.effective_enabled, false)
    assert.equal(initial.reason, 'disclosure_required')
    assert.equal(initial.disclosure_version, 0)
    checks.disclosure_required = true
    const setup = page.getByRole('dialog', { name: 'Your privacy choice', exact: true })
    await setup.waitFor()
    assert.equal(await setup.getByRole('checkbox', { name: 'Share anonymous product statistics', exact: true }).isChecked(), true)
    await setup.getByRole('button', { name: 'Not now', exact: true }).click()
    await setup.waitFor({ state: 'hidden' })
    const deferred = await control('status')
    assert.equal(deferred.storage, 'new')
    assert.equal(deferred.disclosure_version, 0)
    assert.equal(deferred.effective_enabled, false)
    assert.equal(deferred.pending_records, 0)
    checks.setup_disclosure_deferred_without_permission = true
    const bridge = await page.evaluate(() => ({
      available: typeof window.mnemion?.productTelemetry === 'function',
      node_integration: typeof window.require !== 'undefined',
    }))
    assert(bridge.available && !bridge.node_integration)

    await page.getByRole('button', { name: 'Join a workspace' }).click()
    await page.getByLabel('Workspace address', { exact: true }).fill(input.memory.base_url)
    await page.getByLabel('Workspace key', { exact: true }).fill(input.memory.api_key)
    const remember = page.getByRole('checkbox', { name: 'Remember this workspace on this device' })
    if (await remember.isEnabled()) await remember.uncheck()
    await page.getByRole('form', { name: 'Connect a workspace' }).getByRole('button', { name: 'Open workspace', exact: true }).click()
    await page.getByRole('heading', { name: 'Welcome to Mnemion' }).waitFor({ state: 'hidden' })
    await page.evaluate(async entry => {
      const session = await window.mnemion.workspaceResume()
      if (!session?.sessionToken || session.remembered || !/^mnm_session_[A-Za-z0-9_-]{43}$/.test(session.sessionToken)) {
        throw new Error('The renderer must have only a session handle')
      }
      const { MnemionClient, measuredStudioClient, nativeFetch } = await import(entry)
      window.__mnemionReviewMemory = { cycles: 0, client: measuredStudioClient(new MnemionClient({
        baseUrl: session.endpoint, apiKey: session.sessionToken, retries: 0, fetch: nativeFetch,
      })) }
    }, input.probe_entry)
    await privacy()
    await retain('before-permission')
    await page.getByRole('checkbox', { name: 'Pause reports for manual review' }).click()
    await page.getByText('Sending is paused. Inspect a report when local observations are available.', { exact: true }).waitFor()
    await page.getByText('Telemetry connection settings', { exact: true }).click()
    await page.getByRole('combobox', { name: 'Connection for sending statistics', exact: true }).selectOption('unmetered')
    await page.waitForFunction(() => {
      const choice = document.getElementById('telemetry-connection-mode')
      return choice?.value === 'unmetered' && !choice.disabled
    })
    const beforePermission = await review()
    assert.equal(beforePermission.status.effective_enabled, false)
    assert.equal(beforePermission.status.disclosure_version, 0)
    assert.equal(beforePermission.status.pending_records, 0)
    assert.equal(beforePermission.status.connection_mode, 'unmetered')
    assert.equal(beforePermission.review.mode, 'review')
    checks.manual_choice_before_permission = true
    await page.getByRole('button', { name: 'Keep product telemetry on', exact: true }).click()
    await page.getByText('Anonymous product telemetry is on.', { exact: true }).waitFor()
    const enabled = await review()
    assert.equal(enabled.status.effective_enabled, true)
    assert.equal(enabled.status.disclosure_version, enabled.status.required_disclosure_version)
    assert.equal(enabled.review.mode, 'review')
    checks.app_disclosure_acknowledged = true

    await memoryCycle()
    const first = await inspect()
    const repeated = await control('inspect_report', request(first.held))
    assert.equal(repeated.packet.body_base64, first.shown)
    assert.equal(repeated.review.expires_ms, first.held.review.expires_ms)
    assert.equal(repeated.review.token, first.held.review.token)
    checks.exact_review_preserved = true
    await retain('first-report-held')
    await control('configure', { enabled: false, expected_revision: repeated.status.revision,
      expected_generation: repeated.status.store_generation, disclosure_version: 0 })
    await assert.rejects(control('approve_report', request(repeated)), /privacy choice changed|report changed/i)
    await page.evaluate(() => window.dispatchEvent(new Event('focus')))
    await page.getByText('Product telemetry is off by your choice.', { exact: true }).waitFor()
    assert.equal(await page.getByLabel('Exact report bytes', { exact: true }).count(), 0)
    const disabled = await review()
    assert.equal(disabled.status.pending_records, 0)
    assert.equal(disabled.status.delivery_budget.attempts_in_rolling_week, 0)
    assert.equal(disabled.review.report_available, false)
    checks.native_optout_invalidates_review = true
    await retain('native-optout')

    await page.getByRole('checkbox', { name: 'Share anonymous product statistics' }).click()
    await page.getByText('Anonymous product telemetry is on.', { exact: true }).waitFor()
    const reenabling = await review()
    assert.equal(reenabling.status.pending_records, 0)
    assert.equal(reenabling.review.report_available, false)
    assert.equal(reenabling.review.mode, 'review')
    checks.reenable_starts_empty = true
    await memoryCycle()
    await inspect()
    await page.getByRole('button', { name: 'Discard report', exact: true }).click()
    await page.getByText('The report was discarded. Reports remain paused.', { exact: true }).waitFor()
    const discarded = await review()
    assert.equal(discarded.review.outcome, 'discarded')
    assert.equal(discarded.review.report_available, false)
    assert.equal(discarded.status.delivery_budget.attempts_in_rolling_week, 0)
    checks.discard_does_not_spend = true
    await retain('discarded')

    await memoryCycle()
    const approved = await inspect()
    const approvedBodyHex = Buffer.from(approved.shown, 'base64').toString('hex')
    await page.getByRole('button', { name: 'Approve this report', exact: true }).click()
    await page.getByText('This report is approved for one eligible attempt. Later reports remain paused.', { exact: true }).waitFor()
    await settle()
    const consumed = await review()
    assert.equal(consumed.review.outcome, 'consumed')
    assert.equal(consumed.status.delivery_budget.attempts_in_rolling_week, 1)
    checks.approved_attempt_uses_inspected_body = true // Parent also compares actual TLS body.
    await retain('approved')
    await page.getByRole('button', { name: 'Disable product telemetry', exact: true }).click()
    await page.getByText('Product telemetry is off by your choice.', { exact: true }).waitFor()
    await settle()
    const firstCounts = await electron.evaluate(() => ({ ...globalThis.__mnemionOwnedProbe.counts }))
    await electron.close()
    electron = undefined
    await launch()
    await privacy()
    const restored = await review()
    assert.equal(restored.status.user_enabled, false)
    assert.equal(restored.status.effective_enabled, false)
    assert.equal(restored.status.pending_records, 0)
    assert.equal(restored.status.delivery_budget.attempts_in_rolling_week, 1)
    assert.equal(restored.review.mode, 'review')
    assert.equal(restored.review.report_available, false)
    assert.equal(restored.packet, null)
    assert.equal(await page.getByRole('checkbox', { name: 'Pause reports for manual review' }).isChecked(), true)
    assert.equal(await page.getByRole('checkbox', { name: 'Share anonymous product statistics' }).isChecked(), false)
    checks.optout_and_review_survive_restart = true
    await retain('restarted')
    const secondCounts = await electron.evaluate(() => ({ ...globalThis.__mnemionOwnedProbe.counts }))
    assert.equal(secondCounts.accepted_writes, 0)
    assert.equal(secondCounts.reserved_attempts, 0)
    assert.deepEqual(pageErrors, [])
    writeFileSync(process.env.MNEMION_COST_RESULT, JSON.stringify({
      schema_version: 1, variant: 'review', condition: 'review', replicate: 1,
      review_checks: checks, app_launches: launches, memory_cycles: cycles,
      memory_results_verified: cycles === 3, memory_api_operations: cycles * 3,
      approved_body_hex: approvedBodyHex, bridge, ...firstCounts, restarted_counts: secondCounts,
      page_errors: pageErrors, runtime: await electron.evaluate(() => ({
        electron: process.versions.electron, node: process.versions.node,
        platform: process.platform, arch: process.arch, packaged: false,
      })),
      model_calls: 0, production_collection_available: false, resource_acceptance: false,
      qualification: 'Compiled Linux source app, real copied-source CLI over private stdin, actual sandboxed IPC and loopback TLS. Three synthetic memory cycles and one restart. No installed-platform, provider privacy, whole-wire or resource acceptance.',
    }, null, 2) + '\n', { flag: 'wx' })
  } catch (error) {
    const failure = { stage, checks, app_launches: launches, memory_cycles: cycles, page_errors: pageErrors }
    try { failure.dom = await page?.locator('body').ariaSnapshot({ timeout: 3000 }) } catch { /* Keep the original error. */ }
    writeFileSync(join(process.env.MNEMION_PROBE_ARTIFACTS, 'review-failure.json'), JSON.stringify(failure, null, 2) + '\n', { flag: 'wx' })
    throw error
  } finally {
    if (electron) await electron.close()
    marker({ phase: 'review-closed', pid: 0 })
  }
}
