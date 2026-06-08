"""DailyRunOrchestrator — wires the pipeline end-to-end.

Flow: fetch all indicators → score → save → load history → signal → notify.
One indicator failing → unknown + continue; the run always produces a report.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime

from crisis_radar.config import ScoringConfig, SourcesConfig
from crisis_radar.domain.models import DailyReport, Indicator, Signal
from crisis_radar.domain.scorer import score
from crisis_radar.domain.signal import SignalDetector
from crisis_radar.ports import IndicatorSource, Notifier, ReportStore

logger = logging.getLogger(__name__)


def _unknown_indicator(key: str, cluster_key: str) -> Indicator:
    from crisis_radar.domain.models import Indicator as Ind
    return Ind(
        key=key,
        cluster_key=cluster_key,  # type: ignore[arg-type]
        value=None,
        value_kind="unknown",
        confidence=0.0,
        evidence="Source unavailable or raised an exception during fetch.",
        extracted_at=datetime.utcnow(),
    )


class DailyRunOrchestrator:
    """Runs the full daily pipeline."""

    def __init__(
        self,
        scoring_config: ScoringConfig,
        sources_config: SourcesConfig,
        sources: list[IndicatorSource],
        store: ReportStore,
        notifiers: list[Notifier],
    ) -> None:
        self._scoring = scoring_config
        self._sources_cfg = sources_config
        self._sources = sources
        self._store = store
        self._notifiers = notifiers
        self._detector = SignalDetector(scoring_config)

        # Build cluster map: indicator key → cluster key (from scoring config).
        self._cluster_map: dict[str, str] = {}
        for cluster_key, cluster_cfg in scoring_config.clusters.items():
            for ind_key in cluster_cfg.indicators:
                self._cluster_map[ind_key] = cluster_key

    async def run(self, run_date: date | None = None) -> DailyReport:
        """Execute the full daily pipeline and return the produced report."""
        today = run_date or date.today()

        # 1. Fetch all indicators.
        indicators = await self._fetch_all(today)

        # 2. Score (deterministic).
        clusters, total, recommendation, risk_level = score(indicators, self._scoring)

        # 3. Load history (for signal).
        history = self._store.history(window=self._scoring.signal.rotation.consecutive_days + 5)

        # Build a dummy today entry with today's total so the signal sees it.
        # We append after loading history to avoid double-counting.
        today_stub = DailyReport(
            date=today,
            clusters=clusters,
            indicators=indicators,
            total=total,
            recommendation=recommendation,
            risk_level=risk_level,
            signal=Signal(
                active=False,
                streak_days=0,
                required_days=self._scoring.signal.rotation.consecutive_days,
                threshold=self._scoring.signal.rotation.threshold,
            ),
        )
        # Replace any previously saved today entry in history window with today_stub.
        history_without_today = [r for r in history if r.date != today]
        full_history = history_without_today + [today_stub]

        # 4. Evaluate signal.
        signal = self._detector.evaluate(full_history)

        # 5. Build the final report.
        previous_signal_active = False
        if history_without_today:
            last = max(history_without_today, key=lambda r: r.date)
            previous_signal_active = last.signal.active

        report = DailyReport(
            date=today,
            clusters=clusters,
            indicators=indicators,
            total=total,
            recommendation=recommendation,
            risk_level=risk_level,
            signal=signal,
            summary=self._build_summary(total, recommendation, signal),
        )

        # 6. Save.
        self._store.save(report)

        # 7. Notify.
        signal_changed = signal.active != previous_signal_active
        await self._notify_all(report, signal_changed)

        return report

    async def rescore(self, target_date: date) -> DailyReport | None:
        """Re-score stored indicators for a date — no web calls, must reproduce total.

        Returns None if no stored report exists for the date.
        """
        stored = self._store.load(target_date)
        if stored is None:
            return None

        # Re-run only the deterministic core over stored indicators (research-pipeline.md).
        clusters, total, recommendation, risk_level = score(stored.indicators, self._scoring)

        # Reload signal (history unchanged).
        history = self._store.history(window=self._scoring.signal.rotation.consecutive_days + 5)
        stub = DailyReport(
            date=target_date,
            clusters=clusters,
            indicators=stored.indicators,
            total=total,
            recommendation=recommendation,
            risk_level=risk_level,
            signal=Signal(
                active=False,
                streak_days=0,
                required_days=self._scoring.signal.rotation.consecutive_days,
                threshold=self._scoring.signal.rotation.threshold,
            ),
        )
        history_without = [r for r in history if r.date != target_date]
        signal = self._detector.evaluate(history_without + [stub])

        return DailyReport(
            date=target_date,
            clusters=clusters,
            indicators=stored.indicators,
            total=total,
            recommendation=recommendation,
            risk_level=risk_level,
            signal=signal,
            summary=stored.summary,
            generated_at=stored.generated_at,
        )

    async def _fetch_all(self, run_date: date) -> list[Indicator]:
        """Fetch all configured indicators; failures → unknown, run continues."""
        tasks = []
        keys_with_source: list[tuple[str, str]] = []  # (key, cluster_key)

        for cluster_key, cluster_cfg in self._scoring.clusters.items():
            for ind_key in cluster_cfg.indicators:
                keys_with_source.append((ind_key, cluster_key))
                tasks.append(self._safe_fetch(ind_key, cluster_key))

        results = await asyncio.gather(*tasks)
        return list(results)

    async def _safe_fetch(self, key: str, cluster_key: str) -> Indicator:
        """Try each source in order; return first non-unknown result or unknown."""
        for source in self._sources:
            try:
                ind = await source.fetch(key)
                if ind.value_kind != "unknown":
                    ind.cluster_key = cluster_key  # type: ignore[assignment]
                    return ind
            except Exception as exc:
                logger.warning("Source %s failed for %s: %s", type(source).__name__, key, exc)
        return _unknown_indicator(key, cluster_key)

    async def _notify_all(self, report: DailyReport, signal_changed: bool) -> None:
        for notifier in self._notifiers:
            try:
                await notifier.emit(report, signal_changed)
            except Exception as exc:
                logger.warning("Notifier %s failed: %s", type(notifier).__name__, exc)

    @staticmethod
    def _build_summary(total: float, recommendation: str, signal: Signal) -> str:
        if signal.active:
            return (
                f"Gesamtscore {total:+.1f} — Rotation-Signal aktiv ({signal.streak_days} Tage in Folge)."
            )
        if signal.streak_days > 0:
            return (
                f"Gesamtscore {total:+.1f} — Signal baut sich auf "
                f"({signal.streak_days}/{signal.required_days} Tage über Schwelle)."
            )
        return f"Gesamtscore {total:+.1f} — {recommendation}. Kein aktives Rotationssignal."
