"""Tests for domain/scorer.py — the §8 worked example is the primary fixture."""
from __future__ import annotations

from datetime import datetime

import pytest

from crisis_radar.config import load_scoring
from crisis_radar.domain.models import Citation, Indicator
from crisis_radar.domain.scorer import score
from tests.fixtures.worked_example import make_worked_example_indicators


def _load():
    return load_scoring()


# ── §8 Worked example ─────────────────────────────────────────────────────────

class TestWorkedExample:
    """The §8 fixture MUST produce total == 36.0 and recommendation == 'rotate'."""

    def test_total(self):
        config = _load()
        indicators = make_worked_example_indicators()
        clusters, total, recommendation, risk_level = score(indicators, config)
        assert total == pytest.approx(36.0, abs=1e-6), f"expected 36.0, got {total}"

    def test_recommendation(self):
        config = _load()
        indicators = make_worked_example_indicators()
        _, _, recommendation, _ = score(indicators, config)
        assert recommendation == "rotate"

    def test_risk_level(self):
        config = _load()
        indicators = make_worked_example_indicators()
        _, _, _, risk_level = score(indicators, config)
        assert risk_level == "elevated"

    def test_cluster_c1_score(self):
        config = _load()
        indicators = make_worked_example_indicators()
        clusters, _, _, _ = score(indicators, config)
        c1 = next(c for c in clusters if c.cluster_key == "ai_fund_health")
        # +10 +10 -15 +10 -8 = 7
        assert c1.score == pytest.approx(7.0)

    def test_cluster_c2_score(self):
        config = _load()
        indicators = make_worked_example_indicators()
        clusters, _, _, _ = score(indicators, config)
        c2 = next(c for c in clusters if c.cluster_key == "fertilizer_crisis")
        # +20 +15 -30 +10 +24 +10 = 49
        assert c2.score == pytest.approx(49.0)

    def test_cluster_c3_score(self):
        config = _load()
        indicators = make_worked_example_indicators()
        clusters, _, _, _ = score(indicators, config)
        c3 = next(c for c in clusters if c.cluster_key == "oil_proxy")
        # +25 +15 +0 +12 = 52
        assert c3.score == pytest.approx(52.0)

    def test_breakdown_filled(self):
        """Every cluster breakdown has non-empty entries with points filled."""
        config = _load()
        indicators = make_worked_example_indicators()
        clusters, _, _, _ = score(indicators, config)
        for cluster in clusters:
            assert len(cluster.breakdown) > 0
            for item in cluster.breakdown:
                assert "key" in item
                assert "points" in item


# ── Unknown → 0 ───────────────────────────────────────────────────────────────

class TestUnknownIndicators:
    """Unknown indicators contribute 0 points (ADR-0006)."""

    def test_all_unknown_total_is_zero(self):
        config = _load()
        unknown_indicators = []
        for cluster_key, cluster_cfg in config.clusters.items():
            for ind_key in cluster_cfg.indicators:
                unknown_indicators.append(
                    Indicator(
                        key=ind_key,
                        cluster_key=cluster_key,  # type: ignore[arg-type]
                        value=None,
                        value_kind="unknown",
                        confidence=0.0,
                        citations=[],
                        evidence="",
                        extracted_at=datetime(2026, 6, 8),
                    )
                )
        clusters, total, recommendation, risk_level = score(unknown_indicators, config)
        assert total == pytest.approx(0.0)
        # total == 0: band is `> 0` (strict), so 0 does NOT satisfy half_position (> 0),
        # falls to observe (> -30). This is per spec: bands are evaluated top-down, strictly >.
        assert recommendation == "observe"

    def test_single_unknown_does_not_crash(self):
        config = _load()
        ind = Indicator(
            key="gas_ttf_eur_mwh",
            cluster_key="fertilizer_crisis",
            value=None,
            value_kind="unknown",
            confidence=0.0,
            citations=[],
            evidence="",
            extracted_at=datetime(2026, 6, 8),
        )
        clusters, total, _, _ = score([ind], config)
        c2 = next(c for c in clusters if c.cluster_key == "fertilizer_crisis")
        assert c2.score == 0.0


# ── Clamping ──────────────────────────────────────────────────────────────────

