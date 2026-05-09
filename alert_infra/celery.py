"""Optional Celery-backed alert dispatching primitives.

This module does not require Django. Celery is imported lazily unless a caller
passes an app or task object explicitly.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Sequence

from .alert import Alert
from .exceptions import AlertConfigError
from .transports import DeliveryResult

logger = logging.getLogger(__name__)

DEFAULT_TASK_NAME = "alert_infra.dispatch_alert"
DEFAULT_QUEUE = "alerts"
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_BACKOFF_MAX = 300


@dataclass(frozen=True)
class AsyncAlertConfig:
    enabled: bool = False
    backend: str = "celery"
    task_name: str = DEFAULT_TASK_NAME
    queue: str | None = DEFAULT_QUEUE
    max_retries: int = DEFAULT_MAX_RETRIES
    retry_backoff: bool | int = True
    retry_backoff_max: int = DEFAULT_RETRY_BACKOFF_MAX
    retry_jitter: bool = True
    fail_silently: bool = True


def normalize_async_config(config: dict[str, Any] | None) -> AsyncAlertConfig:
    cfg = config or {}
    return AsyncAlertConfig(
        enabled=bool(cfg.get("ENABLED", False)),
        backend=str(cfg.get("BACKEND", "celery")).lower(),
        task_name=str(cfg.get("TASK_NAME", DEFAULT_TASK_NAME)),
        queue=cfg.get("QUEUE", DEFAULT_QUEUE),
        max_retries=int(cfg.get("MAX_RETRIES", DEFAULT_MAX_RETRIES)),
        retry_backoff=cfg.get("RETRY_BACKOFF", True),
        retry_backoff_max=int(cfg.get("RETRY_BACKOFF_MAX", DEFAULT_RETRY_BACKOFF_MAX)),
        retry_jitter=bool(cfg.get("RETRY_JITTER", True)),
        fail_silently=bool(cfg.get("FAIL_SILENTLY", True)),
    )


class CeleryAlertDispatcher:
    """Dispatcher that enqueues sanitized alert payloads on a Celery task."""

    def __init__(
        self,
        *,
        celery_app: Any | None = None,
        task: Any | None = None,
        config: AsyncAlertConfig | dict[str, Any] | None = None,
    ) -> None:
        self.celery_app = celery_app
        self.task = task
        self.config = config if isinstance(config, AsyncAlertConfig) else normalize_async_config(config)
        if self.config.backend != "celery":
            raise AlertConfigError(f"unsupported async alert backend: {self.config.backend}")

    def send(self, alert: Alert, transport_names: Sequence[str] | None = None) -> DeliveryResult:
        payload = alert.to_dict()
        kwargs = {
            "transport_names": list(transport_names) if transport_names else None,
            "async_options": {
                "MAX_RETRIES": self.config.max_retries,
                "RETRY_BACKOFF": self.config.retry_backoff,
                "RETRY_BACKOFF_MAX": self.config.retry_backoff_max,
                "RETRY_JITTER": self.config.retry_jitter,
            },
        }
        try:
            if self.task is not None:
                self.task.apply_async(args=[payload], kwargs=kwargs, queue=self.config.queue)
            elif self.celery_app is not None:
                self.celery_app.send_task(self.config.task_name, args=[payload], kwargs=kwargs, queue=self.config.queue)
            else:
                try:
                    from celery import current_app  # type: ignore
                except ImportError as exc:  # pragma: no cover - exercised by monkeypatch tests.
                    raise AlertConfigError("Celery is not installed; install alert-infra[celery] or disable ALERT_INFRA['ASYNC']") from exc
                current_app.send_task(self.config.task_name, args=[payload], kwargs=kwargs, queue=self.config.queue)
        except Exception as exc:  # noqa: BLE001
            if self.config.fail_silently:
                logger.warning("alert enqueue failed: %s", exc.__class__.__name__)
                return DeliveryResult(failed={"celery": exc.__class__.__name__}, non_retryable=("celery",))
            if isinstance(exc, AlertConfigError):
                raise
            raise AlertConfigError("Celery alert dispatcher is not configured") from exc
        return DeliveryResult(sent=("celery",))


AsyncAlertDispatcher = CeleryAlertDispatcher
