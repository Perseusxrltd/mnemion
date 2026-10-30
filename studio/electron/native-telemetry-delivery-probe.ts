/** Installed review delivery. The packaged bridge, UI and delivery owner stay in place. */
import type { BrowserWindow } from 'electron'
import { app } from 'electron'

const REVIEW_CHECKS = [
  'disclosure_required',
  'setup_disclosure_deferred_without_permission',
  'manual_choice_before_permission',
  'app_disclosure_acknowledged',
  'exact_review_preserved',
  'native_optout_invalidates_review',
  'reenable_starts_empty',
  'discard_does_not_spend',
  'approved_attempt_uses_inspected_body',
  'optout_and_review_survive_restart',
] as const

function loopbackOrigin(value: unknown): string {
  if (typeof value !== 'string' || value.length > 128) throw new Error('Telemetry delivery fixture refused a non-loopback destination')
  let url: URL
  try { url = new URL(value) } catch { throw new Error('Telemetry delivery fixture refused a non-loopback destination') }
  const port = Number(url.port)
  if (url.protocol !== 'http:' || (url.hostname !== '127.0.0.1' && url.hostname !== 'localhost') ||
      url.username || url.password || url.search || url.hash ||
      (url.pathname !== '/' && url.pathname !== '') ||
      !Number.isInteger(port) || port < 1 || port > 65535) {
    throw new Error('Telemetry delivery fixture refused a non-loopback destination')
  }
  return url.origin
}

function deliveryConfig(config: Record<string, unknown>): { endpoint: string; spaceId: string; credential: string } {
  const keys = Object.keys(config).sort().join()
  if (keys !== 'credential,endpoint,phase,spaceId' || config.phase !== 'telemetry-delivery') {
    throw new Error('Invalid telemetry delivery configuration')
  }
  if (typeof config.spaceId !== 'string' || !/^[a-f0-9-]{36}$/.test(config.spaceId) ||
      typeof config.credential !== 'string' || config.credential.length < 16 || config.credential.length > 256 ||
      /\s/.test(config.credential)) throw new Error('Invalid telemetry delivery configuration')
  return { endpoint: loopbackOrigin(config.endpoint), spaceId: config.spaceId, credential: config.credential }
}

export async function verifyInstalledTelemetryDelivery(window: BrowserWindow, config: Record<string, unknown>): Promise<Record<string, unknown>> {
  if (!app.isPackaged) throw new Error('Installed telemetry delivery requires the packaged application')
  const restart = config.phase === 'telemetry-restart'
  const script = restart
    ? (Object.keys(config).join() === 'phase' ? restartJourney() : null)
    : deliveryJourney(deliveryConfig(config))
  if (!script) throw new Error('Invalid telemetry restart configuration')
  const result = await window.webContents.executeJavaScript(script)
  if (!result || typeof result !== 'object' || Array.isArray(result)) throw new Error('Installed telemetry delivery returned no evidence')
  const evidence = result as Record<string, unknown>
  const serialized = JSON.stringify(evidence)
  if (!restart && serialized.includes(String(config.credential))) throw new Error('Telemetry delivery evidence exposed the fixture credential')
  if (serialized.includes('PRIVATE_RENDERER_MEMORY_CANARY')) throw new Error('Telemetry delivery evidence contained sentinel content')
  const runtime = {
    electron: process.versions.electron,
    node: process.versions.node,
    platform: process.platform,
    arch: process.arch,
    packaged: app.isPackaged,
  }
  return { ...evidence, packaged: true, runtime, qualification: 'installed fixture delivery' }
}

