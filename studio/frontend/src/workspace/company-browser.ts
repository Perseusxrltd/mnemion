import type { CompanyCallback } from '../../../shared/company-sign-in'
import { companyStart } from '../../../electron/company-sign-in-protocol'

/** One-use browser handoff shared by Studio sign-in and assistant consent. */
export async function companyBrowserProof(
  providerId: string, begin: (signal: AbortSignal) => Promise<unknown>, controller: AbortController,
): Promise<{ state: string; code_verifier: string; code: string }> {
  if (controller.signal.aborted) throw new Error('Company sign-in was cancelled.')
  if (typeof BroadcastChannel === 'undefined') throw new Error('Use a current browser for company sign-in.')
  const popup = window.open('about:blank', '_blank', 'popup,width=560,height=740')
  if (!popup) throw new Error('Allow the company sign-in window, then try again.')
  // The company provider receives no opener capable of navigating this window.
  popup.opener = null
  popup.document.title = 'Mnemion · Company sign-in'
  popup.document.body.textContent = 'Opening your company’s sign-in page…'
  let channel: BroadcastChannel | undefined
  let timedOut = false
  let cancel: (() => void) | undefined
  let timer = setTimeout(() => { timedOut = true; controller.abort() }, 300_000)
  try {
    const flow = companyStart(await begin(controller.signal), providerId)
    if (controller.signal.aborted) throw new Error('Company sign-in was cancelled.')
    clearTimeout(timer)
    timer = setTimeout(() => { timedOut = true; controller.abort() }, flow.expires_in * 1000)
    channel = new BroadcastChannel('mnemion-company:' + flow.state)
    const code = await new Promise<string>((resolve, reject) => {
      cancel = () => reject(new Error(timedOut ? 'Company sign-in expired. Try again.' : 'Company sign-in was cancelled.'))
      controller.signal.addEventListener('abort', cancel, { once: true })
      channel!.onmessage = ({ data }: MessageEvent<CompanyCallback>) => {
        if (!data || data.type !== 'mnemion-company-callback' || data.state !== flow.state) return
        if (data.error || typeof data.code !== 'string' || !data.code || data.code.length > 4096) reject(new Error('Company sign-in was declined or could not be completed.'))
        else resolve(data.code)
      }
      popup.location.href = flow.authorization_url
    })
    if (controller.signal.aborted) throw new Error('Company sign-in was cancelled.')
    return { state: flow.state, code_verifier: flow.code_verifier, code }
  } finally {
    clearTimeout(timer)
    if (cancel) controller.signal.removeEventListener('abort', cancel)
    channel?.close()
    popup.close()
  }
}
