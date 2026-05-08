"""Email alert transports."""

from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from typing import Callable, Sequence

from alert_infra.alert import Alert
from alert_infra.exceptions import AlertConfigurationError, AlertDeliveryError

EmailSender = Callable[[Sequence[str], str, str, str], None]


def _split_emails(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def format_alert_subject(alert: Alert) -> str:
    return f"[{alert.severity.upper()}] {alert.title}"


def format_alert_body(alert: Alert) -> str:
    lines = [
        format_alert_subject(alert),
        "",
        alert.message,
        "",
        f"Source: {alert.source or 'unknown'}",
        f"Created at: {alert.created_at.isoformat()}",
        f"Correlation ID: {alert.correlation_id}",
    ]
    if alert.request_id:
        lines.append(f"Request ID: {alert.request_id}")
    if alert.tags:
        lines.append(f"Tags: {', '.join(alert.tags)}")
    if alert.metadata:
        lines.extend(["", "Metadata:"])
        lines.extend(f"- {key}: {value}" for key, value in alert.metadata.items())
    return "\n".join(lines)


class SMTPEmailTransport:
    """SMTP transport with injectable sender for tests and custom delivery."""

    name = "email.smtp"

    def __init__(
        self,
        *,
        host: str,
        port: int = 587,
        from_email: str,
        to_emails: Sequence[str],
        username: str | None = None,
        password: str | None = None,
        use_tls: bool = True,
        timeout: float = 8.0,
        sender: EmailSender | None = None,
    ) -> None:
        if not host:
            raise AlertConfigurationError("SMTP host is required")
        if not from_email:
            raise AlertConfigurationError("from_email is required")
        if not to_emails:
            raise AlertConfigurationError("at least one recipient is required")
        self.host = host
        self.port = int(port)
        self.from_email = from_email
        self.to_emails = list(to_emails)
        self.username = username
        self.password = password
        self.use_tls = use_tls
        self.timeout = timeout
        self.sender = sender or self._send_via_smtp

    @classmethod
    def from_env(cls, *, prefix: str = "ALERT_SMTP_", **kwargs: object) -> "SMTPEmailTransport":
        host = os.getenv(f"{prefix}HOST")
        from_email = os.getenv("ALERT_FROM_EMAIL") or os.getenv(f"{prefix}FROM_EMAIL")
        to_emails = _split_emails(os.getenv("ALERT_TO_EMAILS") or os.getenv(f"{prefix}TO_EMAILS"))
        if not host:
            raise AlertConfigurationError(f"{prefix}HOST is required")
        return cls(
            host=host,
            port=int(os.getenv(f"{prefix}PORT", "587")),
            from_email=from_email or "",
            to_emails=to_emails,
            username=os.getenv(f"{prefix}USERNAME"),
            password=os.getenv(f"{prefix}PASSWORD"),
            use_tls=os.getenv(f"{prefix}USE_TLS", "true").lower() not in {"0", "false", "no"},
            **kwargs,
        )

    def _send_via_smtp(self, recipients: Sequence[str], subject: str, body: str, html: str) -> None:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = self.from_email
        msg["To"] = ", ".join(recipients)
        msg.set_content(body)
        msg.add_alternative(html, subtype="html")
        with smtplib.SMTP(self.host, self.port, timeout=self.timeout) as server:
            if self.use_tls:
                server.starttls()
            if self.username and self.password:
                server.login(self.username, self.password)
            server.send_message(msg)

    def send(self, alert: Alert) -> None:
        subject = format_alert_subject(alert)
        body = format_alert_body(alert)
        html = "<br>".join(body.splitlines())
        try:
            self.sender(self.to_emails, subject, body, html)
        except Exception as exc:  # noqa: BLE001
            raise AlertDeliveryError("SMTP email alert delivery failed") from exc