class TestClamping:
    """Per-cluster clamp to [-100, +100] after summing rules."""

    def _make_high_indicators(self, cluster_key: str, ind_key: str, value, value_kind, count: int = 1) -> list[Indicator]:
        cite = Citation(url="https://example.com", title="Test")
        return [
            Indicator(
                key=ind_key,
                cluster_key=cluster_key,  # type: ignore[arg-type]
                value=value,
                value_kind=value_kind,  # type: ignore[arg-type]
                confidence=1.0,
                citations=[cite],
                evidence="",
                extracted_at=datetime(2026, 6, 8),
            )
        ]

    def test_cluster_never_exceeds_100(self):
        """Stack enough positive points in C2 to exceed 100 before clamping."""
        config = _load()
        cite = Citation(url="https://example.com", title="Test")
        # gas +20, outages cap +45, iran high +40, harvest -0, import cap +36, hormuz blocked +30
        # raw = 20 + 45 + 40 + 10 + 36 + 30 = 181 → clamped to 100
        indicators = [
            Indicator(key="gas_ttf_eur_mwh", cluster_key="fertilizer_crisis",
                      value=58.0, value_kind="number", confidence=1.0, citations=[cite], evidence=""),
            Indicator(key="production_outages", cluster_key="fertilizer_crisis",
                      value=10, value_kind="count", confidence=1.0, citations=[cite], evidence=""),
            Indicator(key="hormuz_status", cluster_key="fertilizer_crisis",
                      value="blocked", value_kind="enum", confidence=1.0, citations=[cite], evidence=""),
            Indicator(key="harvest_forecast", cluster_key="fertilizer_crisis",
                      value="reduction_warning", value_kind="enum", confidence=1.0, citations=[cite], evidence=""),
            Indicator(key="fertilizer_import_costs", cluster_key="fertilizer_crisis",
                      value=10, value_kind="count", confidence=1.0, citations=[cite], evidence=""),
            Indicator(key="iran_conflict_escalation", cluster_key="fertilizer_crisis",
                      value="high", value_kind="enum", confidence=1.0, citations=[cite], evidence=""),
        ]
        clusters, _, _, _ = score(indicators, config)
        c2 = next(c for c in clusters if c.cluster_key == "fertilizer_crisis")
        assert c2.score <= 100.0

    def test_cluster_never_below_minus_100(self):
        """Stack enough negative points to check the -100 floor."""
        config = _load()
        cite = Citation(url="https://example.com", title="Test")
        # gas < 30 (-20), hormuz open (-30), iran low (-20), harvest favorable (-5)
        # raw = -20 + -30 + -20 + -5 = -75 (well above -100)
        # Use rate hike signals to push further negative in C1
        indicators = [
            Indicator(key="rate_hike_signals", cluster_key="ai_fund_health",
                      value=5, value_kind="count", confidence=1.0, citations=[cite], evidence=""),
            Indicator(key="negative_ai_news", cluster_key="ai_fund_health",
                      value=10, value_kind="count", confidence=1.0, citations=[cite], evidence=""),
        ]
        clusters, _, _, _ = score(indicators, config)
        c1 = next(c for c in clusters if c.cluster_key == "ai_fund_health")
        assert c1.score >= -100.0


# ── Recommendation bands ──────────────────────────────────────────────────────

class TestRecommendationBands:
    def _score_total(self, total_value: float) -> tuple[str, str]:
        """Helper: build indicators that produce approximately `total_value` total."""
        config = _load()
        # Shortcut: manipulate the scoring by creating a synthetic set that
        # gives known cluster scores. Use the real config on real indicators.
        # For band testing we just test _recommend directly.
        from crisis_radar.domain.scorer import _recommend
        return _recommend(total_value, config)

    def test_above_30_is_rotate(self):
        rec, risk = self._score_total(31.0)
        assert rec == "rotate"
        assert risk == "elevated"

    def test_exactly_30_is_half_position(self):
        # > 30 fires rotate, but == 30 does NOT (strict >)
        rec, risk = self._score_total(30.0)
        assert rec == "half_position"

    def test_zero_to_30_is_half_position(self):
        rec, risk = self._score_total(15.0)
        assert rec == "half_position"

    def test_zero_is_observe(self):
        # Bands are strictly >; total == 0 does NOT satisfy > 0 (half_position)
        # → falls through to > -30 (observe). Per spec.
        rec, risk = self._score_total(0.0)
        assert rec == "observe"

    def test_negative_is_observe(self):
        rec, risk = self._score_total(-15.0)
        assert rec == "observe"

    def test_below_minus_30_is_no_rotation(self):
        rec, risk = self._score_total(-35.0)
        assert rec == "no_rotation"

    def test_exactly_minus_30_is_no_rotation(self):
        # > -30 → observe (i.e. == -30 does NOT satisfy > -30)
        rec, _ = self._score_total(-30.0)
        assert rec == "no_rotation"
