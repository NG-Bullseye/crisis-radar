"""Crisis Radar MCP server (stdio transport).

Tools:
  crisis_radar__today  — ensure today's report (run pipeline if missing), push HA, return scores + news_paragraph
  crisis_radar__trend  — signal/streak over recent window (no recompute)
  crisis_radar__rescore — re-score a stored day deterministically (no web)

House pattern: mcp SDK stdio, ns__tool naming, HA write via _ha_api REST.
Matches nvda-cpi-watch / worker-mcp style.

IMPORTANT: this file imports cleanly with NO env vars set (no API keys required
at import time). All secrets are only accessed at tool-call time.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import date
from typing import Any

from mcp import types
from mcp.server import Server
from mcp.server.stdio import stdio_server

logger = logging.getLogger(__name__)

app = Server("crisis-radar")

# ── Lazy config + adapter initialization ─────────────────────────────────────
# Deferred until first tool call so `import crisis_radar.mcp_server` with no
# env vars never raises (the stop condition requires this).

_orch: Any = None  # DailyRunOrchestrator; lazy-initialized on first tool call
_store: Any = None  # JsonFileStore
_scoring: Any = None  # ScoringConfig
_ha_notifier: Any = None  # HomeAssistantNotifier


def _ensure_initialized():
    """Lazy-init all adapters. Safe to call multiple times (idempotent)."""
    global _orch, _store, _scoring, _ha_notifier

    if _orch is not None:
        return

    from crisis_radar.adapters.notify_console import ConsoleNotifier
    from crisis_radar.adapters.notify_ha import HomeAssistantNotifier
    from crisis_radar.adapters.price_api import PriceApiSource
    from crisis_radar.adapters.research_llm import LLMResearchSource
    from crisis_radar.adapters.store_json import JsonFileStore
    from crisis_radar.application.orchestrator import DailyRunOrchestrator
    from crisis_radar.config import load_scoring, load_sources

    scoring = load_scoring()
    sources_cfg = load_sources()

    cluster_map: dict[str, str] = {}
    for ck, cc in scoring.clusters.items():
        for ik in cc.indicators:
            cluster_map[ik] = ck

    store = JsonFileStore()
    ha = HomeAssistantNotifier()
    price_src = PriceApiSource(sources_cfg, cluster_map)
    llm_src = LLMResearchSource(sources_cfg, cluster_map)

    orch = DailyRunOrchestrator(
        scoring_config=scoring,
        sources_config=sources_cfg,
        sources=[price_src, llm_src],
        store=store,
        notifiers=[ConsoleNotifier(), ha],
    )

    _orch = orch
    _store = store
    _scoring = scoring
    _ha_notifier = ha


# ── Tool list ─────────────────────────────────────────────────────────────────

@app.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="crisis_radar__today",
            description=(
                "Ensure today's Crisis Radar report exists (runs the full pipeline if missing, "
                "else loads cached). Pushes the 8 sensor.crisis_radar_* states to Home Assistant. "
                "Returns scores + a ready-made German news paragraph (TTS-safe). Idempotent per day."
            ),
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="crisis_radar__trend",
            description=(
                "Return the rotation signal status and score series over the recent window. "
                "No recompute — reads stored history only."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "window": {"type": "integer", "default": 30, "description": "Days to look back"},
                },
            },
        ),
        types.Tool(
            name="crisis_radar__rescore",
            description=(
                "Re-score a stored day deterministically (no web calls, no HA push). "
                "Proves the scorer is reproducible over stored indicators."
            ),
            inputSchema={
                "type": "object",
                "required": ["date"],
                "properties": {
                    "date": {"type": "string", "description": "YYYY-MM-DD"},
                },
            },
        ),
    ]


# ── Tool dispatch ─────────────────────────────────────────────────────────────

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    try:
        _ensure_initialized()
        if name == "crisis_radar__today":
            result = await _handle_today()
        elif name == "crisis_radar__trend":
            result = await _handle_trend(arguments)
        elif name == "crisis_radar__rescore":
            result = await _handle_rescore(arguments)
        else:
            result = {"error": f"unknown tool: {name}"}
    except Exception as exc:
        result = {"error": f"{type(exc).__name__}: {exc}"}

    return [types.TextContent(type="text", text=json.dumps(result, indent=2, default=str))]


async def _handle_today() -> dict:
    """Ensure today's report and push HA; return scores + news_paragraph."""
    from crisis_radar.reporting.render import news_paragraph

    today = date.today()

    assert _store is not None and _orch is not None  # guaranteed by _ensure_initialized()
    # Check cache first (idempotent per day).
    existing = _store.load(today)
    if existing is None:
        existing = await _orch.run(today)
    else:
        # Report cached; re-push HA values (idempotent display update).
        if _ha_notifier is not None:
            await _ha_notifier.emit(existing)

    cluster_scores = {c.cluster_key: c.score for c in existing.clusters}

    return {
        "date": existing.date.isoformat(),
        "total": existing.total,
        "clusters": cluster_scores,
        "recommendation": existing.recommendation,
        "risk_level": existing.risk_level,
        "signal": {
            "active": existing.signal.active,
            "streak_days": existing.signal.streak_days,
            "required_days": existing.signal.required_days,
            "since": existing.signal.since.isoformat() if existing.signal.since else None,
        },
        "news_paragraph": news_paragraph(existing),
    }


async def _handle_trend(args: dict) -> dict:
    """Return signal status + score series (read-only)."""
    from crisis_radar.domain.signal import SignalDetector

    assert _store is not None and _scoring is not None  # guaranteed by _ensure_initialized()
    window = int(args.get("window", 30))
    history = _store.history(window=window)
    detector = SignalDetector(_scoring)
    signal = detector.evaluate(history)

    return {
        "active": signal.active,
        "streak_days": signal.streak_days,
        "required_days": signal.required_days,
        "since": signal.since.isoformat() if signal.since else None,
        "threshold": signal.threshold,
        "window_days": len(history),
        "total_series": [
            {"date": r.date.isoformat(), "total": r.total}
            for r in history
        ],
    }


async def _handle_rescore(args: dict) -> dict:
    """Re-score stored indicators for a date (no web)."""
    assert _orch is not None  # guaranteed by _ensure_initialized()
    date_str = args.get("date", "")
    try:
        target = date.fromisoformat(date_str)
    except ValueError:
        return {"error": f"invalid date: {date_str}"}

    report = await _orch.rescore(target)
    if report is None:
        return {"error": f"no stored report for {date_str}"}

    return {
        "date": report.date.isoformat(),
        "total": report.total,
        "recommendation": report.recommendation,
        "risk_level": report.risk_level,
        "clusters": {c.cluster_key: c.score for c in report.clusters},
    }


# ── Entrypoint ────────────────────────────────────────────────────────────────

async def main() -> None:
    async with stdio_server() as (reader, writer):
        await app.run(reader, writer, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
