/** Desktop calls use the narrow main-process bridge; browsers use normal fetch. */
export const nativeFetch: typeof fetch | undefined = window.mnemion?.serviceRequest
  ? async (input, init) => {
      const request = new Request(input, init);
      request.signal.throwIfAborted();
      const body = ["GET", "HEAD"].includes(request.method) ? undefined : await request.text();
      request.signal.throwIfAborted();
      // This token coordinates one local IPC lifetime. It never becomes an
      // HTTP header, workspace identity, idempotency key or telemetry value.
      const requestId = crypto.randomUUID(), bridge = window.mnemion!;
      return new Promise<Response>((resolve, reject) => {
        let settled = false, sent = false;
        const finish = (action: () => void) => {
          if (settled) return;
          settled = true;
          request.signal.removeEventListener("abort", abort);
          action();
        };
        const abort = () => finish(() => {
          if (sent) {
            try { void bridge.serviceRequestCancel?.(requestId).catch(() => {}); }
            catch { /* A closing or older bridge cannot delay caller cancellation. */ }
          }
          reject(request.signal.reason ?? new DOMException("Request cancelled", "AbortError"));
        });
        request.signal.addEventListener("abort", abort, { once: true });
        if (request.signal.aborted) { abort(); return; }
        try {
          sent = true;
          const pending = bridge.serviceRequest!({ requestId, url: request.url, method: request.method,
            headers: Object.fromEntries(request.headers.entries()), body });
          // Keep both handlers attached even after abort: a late native reply
          // must neither replace the cancellation nor reject without an owner.
          pending.then(result => finish(() => {
            try { resolve(new Response(result.body.byteLength ? new Uint8Array(result.body) : null,
              { status: result.status, headers: result.headers })); }
            catch (error) { reject(error); }
          }), error => finish(() => reject(error)));
        } catch (error) { finish(() => reject(error)); }
      });
    }
  : undefined;
