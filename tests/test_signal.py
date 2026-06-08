"""Tests for domain/signal.py — SignalDetector consecutive-days streak."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from crisis_radar.config import load_scoring
from crisis_radar.domain.models import ClusterScore, DailyReport, Signal
from crisis_radar.domain.signal import SignalDetector


def _report(report_date: date, total: float) -> DailyReport:
    """Minimal DailyReport with the given date and total."""
    clusters = [
        ClusterScore(cluster_key="ai_fund_health", score=total, breakdown=[]),
        ClusterScore(cluster_key="fertilizer_crisis", score=total, breakdown=[]),
        ClusterScore(cluster_key="oil_proxy", score=total, breakdown=[]),
    ]
    # total passed through as-is (not recomputed from clusters in this fixture)
    return DailyReport(
        date=report_date,
        clusters=clusters,
        indicators=[],
        total=total,
        recommendation="rotate" if total > 30 else "observe",
        risk_level="elevated" if total > 30 else "low",
        signal=Signal(active=False, streak_days=0, required_days=15, threshold=30.0),
        generated_at=datetime(2026, 6, 8),
    )


def _detector() -> SignalDetector:
    return SignalDetector(load_scoring())


class TestStreakBuilding:
    """Streak increments each consecutive day above threshold."""

    def test_empty_history_inactive(self):
        sig = _detector().evaluate([])
        assert sig.active is False
        assert sig.streak_days == 0
        assert sig.since is None

    def test_single_day_above_not_active(self):
        history = [_report(date(2026, 6, 1), 36.0)]
        sig = _detector().evaluate(history)
        assert sig.active is False
        assert sig.streak_days == 1

    def test_streak_count_correct(self):
        history = [_report(date(2026, 6, 1) + timedelta(days=i), 36.0) for i in range(9)]
        sig = _detector().evaluate(history)
        assert sig.streak_days == 9
        assert sig.active is False

    def test_signal_fires_at_consecutive_days(self):
        """Signal becomes active at exactly 15 consecutive days above threshold."""
        required = load_scoring().signal.rotation.consecutive_days  # 15
        history = [_report(date(2026, 5, 1) + timedelta(days=i), 36.0) for i in range(required)]
        sig = _detector().evaluate(history)
        assert sig.active is True
        assert sig.streak_days == required

    def test_signal_does_not_fire_at_14(self):
        required = load_scoring().signal.rotation.consecutive_days  # 15
        history = [_report(date(2026, 5, 1) + timedelta(days=i), 36.0) for i in range(required - 1)]
        sig = _detector().evaluate(history)
        assert sig.active is False
        assert sig.streak_days == required - 1


class TestStreakReset:
    """A single day below threshold resets the streak."""

    def test_streak_resets_on_break(self):
        # 5 days above, 1 below, 3 more above → streak is 3 (not 8)
        base = date(2026, 5, 1)
        history = (
            [_report(base + timedelta(days=i), 36.0) for i in range(5)]
            + [_report(base + timedelta(days=5), 20.0)]   # break
            + [_report(base + timedelta(days=6 + i), 36.0) for i in range(3)]
        )
        sig = _detector().evaluate(history)
        assert sig.streak_days == 3
        assert sig.active is False

    def test_day_at_threshold_does_not_continue_streak(self):
        """Exactly at threshold (== 30) does NOT count — rule is strictly > 30."""
        base = date(2026, 5, 1)
        history = [
            _report(base, 36.0),
            _report(base + timedelta(days=1), 30.0),  # exactly threshold, NOT above
            _report(base + timedelta(days=2), 36.0),
        ]
        sig = _detector().evaluate(history)
        # Streak starts from the last break
        assert sig.streak_days == 1

    def test_all_below_threshold_zero_streak(self):
        history = [_report(date(2026, 5, 1) + timedelta(days=i), 20.0) for i in range(10)]
        sig = _detector().evaluate(history)
        assert sig.streak_days == 0
        assert sig.active is False
        assert sig.since is None


class TestSinceDate:
    """`since` = first day of the current streak."""

    def test_since_is_first_streak_day(self):
        base = date(2026, 5, 1)
        history = [_report(base + timedelta(days=i), 36.0) for i in range(5)]
        sig = _detector().evaluate(history)
        # Oldest day in streak = base
        assert sig.since == base

    def test_since_resets_after_break(self):
        base = date(2026, 5, 1)
        break_day = base + timedelta(days=3)
        restart = base + timedelta(days=4)
        history = (
            [_report(base + timedelta(days=i), 36.0) for i in range(3)]
            + [_report(break_day, 20.0)]
            + [_report(restart, 36.0)]
        )
        sig = _detector().evaluate(history)
        assert sig.since == restart

    def test_since_none_when_no_streak(self):
        history = [_report(date(2026, 5, 1), 20.0)]
        sig = _detector().evaluate(history)
        assert sig.since is None


class TestRequiredDaysFromConfig:
    def test_required_days_matches_config(self):
        config = load_scoring()
        detector = SignalDetector(config)
        sig = detector.evaluate([])
        assert sig.required_days == config.signal.rotation.consecutive_days

    def test_threshold_matches_config(self):
        config = load_scoring()
        detector = SignalDetector(config)
        sig = detector.evaluate([])
        assert sig.threshold == config.signal.rotation.threshold
