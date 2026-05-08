"""Exceptions raised by alert_infra."""


class AlertInfraError(Exception):
    """Base exception for alert infrastructure failures."""


class AlertValidationError(ValueError, AlertInfraError):
    """Raised when an alert or transport configuration is invalid."""


class AlertConfigurationError(AlertInfraError):
    """Raised when a transport cannot be configured safely."""


class AlertDeliveryError(AlertInfraError):
    """Raised when a transport fails to deliver an alert."""
