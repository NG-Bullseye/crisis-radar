"""Optional Starlette REST mirror — house pattern from worker-mcp/http_server.py.

Endpoints:
  GET  /health   — liveness check
  GET  /today    — ensure today's report; returns scores + news_paragraph
  GET  /trend    — signal/streak + score series

Primary display path is the HA push (once-a-day, event-driven).
This REST mirror is an optional polling fallback for non-LLM consumers.
"""
from __future__ import annotations

import os
from datetime import date

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

PORT = int(os.environ.get("CRISIS_RADAR_PORT", "8910"))


# ── Lazy init (same as mcp_server) ───────────────────────────────────────────

_orch = None
_store = None
_scoring = None
_ha_notifier = None


def _ensure_initialized():
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
    cluster_map = {ik: ck for ck, cc in scoring.clusters.items() for ik in cc.indicators}

    store = JsonFileStore()
    ha = HomeAssistantNotifier()
    price_src = PriceApiSource(sources_cfg, cluster_map)
    llm_src = LLMResearchSource(sources_cfg, cluster_map)

    _orch = DailyRunOrchestrator(
        scoring_config=scoring,
        sources_config=sources_cfg,
        sources=[price_src, llm_src],
        store=store,
        notifiers=[ConsoleNotifier(), ha],
    )
    _store = store
    _scoring = scoring
    _ha_notifier = ha


# ── Route handlers ────────────────────────────────────────────────────────────

async def health(request: Request) -> JSONResponse:
    return JSONResponse({"service": "crisis-radar", "version": "0.1.0", "status": "ok"})


async def today(request: Request) -> JSONResponse:
    _ensure_initialized()
    from crisis_radar.reporting.render import news_paragraph

    assert _store is not None and _orch is not None  # set by _ensure_initialized
    existing = _store.load(date.today())
    if existing is None:
        existing = await _orch.run(date.today())
    else:
        if _ha_notifier is not None:
            await _ha_notifier.emit(existing)

    cluster_scores = {c.cluster_key: c.score for c in existing.clusters}
    return JSONResponse({
        "date": existing.date.isoformat(),
        "total": existing.total,
        "clusters": cluster_scores,
        "recommendation": existing.recommendation,
        "risk_level": existing.risk_level,
        "signal": {
            "active": existing.signal.active,
            "streak_days": existing.signal.streak_days,
            "required_days": existing.signal.required_days,
        },
        "news_paragraph": news_paragraph(existing),
    })


async def trend(request: Request) -> JSONResponse:
    _ensure_initialized()
    from crisis_radar.domain.signal import SignalDetector

    assert _store is not None and _scoring is not None  # set by _ensure_initialized
    window = int(request.query_params.get("window", "30"))
    history = _store.history(window=window)
    detector = SignalDetector(_scoring)
    signal = detector.evaluate(history)

    return JSONResponse({
        "active": signal.active,
        "streak_days": signal.streak_days,
        "required_days": signal.required_days,
        "since": signal.since.isoformat() if signal.since else None,
        "threshold": signal.threshold,
        "total_series": [
            {"date": r.date.isoformat(), "total": r.total}
            for r in history
        ],
    })


routes = [
    Route("/health", health, methods=["GET"]),
    Route("/today", today, methods=["GET"]),
    Route("/trend", trend, methods=["GET"]),
]

app = Starlette(routes=routes)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
