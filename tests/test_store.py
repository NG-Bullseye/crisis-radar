"""Tests for adapters/store_json.py — round-trip lossless + schema valid."""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

from crisis_radar.adapters.store_json import JsonFileStore
from crisis_radar.domain.models import ClusterScore, DailyReport, Signal


def _minimal_report(report_date: date = date(2026, 6, 8)) -> DailyReport:
    return DailyReport(
        date=report_date,
        clusters=[
            ClusterScore(cluster_key="ai_fund_health", score=7.0,
                         breakdown=[{"key": "product_announcements", "points": 10}]),
            ClusterScore(cluster_key="fertilizer_crisis", score=49.0,
                         breakdown=[{"key": "gas_ttf_eur_mwh", "points": 20}]),
            ClusterScore(cluster_key="oil_proxy", score=52.0,
                         breakdown=[{"key": "wti_usd_bbl", "points": 25}]),
        ],
        indicators=[],
        total=36.0,
        recommendation="rotate",
        risk_level="elevated",
        summary="Test report",
        signal=Signal(active=False, streak_days=1, required_days=15, since=None, threshold=30.0),
        generated_at=datetime(2026, 6, 8, 7, 32, 10),
    )


class TestRoundTrip:
    def test_save_and_load(self, tmp_path: Path):
        store = JsonFileStore(reports_dir=tmp_path)
        original = _minimal_report()
        store.save(original)
        loaded = store.load(date(2026, 6, 8))
        assert loaded is not None
        assert loaded.total == original.total
        assert loaded.recommendation == original.recommendation
        assert loaded.date == original.date

    def test_lossless(self, tmp_path: Path):
        """Loaded report must round-trip identically on all scalar fields."""
        store = JsonFileStore(reports_dir=tmp_path)
        original = _minimal_report()
        store.save(original)
        loaded = store.load(date(2026, 6, 8))
        assert loaded is not None
        assert loaded.model_dump() == original.model_dump()

    def test_load_nonexistent_returns_none(self, tmp_path: Path):
        store = JsonFileStore(reports_dir=tmp_path)
        assert store.load(date(2099, 1, 1)) is None

    def test_history_ordered_oldest_first(self, tmp_path: Path):
        store = JsonFileStore(reports_dir=tmp_path)
        dates = [date(2026, 6, 1), date(2026, 6, 3), date(2026, 6, 2)]
        for d in dates:
            store.save(_minimal_report(d))
        history = store.history(window=10)
        assert [r.date for r in history] == sorted(dates)

    def test_history_respects_window(self, tmp_path: Path):
        store = JsonFileStore(reports_dir=tmp_path)
        for i in range(10):
            store.save(_minimal_report(date(2026, 6, 1 + i)))
        history = store.history(window=3)
        assert len(history) == 3

    def test_schema_valid(self, tmp_path: Path):
        """Saved JSON must pass the daily_report.schema.json contract."""
        import jsonschema

        store = JsonFileStore(reports_dir=tmp_path)
        original = _minimal_report()
        store.save(original)
        json_file = tmp_path / "2026-06-08.json"
        raw = json.loads(json_file.read_text())

        schema_path = (
            Path(__file__).parent.parent / "schemas" / "daily_report.schema.json"
        )
        schema = json.loads(schema_path.read_text())
        # Should not raise
        jsonschema.validate(instance=raw, schema=schema)
