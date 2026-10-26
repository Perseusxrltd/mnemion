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
    await click('Show report format');
    await until(() => document.querySelector('.ws-privacy pre')?.textContent === 'AQAHAA==', 'The installed report-format example did not render');
    const shown = await bridge.productTelemetry('telemetry.preview');
    if (shown.outbound_state !== 'not_inspected' || shown.outbound_body !== null || shown.outbound_bytes !== 0 ||
        shown.illustrative_packet?.kind !== 'synthetic_example' || shown.illustrative_packet?.body_base64 !== 'AQAHAA==' ||
        shown.status.storage !== 'new' || shown.status.disclosure_version !== 0) {
      throw new Error('The installed format preview changed consent or claimed actual outgoing data');
    }
    await click('Disable product telemetry');
    await until(() => checkbox()?.checked === false && button('Disable product telemetry'), 'The app did not save telemetry opt-out');
    const disabled = await bridge.productTelemetry('telemetry.status');
    if (disabled.user_enabled || disabled.effective_enabled || disabled.pending_records !== 0 || disabled.reason !== 'user_disabled') {
      throw new Error('The native agent did not observe the app telemetry opt-out');
    }
    await click('Show report format');
    await until(() => document.querySelector('.ws-privacy pre')?.textContent === 'AQAHAA==', 'The opted-out format preview did not render');
    // An agent changes only the saved preference, without acknowledging an
    // unseen disclosure. Focus must refresh the app and discard its old view.
    const edited = await bridge.productTelemetry('telemetry.configure', { enabled: true,
      expected_revision: disabled.revision, expected_generation: disabled.store_generation,
      disclosure_version: 0 });
    if (edited.effective_enabled || edited.disclosure_version !== 0) throw new Error('Agent preference editing acknowledged disclosure');
    window.dispatchEvent(new Event('focus'));
    await until(() => checkbox()?.checked === true && button('Show report format') && !document.querySelector('.ws-privacy pre'),
      'The privacy page retained an old preview after an agent choice');
    await click('Disable product telemetry');
    await until(() => checkbox()?.checked === false && button('Disable product telemetry'), 'Final disposable opt-out did not save');
    const final = await bridge.productTelemetry('telemetry.status');
    if (final.user_enabled || final.effective_enabled || final.pending_records !== 0 || final.delivery_budget?.attempts_in_rolling_week !== 0) {
      throw new Error('Read-only privacy inspection reserved or retained telemetry');
    }
    return { nativeTelemetryDisclosurePreview: true, nativeTelemetryAppAgentChoice: true,
      nativeTelemetryPreviewClearedOnRefresh: true, nativeTelemetryNoAttemptDuringInspection: true };
  })()`)
}
