/** Real privacy controls inside the installed gate's already-isolated profile. */
import type { BrowserWindow } from 'electron'

export async function verifyNativeTelemetry(window: BrowserWindow): Promise<Record<string, boolean>> {
  return window.webContents.executeJavaScript(`(async () => {
    const bridge = window.mnemion;
    const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
    async function until(check, message) {
      const deadline = performance.now() + 30000;
      do { const value = check(); if (value) return value; await pause(100); } while (performance.now() < deadline);
      throw new Error(message);
    }
    const button = text => [...document.querySelectorAll('.ws-privacy button')].find(node =>
      node.textContent.trim() === text && !node.disabled && node.getClientRects().length);
    const checkbox = () => document.querySelector('.ws-privacy .ws-check input[type="checkbox"]');
    const reviewCheckbox = () => document.querySelector('.ws-privacy section[aria-labelledby="telemetry-review-heading"] input[type="checkbox"]');
    async function reviewMode(enabled) {
      const node = await until(() => {
        const value = reviewCheckbox();
        return value && !value.disabled && value.checked !== enabled ? value : null;
      }, 'Missing installed report-review choice');
      node.click();
      await until(() => reviewCheckbox()?.checked === enabled && !reviewCheckbox().disabled,
        'The installed report-review choice did not save');
    }
    async function click(text) {
      const node = await until(() => button(text), 'Missing installed privacy control');
      await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
      if (!node.isConnected || button(text) !== node) throw new Error('Privacy control changed before activation');
      node.click();
    }
    const initial = await bridge.productTelemetry('telemetry.status');
    if (initial.storage !== 'new' || !initial.user_enabled || initial.effective_enabled || initial.disclosure_version !== 0) {
      throw new Error('The disposable installation did not require fresh telemetry disclosure');
    }
    location.hash = '/privacy';
    await until(() => checkbox()?.checked && button('Show report format'), 'The installed privacy page did not open');
    const synthetic = 'AwEELjUAAQEBAQEBAQEBAQEBAQEBAQEBAQ==';
    const syntheticBytes = [3, 1, 4, 46, 53, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1];
    function exactExample(packet) {
      if (!packet || packet.kind !== 'synthetic_example' || packet.body_encoding !== 'base64' ||
          packet.body_base64 !== synthetic || packet.body_bytes !== 25 || packet.schema_version !== 3 ||
          packet.view !== 'bounded_summary' || packet.coordinate !== 0 || packet.randomized_sign !== null ||
          packet.report_selection !== 'automatic' || packet.aggregation !== 'bounded_summary_publication_noise' ||
          packet.randomization_privacy_loss !== null || packet.per_report_privacy_loss !== null ||
          packet.privacy_bound_scope !== 'publication_closed_week' || packet.participation_or_lifetime_guarantee !== false) return false;
      const bytes = Uint8Array.from(atob(packet.body_base64), char => char.charCodeAt(0));
      return bytes.length === syntheticBytes.length && syntheticBytes.every((byte, index) => bytes[index] === byte);
    }
    await click('Show report format');
    await until(() => document.querySelector('.ws-privacy pre')?.textContent === synthetic, 'The installed report-format example did not render');
    const shown = await bridge.productTelemetry('telemetry.preview');
    if (shown.outbound_state !== 'not_inspected' || shown.outbound_body !== null || shown.outbound_bytes !== 0 ||
        !exactExample(shown.illustrative_packet) ||
        shown.status.storage !== 'new' || shown.status.disclosure_version !== 0) {
      throw new Error('The installed format preview changed consent or claimed actual outgoing data');
    }
    await reviewMode(true);
    const held = await bridge.productTelemetry('telemetry.review_status');
    if (held.review?.mode !== 'review' || held.review.report_available || held.packet !== null ||
        held.status.disclosure_version !== 0 || held.status.effective_enabled || held.status.pending_records !== 0) {
      throw new Error('Selecting manual review collected data or acknowledged disclosure');
    }
    for (const text of ['Inspect next report', 'Approve this report', 'Discard report']) {
      const control = [...document.querySelectorAll('.ws-privacy button')].find(node => node.textContent.trim() === text);
      if (!control?.disabled) throw new Error('A report action is available without authorized observations');
    }
    await click('Disable product telemetry');
    await until(() => checkbox()?.checked === false && button('Disable product telemetry'), 'The app did not save telemetry opt-out');
    const disabled = await bridge.productTelemetry('telemetry.status');
    if (disabled.user_enabled || disabled.effective_enabled || disabled.pending_records !== 0 || disabled.reason !== 'user_disabled') {
      throw new Error('The native agent did not observe the app telemetry opt-out');
    }
    const paused = await bridge.productTelemetry('telemetry.review_status');
    if (paused.review?.mode !== 'review' || paused.packet !== null || paused.review.report_available) {
      throw new Error('Opt-out lost the saved manual-review choice');
    }
    await click('Show report format');
    await until(() => document.querySelector('.ws-privacy pre')?.textContent === synthetic, 'The opted-out format preview did not render');
    // An agent changes only the saved preference, without acknowledging an
    // unseen disclosure. Focus must refresh the app and discard its old view.
    const edited = await bridge.productTelemetry('telemetry.configure', { enabled: true,
      expected_revision: disabled.revision, expected_generation: disabled.store_generation,
      disclosure_version: 0 });
    if (edited.effective_enabled || edited.disclosure_version !== 0) throw new Error('Agent preference editing acknowledged disclosure');
    window.dispatchEvent(new Event('focus'));
    await until(() => checkbox()?.checked === true && button('Show report format') && !document.querySelector('.ws-privacy pre'),
      'The privacy page retained an old preview after an agent choice');
    const currentReview = await bridge.productTelemetry('telemetry.review_status');
    const automatic = await bridge.productTelemetry('telemetry.review_mode', {
      expected_revision: currentReview.status.revision, expected_generation: currentReview.status.store_generation,
      expected_review_token: currentReview.review.token, mode: 'automatic' });
    if (automatic.review?.mode !== 'automatic' || automatic.status.effective_enabled || automatic.packet !== null) {
      throw new Error('The agent could not change review mode without granting collection');
    }
    window.dispatchEvent(new Event('focus'));
    await until(() => reviewCheckbox()?.checked === false && !reviewCheckbox().disabled,
      'The app did not refresh an agent report-review choice');
    await reviewMode(true);
    await click('Disable product telemetry');
    await until(() => checkbox()?.checked === false && button('Disable product telemetry'), 'Final disposable opt-out did not save');
    const final = await bridge.productTelemetry('telemetry.status');
    if (final.user_enabled || final.effective_enabled || final.pending_records !== 0 || final.delivery_budget?.attempts_in_rolling_week !== 0) {
      throw new Error('Read-only privacy inspection reserved or retained telemetry');
    }
    return { nativeTelemetryDisclosurePreview: true, nativeTelemetryAppAgentChoice: true,
      nativeTelemetryPreviewClearedOnRefresh: true, nativeTelemetryNoAttemptDuringInspection: true,
      nativeTelemetryReviewBeforePermission: true, nativeTelemetryReviewAppAgentChoice: true };
  })()`)
}
