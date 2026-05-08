from __future__ import annotations

import pytest
from django.test import override_settings

from alert_infra import NoOpTransport, REDACTED
from alert_infra.django import build_dispatcher, get_alert_infra_settings, request_metadata, send_alert
from alert_infra.django import DjangoEmailTransport
from alert_infra.email import SMTPEmailTransport
from alert_infra.exceptions import AlertConfigurationError


def test_django_settings_loading_merges_defaults() -> None:
    with override_settings(ALERT_INFRA={"ENABLED": True, "SLACK": {"ENABLED": False}}):
        cfg = get_alert_infra_settings()

    assert cfg["ENABLED"] is True
    assert cfg["DEFAULT_SEVERITY"] == "error"
    assert cfg["SLACK"]["ENABLED"] is False


def test_disabled_alerting_mode_uses_disabled_dispatcher() -> None:
    dispatcher = build_dispatcher({"ENABLED": False})

    assert dispatcher.enabled is False
    assert isinstance(dispatcher.transports[0], NoOpTransport)


def test_build_dispatcher_with_django_email_settings() -> None:
    dispatcher = build_dispatcher(
        {
            "ENABLED": True,
            "EMAIL": {"ENABLED": True, "FROM_EMAIL": "alerts@example.com", "TO_EMAILS": ["ops@example.com"]},
            "SLACK": {"ENABLED": False},
            "TELEGRAM": {"ENABLED": False},
        }
    )

    assert isinstance(dispatcher.transports[0], DjangoEmailTransport)


def test_build_dispatcher_with_smtp_email_settings() -> None:
    dispatcher = build_dispatcher(
        {
            "ENABLED": True,
            "EMAIL": {
                "ENABLED": True,
                "BACKEND": "smtp",
                "SMTP_HOST": "smtp.example.com",
                "FROM_EMAIL": "alerts@example.com",
                "TO_EMAILS": ["ops@example.com"],
            },
            "SLACK": {"ENABLED": False},
            "TELEGRAM": {"ENABLED": False},
        }
    )

    assert isinstance(dispatcher.transports[0], SMTPEmailTransport)


def test_build_dispatcher_missing_credentials() -> None:
    with pytest.raises(AlertConfigurationError):
        build_dispatcher({"ENABLED": True, "EMAIL": {"ENABLED": True}, "SLACK": {"ENABLED": False}, "TELEGRAM": {"ENABLED": False}})


class User:
    id = 7


class Request:
    method = "POST"
    path = "/invoices/1/"
    user = User()
    headers = {"Authorization": "Bearer secret", "X-Api-Key": "secret-key", "Accept": "application/json"}
    META = {"HTTP_X_REQUEST_ID": "req-123"}


def test_request_metadata_redacts_sensitive_headers() -> None:
    metadata = request_metadata(Request())

    assert metadata["headers"]["Authorization"] == REDACTED
    assert metadata["headers"]["X-Api-Key"] == REDACTED
    assert "Accept" not in metadata.get("headers", {})


def test_send_alert_redacts_sensitive_metadata_with_disabled_mode() -> None:
    with override_settings(ALERT_INFRA={"ENABLED": False, "REDACT_SENSITIVE_DATA": True}):
        result = send_alert(
            title="Suspicious invoice update",
            message="Blocked",
            severity="warning",
            source="invoice",
            metadata={"invoice_id": "INV-001", "authorization": "Bearer secret"},
            request=Request(),
        )

    assert result.sent == ()
