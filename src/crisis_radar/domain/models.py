"""Domain models — the shared data contracts.

All fields are per data-model.md. This module MUST remain I/O-free and must
not import anthropic, httpx, or any network library.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

ClusterKey = Literal["ai_fund_health", "fertilizer_crisis", "oil_proxy"]
ValueKind = Literal["number", "count", "enum", "bool", "unknown"]
RecommendationEnum = Literal["rotate", "half_position", "observe", "no_rotation"]
RiskLevelEnum = Literal["low", "medium", "elevated"]


class Citation(BaseModel):
    """A single source reference for an indicator value."""

    url: str
    title: str
    published: date | None = None


class Indicator(BaseModel):
    """The atomic unit of measured truth — produced by a source, scored by the engine.

    `points` is None until the Scorer fills it. `unknown` indicators carry no citations
    and contribute 0 points (ADR-0006).
    """

    key: str
    cluster_key: ClusterKey
    value: Any = None  # number | int | bool | str | None
    value_kind: ValueKind = "unknown"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    citations: list[Citation] = Field(default_factory=list)
    evidence: str = ""
    points: int | None = None
    extracted_at: datetime = Field(default_factory=datetime.utcnow)


class ClusterScore(BaseModel):
    """Scored result for one cluster — clamped sum with per-indicator breakdown."""

    cluster_key: ClusterKey
    score: float  # clamped to [-100, +100]
    breakdown: list[dict[str, Any]] = Field(default_factory=list)  # [{key, points}]


class Signal(BaseModel):
    """Rotation signal derived from trend history, not a single day."""

    active: bool
    streak_days: int = 0
    required_days: int = 15
    since: date | None = None
    threshold: float = 30.0


class DailyReport(BaseModel):
    """The persisted output of one Crisis Radar daily run (one per day)."""

    schema_version: str = "1.0"
    date: date
    clusters: list[ClusterScore]  # exactly three
    indicators: list[Indicator]
    total: float  # mean(cluster scores), range [-100, +100]
    recommendation: RecommendationEnum
    risk_level: RiskLevelEnum
    summary: str = ""
    signal: Signal
    generated_at: datetime = Field(default_factory=datetime.utcnow)
