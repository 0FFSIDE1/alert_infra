"""Public API for framework-agnostic alerting."""

from .alert import Alert, VALID_SEVERITIES
from .exceptions import (
    AlertConfigError,
    AlertConfigurationError,
    AlertDeliveryError,
    AlertInfraError,
    AlertTransportError,
    AlertValidationError,
    NonRetryableAlertTransportError,
    RetryableAlertTransportError,
)
from .security import REDACTED, SENSITIVE_KEYWORDS, redact_metadata
from .transports import AlertDispatcher, AlertTransport, DeliveryResult, NoOpTransport

__all__ = [
    "Alert",
    "AlertConfigError",
    "AlertConfigurationError",
    "AlertDeliveryError",
    "AlertDispatcher",
    "AlertInfraError",
    "AlertTransport",
    "AlertTransportError",
    "AlertValidationError",
    "NonRetryableAlertTransportError",
    "RetryableAlertTransportError",
    "DeliveryResult",
    "NoOpTransport",
    "REDACTED",
    "SENSITIVE_KEYWORDS",
    "VALID_SEVERITIES",
    "redact_metadata",
]
