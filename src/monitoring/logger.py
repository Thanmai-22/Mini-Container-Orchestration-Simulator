"""Centralized event logger — records every significant cluster event."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EventSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


@dataclass
class Event:
    timestamp: float
    severity: EventSeverity
    source: str
    message: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def snapshot(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "severity": self.severity.value,
            "source": self.source,
            "message": self.message,
            "metadata": self.metadata,
        }


class EventLogger:
    """Append-only event log for the entire cluster."""

    def __init__(self, max_events: int = 5000) -> None:
        self._events: list[Event] = []
        self._max = max_events

    def log(
        self,
        severity: EventSeverity | str,
        source: str,
        message: str,
        **metadata: Any,
    ) -> Event:
        if isinstance(severity, str):
            severity = EventSeverity(severity)
        evt = Event(
            timestamp=time.time(),
            severity=severity,
            source=source,
            message=message,
            metadata=metadata,
        )
        self._events.append(evt)
        if len(self._events) > self._max:
            self._events = self._events[-self._max:]
        return evt

    def info(self, source: str, message: str, **kw: Any) -> Event:
        return self.log(EventSeverity.INFO, source, message, **kw)

    def warning(self, source: str, message: str, **kw: Any) -> Event:
        return self.log(EventSeverity.WARNING, source, message, **kw)

    def error(self, source: str, message: str, **kw: Any) -> Event:
        return self.log(EventSeverity.ERROR, source, message, **kw)

    def critical(self, source: str, message: str, **kw: Any) -> Event:
        return self.log(EventSeverity.CRITICAL, source, message, **kw)

    def recent(self, count: int = 50) -> list[dict]:
        return [e.snapshot() for e in self._events[-count:]]

    @property
    def total_events(self) -> int:
        return len(self._events)

    def count_by_severity(self) -> dict[str, int]:
        counts: dict[str, int] = {s.value: 0 for s in EventSeverity}
        for e in self._events:
            counts[e.severity.value] += 1
        return counts
