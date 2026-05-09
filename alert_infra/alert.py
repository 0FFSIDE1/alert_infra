"""Core alert domain objects."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import uuid4

from .exceptions import AlertValidationError
from .security import redact_metadata, redact_value

Severity = str
VALID_SEVERITIES = frozenset({"info", "warning", "error", "critical"})


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        raise AlertValidationError("created_at must be a datetime or ISO-8601 string")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


@dataclass(frozen=True)
class Alert:
    """A framework-agnostic alert message.

    Metadata is redacted during initialization so every transport receives a safe
    representation by default.
    """

    title: str
    message: str
    severity: Severity = "error"
    source: str | None = None
    tags: tuple[str, ...] = field(default_factory=tuple)
    metadata: Mapping[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utc_now)
    correlation_id: str | None = None
    request_id: str | None = None
    redact_sensitive_data: bool = True

    def __post_init__(self) -> None:
        title = self.title.strip() if isinstance(self.title, str) else ""
        message = self.message.strip() if isinstance(self.message, str) else ""
        severity = self.severity.lower() if isinstance(self.severity, str) else self.severity

        if not title:
            raise AlertValidationError("title is required")
        if not message:
            raise AlertValidationError("message is required")
        if severity not in VALID_SEVERITIES:
            raise AlertValidationError(
                f"unsupported severity '{self.severity}'. Expected one of: {', '.join(sorted(VALID_SEVERITIES))}"
            )
        if not isinstance(self.tags, tuple):
            object.__setattr__(self, "tags", tuple(str(tag) for tag in self.tags))
        if self.created_at.tzinfo is None:
            object.__setattr__(self, "created_at", self.created_at.replace(tzinfo=timezone.utc))

        object.__setattr__(self, "title", title)
        object.__setattr__(self, "message", message)
        object.__setattr__(self, "severity", severity)
        object.__setattr__(self, "metadata", redact_metadata(self.metadata) if self.redact_sensitive_data else dict(self.metadata))
        if self.correlation_id is None:
            object.__setattr__(self, "correlation_id", str(uuid4()))

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe, queue-safe dictionary representation."""
        return {
            "title": self.title,
            "message": self.message,
            "severity": self.severity,
            "source": self.source,
            "tags": list(self.tags),
            "metadata": redact_value(self.metadata),
            "created_at": self.created_at.astimezone(timezone.utc).isoformat(),
            "correlation_id": self.correlation_id,
            "request_id": self.request_id,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Alert":
        """Rehydrate an :class:`Alert` from ``to_dict`` output."""
        return cls(
            title=str(data.get("title") or ""),
            message=str(data.get("message") or ""),
            severity=str(data.get("severity") or "error"),
            source=data.get("source"),
            tags=tuple(str(tag) for tag in data.get("tags") or ()),
            metadata=redact_metadata(data.get("metadata") or {}),
            created_at=_parse_datetime(data.get("created_at") or _utc_now()),
            correlation_id=data.get("correlation_id"),
            request_id=data.get("request_id"),
            redact_sensitive_data=True,
        )