function deliveryJourney(config: { endpoint: string; spaceId: string; credential: string }): string {
  return `(async () => {
    const fixture = ${JSON.stringify(config)};
    const bridge = window.mnemion;
    const checks = {};
    const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
    async function until(check, message, timeout = 30000) {
      const deadline = Date.now() + timeout;
      do { const value = await check(); if (value) return value; await pause(100); } while (Date.now() < deadline);
      throw new Error(message);
    }
    const button = text => [...document.querySelectorAll('button')].find(node =>
      node.textContent.trim() === text && !node.disabled && node.getClientRects().length);
    async function click(text) {
      const node = await until(() => button(text), 'Missing installed privacy control: ' + text);
      node.click();
    }
    const checkbox = text => [...document.querySelectorAll('input[type="checkbox"]')].find(node =>
      node.closest('label')?.textContent.includes(text));
    const control = (action, value = {}) => bridge.productTelemetry('telemetry.' + action, value);
    const review = () => control('review_status');
    const request = value => ({ expected_revision: value.status.revision,
      expected_generation: value.status.store_generation, expected_review_token: value.review.token });
    function setValue(field, value) {
      const prototype = field instanceof HTMLTextAreaElement ? HTMLTextAreaElement : field instanceof HTMLSelectElement ? HTMLSelectElement : HTMLInputElement;
      Object.getOwnPropertyDescriptor(prototype.prototype, 'value').set.call(field, value);
      field.dispatchEvent(new Event('input', { bubbles: true }));
      field.dispatchEvent(new Event('change', { bubbles: true }));
    }
    async function privacy() {
      location.hash = '/privacy';
      await until(() => document.querySelector('#privacy-heading')?.textContent.includes('Privacy & product telemetry') &&
        button('Disable product telemetry'), 'The installed privacy page did not open');
    }
    async function memoryCycle() {
      location.hash = '/workspace/new';
      const draft = await until(() => document.querySelector('.ws-page textarea[placeholder="What should this workspace remember?"]'),
        'The installed memory editor did not open');
      const token = crypto.randomUUID().replaceAll('-', '');
      setValue(draft, ('installed delivery observation ' + token + ' ').repeat(8));
      const subject = document.querySelector('.ws-page input[placeholder="e.g. Billing project"]');
      if (!subject) throw new Error('The installed memory editor has no subject field');
      setValue(subject, 'Delivery ' + token.slice(0, 8));
      const kind = document.querySelector('.ws-page select');
      if (kind) { setValue(kind, 'procedure'); }
      await click('Save memory');
      await until(() => location.hash.startsWith('#/workspace/memory/'), 'The real save did not open the saved memory');
      location.hash = '/workspace/search';
      const query = await until(() => document.querySelector('input[aria-label="Search shared memory"]'), 'The installed search did not open');
      const method = [...document.querySelectorAll('label')].find(node => node.textContent.includes('Search method'))?.querySelector('select');
      const lexical = method && [...method.options].find(option => option.value === 'lexical' || option.textContent.trim().toLowerCase() === 'lexical');
      if (lexical) { setValue(method, lexical.value); }
      setValue(query, token);
      await click('Search');
      await until(() => document.querySelector('.ws-search-result h2')?.textContent.includes(token.slice(0, 8)),
        'The real search did not show the saved memory');
      await until(async () => {
        const status = await review();
        return status.review?.report_available ? status : null;
      }, 'The packaged app recorded no real report after the memory actions', 60000);
    }
    const initial = await control('status');
    if (initial.storage !== 'new' || initial.user_enabled !== true || initial.effective_enabled !== false ||
        initial.reason !== 'disclosure_required' || initial.disclosure_version !== 0) {
      throw new Error('The packaged app did not require fresh telemetry disclosure');
    }
    checks.disclosure_required = true;
    const setupDialog = [...document.querySelectorAll('dialog, [role="dialog"]')].find(node =>
      node.textContent.includes('Your privacy choice'));
    if (setupDialog) {
      const share = checkbox('Share anonymous product statistics');
      if (!share?.checked) throw new Error('The packaged setup disclosure did not offer the default choice');
      const defer = [...setupDialog.querySelectorAll('button')].find(node => node.textContent.trim() === 'Not now');
      if (!defer) throw new Error('The packaged setup disclosure has no deferral');
      defer.click();
      await until(() => ![...document.querySelectorAll('[role="dialog"], dialog')].some(node =>
        node.textContent.includes('Your privacy choice') && node.getClientRects().length), 'Setup disclosure stayed open');
    }
    const deferred = await control('status');
    if (deferred.storage !== 'new' || deferred.disclosure_version !== 0 || deferred.effective_enabled !== false || deferred.pending_records !== 0) {
      throw new Error('Deferring setup disclosure granted permission');
    }
    checks.setup_disclosure_deferred_without_permission = true;
    location.hash = '/workspace';
    await until(() => button('Join a workspace') || document.querySelector('input[aria-label="Workspace address"], input[name="endpoint"]') ||
      [...document.querySelectorAll('label')].some(node => node.textContent.includes('Workspace address')),
      'The packaged app did not offer workspace join');
    const join = button('Join a workspace');
    if (join) join.click();
    const address = await until(() => [...document.querySelectorAll('input')].find(node =>
      node.getAttribute('aria-label') === 'Workspace address' || node.labels?.[0]?.textContent.includes('Workspace address')),
      'Missing workspace address');
    const key = [...document.querySelectorAll('input')].find(node =>
      node.getAttribute('aria-label') === 'Workspace key' || node.labels?.[0]?.textContent.includes('Workspace key'));
    if (!key) throw new Error('Missing workspace key');
    setValue(address, fixture.endpoint);
    setValue(key, fixture.credential);
    const remember = checkbox('Remember this workspace on this device');
    if (remember && !remember.disabled && remember.checked) remember.click();
    const form = address.closest('form') || document;
    const open = [...form.querySelectorAll('button')].find(node => node.textContent.trim() === 'Open workspace' && !node.disabled);
    if (!open) throw new Error('Missing workspace open control');
    open.click();
    await until(() => !document.body.innerText.includes('Welcome to Mnemion') || document.querySelector('.ws-shell, .ws-workspace-name'),
      'The packaged app did not open the fixture workspace');
    await privacy();
    const reviewBox = () => checkbox('Pause reports for manual review');
    if (!reviewBox() || reviewBox().checked) throw new Error('Manual review was already selected');
    reviewBox().click();
    await until(async () => (await review()).review?.mode === 'review', 'Manual review did not save before permission');
    const summary = [...document.querySelectorAll('summary')].find(node => node.textContent.trim() === 'Telemetry connection settings');
    if (!summary) throw new Error('Missing telemetry connection settings');
    summary.click();
    const connection = await until(() => document.getElementById('telemetry-connection-mode'), 'Missing connection choice');
    setValue(connection, 'unmetered');
    const beforePermission = await until(async () => {
      const value = await review();
      return value.status?.connection_mode === 'unmetered' ? value : null;
    }, 'The unmetered connection choice did not save');
    if (beforePermission.status.effective_enabled !== false || beforePermission.status.disclosure_version !== 0 ||
        beforePermission.status.pending_records !== 0 || beforePermission.review.mode !== 'review') {
      throw new Error('The manual choice granted collection before disclosure');
    }
    checks.manual_choice_before_permission = true;
    await click('Keep product telemetry on');
    const enabled = await until(async () => {
      const value = await review();
      return value.status?.effective_enabled === true ? value : null;
    }, 'The packaged disclosure acknowledgement did not enable collection');
    if (enabled.status.disclosure_version !== enabled.status.required_disclosure_version || enabled.review.mode !== 'review') {
      throw new Error('The packaged disclosure acknowledgement did not keep manual review');
    }
    checks.app_disclosure_acknowledged = true;
    await memoryCycle();
    await click('Refresh privacy status');
    await click('Inspect next report');
    const shown = await until(() => document.querySelector('[aria-label="Exact report bytes"]')?.textContent, 'The held report did not render');
    const held = await review();
    if (held.review.outcome !== 'held' || held.packet !== null || held.status.delivery_budget.attempts_in_rolling_week !== 0) {
      throw new Error('Inspecting the report disclosed or spent it');
    }
    const inspected = Uint8Array.from(atob(shown), char => char.charCodeAt(0));
    if (inspected.length !== 25) throw new Error('The held report was not the 25-byte body');
    const repeated = await control('inspect_report', request(held));
    if (repeated.packet.body_base64 !== shown || repeated.review.expires_ms !== held.review.expires_ms || repeated.review.token !== held.review.token) {
      throw new Error('Repeating inspection changed the held report');
    }
    checks.exact_review_preserved = true;
    const disabled = await control('configure', { enabled: false, expected_revision: repeated.status.revision,
      expected_generation: repeated.status.store_generation, disclosure_version: 0 });
    if (disabled.user_enabled !== false || disabled.effective_enabled !== false) throw new Error('The native helper did not record opt-out');
    let invalidated = false;
    try { await control('approve_report', request(repeated)); }
    catch (error) { invalidated = /privacy choice changed|report changed/i.test(String(error?.message || error)); }
    if (!invalidated) throw new Error('Opt-out through the native helper did not invalidate the held report');
    window.dispatchEvent(new Event('focus'));
    await until(() => document.body.innerText.includes('Product telemetry is off by your choice.') &&
      !document.querySelector('[aria-label="Exact report bytes"]'), 'The privacy page kept the invalidated report');
    const cleared = await review();
    if (cleared.status.pending_records !== 0 || cleared.status.delivery_budget.attempts_in_rolling_week !== 0 || cleared.review.report_available) {
      throw new Error('The invalidated report remained available');
    }
    checks.native_optout_invalidates_review = true;
    const share = checkbox('Share anonymous product statistics');
    if (!share || share.checked) throw new Error('Opt-out did not clear the share choice');
    share.click();
    const reenabled = await until(async () => {
      const value = await review();
      return value.status?.effective_enabled === true ? value : null;
    }, 'Re-enable did not restore collection');
    if (reenabled.status.pending_records !== 0 || reenabled.review.report_available || reenabled.review.mode !== 'review') {
      throw new Error('Re-enable kept a report');
    }
    checks.reenable_starts_empty = true;
    await memoryCycle();
    await click('Refresh privacy status');
    await click('Inspect next report');
    await until(() => document.querySelector('[aria-label="Exact report bytes"]')?.textContent, 'The discard report did not render');
    await click('Discard report');
    const discarded = await until(async () => {
      const value = await review();
      return value.review?.outcome === 'discarded' ? value : null;
    }, 'Discard did not complete');
    if (discarded.review.report_available || discarded.status.delivery_budget.attempts_in_rolling_week !== 0) {
      throw new Error('Discard spent an attempt');
    }
    checks.discard_does_not_spend = true;
    await memoryCycle();
    await click('Refresh privacy status');
    await click('Inspect next report');
    const approvedShown = await until(() => document.querySelector('[aria-label="Exact report bytes"]')?.textContent, 'The approved report did not render');
    const approvedBytes = Uint8Array.from(atob(approvedShown), char => char.charCodeAt(0));
    if (approvedBytes.length !== 25) throw new Error('The approved report was not the 25-byte body');
    await click('Approve this report');
    const consumed = await until(async () => {
      const value = await review();
      return value.review?.outcome === 'consumed' && value.status?.delivery_budget?.attempts_in_rolling_week === 1 ? value : null;
    }, 'The packaged delivery owner did not record one attempt', 60000);
    if (consumed.status.delivery_budget.attempts_in_rolling_week !== 1) throw new Error('Approval did not spend exactly one attempt');
    checks.approved_attempt_uses_inspected_body = true;
    await click('Disable product telemetry');
    await until(async () => (await control('status')).user_enabled === false, 'Final opt-out did not save');
    const approved_body_hex = [...approvedBytes].map(byte => byte.toString(16).padStart(2, '0')).join('');
    return { checks, approved_body_hex, app_launches: 1 };
  })()`
}

