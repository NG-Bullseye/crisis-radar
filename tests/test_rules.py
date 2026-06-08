"""Tests for domain/rules.py — band / count / enum / bool evaluators."""
from __future__ import annotations

from datetime import datetime

from crisis_radar.config import BandRule, BandThreshold, BoolRule, CountRule, EnumRule
from crisis_radar.domain.models import Indicator
from crisis_radar.domain.rules import _band, _bool, _count, _enum, evaluate


def _ind(key: str, value, value_kind: str, cluster_key: str = "ai_fund_health") -> Indicator:
    from crisis_radar.domain.models import Citation
    cite = Citation(url="https://example.com", title="Test")
    return Indicator(
        key=key,
        cluster_key=cluster_key,  # type: ignore[arg-type]
        value=value,
        value_kind=value_kind,  # type: ignore[arg-type]
        confidence=0.9,
        citations=[cite] if value_kind != "unknown" else [],
        evidence="test",
        extracted_at=datetime(2026, 6, 8),
    )


# ── Band rule ─────────────────────────────────────────────────────────────────

class TestBandRule:
    def _rule(self) -> BandRule:
        return BandRule(
            type="band",
            gt=BandThreshold(threshold=50, points=20),
            lt=BandThreshold(threshold=30, points=-20),
        )

    def test_gt_fires(self):
        assert _band(58.0, self._rule()) == 20

    def test_lt_fires(self):
        assert _band(25.0, self._rule()) == -20

    def test_in_band_zero(self):
        assert _band(40.0, self._rule()) == 0

    def test_exact_boundary_gt_does_not_fire(self):
        # > 50 is the condition, so exactly 50 → 0
        assert _band(50.0, self._rule()) == 0

    def test_exact_boundary_lt_does_not_fire(self):
        # < 30 is the condition, so exactly 30 → 0
        assert _band(30.0, self._rule()) == 0

    def test_evaluate_unknown_returns_zero(self):
        ind = _ind("gas", None, "unknown")
        rule = self._rule()
        assert evaluate(ind, rule) == 0

    def test_evaluate_number(self):
        ind = _ind("gas", 58.0, "number", "fertilizer_crisis")
        rule = self._rule()
        assert evaluate(ind, rule) == 20


# ── Count rule ────────────────────────────────────────────────────────────────

class TestCountRule:
    def _rule(self, points_each: int = 5, cap: int = 40) -> CountRule:
        return CountRule(type="count", points_each=points_each, cap=cap)

    def test_basic_count(self):
        assert _count(2, self._rule()) == 10

    def test_cap_clamps_positive(self):
        # 10 * 5 = 50, capped at 40
        assert _count(10, self._rule(5, 40)) == 40

    def test_cap_clamps_negative(self):
        # 3 * -15 = -45, cap=-45 → exactly at cap
        rule = CountRule(type="count", points_each=-15, cap=-45)
        assert _count(3, rule) == -45

    def test_negative_count_exceeds_cap(self):
        # 5 * -15 = -75, cap=-45 → -45
        rule = CountRule(type="count", points_each=-15, cap=-45)
        assert _count(5, rule) == -45

    def test_negative_value_returns_zero(self):
        # Negative counts are invalid per data model
        assert _count(-1, self._rule()) == 0

    def test_zero_count(self):
        assert _count(0, self._rule()) == 0

    def test_unknown_returns_zero(self):
        ind = _ind("announcements", None, "unknown")
        rule = self._rule()
        assert evaluate(ind, rule) == 0

    def test_negative_rule_no_overshoot(self):
        # -8 each, cap -40: 4 × -8 = -32 (under cap, passes through)
        rule = CountRule(type="count", points_each=-8, cap=-40)
        assert _count(4, rule) == -32

    def test_negative_rule_hits_cap(self):
        # -8 each, cap -40: 6 × -8 = -48 → clamped to -40
        rule = CountRule(type="count", points_each=-8, cap=-40)
        assert _count(6, rule) == -40


# ── Enum rule ─────────────────────────────────────────────────────────────────

class TestEnumRule:
    def _rule(self) -> EnumRule:
        return EnumRule(type="enum", values={"low": -20, "medium": 10, "high": 40})

    def test_known_value(self):
        assert _enum("medium", self._rule()) == 10

    def test_unknown_value_returns_zero(self):
        assert _enum("extreme", self._rule()) == 0

    def test_case_sensitive(self):
        # Enum values must match exactly
        assert _enum("Medium", self._rule()) == 0

    def test_non_string_returns_zero(self):
        assert _enum(42, self._rule()) == 0  # type: ignore[arg-type]

    def test_evaluate_unknown_indicator(self):
        ind = _ind("iran", None, "unknown", "fertilizer_crisis")
        rule = self._rule()
        assert evaluate(ind, rule) == 0


# ── Bool rule ─────────────────────────────────────────────────────────────────

class TestBoolRule:
    def _rule(self) -> BoolRule:
        return BoolRule(type="bool", points_true=12, points_false=0)

    def test_true_python(self):
        assert _bool(True, self._rule()) == 12

    def test_false_python(self):
        assert _bool(False, self._rule()) == 0

    def test_string_true(self):
        assert _bool("true", self._rule()) == 12

    def test_string_false(self):
        assert _bool("false", self._rule()) == 0

    def test_evaluate_bool_indicator(self):
        ind = _ind("hormuz_insurance_rising", True, "bool", "oil_proxy")
        rule = self._rule()
        assert evaluate(ind, rule) == 12


# ── evaluate() — unknown always 0 ────────────────────────────────────────────

def test_evaluate_unknown_with_any_rule():
    """Unknown value_kind → 0 regardless of rule type (ADR-0006)."""
    ind = Indicator(
        key="whatever",
        cluster_key="ai_fund_health",
        value=None,
        value_kind="unknown",
        confidence=0.0,
        citations=[],
        evidence="",
        extracted_at=datetime(2026, 6, 8),
    )
    rule = BandRule(type="band", gt=BandThreshold(threshold=0, points=100))
    assert evaluate(ind, rule) == 0
