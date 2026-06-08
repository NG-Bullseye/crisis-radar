"""Tests for adapters/notify_ha.py — 8 POSTs to HA REST API (mocked httpx)."""
from __future__ import annotations

from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from crisis_radar.adapters.notify_ha import HomeAssistantNotifier, _signal_string
from crisis_radar.domain.models import ClusterScore, DailyReport, Signal


def _report() -> DailyReport:
    return DailyReport(
        date=date(2026, 6, 8),
        clusters=[
            ClusterScore(cluster_key="ai_fund_health", score=7.0, breakdown=[]),
            ClusterScore(cluster_key="fertilizer_crisis", score=49.0, breakdown=[]),
            ClusterScore(cluster_key="oil_proxy", score=52.0, breakdown=[]),
        ],
        indicators=[],
        total=36.0,
        recommendation="rotate",
        risk_level="elevated",
        signal=Signal(active=False, streak_days=9, required_days=15, since=None, threshold=30.0),
        generated_at=datetime(2026, 6, 8, 7, 32),
    )


class TestSignalString:
    def test_active(self):
        report = _report()
        report.signal = Signal(active=True, streak_days=15, required_days=15, threshold=30.0)
        assert _signal_string(report) == "ACTIVE"

    def test_building(self):
        report = _report()
        assert _signal_string(report) == "9/15"

    def test_zero_streak(self):
        report = _report()
        report.signal = Signal(active=False, streak_days=0, required_days=15, threshold=30.0)
        assert _signal_string(report) == "—"


class TestHomeAssistantNotifier:
    @pytest.mark.asyncio
    async def test_no_config_skips_silently(self):
        """Missing HA_URL/HA_TOKEN → emit does nothing, no crash."""
        notifier = HomeAssistantNotifier(ha_url="", ha_token="")
        # Should not raise
        await notifier.emit(_report())

    @pytest.mark.asyncio
    async def test_posts_8_entities(self):
        """When configured, 8 POST calls are made to HA REST API."""
        post_calls = []

        async def mock_post(url, headers, json):
            post_calls.append(url)
            mock_resp = MagicMock()
            return mock_resp

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(side_effect=lambda url, **kw: (
            post_calls.append(url), MagicMock()
        )[1])

        notifier = HomeAssistantNotifier(ha_url="http://ha:8123", ha_token="test-token")

        with patch("crisis_radar.adapters.notify_ha._httpx") as mock_httpx:
            mock_httpx.AsyncClient.return_value = mock_client
            mock_client.post = AsyncMock(side_effect=lambda url, **kw: (
                post_calls.append(url), MagicMock()
            )[1])
            await notifier.emit(_report())

        # 8 sensor entities should be posted
        assert len(post_calls) == 8

    @pytest.mark.asyncio
    async def test_entity_urls_correct(self):
        """Verify the 8 entity IDs are the contracted ones."""
        posted_entities = []

        notifier = HomeAssistantNotifier(ha_url="http://ha:8123", ha_token="tok")

        async def fake_ha_api(endpoint, data):
            posted_entities.append(endpoint)

        notifier._ha_api = fake_ha_api  # type: ignore[method-assign]

        with patch("crisis_radar.adapters.notify_ha._HTTPX_AVAILABLE", True):
            await notifier.emit(_report())

        expected = {
            "/api/states/sensor.crisis_radar_total",
            "/api/states/sensor.crisis_radar_ai_fund",
            "/api/states/sensor.crisis_radar_fertilizer",
            "/api/states/sensor.crisis_radar_oil",
            "/api/states/sensor.crisis_radar_recommendation",
            "/api/states/sensor.crisis_radar_risk",
            "/api/states/sensor.crisis_radar_signal",
            "/api/states/sensor.crisis_radar_updated",
        }
        assert set(posted_entities) == expected
