/** Installed review delivery. The packaged bridge, UI and delivery owner stay in place. */
import type { BrowserWindow } from 'electron'
import { app } from 'electron'
import { telemetryPrivacyGate, telemetryReadinessError, telemetrySnapshotDecision, telemetryWorkspaceSettled } from './telemetry-readiness.mjs'
import { publicObservation } from './telemetry-observation-diagnostic.mjs'

/** The page script cannot import modules. These functions carry their own allowlists. */
function readinessRuntime(): string {
  return `
    const decide = ${telemetrySnapshotDecision.toString()};
    const readinessError = ${telemetryReadinessError.toString()};
    async function ready(phase, accept, timeout = 30000) {
      let gate = 'review_unavailable';
      try {
        const snapshot = await until(async () => {
          let snapshot;
          try { snapshot = await reviewStatus(); }
          catch { gate = 'control_unavailable'; return null; }
          const decision = decide(snapshot, accept);
          if (decision.ready) return decision.snapshot;
          gate = decision.gate || 'review_unavailable';
          return null;
        }, phase, timeout);
        if (typeof noteProbe === 'function') noteProbe(phase, 'none');
        return snapshot;
      } catch (error) {
        if (String((error && error.message) || error) !== phase) throw error;
        if (typeof publishProbe === 'function') await publishProbe(phase, gate);
        throw new Error(readinessError(phase, gate));
      }
    }
    function view(snapshot, phase) {
      const decision = decide(snapshot, () => true);
      if (!decision.ready) {
        if (typeof noteProbe === 'function') noteProbe(phase, decision.gate);
        throw new Error(readinessError(phase, decision.gate));
      }
      return snapshot;
    }
    function attemptCount(snapshot) {
      const budget = snapshot.status && snapshot.status.delivery_budget;
      const count = budget ? budget.attempts_in_rolling_week : null;
      return Number.isInteger(count) ? count : null;
    }`
}

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
  let evidence = result as Record<string, unknown>
  if (!restart && evidence.delivery_pending === true) {
    const { settleInstalledTelemetryDelivery } = await import('./service-bridge.js')
    await settleInstalledTelemetryDelivery()
    const finished = await window.webContents.executeJavaScript(finalOptOut())
    if (!finished || typeof finished !== 'object' || finished.checks?.final_opt_out !== true) {
      throw new Error('Final opt-out did not save after delivery')
    }
    evidence = {
      ...evidence,
      checks: { ...(evidence.checks as Record<string, unknown>), ...finished.checks },
      delivery_pending: undefined,
    }
  }
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
  const observation = publicObservation()
  return { ...evidence, ...(observation ? { observation } : {}), packaged: true, runtime, qualification: 'installed fixture delivery' }
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
    const controlLabel = node => (node.querySelector('strong')?.textContent ?? node.textContent ?? '').trim();
    const button = text => [...document.querySelectorAll('button')].find(node =>
      controlLabel(node) === text && !node.disabled && node.getClientRects().length);
    async function click(text, phase) {
      let gate = 'control_unavailable';
      try {
        const node = await until(() => button(text), phase || ('Missing installed privacy control: ' + text));
        node.click();
      } catch (error) {
        if (!phase || String((error && error.message) || error) !== phase) throw error;
        try {
          const decision = decide(await reviewStatus(), () => true);
          gate = decision.ready ? 'control_unavailable' : decision.gate;
        } catch { gate = 'control_unavailable'; }
        if (typeof publishProbe === 'function') await publishProbe(phase, gate);
        throw new Error(readinessError(phase, gate));
      }
    }
    const checkbox = text => [...document.querySelectorAll('input[type="checkbox"]')].find(node =>
      node.closest('label')?.textContent.includes(text));
    const control = (action, value = {}) => bridge.productTelemetry('telemetry.' + action, value);
    const reviewStatus = () => control('review_status');
    ${readinessRuntime()}
    const request = value => {
      const opened = view(value, 'review_request');
      return { expected_revision: opened.status.revision,
        expected_generation: opened.status.store_generation, expected_review_token: opened.review.token };
    };
    function setValue(field, value) {
      const prototype = field instanceof HTMLTextAreaElement ? HTMLTextAreaElement : field instanceof HTMLSelectElement ? HTMLSelectElement : HTMLInputElement;
      Object.getOwnPropertyDescriptor(prototype.prototype, 'value').set.call(field, value);
      field.dispatchEvent(new Event('input', { bubbles: true }));
      field.dispatchEvent(new Event('change', { bubbles: true }));
    }
    const workspaceSettled = ${telemetryWorkspaceSettled.toString()};
    const privacyGate = ${telemetryPrivacyGate.toString()};
    function privacyView() {
      const heading = document.querySelector('#privacy-heading');
      const disable = [...document.querySelectorAll('button')].find(node => controlLabel(node) === 'Disable product telemetry');
      const control = !disable ? 'absent' : disable.disabled ? 'disabled' : disable.getClientRects().length ? 'ready' : 'hidden';
      return {
        hash: location.hash,
        heading: !!(heading && heading.textContent && heading.textContent.includes('Privacy & product telemetry')),
        control,
      };
    }
    async function privacy() {
      location.hash = '/privacy';
      try {
        await until(() => privacyGate(privacyView()) === 'none', 'The installed privacy page did not open');
      } catch (error) {
        if (String((error && error.message) || error) !== 'The installed privacy page did not open') throw error;
        noteProbe('privacy_open', privacyGate(privacyView()));
        throw error;
      }
    }
    const probePhases = ['none', 'manual_review', 'before_permission', 'collection_enabled', 'memory_observations', 'report_inspect', 'report_bytes', 'report_held', 'invalidated_report', 'collection_reenabled', 'report_discard', 'report_discarded', 'report_approve', 'report_consumed', 'final_opt_out', 'restart_review', 'review_request', 'privacy_open', 'unknown_phase'];
    const probeGates = ['none', 'unavailable', 'not_initialized', 'upgrade_required', 'stored_snapshot', 'inactive', 'paused', 'held', 'discarded', 'approved', 'consumed', 'expired', 'invalidated', 'no_report', 'no_observations', 'collection_not_permitted', 'transport_unavailable', 'delivery_not_ready', 'control_unavailable', 'review_unavailable', 'review_not_paused', 'connection_pending', 'collection_pending', 'observations_pending', 'report_not_held', 'report_not_discarded', 'report_not_consumed', 'privacy_navigation', 'privacy_page', 'privacy_state', 'privacy_control'];
    const probeDiagnostic = { cycle: 0, readiness: 'none', pending: 'none' };
    function noteProbe(phase, pending) {
      probeDiagnostic.readiness = probePhases.includes(phase) ? phase : 'unknown_phase';
      probeDiagnostic.pending = probeGates.includes(pending) ? pending : 'review_unavailable';
    }
    function rendererObservation() {
      const value = globalThis.__mnObservationDiagnostic;
      const keys = ['snapshot_admitted', 'snapshot_null', 'snapshot_rejected', 'snapshot_deadline', 'snapshot_elapsed_lt_5', 'snapshot_elapsed_lt_25', 'snapshot_elapsed_ge_25'];
      if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
      const safe = {};
      for (const key of keys) {
        const number = value[key];
        if (!Number.isInteger(number) || number < 0 || number > 255) return null;
        safe[key] = number;
      }
      return safe;
    }
    async function publishProbe(phase, pending) {
      noteProbe(phase, pending);
      if (typeof bridge.observationDiagnostic !== 'function') return;
      try {
        await bridge.observationDiagnostic({ cycle: probeDiagnostic.cycle, readiness: probeDiagnostic.readiness, pending: probeDiagnostic.pending, renderer: rendererObservation() });
      } catch { /* Diagnostic retention cannot change the journey. */ }
    }
    async function memoryCycle() {
      probeDiagnostic.cycle = Math.min(3, probeDiagnostic.cycle + 1);
      const token = crypto.randomUUID().replaceAll('-', '');
      const canary = 'PRIVATE_RENDERER_MEMORY_CANARY';
      location.hash = '/workspace/new';
      const draft = await until(() => document.querySelector('.ws-page textarea[placeholder="What should this workspace remember?"]'),
        'The installed memory editor did not open');
      setValue(draft, (canary + ' installed delivery observation ' + token + ' ').repeat(4));
      const subject = document.querySelector('.ws-page input[placeholder="e.g. Billing project"]');
      if (!subject) throw new Error('The installed memory editor has no subject field');
      setValue(subject, canary + ' ' + token.slice(0, 8));
      const kind = [...document.querySelectorAll('.ws-page select')].find(node =>
        [...node.options].some(option => option.value === 'procedure' || option.textContent.trim() === 'procedure'));
      if (!kind) throw new Error('The installed memory editor has no memory type');
      setValue(kind, 'procedure');
      await click('Save memory');
      await until(() => location.hash.startsWith('#/workspace/memory/') &&
        [...document.querySelectorAll('.ws-prose')].some(node => node.textContent.includes(canary) && node.textContent.includes(token)),
        'The real fetch did not show the saved memory');
      location.hash = '/workspace/search';
      const query = await until(() => document.querySelector('input[aria-label="Search shared memory"]'), 'The installed search did not open');
      const method = [...document.querySelectorAll('label')].find(node => node.textContent.includes('Search method'))?.querySelector('select');
      const lexical = method && [...method.options].find(option => option.value === 'lexical');
      if (!method || !lexical) throw new Error('The installed search has no exact-text method');
      setValue(method, lexical.value);
      setValue(query, token);
      const search = await until(() => [...document.querySelectorAll('.ws-search-form button')].find(node =>
        node.textContent.trim() === 'Search' && !node.disabled), 'The installed search control is not ready');
      search.click();
      await until(() => [...document.querySelectorAll('.ws-search-result')].some(node => {
        const prose = node.querySelector('.ws-prose')?.textContent || '';
        return prose.includes(canary) && prose.includes(token);
      }), 'The real lexical recall did not show the saved memory');
    }
    async function stageHeld() {
      await privacy();
      await ready('memory_observations', snapshot => {
        if (snapshot.review.mode !== 'review') return 'review_not_paused';
        if (snapshot.status?.effective_enabled !== true) return 'collection_pending';
        if (!(snapshot.status?.pending_records > 0)) return 'no_observations';
        return true;
      }, 60000);
      await click('Refresh privacy status');
      await click('Inspect next report', 'report_inspect');
      let shown;
      try {
        shown = await until(() => {
          const text = document.querySelector('[aria-label="Exact report bytes"]')?.textContent;
          return text && text.trim() ? text.trim() : null;
        }, 'report_bytes', 60000);
      } catch (error) {
        if (String((error && error.message) || error) !== 'report_bytes') throw error;
        await publishProbe('report_bytes', 'report_not_held');
        throw new Error(readinessError('report_bytes', 'report_not_held'));
      }
      const held = await ready('report_held', snapshot => {
        if (snapshot.review.outcome !== 'held') return 'report_not_held';
        if (snapshot.packet !== null) throw new Error('Inspecting the report disclosed or spent it');
        const count = attemptCount(snapshot);
        if (count === null) return 'delivery_not_ready';
        if (count !== 0) throw new Error('Inspecting the report disclosed or spent it');
        return true;
      });
      return { shown, held };
    }
    try {
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
    const join = await until(() => [...document.querySelectorAll('button.ws-setup-choice')].find(node =>
      node.querySelector('strong')?.textContent.trim() === 'Join a workspace' && !node.disabled && node.getClientRects().length),
      'The packaged app did not offer workspace join');
    join.click();
    const keyMethod = await until(() => [...document.querySelectorAll('[aria-label="Choose how to join"] button')].find(node =>
      node.textContent.trim() === 'Workspace key' && !node.disabled && node.getClientRects().length),
      'The packaged app did not offer workspace-key join');
    keyMethod.click();
    const form = await until(() => document.querySelector('form.ws-join-form'), 'The workspace key form did not open');
    const address = await until(() => [...form.querySelectorAll('input')].find(node =>
      !node.disabled && node.labels?.[0]?.textContent.includes('Workspace address')),
      'Missing workspace address');
    const key = [...form.querySelectorAll('input')].find(node =>
      !node.disabled && node.labels?.[0]?.textContent.includes('Workspace key') && !node.labels?.[0]?.textContent.includes('Workspace address'));
    if (!key) throw new Error('Missing workspace key');
    setValue(address, fixture.endpoint);
    setValue(key, fixture.credential);
    const remember = [...form.querySelectorAll('input[type="checkbox"]')].find(node =>
      node.closest('label')?.textContent.includes('Remember this workspace on this device'));
    if (remember && !remember.disabled && remember.checked) remember.click();
    const open = await until(() => [...form.querySelectorAll('button')].find(node =>
      controlLabel(node) === 'Open workspace' && !node.disabled && node.getClientRects().length),
      'The workspace key form did not enable Open workspace');
    open.click();
    await until(() => workspaceSettled({
      shell: !!document.querySelector('.ws-shell')?.getClientRects().length,
      name: !!document.querySelector('.ws-workspace-name')?.getClientRects().length,
      hash: location.hash,
    }), 'The packaged app did not open the fixture workspace');
    await privacy();
    await ready('manual_review', snapshot => snapshot.review.mode === 'automatic' || snapshot.review.mode === 'review' ? true : 'review_unavailable');
    await click('Refresh privacy status');
    const reviewBox = () => checkbox('Pause reports for manual review');
    let manual;
    try {
      manual = await until(() => {
        const box = reviewBox();
        return box && !box.disabled && box.getClientRects().length ? box : null;
      }, 'manual_review_control');
    } catch (error) {
      if (String((error && error.message) || error) !== 'manual_review_control') throw error;
      await publishProbe('manual_review', 'review_unavailable');
      throw new Error(readinessError('manual_review', 'review_unavailable'));
    }
    if (manual.checked) throw new Error('Manual review was already selected');
    manual.click();
    await ready('manual_review', snapshot => snapshot.review.mode === 'review' ? true : 'review_not_paused');
    const summary = [...document.querySelectorAll('summary')].find(node => node.textContent.trim() === 'Telemetry connection settings');
    if (!summary) {
      await publishProbe('before_permission', 'control_unavailable');
      throw new Error(readinessError('before_permission', 'control_unavailable'));
    }
    summary.click();
    let connection;
    try {
      connection = await until(() => {
        const node = document.getElementById('telemetry-connection-mode');
        const review = reviewBox();
        const reviewSettled = Boolean(review && review.checked && !review.disabled && review.getClientRects().length);
        if (!(node instanceof HTMLSelectElement) || node.disabled || !node.getClientRects().length || !reviewSettled) return null;
        return node;
      }, 'connection_control');
    } catch (error) {
      if (String((error && error.message) || error) !== 'connection_control') throw error;
      await publishProbe('before_permission', 'control_unavailable');
      throw new Error(readinessError('before_permission', 'control_unavailable'));
    }
    setValue(connection, 'unmetered');
    const beforePermission = await ready('before_permission', snapshot => {
      if (snapshot.review.mode !== 'review') return 'review_not_paused';
      if (snapshot.status?.connection_mode !== 'unmetered') return 'connection_pending';
      return true;
    });
    if (beforePermission.status.effective_enabled !== false || beforePermission.status.disclosure_version !== 0 ||
        beforePermission.status.pending_records !== 0) {
      throw new Error('The manual choice granted collection before disclosure');
    }
    checks.manual_choice_before_permission = true;
    await click('Keep product telemetry on');
    const enabled = await ready('collection_enabled', snapshot => {
      if (snapshot.review.mode !== 'review') return 'review_not_paused';
      if (snapshot.status?.effective_enabled !== true) return 'collection_pending';
      return true;
    });
    if (enabled.status.disclosure_version !== enabled.status.required_disclosure_version) {
      throw new Error('The packaged disclosure acknowledgement did not keep manual review');
    }
    checks.app_disclosure_acknowledged = true;
    await memoryCycle();
    const staged = await stageHeld();
    const shown = staged.shown;
    const held = staged.held;
    const inspected = Uint8Array.from(atob(shown), char => char.charCodeAt(0));
    if (inspected.length !== 25) throw new Error('The held report was not the 25-byte body');
    const repeated = view(await control('inspect_report', request(held)), 'report_held');
    if (!repeated.packet || repeated.packet.body_base64 !== shown || repeated.review.expires_ms !== held.review.expires_ms || repeated.review.token !== held.review.token) {
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
    await ready('invalidated_report', snapshot => {
      const count = attemptCount(snapshot);
      if (count === null) return 'delivery_not_ready';
      if (snapshot.status?.pending_records !== 0 || count !== 0 || snapshot.review.report_available) {
        throw new Error('The invalidated report remained available');
      }
      return true;
    });
    checks.native_optout_invalidates_review = true;
    const share = checkbox('Share anonymous product statistics');
    if (!share || share.checked) throw new Error('Opt-out did not clear the share choice');
    share.click();
    const reenabled = await ready('collection_reenabled', snapshot => {
      if (snapshot.review.mode !== 'review') return 'review_not_paused';
      if (snapshot.status?.effective_enabled !== true) return 'collection_pending';
      return true;
    });
    if (reenabled.status.pending_records !== 0 || reenabled.review.report_available) {
      throw new Error('Re-enable kept a report');
    }
    checks.reenable_starts_empty = true;
    await memoryCycle();
    await stageHeld();
    await click('Discard report', 'report_discard');
    await ready('report_discarded', snapshot => {
      if (snapshot.review.outcome !== 'discarded') return 'report_not_discarded';
      const count = attemptCount(snapshot);
      if (count === null) return 'delivery_not_ready';
      if (snapshot.review.report_available || count !== 0) throw new Error('Discard spent an attempt');
      return true;
    });
    checks.discard_does_not_spend = true;
    await memoryCycle();
    const approved = await stageHeld();
    const approvedBytes = Uint8Array.from(atob(approved.shown), char => char.charCodeAt(0));
    if (approvedBytes.length !== 25) throw new Error('The approved report was not the 25-byte body');
    await click('Approve this report', 'report_approve');
    await ready('report_consumed', snapshot => {
      if (snapshot.review.outcome !== 'consumed') return 'report_not_consumed';
      const count = attemptCount(snapshot);
      if (count === null) return 'delivery_not_ready';
      if (count !== 1) throw new Error('Approval did not spend exactly one attempt');
      return true;
    }, 60000);
    checks.approved_attempt_uses_inspected_body = true;
    const approved_body_hex = [...approvedBytes].map(byte => byte.toString(16).padStart(2, '0')).join('');
    await publishProbe('report_consumed', 'none');
    return { checks, approved_body_hex, app_launches: 1, delivery_pending: true };
    } catch (error) {
      await publishProbe(probeDiagnostic.readiness, probeDiagnostic.pending);
      throw error;
    }
  })()`
}

function finalOptOut(): string {
  return `(async () => {
    const bridge = window.mnemion;
    const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
    async function until(check, message, timeout = 30000) {
      const deadline = Date.now() + timeout;
      do { const value = await check(); if (value) return value; await pause(100); } while (Date.now() < deadline);
      throw new Error(message);
    }
    const button = text => [...document.querySelectorAll('button')].find(node =>
      node.textContent.trim() === text && !node.disabled && node.getClientRects().length);
    const reviewStatus = () => bridge.productTelemetry('telemetry.review_status');
    ${readinessRuntime()}
    location.hash = '/privacy';
    await until(() => document.querySelector('#privacy-heading')?.textContent.includes('Privacy & product telemetry') &&
      button('Disable product telemetry'), 'The installed privacy page did not open');
    button('Disable product telemetry').click();
    let missing = true;
    try {
      await until(async () => {
        let status;
        try { status = await bridge.productTelemetry('telemetry.status'); }
        catch { missing = true; return null; }
        if (!status || typeof status !== 'object' || Array.isArray(status)) { missing = true; return null; }
        missing = false;
        return status.user_enabled === false ? status : null;
      }, 'final_opt_out');
    } catch (error) {
      if (String((error && error.message) || error) !== 'final_opt_out') throw error;
      if (missing) throw new Error(readinessError('final_opt_out', 'control_unavailable'));
      throw new Error('Final opt-out did not save');
    }
    return { checks: { final_opt_out: true } };
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
    const reviewStatus = () => bridge.productTelemetry('telemetry.review_status');
    ${readinessRuntime()}
    if ([...document.querySelectorAll('[role="dialog"], dialog')].some(node => node.textContent.includes('Your privacy choice'))) {
      throw new Error('Restart offered disclosure again after a saved opt-out');
    }
    location.hash = '/privacy';
    await until(() => document.querySelector('#privacy-heading') && document.body.innerText.includes('Product telemetry is off by your choice.'),
      'Restart did not show the saved opt-out');
    const share = [...document.querySelectorAll('input[type="checkbox"]')].find(node =>
      node.closest('label')?.textContent.includes('Share anonymous product statistics'));
    const review = [...document.querySelectorAll('input[type="checkbox"]')].find(node =>
      node.closest('label')?.textContent.includes('Pause reports for manual review'));
    await ready('restart_review', snapshot => {
      const count = attemptCount(snapshot);
      if (count === null) return 'delivery_not_ready';
      if (snapshot.status?.user_enabled !== false || snapshot.status?.effective_enabled !== false || snapshot.status?.pending_records !== 0 ||
          count !== 1 || snapshot.review.mode !== 'review' || snapshot.review.report_available !== false || snapshot.packet !== null ||
          share?.checked !== false || review?.checked !== true) {
        throw new Error('Opt-out or manual review did not survive the clean restart');
      }
      return true;
    });
    return { checks: { optout_and_review_survive_restart: true }, app_launches: 1 };
  })()`
}

export { REVIEW_CHECKS }
