"""Celery tasks for Django-configured alert dispatch."""

from __future__ import annotations

import logging
import random
from typing import Any, Sequence

from alert_infra.alert import Alert
from alert_infra.celery import DEFAULT_MAX_RETRIES, DEFAULT_RETRY_BACKOFF_MAX
from alert_infra.django.config import build_dispatcher

logger = logging.getLogger(__name__)


def _retry_countdown(retries: int, options: dict[str, Any]) -> int:
    backoff = options.get("RETRY_BACKOFF", True)
    max_countdown = int(options.get("RETRY_BACKOFF_MAX", DEFAULT_RETRY_BACKOFF_MAX))
    if backoff is True:
        countdown = min(2 ** max(retries, 0), max_countdown)
    elif isinstance(backoff, int) and backoff > 0:
        countdown = min(backoff * (2 ** max(retries, 0)), max_countdown)
    else:
        countdown = min(60, max_countdown)
    if options.get("RETRY_JITTER", True):
        countdown = random.randint(0, max(1, countdown))
    return countdown


def _dispatch_alert(alert_payload: dict[str, Any], transport_names: Sequence[str] | None = None) -> Any:
    alert = Alert.from_dict(alert_payload)
    return build_dispatcher().send(alert, transport_names=transport_names)

try:
    from celery import shared_task  # type: ignore
except ImportError:  # pragma: no cover
    shared_task = None  # type: ignore[assignment]


if shared_task is not None:

    @shared_task(bind=True, name="alert_infra.dispatch_alert")
    def dispatch_alert_task(
        self: Any,
        alert_payload: dict[str, Any],
        transport_names: Sequence[str] | None = None,
        async_options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        options = async_options or {}
        result = _dispatch_alert(alert_payload, transport_names=transport_names)
        if result.retryable:
            max_retries = int(options.get("MAX_RETRIES", DEFAULT_MAX_RETRIES))
            retries = int(getattr(getattr(self, "request", None), "retries", 0))
            if retries < max_retries:
                logger.warning("retrying alert dispatch for transports: %s", ", ".join(result.retryable))
                raise self.retry(
                    args=(),
                    kwargs={
                        "alert_payload": alert_payload,
                        "transport_names": list(result.retryable),
                        "async_options": options,
                    },
                    countdown=_retry_countdown(retries, options),
                    max_retries=max_retries,
                )
            logger.warning("alert dispatch retries exhausted for transports: %s", ", ".join(result.retryable))
        return {
            "sent": list(result.sent),
            "failed": result.failed,
            "retryable": list(result.retryable),
            "non_retryable": list(result.non_retryable),
        }
else:

    def dispatch_alert_task(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("Celery is required to run alert_infra.dispatch_alert")
