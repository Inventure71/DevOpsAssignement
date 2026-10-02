"""Small bounded JSON transport; provider errors never expose response bodies."""

import json
import math
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from backend.core.errors import DomainError


class MusicProviderError(DomainError):
    """Safe domain error suitable for the application transport boundary."""


class ProviderHttpError(Exception):
    def __init__(self, status, retry_after=None):
        super().__init__("Music provider request failed")
        self.status = status
        self.retry_after = retry_after


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('Provider redirects are not permitted')


def _retry_after(value):
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return None
    return min(120, max(1, math.ceil(seconds))) if math.isfinite(seconds) else None


class JsonHttpTransport:
    """Injectable urllib transport with fixed time and response-size budgets."""

    def __init__(self, timeout=8, max_bytes=2_000_000, opener=None):
        self.timeout = timeout
        self.max_bytes = max_bytes
        self.opener = opener or build_opener(_NoRedirect()).open

    def request(self, method, url, headers=None, data=None):
        request = Request(url, data=data, method=method,
                          headers={"Accept": "application/json", **(headers or {})})
        try:
            with self.opener(request, timeout=self.timeout) as response:
                body = response.read(self.max_bytes + 1)
            if len(body) > self.max_bytes:
                raise ValueError("Response exceeded size budget")
            payload = json.loads(body)
            if not isinstance(payload, dict):
                raise ValueError("Expected a JSON object")
            return payload
        except HTTPError as error:
            retry_after = _retry_after(error.headers.get("Retry-After") if error.headers else None)
            # Do not retain or read provider bodies, which can include credentials.
            error.close()
            raise ProviderHttpError(error.code, retry_after) from None
        except (URLError, TimeoutError, OSError, ValueError) as error:
            raise MusicProviderError("music_provider_unavailable",
                                     "The music provider is unavailable. Try again shortly.", 503) from None
