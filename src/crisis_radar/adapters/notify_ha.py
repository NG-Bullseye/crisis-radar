"""HomeAssistantNotifier — push Crisis Radar metrics into HA sensor states.

Writes 8 sensor.crisis_radar_* entities via HA REST API POST /api/states/<entity>
with Bearer token from env (HA_URL / HA_TOKEN). Matches the _ha_api pattern in
worker-mcp/server.py.

Entity contract: docs/integrations/mcp-news-and-display.md § Home Assistant entity contract.
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from crisis_radar.domain.models import DailyReport

# httpx is only imported when actually pushing — missing key means we never get there.
try:
    import httpx as _httpx
    _HTTPX_AVAILABLE = True
except ImportError:
    _HTTPX_AVAILABLE = False


def _signal_string(report: DailyReport) -> str:
    """Format the signal as a display string (e.g. '9/15', 'ACTIVE', or '—')."""
    sig = report.signal
    if sig.active:
        return "ACTIVE"
    if sig.streak_days > 0:
        return f"{sig.streak_days}/{sig.required_days}"
    return "—"  # em-dash


class HomeAssistantNotifier:
    """Push report metrics to 8 Home Assistant sensor states.

    Silently skips if HA_URL / HA_TOKEN are not set.
    """

    def __init__(self, ha_url: str | None = None, ha_token: str | None = None) -> None:
        self._url = ha_url or os.environ.get("HA_URL", "")
        self._token = ha_token or os.environ.get("HA_TOKEN", "")

    def _configured(self) -> bool:
        return bool(self._url and self._token)

    async def _ha_api(self, endpoint: str, data: dict[str, Any]) -> None:
        """POST to HA REST API — same pattern as worker-mcp `_ha_api`."""
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }
        async with _httpx.AsyncClient(timeout=15) as client:
            await client.post(f"{self._url}{endpoint}", headers=headers, json=data)

    async def emit(self, report: DailyReport, signal_changed: bool = False) -> None:
        if not self._configured():
            return  # HA not wired → skip silently

        if not _HTTPX_AVAILABLE:
            return

        # Build cluster score lookup.
        cluster_scores = {c.cluster_key: c.score for c in report.clusters}

        entities: dict[str, dict[str, Any]] = {
            "sensor.crisis_radar_total": {
                "state": report.total,
                "attributes": {"unit_of_measurement": "score", "friendly_name": "Crisis Radar Total"},
            },
            "sensor.crisis_radar_ai_fund": {
                "state": cluster_scores.get("ai_fund_health", 0),
                "attributes": {"unit_of_measurement": "score", "friendly_name": "Crisis Radar AI Fund"},
            },
            "sensor.crisis_radar_fertilizer": {
                "state": cluster_scores.get("fertilizer_crisis", 0),
                "attributes": {"unit_of_measurement": "score", "friendly_name": "Crisis Radar Fertilizer"},
            },
            "sensor.crisis_radar_oil": {
                "state": cluster_scores.get("oil_proxy", 0),
                "attributes": {"unit_of_measurement": "score", "friendly_name": "Crisis Radar Oil"},
            },
            "sensor.crisis_radar_recommendation": {
                "state": report.recommendation,
                "attributes": {"friendly_name": "Crisis Radar Recommendation"},
            },
            "sensor.crisis_radar_risk": {
                "state": report.risk_level,
                "attributes": {"friendly_name": "Crisis Radar Risk Level"},
            },
            "sensor.crisis_radar_signal": {
                "state": _signal_string(report),
                "attributes": {
                    "active": report.signal.active,
                    "streak_days": report.signal.streak_days,
                    "required_days": report.signal.required_days,
                    "friendly_name": "Crisis Radar Signal",
                },
            },
            "sensor.crisis_radar_updated": {
                "state": datetime.utcnow().isoformat(timespec="seconds"),
                "attributes": {"friendly_name": "Crisis Radar Last Updated"},
            },
        }

        for entity_id, payload in entities.items():
            try:
                await self._ha_api(f"/api/states/{entity_id}", payload)
            except Exception:
                pass  # Individual entity failure never aborts the push
