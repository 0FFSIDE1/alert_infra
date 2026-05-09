from __future__ import annotations

import pytest

from alert_infra import Alert, REDACTED
from alert_infra.apps import SlackWebhookTransport, TelegramBotTransport
from alert_infra.exceptions import AlertConfigurationError, AlertDeliveryError
from alert_infra.email import SMTPEmailTransport


class MockHttpClient:
    def __init__(self, exc: Exception | None = None) -> None:
        self.calls = []
        self.exc = exc

    def post(self, url, *, json, headers=None, timeout):
        self.calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        if self.exc:
            raise self.exc
        return 200


def test_email_transport_uses_injected_sender_and_redacts_metadata() -> None:
    calls = []

    def sender(recipients, subject, body, html):
        calls.append((recipients, subject, body, html))

    transport = SMTPEmailTransport(
        host="smtp.example.com",
        from_email="alerts@example.com",
        to_emails=["ops@example.com"],
        sender=sender,
    )
    alert = Alert(title="Payment failure", message="Failed", metadata={"api_key": "secret"})

    transport.send(alert)

    recipients, subject, body, html = calls[0]
    assert recipients == ["ops@example.com"]
    assert subject == "[ERROR] Payment failure"
    assert REDACTED in body
    assert "secret" not in body
    assert "<br>" in html


def test_email_transport_wraps_sender_failure() -> None:
    def sender(*args, **kwargs):
        raise TimeoutError("smtp timeout")

    transport = SMTPEmailTransport(host="smtp.example.com", from_email="a@example.com", to_emails=["b@example.com"], sender=sender)

    with pytest.raises(AlertDeliveryError):
        transport.send(Alert(title="title", message="body"))


def test_email_transport_missing_credentials() -> None:
    with pytest.raises(AlertConfigurationError):
        SMTPEmailTransport(host="", from_email="a@example.com", to_emails=["b@example.com"])


def test_slack_transport_posts_redacted_payload() -> None:
    client = MockHttpClient()
    transport = SlackWebhookTransport("https://hooks.slack.com/services/test", http_client=client)
    alert = Alert(title="title", message="body", metadata={"authorization": "Bearer secret"})

    transport.send(alert)

    payload = client.calls[0]["json"]
    assert client.calls[0]["url"] == "https://hooks.slack.com/services/test"
    assert payload["metadata"]["metadata"]["authorization"] == REDACTED
    assert "Bearer secret" not in str(payload)


@pytest.mark.parametrize("url", ["http://hooks.slack.com/test", "not-a-url", ""])
def test_invalid_slack_webhook_urls(url: str) -> None:
    with pytest.raises(AlertConfigurationError):
        SlackWebhookTransport(url)


def test_slack_network_failure() -> None:
    transport = SlackWebhookTransport("https://hooks.slack.com/services/test", http_client=MockHttpClient(TimeoutError("timeout")))

    with pytest.raises(AlertDeliveryError):
        transport.send(Alert(title="title", message="body"))


def test_telegram_transport_posts_message_without_leaking_token_in_payload() -> None:
    client = MockHttpClient()
    transport = TelegramBotTransport("123:token", "456", http_client=client)

    transport.send(Alert(title="title", message="body"))

    call = client.calls[0]
    assert call["url"] == "https://api.telegram.org/bot123:token/sendMessage"
    assert call["json"]["chat_id"] == "456"
    assert "123:token" not in str(call["json"])


def test_telegram_missing_credentials() -> None:
    with pytest.raises(AlertConfigurationError):
        TelegramBotTransport("", "456")
    with pytest.raises(AlertConfigurationError):
        TelegramBotTransport("123", "")


def test_telegram_invalid_api_url() -> None:
    with pytest.raises(AlertConfigurationError):
        TelegramBotTransport("123", "456", api_base_url="http://api.telegram.org")


def test_telegram_timeout_failure() -> None:
    transport = TelegramBotTransport("123", "456", http_client=MockHttpClient(TimeoutError("timeout")))

    with pytest.raises(AlertDeliveryError):
        transport.send(Alert(title="title", message="body"))


def test_slack_5xx_failure_is_retryable() -> None:
    from alert_infra.exceptions import RetryableAlertTransportError

    transport = SlackWebhookTransport(
        "https://hooks.slack.com/services/test",
        http_client=MockHttpClient(RetryableAlertTransportError("HTTP alert delivery failed with status 503")),
    )

    with pytest.raises(RetryableAlertTransportError):
        transport.send(Alert(title="title", message="body"))


def test_slack_4xx_failure_is_non_retryable() -> None:
    from alert_infra.exceptions import NonRetryableAlertTransportError

    transport = SlackWebhookTransport(
        "https://hooks.slack.com/services/test",
        http_client=MockHttpClient(NonRetryableAlertTransportError("HTTP alert delivery failed with status 401")),
    )

    with pytest.raises(NonRetryableAlertTransportError):
        transport.send(Alert(title="title", message="body"))


def test_telegram_5xx_failure_is_retryable() -> None:
    from alert_infra.exceptions import RetryableAlertTransportError

    transport = TelegramBotTransport(
        "123",
        "456",
        http_client=MockHttpClient(RetryableAlertTransportError("HTTP alert delivery failed with status 500")),
    )

    with pytest.raises(RetryableAlertTransportError):
        transport.send(Alert(title="title", message="body"))


def test_telegram_4xx_failure_is_non_retryable() -> None:
    from alert_infra.exceptions import NonRetryableAlertTransportError

    transport = TelegramBotTransport(
        "123",
        "456",
        http_client=MockHttpClient(NonRetryableAlertTransportError("HTTP alert delivery failed with status 400")),
    )

    with pytest.raises(NonRetryableAlertTransportError):
        transport.send(Alert(title="title", message="body"))
