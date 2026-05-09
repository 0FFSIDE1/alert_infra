"""Exceptions raised by alert_infra."""

from __future__ import annotations


class AlertInfraError(Exception):
    """Base exception for alert infrastructure failures."""


class AlertValidationError(ValueError, AlertInfraError):
    """Raised when an alert payload is invalid."""


class AlertConfigError(AlertInfraError):
    """Raised when alerting or a transport is configured unsafely."""


class AlertTransportError(AlertInfraError):
    """Base class for transport delivery failures."""


class AlertDeliveryError(AlertTransportError):
    """Backward-compatible base delivery error name."""


class RetryableAlertTransportError(AlertDeliveryError):
    """Raised for transient transport failures that are safe to retry."""


class NonRetryableAlertTransportError(AlertDeliveryError):
    """Raised for permanent transport failures that should not be retried."""


class AlertConfigurationError(AlertConfigError, NonRetryableAlertTransportError):
    """Backward-compatible configuration error name."""
