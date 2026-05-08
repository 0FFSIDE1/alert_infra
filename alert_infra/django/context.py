"""Helpers for extracting safe Django request context."""

from __future__ import annotations

from typing import Any

from alert_infra.security import redact_metadata

SENSITIVE_HEADERS = {"authorization", "cookie", "x-csrftoken", "x-csrf-token"}


def request_metadata(request: Any) -> dict[str, Any]:
    """Return safe request metadata for alerts.

    Only minimal identifiers are captured. Header values with sensitive names are
    redacted by the core redaction layer.
    """
    headers = {}
    for key in getattr(request, "headers", {}) or {}:
        lowered = str(key).lower()
        if lowered in SENSITIVE_HEADERS or any(part in lowered for part in ("token", "secret", "key")):
            headers[key] = getattr(request, "headers", {}).get(key)

    user = getattr(request, "user", None)
    user_id = getattr(user, "pk", None) or getattr(user, "id", None)
    data = {
        "method": getattr(request, "method", None),
        "path": getattr(request, "path", None),
        "request_id": getattr(request, "request_id", None) or (getattr(request, "META", {}) or {}).get("HTTP_X_REQUEST_ID"),
        "user_id": user_id,
        "headers": headers,
    }
    return redact_metadata({key: value for key, value in data.items() if value not in ({}, None)})
