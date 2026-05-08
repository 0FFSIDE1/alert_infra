"""Django email backend transport."""

from __future__ import annotations

from typing import Sequence

from alert_infra.alert import Alert
from alert_infra.email.transports import format_alert_body, format_alert_subject
from alert_infra.exceptions import AlertConfigurationError, AlertDeliveryError


class DjangoEmailTransport:
    """Email transport backed by Django's configured email backend."""

    name = "email.django"

    def __init__(self, *, from_email: str, to_emails: Sequence[str], timeout: float = 8.0) -> None:
        if not from_email:
            raise AlertConfigurationError("from_email is required")
        if not to_emails:
            raise AlertConfigurationError("at least one recipient is required")
        self.from_email = from_email
        self.to_emails = list(to_emails)
        self.timeout = timeout

    def send(self, alert: Alert) -> None:
        try:
            from django.core.mail import EmailMultiAlternatives
        except ImportError as exc:  # pragma: no cover - covered in environments without django.
            raise AlertConfigurationError("Django is required for DjangoEmailTransport") from exc

        subject = format_alert_subject(alert)
        body = format_alert_body(alert)
        email = EmailMultiAlternatives(subject, body, self.from_email, self.to_emails)
        email.attach_alternative("<br>".join(body.splitlines()), "text/html")
        try:
            email.send(fail_silently=False)
        except Exception as exc:  # noqa: BLE001
            raise AlertDeliveryError("Django email alert delivery failed") from exc
