"""Deterministic scorer — indicators + config → cluster scores + recommendation.

Pure function; no I/O. All scoring values come from ScoringConfig (ADR-0002).
"""
from __future__ import annotations

from crisis_radar.config import ScoringConfig
from crisis_radar.domain.models import (
    ClusterScore,
    Indicator,
    RecommendationEnum,
    RiskLevelEnum,
)
from crisis_radar.domain.rules import evaluate


def score(
    indicators: list[Indicator],
    config: ScoringConfig,
) -> tuple[list[ClusterScore], float, RecommendationEnum, RiskLevelEnum]:
    """Score a list of indicators.

    Returns:
        (clusters, total, recommendation, risk_level)
        - clusters: one ClusterScore per configured cluster, clamped to [-100, +100]
        - total: mean of cluster scores (or weighted mean if configured)
        - recommendation / risk_level: from recommendation_bands
    """
    clusters: list[ClusterScore] = []

    for cluster_key, cluster_cfg in config.clusters.items():
        cluster_indicators = [i for i in indicators if i.cluster_key == cluster_key]
        raw_sum = 0
        breakdown: list[dict] = []

        for indicator in cluster_indicators:
            rule = cluster_cfg.indicators.get(indicator.key)
            if rule is None:
                # Indicator not in config → contributes 0 (unknown territory).
                pts = 0
            else:
                pts = evaluate(indicator, rule)
            indicator.points = pts  # fill in-place (Scorer is the authority on points)
            breakdown.append({"key": indicator.key, "points": pts})
            raw_sum += pts

        # Clamp each cluster score to the configured range.
        clamped = max(
            config.clamp.cluster_min,
            min(config.clamp.cluster_max, raw_sum),
        )
        clusters.append(
            ClusterScore(
                cluster_key=cluster_key,  # type: ignore[arg-type]
                score=float(clamped),
                breakdown=breakdown,
            )
        )

    total = _compute_total(clusters, config)
    recommendation, risk_level = _recommend(total, config)
    return clusters, total, recommendation, risk_level


def _compute_total(clusters: list[ClusterScore], config: ScoringConfig) -> float:
    """Mean (or weighted mean) of cluster scores."""
    if not clusters:
        return 0.0

    if config.total.method == "weighted":
        weights = config.total.weights
        weighted_sum = sum(
            c.score * weights.get(c.cluster_key, 1.0) for c in clusters
        )
        weight_total = sum(weights.get(c.cluster_key, 1.0) for c in clusters)
        if weight_total == 0:
            return 0.0
        return round(weighted_sum / weight_total, 10)

    # Default: equal-weight mean.
    return round(sum(c.score for c in clusters) / len(clusters), 10)


def _recommend(
    total: float,
    config: ScoringConfig,
) -> tuple[RecommendationEnum, RiskLevelEnum]:
    """Map total to recommendation + risk_level using config bands (evaluated top-down)."""
    for band in config.recommendation_bands:
        if total > band.min:
            return band.recommendation, band.risk_level  # type: ignore[return-value]

    # Fallback to the last band (covers total == min of last band exactly).
    last = config.recommendation_bands[-1]
    return last.recommendation, last.risk_level  # type: ignore[return-value]
