"""Transport protocols and dispatching primitives."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Protocol, Sequence, runtime_checkable

from .alert import Alert
from .exceptions import AlertDeliveryError, NonRetryableAlertTransportError, RetryableAlertTransportError

logger = logging.getLogger(__name__)


@runtime_checkable
class AlertTransport(Protocol):
    """Protocol implemented by all alert transports."""

    name: str

    def send(self, alert: Alert) -> None:
        """Send an alert or raise an exception on delivery failure."""


@dataclass(frozen=True)
class DeliveryResult:
    """Result of dispatching an alert to multiple transports."""

    sent: tuple[str, ...] = field(default_factory=tuple)
    failed: dict[str, str] = field(default_factory=dict)
    retryable: tuple[str, ...] = field(default_factory=tuple)
    non_retryable: tuple[str, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        return not self.failed


class NoOpTransport:
    """Transport for tests, development, and disabled alerting mode."""

    name = "noop"

    def __init__(self) -> None:
        self.alerts: list[Alert] = []

    def send(self, alert: Alert) -> None:
        self.alerts.append(alert)


def is_retryable_exception(exc: Exception) -> bool:
    """Return whether ``exc`` represents a retryable transport failure."""
    if isinstance(exc, NonRetryableAlertTransportError):
        return False
    if isinstance(exc, (RetryableAlertTransportError, AlertDeliveryError)):
        return True
    return isinstance(exc, (TimeoutError, ConnectionError, OSError))


class AlertDispatcher:
    """Dispatch alerts to one or more transports.

    Delivery failures are isolated per transport. By default dispatching fails
    safely and returns a result object; set ``raise_on_failure=True`` to raise
    after all transports have been attempted.
    """

    def __init__(
        self,
        transports: Sequence[AlertTransport] | None = None,
        *,
        enabled: bool = True,
        raise_on_failure: bool = False,
        logger_: logging.Logger | None = None,
    ) -> None:
        self.transports = list(transports or [])
        self.enabled = enabled
        self.raise_on_failure = raise_on_failure
        self.logger = logger_ or logger

    def send(self, alert: Alert, transport_names: Sequence[str] | None = None) -> DeliveryResult:
        if not self.enabled:
            self.logger.debug("alert dispatch skipped because alerting is disabled")
            return DeliveryResult()

        selected = set(transport_names or [])
        sent: list[str] = []
        failed: dict[str, str] = {}
        retryable: list[str] = []
        non_retryable: list[str] = []
        for transport in self.transports:
            name = getattr(transport, "name", transport.__class__.__name__)
            if selected and name not in selected:
                continue
            try:
                transport.send(alert)
                sent.append(name)
            except Exception as exc:  # noqa: BLE001 - dispatcher intentionally isolates transports.
                failed[name] = exc.__class__.__name__
                if is_retryable_exception(exc):
                    retryable.append(name)
                else:
                    non_retryable.append(name)
                self.logger.warning("alert transport %s failed: %s", name, exc.__class__.__name__)

        result = DeliveryResult(sent=tuple(sent), failed=failed, retryable=tuple(retryable), non_retryable=tuple(non_retryable))
        if failed and self.raise_on_failure:
            raise AlertDeliveryError(f"alert delivery failed for: {', '.join(failed)}")
        return result
