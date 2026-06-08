"""Fixture: the §8 worked example from scoring-spec.md.

C1: announcements=2, funding=12B$, rate_signals=1, tech_5d=+3.1%, negative=1
  → +10 +10 -15 +10 -8 = +7

C2: gas=58, outages=1, hormuz=open, harvest=reduction_warning, imports=2, iran=medium
  → +20 +15 -30 +10 +24 +10 = +49

C3: wti=94, tension=high, refinery=0, insurance=True
  → +25 +15 +0 +12 = +52

total = mean(7, 49, 52) = 36.0  →  recommendation=rotate, risk=elevated
"""
from __future__ import annotations

from datetime import datetime

from crisis_radar.domain.models import Citation, Indicator

_CITE = Citation(url="https://example.com/test", title="Test Source", published=None)


def make_worked_example_indicators() -> list[Indicator]:
    """Return the exact §8 indicator set."""
    return [
        # Cluster 1 — ai_fund_health
        Indicator(
            key="product_announcements",
            cluster_key="ai_fund_health",
            value=2,
            value_kind="count",
            confidence=0.9,
            citations=[_CITE],
            evidence="2 major AI product launches this week.",
            extracted_at=datetime(2026, 6, 8, 7, 30),
        ),
        Indicator(
            key="ai_startup_funding_weekly_busd",
            cluster_key="ai_fund_health",
            value=12.0,
            value_kind="number",
            confidence=0.85,
            citations=[_CITE],
            evidence="Total AI startup funding this week: $12B.",
            extracted_at=datetime(2026, 6, 8, 7, 30),
        ),
        Indicator(
            key="rate_hike_signals",
            cluster_key="ai_fund_health",
            value=1,
            value_kind="count",
            confidence=0.8,
            citations=[_CITE],
            evidence="One ECB hike-leaning statement.",
            extracted_at=datetime(2026, 6, 8, 7, 30),
        ),
        Indicator(
            key="tech_performance_5d_pct",
            cluster_key="ai_fund_health",
            value=3.1,
            value_kind="number",
            confidence=0.95,
            citations=[_CITE],
            evidence="Tech index up +3.1% over 5 days.",
            extracted_at=datetime(2026, 6, 8, 7, 30),
        ),
        Indicator(
            key="negative_ai_news",
            cluster_key="ai_fund_health",
            value=1,
            value_kind="count",
            confidence=0.7,
            citations=[_CITE],
            evidence="1 regulation story.",
            extracted_at=datetime(2026, 6, 8, 7, 30),
        ),
        # Cluster 2 — fertilizer_crisis
        Indicator(
            key="gas_ttf_eur_mwh",
            cluster_key="fertilizer_crisis",
            value=58.0,
            value_kind="number",
            confidence=0.99,
            citations=[_CITE],
            evidence="TTF front-month at €58/MWh.",
            extracted_at=datetime(2026, 6, 8, 7, 30),
        ),
        Indicator(
            key="production_outages",
            cluster_key="fertilizer_crisis",
            value=1,
            value_kind="count",
            confidence=0.8,
            citations=[_CITE],
            evidence="1 plant offline.",
            extracted_at=datetime(2026, 6, 8, 7, 30),
        ),
        Indicator(
            key="hormuz_status",
            cluster_key="fertilizer_crisis",
            value="open",
            value_kind="enum",
            confidence=0.9,
            citations=[_CITE],
            evidence="Strait of Hormuz open.",
            extracted_at=datetime(2026, 6, 8, 7, 30),
        ),
        Indicator(
            key="harvest_forecast",
            cluster_key="fertilizer_crisis",
            value="reduction_warning",
            value_kind="enum",
            confidence=0.75,
            citations=[_CITE],
            evidence="FAO reduction warning issued.",
            extracted_at=datetime(2026, 6, 8, 7, 30),
        ),
        Indicator(
            key="fertilizer_import_costs",
            cluster_key="fertilizer_crisis",
            value=2,
            value_kind="count",
            confidence=0.8,
            citations=[_CITE],
            evidence="2 shortage reports this week.",
            extracted_at=datetime(2026, 6, 8, 7, 30),
        ),
        Indicator(
            key="iran_conflict_escalation",
            cluster_key="fertilizer_crisis",
            value="medium",
            value_kind="enum",
            confidence=0.8,
            citations=[_CITE],
            evidence="Iran tensions at medium level.",
            extracted_at=datetime(2026, 6, 8, 7, 30),
        ),
        # Cluster 3 — oil_proxy
        Indicator(
            key="wti_usd_bbl",
            cluster_key="oil_proxy",
            value=94.0,
            value_kind="number",
            confidence=0.99,
            citations=[_CITE],
            evidence="WTI crude at $94/bbl.",
            extracted_at=datetime(2026, 6, 8, 7, 30),
        ),
        Indicator(
            key="mideast_tension",
            cluster_key="oil_proxy",
            value="high",
            value_kind="enum",
            confidence=0.85,
            citations=[_CITE],
            evidence="Middle East tension assessed as high.",
            extracted_at=datetime(2026, 6, 8, 7, 30),
        ),
        Indicator(
            key="refinery_outages",
            cluster_key="oil_proxy",
            value=0,
            value_kind="count",
            confidence=0.9,
            citations=[_CITE],
            evidence="No refinery outages reported.",
            extracted_at=datetime(2026, 6, 8, 7, 30),
        ),
        Indicator(
            key="hormuz_insurance_rising",
            cluster_key="oil_proxy",
            value=True,
            value_kind="bool",
            confidence=0.85,
            citations=[_CITE],
            evidence="Hormuz war-risk insurance premiums rising.",
            extracted_at=datetime(2026, 6, 8, 7, 30),
        ),
    ]
