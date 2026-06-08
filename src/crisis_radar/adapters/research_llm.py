"""LLMResearchSource — Claude + web search → typed, cited Indicator.

Anti-hallucination rules (enforced in code, not just prompt — research-pipeline.md):
  1. No citation → downgrade to unknown.
  2. Enum value not in whitelist → unknown.
  3. Type mismatch (bad number, negative count) → unknown.
  4. Model raises / returns malformed JSON → unknown, never a crash.

The LLM's job is EXTRACTION, not scoring. It never sees points or clusters.
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from crisis_radar.config import SourcesConfig
from crisis_radar.domain.models import Citation, Indicator

# anthropic is optional at import time — missing key or missing lib → unknown indicators,
# never an ImportError that prevents the rest of the app from starting.
try:
    import anthropic as _anthropic
    _ANTHROPIC_AVAILABLE = True
except ImportError:
    _ANTHROPIC_AVAILABLE = False

_MODEL = "claude-opus-4-5"

# Tool schema that forces structured output from the LLM.
_EXTRACTION_TOOL = {
    "name": "record_indicator",
    "description": (
        "Record the extracted value for the requested indicator. "
        "Always call this tool — use value_kind=unknown if you cannot find reliable data."
    ),
    "input_schema": {
        "type": "object",
        "required": ["value", "value_kind", "confidence", "evidence", "citations"],
        "properties": {
            "value": {
                "description": "The measured value (number, count int, enum string, bool, or null for unknown)",
                "type": ["number", "integer", "string", "boolean", "null"],
            },
            "value_kind": {
                "type": "string",
                "enum": ["number", "count", "enum", "bool", "unknown"],
            },
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "evidence": {
                "type": "string",
                "description": "One sentence quoting or paraphrasing the key finding from a source.",
            },
            "citations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["url", "title"],
                    "properties": {
                        "url": {"type": "string"},
                        "title": {"type": "string"},
                        "published": {"type": ["string", "null"]},
                    },
                },
            },
        },
    },
}


def _unknown(key: str, cluster_key: str) -> Indicator:
    """Return a well-formed unknown indicator — contributes 0, stays visible."""
    return Indicator(
        key=key,
        cluster_key=cluster_key,  # type: ignore[arg-type]
        value=None,
        value_kind="unknown",
        confidence=0.0,
        citations=[],
        evidence="No reliable data found or extraction failed.",
        extracted_at=datetime.utcnow(),
    )


def _validate_extracted(
    data: dict[str, Any],
    key: str,
    cluster_key: str,
    allowed_values: list[str],
) -> Indicator:
    """Apply anti-hallucination rules and return a valid Indicator.

    All failing cases produce unknown, never a crash.
    """
    value_kind = data.get("value_kind", "unknown")
    value = data.get("value")
    confidence = float(data.get("confidence", 0.0))
    evidence = str(data.get("evidence", ""))
    raw_citations = data.get("citations", [])

    # Rule 1: no citation on non-unknown → downgrade.
    if value_kind != "unknown" and not raw_citations:
        return _unknown(key, cluster_key)

    # Rule 2: enum whitelist.
    if value_kind == "enum" and allowed_values:
        if not isinstance(value, str) or value not in allowed_values:
            return _unknown(key, cluster_key)

    # Rule 3: type mismatch.
    if value_kind == "number":
        try:
            value = float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return _unknown(key, cluster_key)
    elif value_kind == "count":
        try:
            count = int(value)  # type: ignore[arg-type]
            if count < 0:
                return _unknown(key, cluster_key)
            value = count
        except (TypeError, ValueError):
            return _unknown(key, cluster_key)
    elif value_kind == "bool":
        if isinstance(value, str):
            if value.lower() not in ("true", "false"):
                return _unknown(key, cluster_key)
            value = value.lower() == "true"
        elif not isinstance(value, bool):
            return _unknown(key, cluster_key)

    # Build citations.
    citations: list[Citation] = []
    for c in raw_citations:
        if not isinstance(c, dict) or not c.get("url") or not c.get("title"):
            continue
        try:
            citations.append(
                Citation(
                    url=c["url"],
                    title=c["title"],
                    published=c.get("published"),
                )
            )
        except Exception:
            pass

    if value_kind != "unknown" and not citations:
        return _unknown(key, cluster_key)

    return Indicator(
        key=key,
        cluster_key=cluster_key,  # type: ignore[arg-type]
        value=value if value_kind != "unknown" else None,
        value_kind=value_kind,  # type: ignore[arg-type]
        confidence=confidence,
        citations=citations,
        evidence=evidence,
        extracted_at=datetime.utcnow(),
    )


class LLMResearchSource:
    """Fetch one indicator via Claude + web search.

    Falls back to unknown on any error (missing API key, network failure, bad
    model output) — the run always continues (architecture.md §10).
    """

    def __init__(
        self,
        sources_config: SourcesConfig,
        cluster_map: dict[str, str],  # indicator key → cluster key
        client: Any = None,  # injectable for testing
    ) -> None:
        self._sources = sources_config.indicators
        self._cluster_map = cluster_map
        self._client = client  # None = create lazily from env

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        if not _ANTHROPIC_AVAILABLE:
            return None
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            return None
        return _anthropic.Anthropic(api_key=api_key)

    async def fetch(self, key: str) -> Indicator:
        """Fetch one indicator by key.

        Any exception inside → unknown indicator, no crash.
        """
        cluster_key = self._cluster_map.get(key, "ai_fund_health")
        source = self._sources.get(key)
        if source is None or source.source_type != "llm_research":
            return _unknown(key, cluster_key)

        client = self._get_client()
        if client is None:
            # No API key configured — honest unknown, not a guess.
            return _unknown(key, cluster_key)

        try:
            return await self._run_extraction(key, cluster_key, source, client)
        except Exception:
            return _unknown(key, cluster_key)

    def _call_client(self, client: Any, system: str, user_msg: str) -> Any:
        """Call the Anthropic client synchronously. Extracted for testability."""
        return client.messages.create(
            model=_MODEL,
            max_tokens=1024,
            system=system,
            tools=[
                {"type": "web_search_20250305", "name": "web_search"},
                _EXTRACTION_TOOL,
            ],
            messages=[{"role": "user", "content": user_msg}],
        )

    async def _run_extraction(
        self, key: str, cluster_key: str, source: Any, client: Any
    ) -> Indicator:
        """Call Claude with web_search tool + extraction tool."""
        import asyncio

        system = (
            "You are a financial/geopolitical data extraction agent. "
            "Your only job: find the current value of the requested indicator and cite your sources. "
            "Do NOT score, rate, or recommend anything — only extract the measured fact. "
            "If you cannot find reliable recent data, use value_kind=unknown. "
            "Always call the record_indicator tool with your result."
        )

        user_msg = (
            f"Find the current value of indicator: {key}\n"
            f"Query: {source.query or f'Current value of {key}'}\n"
        )
        if source.allowed_values:
            user_msg += f"Allowed enum values: {source.allowed_values}\n"
        if source.allowed_domains:
            user_msg += f"Preferred sources: {', '.join(source.allowed_domains)}\n"

        # Run sync Anthropic client in executor to keep async compatibility.
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None, lambda: self._call_client(client, system, user_msg)
        )

        # Extract the record_indicator tool call result.
        for block in response.content:
            if (
                hasattr(block, "type") and block.type == "tool_use"
                and block.name == "record_indicator"
            ):
                return _validate_extracted(
                    block.input,
                    key,
                    cluster_key,
                    source.allowed_values,
                )

        # Model didn't call the tool → unknown.
        return _unknown(key, cluster_key)
