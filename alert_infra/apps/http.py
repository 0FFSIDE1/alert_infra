"""Small HTTP helpers for webhook transports."""

from __future__ import annotations

import urllib.error
import urllib.request
from typing import Any, Protocol
from urllib.parse import urlparse

from alert_infra.exceptions import AlertConfigurationError, AlertDeliveryError


class HttpClient(Protocol):
    def post(self, url: str, *, json: dict[str, Any], headers: dict[str, str] | None = None, timeout: float) -> Any:
        """Post JSON to ``url``."""


def validate_https_url(url: str, *, field_name: str = "url") -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise AlertConfigurationError(f"{field_name} must be an absolute https URL")
    return url


class UrllibHttpClient:
    """Minimal JSON POST client to avoid mandatory third-party dependencies."""

    def post(self, url: str, *, json: dict[str, Any], headers: dict[str, str] | None = None, timeout: float) -> int:
        body = __import__("json").dumps(json).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json", **(headers or {})},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - URL is validated by transports.
                status = int(response.getcode())
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise AlertDeliveryError("HTTP alert delivery failed") from exc
        if status >= 400:
            raise AlertDeliveryError(f"HTTP alert delivery failed with status {status}")
        return status
