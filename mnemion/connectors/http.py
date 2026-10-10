"""Bounded provider HTTP requests with token rotation and rate-limit handling."""

import time

import httpx

from .providers import ProviderError


class ProviderHTTP:
    def __init__(self, base_url, token, *, transport=None, sleep=time.sleep):
        self.token, self.sleep = token, sleep
        self.client = httpx.Client(
            base_url=base_url, timeout=30, follow_redirects=False, transport=transport
        )

    def close(self):
        self.client.close()

    def get(self, path, params=None, *, maximum=20_000_000, binary=False):
        for attempt in range(3):
            try:
                with self.client.stream(
                    "GET",
                    path,
                    params=params,
                    headers={"Authorization": "Bearer " + self.token.read()},
                ) as response:
                    if response.status_code in (429, 500, 502, 503, 504):
                        delay = response.headers.get("Retry-After", str(2**attempt))
                        try:
                            delay = float(delay)
                        except ValueError:
                            delay = 2**attempt
                        if attempt == 2 or not 0 <= delay <= 60:
                            raise ProviderError(
                                "provider_rate_limited"
                                if response.status_code == 429
                                else "provider_unavailable"
                            )
                        self.sleep(max(0.1, delay))
                        continue
                    if response.status_code in (401, 403, 404, 410):
                        raise ProviderError("provider_access_lost", access_lost=True)
                    if not response.is_success:
                        raise ProviderError("provider_request_failed")
                    data = bytearray()
                    for chunk in response.iter_bytes():
                        data.extend(chunk)
                        if len(data) > maximum:
                            raise ProviderError("provider_response_too_large")
                    if binary:
                        return bytes(data)
                    import json

                    value = json.loads(data)
                    if not isinstance(value, dict):
                        raise ProviderError("invalid_provider_response")
                    return value
            except (httpx.HTTPError, ValueError):
                raise ProviderError("provider_unavailable") from None
        raise ProviderError("provider_unavailable")
