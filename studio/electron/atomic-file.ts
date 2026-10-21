/** Keep replacement atomic while Windows readers briefly deny delete sharing. */
import { rename } from 'node:fs/promises'
import { setTimeout as wait } from 'node:timers/promises'

const delays = [20, 40, 80, 160, 200, 200, 200, 200, 200, 200]
const sharingErrors = new Set(['EPERM', 'EACCES', 'EBUSY'])

export async function replaceFile(temporary: string, destination: string, signal?: AbortSignal): Promise<void> {
  for (let attempt = 0; ; attempt++) {
    signal?.throwIfAborted()
    try {
      await rename(temporary, destination)
      return
    } catch (error) {
      const delay = delays[attempt]
      if (process.platform !== 'win32' || delay === undefined ||
          !sharingErrors.has((error as NodeJS.ErrnoException).code ?? '')) throw error
      // Never unlink the destination or rewrite it in place to work around a
      // sharing lock. Failure/cancellation leaves the previous complete file.
      await wait(delay, undefined, { signal })
    }
  }
}
