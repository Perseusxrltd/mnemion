/** Desktop calls use the narrow main-process bridge; browsers use normal fetch. */
export const nativeFetch: typeof fetch | undefined = window.mnemion?.serviceRequest
  ? async (input, init) => {
      const request = new Request(input, init);
      if (request.signal.aborted) throw new DOMException("Request cancelled", "AbortError");
      const result = await window.mnemion!.serviceRequest!({
        url: request.url,
        method: request.method,
        headers: Object.fromEntries(request.headers.entries()),
        body: ["GET", "HEAD"].includes(request.method) ? undefined : await request.text(),
      });
      if (request.signal.aborted) throw new DOMException("Request cancelled", "AbortError");
      return new Response(result.body.byteLength ? new Uint8Array(result.body) : null, {
        status: result.status,
        headers: result.headers,
      });
    }
  : undefined;
