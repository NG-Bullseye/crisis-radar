# ADR-0007 — One MCP server as the integration surface; the daily call is the trigger

- **Status:** accepted
- **Date:** 2026-06-08

## Context

Crisis Radar must (a) appear as a paragraph in the news-agent's morning briefing and (b) update a once-a-day Cortex wall display. The briefing is produced by an LLM with tools (Cortex's Claude path); the display is an ESPHome device that already knows how to read Home Assistant entities. Two consumers, one daily cadence.

The naive design would give each consumer its own path: an HTTP endpoint the briefing scrapes, plus a separate cron that recomputes and pushes to the display. That duplicates the run and creates two code paths that can drift.

## Decision

Expose **one MCP server** (house pattern: `mcp` SDK stdio + `.mcp.json`, like `nvda-cpi-watch`/`worker-mcp`) with a single primary tool `crisis_radar__today`. That tool is the **one trigger**:

1. ensures today's report exists (runs the deterministic pipeline if missing, else returns cached — idempotent per day),
2. pushes the metrics to Home Assistant entities (`sensor.crisis_radar_*`) as a side effect — the display reads HA, never Crisis Radar directly,
3. returns the structured scores **plus** a ready-made German `news_paragraph`.

The news-agent calls the tool during its briefing (becoming the de-facto daily trigger); the same call updates the display. An optional `http_server.py` REST mirror serves non-LLM consumers as a fallback.

## Consequences

- One run per day, one source of truth for the day's number; the briefing paragraph and the display can never disagree.
- The display stays decoupled (ESP ↔ HA only), consistent with the home's "HA is the protocol adapter" pattern.
- The MCP hop carries real work (pipeline + persistence + HA push + paragraph rendering), so it is not a thin forwarder.
- Cross-repo touches are minimal and explicit: one `prompt.md` block in news-agent, one `.mcp.json` registration in the Cortex news path.
- Trade-off: the briefing run absorbs the report latency on the first call of the day. If that ever hurts, a 06:00 pre-warm cron makes the 08:30 call a cache hit — without changing this design.
