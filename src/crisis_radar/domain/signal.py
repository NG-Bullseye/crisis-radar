"""SignalDetector — sustained-pressure rotation signal over history.

A single day above threshold is NOT a signal. The signal fires only after
`consecutive_days` consecutive days where total > threshold (scoring-spec.md §6).
"""
from __future__ import annotations

from datetime import date

from crisis_radar.config import ScoringConfig
from crisis_radar.domain.models import DailyReport, Signal


class SignalDetector:
    """Evaluate the rotation signal across a window of historical reports."""

    def __init__(self, config: ScoringConfig) -> None:
        self._threshold = config.signal.rotation.threshold
        self._required_days = config.signal.rotation.consecutive_days

    def evaluate(self, history: list[DailyReport]) -> Signal:
        """Compute the signal from `history` (ordered oldest-first or any order).

        Returns the Signal that should be attached to the *most recent* report.
        An empty history → inactive signal with streak_days=0.
        """
        if not history:
            return Signal(
                active=False,
                streak_days=0,
                required_days=self._required_days,
                since=None,
                threshold=self._threshold,
            )

        # Sort oldest-first for streak counting.
        sorted_reports = sorted(history, key=lambda r: r.date)

        streak = 0
        since: date | None = None

        # Walk from newest backward to find the current trailing streak.
        for report in reversed(sorted_reports):
            if report.total > self._threshold:
                streak += 1
                since = report.date  # keeps updating to oldest in streak
            else:
                break  # streak broken — stop

        active = streak >= self._required_days

        return Signal(
            active=active,
            streak_days=streak,
            required_days=self._required_days,
            # `since` is the FIRST day of the current streak (oldest = minimum date in streak).
            since=since if streak > 0 else None,
            threshold=self._threshold,
        )
