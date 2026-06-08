"""Rule evaluators — pure functions, no I/O, no magic numbers.

Every rule type maps a raw indicator value to an integer point contribution.
All thresholds and point values come from the caller's config (ADR-0002).

Unknown indicators always return 0 — they are never dropped but never invented
(ADR-0006).
"""
from __future__ import annotations

from crisis_radar.config import BandRule, BoolRule, CountRule, EnumRule, IndicatorRule
from crisis_radar.domain.models import Indicator


def evaluate(indicator: Indicator, rule: IndicatorRule) -> int:
    """Return the integer point contribution of an indicator under its rule.

    Returns 0 for unknown value_kind regardless of rule type — missing data
    contributes nothing but stays visible in the report.
    """
    # Unknown = no data found; always contributes 0 (ADR-0006).
    if indicator.value_kind == "unknown" or indicator.value is None:
        return 0

    if isinstance(rule, BandRule):
        return _band(indicator.value, rule)
    if isinstance(rule, CountRule):
        return _count(indicator.value, rule)
    if isinstance(rule, EnumRule):
        return _enum(indicator.value, rule)
    if isinstance(rule, BoolRule):
        return _bool(indicator.value, rule)

    return 0  # should not be reached — config validation catches unknown types


def _band(value: float | int, rule: BandRule) -> int:
    """Numeric tier rule: gt → a points, lt → b points, else 0."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 0

    # Evaluate top-down so the stronger tier wins on ties.
    if rule.gt is not None and v > rule.gt.threshold:
        return rule.gt.points
    if rule.lt is not None and v < rule.lt.threshold:
        return rule.lt.points
    return 0


def _count(value: int, rule: CountRule) -> int:
    """Integer count × points_each, hard-capped by config.

    cap may be positive (positive rules) or negative (rate hike signals, etc.).
    The cap acts as an absolute bound in the natural direction.
    """
    try:
        count = int(value)
    except (TypeError, ValueError):
        return 0

    if count < 0:
        # Negative counts are invalid by the data model; treat as 0.
        return 0

    raw = count * rule.points_each

    # cap is the extreme value — clamp toward zero beyond it.
    cap = rule.cap
    if cap >= 0:
        return min(raw, cap)
    else:
        return max(raw, cap)


def _enum(value: str, rule: EnumRule) -> int:
    """Categorical key → points; unknown key (not in whitelist) → 0."""
    if not isinstance(value, str):
        return 0
    # Missing from map is treated as unknown — not a crash (ADR-0006 anti-hallucination).
    return rule.values.get(value, 0)


def _bool(value: bool | str, rule: BoolRule) -> int:
    """Boolean → points_true / points_false."""
    if isinstance(value, bool):
        truthy = value
    elif isinstance(value, str):
        truthy = value.lower() in ("true", "1", "yes")
    else:
        truthy = bool(value)

    return rule.points_true if truthy else rule.points_false
