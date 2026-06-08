# ADR-0005 — Pluggable indicator sources (LLM research vs. structured feeds)

- **Status:** accepted
- **Date:** 2026-06-08

## Context

Indicators differ in kind. Gas and oil prices are exact numbers best taken from a data feed; escalation levels, outages, and news counts are qualitative judgments that require reading many sources. Forcing both through one mechanism either makes prices unreliable (scraped prose) or makes qualitative cues rigid.

## Decision

Define one port, `IndicatorSource.fetch(key) -> Indicator`, with multiple adapters chosen per indicator via `config/sources.yaml`:

- `PriceApiSource` — direct numeric feeds for `gas_ttf_eur_mwh`, `wti_usd_bbl` (confidence ≈ 1.0).
- `LLMResearchSource` — Claude + web search for everything qualitative, under the extraction contract.

## Consequences

- Each indicator uses the most reliable channel available; routing is config, not code.
- New source types (another price API, a specialized feed) are new adapters behind the same port — the orchestrator and scorer never change.
- The orchestrator treats all sources uniformly; a failing source degrades that one indicator to `unknown` (ADR-0006), never aborting the run.
