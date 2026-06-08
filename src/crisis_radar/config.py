"""Load and validate scoring.yaml and sources.yaml.

Fails loudly on unknown indicator keys, malformed bands, or missing required
fields — so mis-configurations surface at startup, not mid-run (ADR-0002).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, model_validator

# ── Per-rule config models ────────────────────────────────────────────────────

class BandThreshold(BaseModel):
    threshold: float
    points: int


class BandRule(BaseModel):
    type: Literal["band"]
    gt: BandThreshold | None = None
    lt: BandThreshold | None = None


class CountRule(BaseModel):
    type: Literal["count"]
    points_each: int
    cap: int  # positive cap for positive rules, negative cap for negative rules


class EnumRule(BaseModel):
    type: Literal["enum"]
    values: dict[str, int]  # categorical key -> points


class BoolRule(BaseModel):
    type: Literal["bool"]
    points_true: int
    points_false: int = 0


IndicatorRule = BandRule | CountRule | EnumRule | BoolRule


class ClampConfig(BaseModel):
    cluster_min: int = -100
    cluster_max: int = 100


class TotalConfig(BaseModel):
    method: Literal["mean", "weighted"] = "mean"
    weights: dict[str, float] = Field(default_factory=lambda: {
        "ai_fund_health": 1.0,
        "fertilizer_crisis": 1.0,
        "oil_proxy": 1.0,
    })


class RecommendationBand(BaseModel):
    min: float
    recommendation: str
    risk_level: str


class SignalRotationConfig(BaseModel):
    threshold: float = 30.0
    consecutive_days: int = 15


class SignalConfig(BaseModel):
    rotation: SignalRotationConfig = Field(default_factory=SignalRotationConfig)


class ClusterConfig(BaseModel):
    indicators: dict[str, IndicatorRule]


# ── Top-level scoring config ──────────────────────────────────────────────────

_KNOWN_CLUSTERS = {"ai_fund_health", "fertilizer_crisis", "oil_proxy"}


class ScoringConfig(BaseModel):
    schema_version: str = "1.0"
    clamp: ClampConfig = Field(default_factory=ClampConfig)
    total: TotalConfig = Field(default_factory=TotalConfig)
    clusters: dict[str, ClusterConfig]
    recommendation_bands: list[RecommendationBand]
    signal: SignalConfig = Field(default_factory=SignalConfig)

    @model_validator(mode="after")
    def _validate_clusters(self) -> "ScoringConfig":
        unknown = set(self.clusters) - _KNOWN_CLUSTERS
        if unknown:
            raise ValueError(f"Unknown clusters in scoring.yaml: {unknown}")
        return self


# ── Sources config models ─────────────────────────────────────────────────────

class IndicatorSource(BaseModel):
    source_type: Literal["price_api", "llm_research"]
    feed: str | None = None
    unit: str | None = None
    query: str | None = None
    allowed_domains: list[str] = Field(default_factory=list)
    allowed_values: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _coerce_allowed_values(cls, data: dict) -> dict:
        """YAML parses `[true, false]` as Python booleans — coerce to strings."""
        avs = data.get("allowed_values")
        if isinstance(avs, list):
            data["allowed_values"] = [str(v).lower() for v in avs]
        return data


class SourcesConfig(BaseModel):
    schema_version: str = "1.0"
    indicators: dict[str, IndicatorSource]


# ── Loaders ──────────────────────────────────────────────────────────────────

_REPO_ROOT = Path(__file__).parent.parent.parent  # crisis-radar/


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with path.open() as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Config file is not a YAML mapping: {path}")
    return data


def load_scoring(path: Path | None = None) -> ScoringConfig:
    """Load and validate config/scoring.yaml."""
    resolved = path or (_REPO_ROOT / "config" / "scoring.yaml")
    raw = _load_yaml(resolved)
    # Discriminated-union parsing for indicator rules
    raw_clusters = raw.get("clusters", {})
    for cluster_key, cluster_data in raw_clusters.items():
        raw_indicators = cluster_data.get("indicators", {})
        for ind_key, ind_data in raw_indicators.items():
            rule_type = ind_data.get("type")
            if rule_type not in ("band", "count", "enum", "bool"):
                raise ValueError(
                    f"Unknown rule type '{rule_type}' for indicator '{ind_key}' "
                    f"in cluster '{cluster_key}'"
                )
    return ScoringConfig.model_validate(raw)


def load_sources(path: Path | None = None) -> SourcesConfig:
    """Load and validate config/sources.yaml."""
    resolved = path or (_REPO_ROOT / "config" / "sources.yaml")
    raw = _load_yaml(resolved)
    return SourcesConfig.model_validate(raw)
