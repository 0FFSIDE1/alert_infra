"""Public API for framework-agnostic alerting."""

from .alert import Alert, VALID_SEVERITIES
from .exceptions import AlertConfigurationError, AlertDeliveryError, AlertInfraError, AlertValidationError
from .security import REDACTED, SENSITIVE_KEYWORDS, redact_metadata
from .transports import AlertDispatcher, AlertTransport, DeliveryResult, NoOpTransport

__all__ = [
    "Alert",
    "AlertConfigurationError",
    "AlertDeliveryError",
    "AlertDispatcher",
    "AlertInfraError",
    "AlertTransport",
    "AlertValidationError",
    "DeliveryResult",
    "NoOpTransport",
    "REDACTED",
    "SENSITIVE_KEYWORDS",
    "VALID_SEVERITIES",
    "redact_metadata",
]
