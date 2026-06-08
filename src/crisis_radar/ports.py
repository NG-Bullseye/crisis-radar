"""Ports (interfaces) — the core depends on these, never on concrete I/O (ADR-0005).

The orchestrator wires concrete adapters in; the domain never sees them.
"""
from __future__ import annotations

from datetime import date
from typing import Protocol, runtime_checkable

from crisis_radar.domain.models import DailyReport, Indicator


@runtime_checkable
class IndicatorSource(Protocol):
    """Produce one indicator's value, evidence, citations, and confidence."""

    async def fetch(self, key: str) -> Indicator:
        ...


@runtime_checkable
class ReportStore(Protocol):
    """Persist and retrieve daily reports."""

    def save(self, report: DailyReport) -> None:
        ...

    def load(self, report_date: date) -> DailyReport | None:
        ...

    def history(self, window: int = 30) -> list[DailyReport]:
        """Return up to `window` most-recent reports, ordered oldest-first."""
        ...


@runtime_checkable
class Notifier(Protocol):
    """Deliver a report (and optional signal-change flag) to a consumer."""

    async def emit(self, report: DailyReport, signal_changed: bool = False) -> None:
        ...
