"""Django email backend transport."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from alert_infra.alert import Alert
from alert_infra.email.transports import format_alert_body, format_alert_subject
from alert_infra.exceptions import AlertConfigurationError, RetryableAlertTransportError


class DjangoEmailTransport:
    """Email transport backed by Django's configured email backend.

    Optional Django template names may be supplied for the subject, plain-text
    body, and HTML body. Templates are rendered with ``alert``, ``alert_dict``,
    and any configured ``template_context`` values.
    """

    name = "email.django"

    def __init__(
        self,
        *,
        from_email: str,
        to_emails: Sequence[str],
        timeout: float = 8.0,
        subject_template_name: str | None = None,
        body_template_name: str | None = None,
        html_template_name: str | None = None,
        template_context: Mapping[str, Any] | None = None,
    ) -> None:
        if not from_email:
            raise AlertConfigurationError("from_email is required")
        if not to_emails:
            raise AlertConfigurationError("at least one recipient is required")
        self.from_email = from_email
        self.to_emails = list(to_emails)
        self.timeout = timeout
        self.subject_template_name = subject_template_name
        self.body_template_name = body_template_name
        self.html_template_name = html_template_name
        self.template_context = dict(template_context or {})

    def _template_context(self, alert: Alert) -> dict[str, Any]:
        alert_dict = alert.to_dict()
        return {
            **self.template_context,
            "alert": alert,
            "alert_dict": alert_dict,
            "metadata": alert_dict["metadata"],
            "tags": alert_dict["tags"],
        }

    def _render_email(self, alert: Alert) -> tuple[str, str, str]:
        try:
            from django.template.loader import render_to_string
        except ImportError as exc:  # pragma: no cover - covered in environments without django.
            raise AlertConfigurationError("Django is required for DjangoEmailTransport") from exc

        context = self._template_context(alert)

        if self.subject_template_name:
            subject = " ".join(render_to_string(self.subject_template_name, context).splitlines()).strip()
        else:
            subject = format_alert_subject(alert)

        if self.body_template_name:
            body = render_to_string(self.body_template_name, context).strip()
        else:
            body = format_alert_body(alert)

        if self.html_template_name:
            html = render_to_string(self.html_template_name, context).strip()
        else:
            html = "<br>".join(body.splitlines())

        return subject, body, html

    def send(self, alert: Alert) -> None:
        try:
            from django.core.mail import EmailMultiAlternatives
        except ImportError as exc:  # pragma: no cover - covered in environments without django.
            raise AlertConfigurationError("Django is required for DjangoEmailTransport") from exc

        subject, body, html = self._render_email(alert)
        email = EmailMultiAlternatives(subject, body, self.from_email, self.to_emails)
        email.attach_alternative(html, "text/html")
        try:
            email.send(fail_silently=False)
        except Exception as exc:  # noqa: BLE001
            raise RetryableAlertTransportError("Django email alert delivery failed") from exc
