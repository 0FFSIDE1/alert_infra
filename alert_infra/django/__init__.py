"""Django integration public API."""

from __future__ import annotations

from typing import Any, Mapping

from alert_infra import Alert
from alert_infra.transports import DeliveryResult
from .config import build_async_dispatcher, build_dispatcher, get_alert_infra_settings
from .email import DjangoEmailTransport
from .context import request_metadata


def send_alert(
    *,
    title: str,
    message: str,
    severity: str | None = None,
    source: str | None = None,
    tags: tuple[str, ...] | list[str] = (),
    metadata: Mapping[str, Any] | None = None,
    request: Any | None = None,
    request_id: str | None = None
) -> DeliveryResult:
    """Send an alert using transports configured in Django settings."""
    cfg = get_alert_infra_settings()
    merged_metadata: dict[str, Any] = dict(metadata or {})

    if request is not None:
        request_meta = request_metadata(request)
        request_meta_id = request_meta.get("request_id")
        merged_metadata["request"] = request_meta
    else:
        request_meta_id = request_id


    alert = Alert(
        title=title,
        message=message,
        severity=severity or cfg.get("DEFAULT_SEVERITY", "error"),
        source=source,
        tags=tuple(tags),
        metadata=merged_metadata,
        request_id=request_meta_id if request_meta_id is not None else request_id,
        redact_sensitive_data=bool(cfg.get("REDACT_SENSITIVE_DATA", True)),
    )
    async_cfg = cfg.get("ASYNC", {}) or {}
    if cfg.get("ENABLED", True) and async_cfg.get("ENABLED"):
        return build_async_dispatcher(cfg).send(alert)
    return build_dispatcher(cfg).send(alert)


__all__ = [
    "DjangoEmailTransport",
    "build_async_dispatcher",
    "build_dispatcher",
    "get_alert_infra_settings",
    "request_metadata",
    "send_alert",
]
