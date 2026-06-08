"""Tests for application/orchestrator.py — mocked sources, valid report produced."""
from __future__ import annotations

from datetime import date, datetime

import pytest

from crisis_radar.adapters.store_json import JsonFileStore
from crisis_radar.application.orchestrator import DailyRunOrchestrator
from crisis_radar.config import load_scoring, load_sources
from crisis_radar.domain.models import Indicator
from tests.fixtures.worked_example import make_worked_example_indicators


def _make_orchestrator(tmp_path, indicators: list[Indicator] | None = None) -> DailyRunOrchestrator:
    """Build an orchestrator with a mock source that returns the worked example."""
    scoring = load_scoring()
    sources_cfg = load_sources()
    store = JsonFileStore(reports_dir=tmp_path)

    ind_list = indicators if indicators is not None else make_worked_example_indicators()
    ind_map = {i.key: i for i in ind_list}

    class MockSource:
        async def fetch(self, key: str) -> Indicator:
            return ind_map.get(key, Indicator(
                key=key,
                cluster_key="ai_fund_health",
                value=None,
                value_kind="unknown",
                confidence=0.0,
                citations=[],
                evidence="mock not configured",
                extracted_at=datetime.utcnow(),
            ))

    return DailyRunOrchestrator(
        scoring_config=scoring,
        sources_config=sources_cfg,
        sources=[MockSource()],
        store=store,
        notifiers=[],
    )


class TestOrchestratorRun:
    @pytest.mark.asyncio
    async def test_produces_valid_report(self, tmp_path):
        orch = _make_orchestrator(tmp_path)
        report = await orch.run(date(2026, 6, 8))
        assert report is not None
        assert report.total == pytest.approx(36.0)
        assert report.recommendation == "rotate"

    @pytest.mark.asyncio
    async def test_report_saved_to_store(self, tmp_path):
        orch = _make_orchestrator(tmp_path)
        await orch.run(date(2026, 6, 8))
        store = JsonFileStore(reports_dir=tmp_path)
        loaded = store.load(date(2026, 6, 8))
        assert loaded is not None
        assert loaded.total == pytest.approx(36.0)

    @pytest.mark.asyncio
    async def test_all_unknown_run_continues(self, tmp_path):
        """If all indicators are unknown the run still produces a report."""
        scoring = load_scoring()
        sources_cfg = load_sources()
        store = JsonFileStore(reports_dir=tmp_path)

        class AlwaysUnknownSource:
            async def fetch(self, key: str) -> Indicator:
                return Indicator(
                    key=key,
                    cluster_key="ai_fund_health",
                    value=None,
                    value_kind="unknown",
                    confidence=0.0,
                    citations=[],
                    evidence="always unknown",
                    extracted_at=datetime.utcnow(),
                )

        orch = DailyRunOrchestrator(
            scoring_config=scoring,
            sources_config=sources_cfg,
            sources=[AlwaysUnknownSource()],
            store=store,
            notifiers=[],
        )
        report = await orch.run(date(2026, 6, 8))
        assert report is not None
        assert report.total == pytest.approx(0.0)

    @pytest.mark.asyncio
    async def test_rescore_reproduces_total(self, tmp_path):
        """rescore() over stored indicators must reproduce the same total (determinism proof)."""
        orch = _make_orchestrator(tmp_path)
        original = await orch.run(date(2026, 6, 8))

        rescored = await orch.rescore(date(2026, 6, 8))
        assert rescored is not None
        assert rescored.total == pytest.approx(original.total, abs=1e-6)
        assert rescored.recommendation == original.recommendation

    @pytest.mark.asyncio
    async def test_rescore_nonexistent_returns_none(self, tmp_path):
        orch = _make_orchestrator(tmp_path)
        result = await orch.rescore(date(2099, 1, 1))
        assert result is None


class TestMcpServerImport:
    """MCP server must import cleanly with no env vars set (stop condition)."""

    def test_import_without_env_vars(self):
        """Import crisis_radar.mcp_server without ANTHROPIC_API_KEY or HA_TOKEN."""
        import os
        # Remove keys temporarily
        env_backup = {}
        for key in ("ANTHROPIC_API_KEY", "HA_URL", "HA_TOKEN"):
            env_backup[key] = os.environ.pop(key, None)
        try:
            # Re-import to verify clean import
            import crisis_radar.mcp_server as m
            # Just accessing the module (which calls no network) must not raise
            assert hasattr(m, "app")
        finally:
            for key, val in env_backup.items():
                if val is not None:
                    os.environ[key] = val
