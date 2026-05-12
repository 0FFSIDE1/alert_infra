"""Telegram bot alert transport."""

from __future__ import annotations

import os
from typing import Any

from alert_infra.alert import Alert
from alert_infra.exceptions import AlertConfigurationError, AlertTransportError, RetryableAlertTransportError
from .http import HttpClient, UrllibHttpClient, validate_https_url


class TelegramBotTransport:
    """Send alerts through the Telegram Bot API."""

    name = "telegram"

    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        *,
        timeout: float = 5.0,
        api_base_url: str = "https://api.telegram.org",
        http_client: HttpClient | None = None,
    ) -> None:
        if not bot_token:
            raise AlertConfigurationError("Telegram bot_token is required")
        if not chat_id:
            raise AlertConfigurationError("Telegram chat_id is required")
        self.bot_token = bot_token
        self.chat_id = str(chat_id)
        self.timeout = timeout
        self.api_base_url = validate_https_url(api_base_url.rstrip("/"), field_name="Telegram api_base_url")
        self.http_client = http_client or UrllibHttpClient()

    @classmethod
    def from_env(
        cls,
        *,
        token_env: str = "ALERT_TELEGRAM_BOT_TOKEN",
        chat_env: str = "ALERT_TELEGRAM_CHAT_ID",
        **kwargs: Any,
    ) -> "TelegramBotTransport":
        token = os.getenv(token_env)
        chat_id = os.getenv(chat_env)
        if not token:
            raise AlertConfigurationError(f"{token_env} is required")
        if not chat_id:
            raise AlertConfigurationError(f"{chat_env} is required")
        return cls(token, chat_id, **kwargs)

    @property
    def url(self) -> str:
        return f"{self.api_base_url}/bot{self.bot_token}/sendMessage"

    def build_payload(self, alert: Alert) -> dict[str, Any]:
        return {
            "chat_id": self.chat_id,
            "text": f"[{alert.severity.upper()}] {alert.title}\n{alert.message}\nSource: {alert.source or 'unknown'}\nRequest ID: {alert.request_id}",
            "disable_web_page_preview": True,
        }

    def send(self, alert: Alert) -> None:
        try:
            self.http_client.post(self.url, json=self.build_payload(alert), timeout=self.timeout)
        except Exception as exc:  # noqa: BLE001
            if isinstance(exc, AlertTransportError):
                raise
            raise RetryableAlertTransportError("Telegram alert delivery failed") from exc
