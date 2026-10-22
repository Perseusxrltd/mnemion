"""Bounded provider HTTP requests with token rotation and rate-limit handling."""

import json
import math
import time

import httpx

from .providers import ProviderError
from .http_deadline import Budget, DeadlineClient, DeadlineExpired, current_budget


class ProviderHTTP:
    def __init__(
        self,
        base_url,
        token,
        *,
        transport=None,
        sleep=time.sleep,
        clock=time.monotonic,
        total_timeout=60,
    ):
        if (
            not isinstance(total_timeout, (int, float))
            or not math.isfinite(total_timeout)
            or not 0 < total_timeout <= 300
        ):
            raise ValueError("Provider request budget must be between zero and 300 seconds")
        self.token, self.sleep, self.clock = token, sleep, clock
        self.total_timeout = total_timeout
        # Supplied transports are trusted test/embedding adapters; the native
        # network path keeps HTTPX's environment proxies and certificate trust.
        client_type = DeadlineClient if transport is None else httpx.Client
        self.client = client_type(
            base_url=base_url, timeout=30, follow_redirects=False, transport=transport
        )

    def close(self):
        self.client.close()

    def get(self, path, params=None, *, maximum=20_000_000, binary=False):
        if type(maximum) is not int or maximum < 0:
            raise ValueError("Provider response limit must be a nonnegative byte count")
        budget = Budget(self.clock() + self.total_timeout, self.clock)
        reset = current_budget.set(budget)
        try:
            return self._get(path, params, maximum=maximum, binary=binary, budget=budget)
        except (httpx.HTTPError, ValueError, DeadlineExpired):
            raise ProviderError("provider_unavailable") from None
        finally:
            current_budget.reset(reset)

    def _get(self, path, params, *, maximum, binary, budget):
        for attempt in range(3):
            budget.timeout()
            token = self.token.read()
            with self.client.stream(
                "GET",
                path,
                params=params,
                headers={"Authorization": "Bearer " + token, "Accept-Encoding": "identity"},
                timeout=budget.timeout(30),
            ) as response:
                budget.timeout()
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
                    delay = max(0.1, delay)
                else:
                    if response.status_code in (401, 403, 404, 410):
                        raise ProviderError("provider_access_lost", access_lost=True)
                    if not response.is_success:
                        raise ProviderError("provider_request_failed")
                    if (
                        response.headers.get("Content-Encoding", "identity").strip().lower()
                        != "identity"
                    ):
                        raise ProviderError("invalid_provider_response")
                    length = response.headers.get("Content-Length")
                    if length is not None and int(length) > maximum:
                        raise ProviderError("provider_response_too_large")
                    data = bytearray()
                    # Preloaded responses are supplied by trusted mock/adaptor
                    # transports. Real responses stay raw, with no decompressor.
                    chunks = (
                        (response.content,) if response.is_stream_consumed else response.iter_raw()
                    )
                    for chunk in chunks:
                        budget.timeout()
                        if len(chunk) > maximum - len(data):
                            raise ProviderError("provider_response_too_large")
                        data.extend(chunk)
                    budget.timeout()
                    if binary:
                        return bytes(data)
                    value = json.loads(data)
                    if not isinstance(value, dict):
                        raise ProviderError("invalid_provider_response")
                    budget.timeout()
                    return value
            # Close the response before backoff. A retry cannot reset the
            # operation budget or keep a previous stream open during the wait.
            if delay >= budget.timeout():
                raise DeadlineExpired("Provider retry exceeds the request budget")
            self.sleep(delay)
            budget.timeout()
        raise ProviderError("provider_unavailable")
