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


@pytest.mark.parametrize("backend", ["resend", "sendgrid"])
def test_build_dispatcher_rejects_legacy_email_provider_names(backend: str) -> None:
    with pytest.raises(AlertConfigurationError, match="supported alert email backends"):
        build_dispatcher(
            {
                "ENABLED": True,
                "EMAIL": {
                    "ENABLED": True,
                    "BACKEND": backend,
                    "FROM_EMAIL": "alerts@example.com",
                    "TO_EMAILS": ["ops@example.com"],
                },
                "SLACK": {"ENABLED": False},
                "TELEGRAM": {"ENABLED": False},
            }
        )


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


def test_build_dispatcher_passes_django_email_templates() -> None:
    dispatcher = build_dispatcher(
        {
            "ENABLED": True,
            "EMAIL": {
                "ENABLED": True,
                "FROM_EMAIL": "alerts@example.com",
                "TO_EMAILS": ["ops@example.com"],
                "SUBJECT_TEMPLATE": "alerts/subject.txt",
                "BODY_TEMPLATE": "alerts/body.txt",
                "HTML_TEMPLATE": "alerts/body.html",
                "TEMPLATE_CONTEXT": {"product_name": "Billing"},
            },
            "SLACK": {"ENABLED": False},
            "TELEGRAM": {"ENABLED": False},
        }
    )

    transport = dispatcher.transports[0]

    assert isinstance(transport, DjangoEmailTransport)
    assert transport.subject_template_name == "alerts/subject.txt"
    assert transport.body_template_name == "alerts/body.txt"
    assert transport.html_template_name == "alerts/body.html"
    assert transport.template_context == {"product_name": "Billing"}


def test_django_email_transport_renders_templates() -> None:
    from django.core import mail

    from alert_infra import Alert

    template_settings = {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": False,
        "OPTIONS": {
            "loaders": [
                (
                    "django.template.loaders.locmem.Loader",
                    {
                        "alerts/subject.txt": "{{ product_name }} {{ alert.severity|upper }} {{ alert.title }}\n",
                        "alerts/body.txt": "{{ alert.message }} for {{ metadata.invoice_id }}",
                        "alerts/body.html": "<strong>{{ alert.title }}</strong>: {{ alert.message }}",
                    },
                )
            ]
        },
    }

    with override_settings(TEMPLATES=[template_settings]):
        transport = DjangoEmailTransport(
            from_email="alerts@example.com",
            to_emails=["ops@example.com"],
            subject_template_name="alerts/subject.txt",
            body_template_name="alerts/body.txt",
            html_template_name="alerts/body.html",
            template_context={"product_name": "Billing"},
        )
        transport.send(
            Alert(
                title="Payment failed",
                message="Provider returned 500",
                severity="critical",
                metadata={"invoice_id": "INV-001"},
            )
        )

    message = mail.outbox[-1]

    assert message.subject == "Billing CRITICAL Payment failed"
    assert message.body == "Provider returned 500 for INV-001"
    assert message.alternatives[0][0] == "<strong>Payment failed</strong>: Provider returned 500"
    assert message.alternatives[0][1] == "text/html"


def test_feature_flag_infra_settings_alias_is_supported() -> None:
    with override_settings(
        ALERT_INFRA=None,
        FEATURE_FLAG_INFRA={
            "ENABLED": True,
            "EMAIL": {"ENABLED": True, "FROM_EMAIL": "alerts@example.com", "TO_EMAILS": ["ops@example.com"]},
        },
    ):
        cfg = get_alert_infra_settings()

    assert cfg["EMAIL"]["ENABLED"] is True
    assert cfg["EMAIL"]["FROM_EMAIL"] == "alerts@example.com"


def test_feature_flag_infra_namespace_reexports_django_helpers() -> None:
    from feature_flag_infra.django import DjangoEmailTransport as FeatureFlagDjangoEmailTransport
    from feature_flag_infra.django import build_dispatcher as feature_flag_build_dispatcher

    assert FeatureFlagDjangoEmailTransport is DjangoEmailTransport
    assert feature_flag_build_dispatcher is build_dispatcher
