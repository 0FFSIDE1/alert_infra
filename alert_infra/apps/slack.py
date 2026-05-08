"""Slack webhook alert transport."""

from __future__ import annotations

import os
from typing import Any

from alert_infra.alert import Alert
from alert_infra.exceptions import AlertConfigurationError, AlertDeliveryError
from .http import HttpClient, UrllibHttpClient, validate_https_url


class SlackWebhookTransport:
    """Send alerts to Slack using an incoming webhook URL."""

    name = "slack"

    def __init__(self, webhook_url: str, *, timeout: float = 5.0, http_client: HttpClient | None = None) -> None:
        if not webhook_url:
            raise AlertConfigurationError("Slack webhook_url is required")
        self.webhook_url = validate_https_url(webhook_url, field_name="Slack webhook_url")
        self.timeout = timeout
        self.http_client = http_client or UrllibHttpClient()

    @classmethod
    def from_env(cls, *, env_var: str = "ALERT_SLACK_WEBHOOK_URL", **kwargs: Any) -> "SlackWebhookTransport":
        value = os.getenv(env_var)
        if not value:
            raise AlertConfigurationError(f"{env_var} is required")
        return cls(value, **kwargs)

    def build_payload(self, alert: Alert) -> dict[str, Any]:
        data = alert.to_dict()
        return {
            "text": f"[{alert.severity.upper()}] {alert.title}",
            "blocks": [
                {"type": "section", "text": {"type": "mrkdwn", "text": f"*[{alert.severity.upper()}] {alert.title}*\n{alert.message}"}},
                {"type": "section", "text": {"type": "mrkdwn", "text": f"```{data}```"}},
            ],
            "metadata": data,
        }

    def send(self, alert: Alert) -> None:
        try:
            self.http_client.post(self.webhook_url, json=self.build_payload(alert), timeout=self.timeout)
        except Exception as exc:  # noqa: BLE001
            if isinstance(exc, AlertDeliveryError):
                raise
            raise AlertDeliveryError("Slack alert delivery failed") from exc
