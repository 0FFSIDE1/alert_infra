"""Django settings adapter for alert_infra."""

from __future__ import annotations

import os
from typing import Any

from alert_infra import AlertDispatcher, NoOpTransport
from alert_infra.apps import SlackWebhookTransport, TelegramBotTransport
from alert_infra.email import SMTPEmailTransport
from .email import DjangoEmailTransport

DEFAULTS: dict[str, Any] = {
    "ENABLED": True,
    "DEFAULT_SEVERITY": "error",
    "REDACT_SENSITIVE_DATA": True,
    "EMAIL": {
        "ENABLED": False,
        "BACKEND": "django",
        "SUBJECT_TEMPLATE": None,
        "BODY_TEMPLATE": None,
        "HTML_TEMPLATE": None,
        "TEMPLATE_CONTEXT": {},
    },
    "SLACK": {"ENABLED": False},
    "TELEGRAM": {"ENABLED": False},
}


def _get_django_settings():
    from django.conf import settings

    return settings


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = {**base}
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def get_alert_infra_settings() -> dict[str, Any]:
    settings = _get_django_settings()
    configured = getattr(settings, "ALERT_INFRA", None)
    if configured is None:
        configured = getattr(settings, "FEATURE_FLAG_INFRA", {})
    return _merge(DEFAULTS, configured or {})


def _list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return [str(item) for item in value]


def build_dispatcher(config: dict[str, Any] | None = None) -> AlertDispatcher:
    cfg = config or get_alert_infra_settings()
    if not cfg.get("ENABLED", True):
        return AlertDispatcher([NoOpTransport()], enabled=False)

    transports = []
    email = cfg.get("EMAIL", {}) or {}
    if email.get("ENABLED"):
        from_email = email.get("FROM_EMAIL") or os.getenv("ALERT_FROM_EMAIL")
        to_emails = _list(email.get("TO_EMAILS") or os.getenv("ALERT_TO_EMAILS"))
        backend = str(email.get("BACKEND", "django")).lower()
        if backend == "smtp" or email.get("SMTP_HOST") or os.getenv("ALERT_SMTP_HOST"):
            transports.append(
                SMTPEmailTransport(
                    host=email.get("SMTP_HOST") or os.getenv("ALERT_SMTP_HOST", ""),
                    port=int(email.get("SMTP_PORT") or os.getenv("ALERT_SMTP_PORT", "587")),
                    from_email=from_email or "",
                    to_emails=to_emails,
                    username=email.get("SMTP_USERNAME") or os.getenv("ALERT_SMTP_USERNAME"),
                    password=email.get("SMTP_PASSWORD") or os.getenv("ALERT_SMTP_PASSWORD"),
                    use_tls=bool(email.get("SMTP_USE_TLS", True)),
                    timeout=float(email.get("TIMEOUT", 8.0)),
                )
            )
        else:
            transports.append(
                DjangoEmailTransport(
                    from_email=from_email or "",
                    to_emails=to_emails,
                    timeout=float(email.get("TIMEOUT", 8.0)),
                    subject_template_name=email.get("SUBJECT_TEMPLATE") or email.get("SUBJECT_TEMPLATE_NAME"),
                    body_template_name=email.get("BODY_TEMPLATE") or email.get("BODY_TEMPLATE_NAME"),
                    html_template_name=email.get("HTML_TEMPLATE") or email.get("HTML_TEMPLATE_NAME"),
                    template_context=email.get("TEMPLATE_CONTEXT"),
                )
            )

    slack = cfg.get("SLACK", {}) or {}
    if slack.get("ENABLED"):
        webhook_url = slack.get("WEBHOOK_URL") or os.getenv("ALERT_SLACK_WEBHOOK_URL")
        transports.append(SlackWebhookTransport(webhook_url or "", timeout=float(slack.get("TIMEOUT", 5.0))))

    telegram = cfg.get("TELEGRAM", {}) or {}
    if telegram.get("ENABLED"):
        bot_token = telegram.get("BOT_TOKEN") or os.getenv("ALERT_TELEGRAM_BOT_TOKEN")
        chat_id = telegram.get("CHAT_ID") or os.getenv("ALERT_TELEGRAM_CHAT_ID")
        transports.append(TelegramBotTransport(bot_token or "", chat_id or "", timeout=float(telegram.get("TIMEOUT", 5.0))))

    if not transports:
        transports.append(NoOpTransport())
    return AlertDispatcher(transports, enabled=True)