function restartJourney(): string {
  return `(async () => {
    const bridge = window.mnemion;
    const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
    async function until(check, message, timeout = 30000) {
      const deadline = Date.now() + timeout;
      do { const value = await check(); if (value) return value; await pause(100); } while (Date.now() < deadline);
      throw new Error(message);
    }
    if ([...document.querySelectorAll('[role="dialog"], dialog')].some(node => node.textContent.includes('Your privacy choice'))) {
      throw new Error('Restart offered disclosure again after a saved opt-out');
    }
    location.hash = '/privacy';
    await until(() => document.querySelector('#privacy-heading') && document.body.innerText.includes('Product telemetry is off by your choice.'),
      'Restart did not show the saved opt-out');
    const restored = await bridge.productTelemetry('telemetry.review_status');
    const share = [...document.querySelectorAll('input[type="checkbox"]')].find(node =>
      node.closest('label')?.textContent.includes('Share anonymous product statistics'));
    const review = [...document.querySelectorAll('input[type="checkbox"]')].find(node =>
      node.closest('label')?.textContent.includes('Pause reports for manual review'));
    if (restored.status.user_enabled !== false || restored.status.effective_enabled !== false || restored.status.pending_records !== 0 ||
        restored.status.delivery_budget.attempts_in_rolling_week !== 1 || restored.review.mode !== 'review' ||
        restored.review.report_available !== false || restored.packet !== null || share?.checked !== false || review?.checked !== true) {
      throw new Error('Opt-out or manual review did not survive the clean restart');
    }
    return { checks: { optout_and_review_survive_restart: true }, app_launches: 1 };
  })()`
}

export { REVIEW_CHECKS }
