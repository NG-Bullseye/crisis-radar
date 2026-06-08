"""PriceApiSource — structured numeric feed for gas/oil prices.

Hard numbers (gas TTF, WTI crude) come from a reliable data feed rather than
scraped prose — more deterministic and exact (research-pipeline.md §Two source types).

The concrete provider is configured via PRICE_API_KEY in env. If unconfigured,
the adapter returns unknown cleanly rather than crashing.
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from crisis_radar.config import SourcesConfig
from crisis_radar.domain.models import Indicator

# httpx availability checked at call time — import deferred to avoid crash on missing key
_HTTPX_AVAILABLE = True
try:
    import httpx as _httpx  # noqa: F401 — availability probe; used when provider is wired in
except ImportError:
    _HTTPX_AVAILABLE = False


# Feed → URL/resolver registry (add providers here, not in domain code).
# Currently a stub: provider selection lives in PRICE_API_PROVIDER env var.
_FEED_REGISTRY: dict[str, dict[str, str]] = {
    "ttf_front_month": {
        "description": "European TTF natural gas front-month price (EUR/MWh)",
        "unit": "EUR/MWh",
    },
    "wti_crude": {
        "description": "WTI crude oil front-month price (USD/bbl)",
        "unit": "USD/bbl",
    },
}


def _unknown(key: str, cluster_key: str) -> Indicator:
    return Indicator(
        key=key,
        cluster_key=cluster_key,  # type: ignore[arg-type]
        value=None,
        value_kind="unknown",
        confidence=0.0,
        citations=[],
        evidence="Price feed not configured or fetch failed.",
        extracted_at=datetime.utcnow(),
    )


class PriceApiSource:
    """Fetch hard numeric prices from a structured feed.

    Gracefully degrades to unknown when the API key is not set — never crashes.
    """

    def __init__(
        self,
        sources_config: SourcesConfig,
        cluster_map: dict[str, str],
        client: Any = None,  # injectable httpx.AsyncClient for testing
    ) -> None:
        self._sources = sources_config.indicators
        self._cluster_map = cluster_map
        self._client = client

    async def fetch(self, key: str) -> Indicator:
        """Fetch price for `key`; returns unknown on any error."""
        cluster_key = self._cluster_map.get(key, "oil_proxy")
        source = self._sources.get(key)
        if source is None or source.source_type != "price_api":
            return _unknown(key, cluster_key)

        api_key = os.environ.get("PRICE_API_KEY", "")
        if not api_key:
            # No provider configured — honest unknown, logged in evidence.
            return _unknown(key, cluster_key)

        try:
            return await self._fetch_price(key, cluster_key, source, api_key)
        except Exception:
            return _unknown(key, cluster_key)

    async def _fetch_price(
        self,
        key: str,
        cluster_key: str,
        source: Any,
        api_key: str,
    ) -> Indicator:
        """Provider stub: extend here when a concrete feed is wired in."""
        # TODO: wire a real provider (e.g. Commodities API, Stooq, Alpha Vantage)
        # For now returns unknown — the caller handles it gracefully.
        return _unknown(key, cluster_key)
