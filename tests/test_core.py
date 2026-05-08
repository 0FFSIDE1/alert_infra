from __future__ import annotations

import logging

import pytest

from alert_infra import Alert, AlertDispatcher, AlertValidationError, NoOpTransport, REDACTED, redact_metadata


def test_alert_creation_defaults_and_redaction() -> None:
    alert = Alert(
        title=" Payment failure ",
        message="Provider returned an error",
        severity="ERROR",
        source="billing",
        tags=["payments"],
        metadata={"invoice_id": "INV-001", "authorization": "Bearer secret", "nested": {"api_key": "abc"}},
    )

    assert alert.title == "Payment failure"
    assert alert.severity == "error"
    assert alert.tags == ("payments",)
    assert alert.metadata["authorization"] == REDACTED
    assert alert.metadata["nested"]["api_key"] == REDACTED
    assert alert.correlation_id


@pytest.mark.parametrize("kwargs", [{"title": "", "message": "body"}, {"title": "title", "message": ""}])
def test_alert_rejects_empty_title_or_message(kwargs: dict[str, str]) -> None:
    with pytest.raises(AlertValidationError):
        Alert(**kwargs)


def test_alert_rejects_unsupported_severity() -> None:
    with pytest.raises(AlertValidationError):
        Alert(title="title", message="body", severity="debug")


def test_invalid_metadata_type_raises() -> None:
    with pytest.raises(TypeError):
        Alert(title="title", message="body", metadata=[("token", "secret")])  # type: ignore[arg-type]


def test_redact_metadata_handles_nested_sequences_and_sets() -> None:
    redacted = redact_metadata({"items": [{"refresh_token": "secret"}], "roles": {"admin", "user"}})

    assert redacted["items"][0]["refresh_token"] == REDACTED
    assert redacted["roles"] == ["admin", "user"]


def test_noop_transport_records_alert() -> None:
    transport = NoOpTransport()
    alert = Alert(title="title", message="body")

    transport.send(alert)

    assert transport.alerts == [alert]


class RecordingTransport:
    name = "recording"

    def __init__(self) -> None:
        self.sent = []

    def send(self, alert: Alert) -> None:
        self.sent.append(alert)


class FailingTransport:
    name = "failing"

    def send(self, alert: Alert) -> None:
        raise TimeoutError("network token should not be logged")


def test_dispatcher_success() -> None:
    transport = RecordingTransport()
    alert = Alert(title="title", message="body")

    result = AlertDispatcher([transport]).send(alert)

    assert result.ok
    assert result.sent == ("recording",)
    assert transport.sent == [alert]


def test_dispatcher_partial_failure_does_not_leak_exception_message(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING)
    alert = Alert(title="title", message="body", metadata={"password": "super-secret"})

    result = AlertDispatcher([FailingTransport(), RecordingTransport()]).send(alert)

    assert result.sent == ("recording",)
    assert result.failed == {"failing": "TimeoutError"}
    assert "super-secret" not in caplog.text
    assert "network token" not in caplog.text


def test_disabled_dispatcher_skips_transports() -> None:
    transport = RecordingTransport()
    result = AlertDispatcher([transport], enabled=False).send(Alert(title="title", message="body"))

    assert result.sent == ()
    assert transport.sent == []
