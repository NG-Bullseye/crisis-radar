"""Tests for adapters/research_llm.py — anti-hallucination contract, mocked client."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from crisis_radar.adapters.research_llm import (
    LLMResearchSource,
    _validate_extracted,
)
from crisis_radar.config import load_sources


def _sources():
    return load_sources()


def _cluster_map():
    from crisis_radar.config import load_scoring
    cfg = load_scoring()
    return {ik: ck for ck, cc in cfg.clusters.items() for ik in cc.indicators}


# ── _validate_extracted ────────────────────────────────────────────────────────

class TestValidateExtracted:
    def _basic(self, **kwargs) -> dict:
        return {
            "value": 58.0,
            "value_kind": "number",
            "confidence": 0.9,
            "evidence": "TTF at 58.",
            "citations": [{"url": "https://example.com", "title": "Test"}],
            **kwargs,
        }

    def test_valid_number(self):
        ind = _validate_extracted(self._basic(), "gas_ttf_eur_mwh", "fertilizer_crisis", [])
        assert ind.value_kind == "number"
        assert ind.value == 58.0
        assert len(ind.citations) == 1

    def test_no_citation_downgrades_to_unknown(self):
        """Rule 1: no citation → unknown (ADR-0006 / research-pipeline.md)."""
        ind = _validate_extracted(
            self._basic(citations=[]),
            "gas_ttf_eur_mwh", "fertilizer_crisis", []
        )
        assert ind.value_kind == "unknown"

    def test_enum_not_in_whitelist_unknown(self):
        """Rule 2: enum value not in allowed_values → unknown."""
        data = {
            "value": "extreme",
            "value_kind": "enum",
            "confidence": 0.9,
            "evidence": "Bad enum.",
            "citations": [{"url": "https://example.com", "title": "Test"}],
        }
        ind = _validate_extracted(data, "iran_conflict_escalation", "fertilizer_crisis",
                                   ["low", "medium", "high"])
        assert ind.value_kind == "unknown"

    def test_enum_in_whitelist_accepted(self):
        data = {
            "value": "medium",
            "value_kind": "enum",
            "confidence": 0.9,
            "evidence": "Iran at medium.",
            "citations": [{"url": "https://example.com", "title": "Test"}],
        }
        ind = _validate_extracted(data, "iran_conflict_escalation", "fertilizer_crisis",
                                   ["low", "medium", "high"])
        assert ind.value_kind == "enum"
        assert ind.value == "medium"

    def test_bad_number_unknown(self):
        """Rule 3: type mismatch → unknown."""
        ind = _validate_extracted(
            self._basic(value="not-a-number"),
            "gas_ttf_eur_mwh", "fertilizer_crisis", []
        )
        assert ind.value_kind == "unknown"

    def test_negative_count_unknown(self):
        data = {
            "value": -5,
            "value_kind": "count",
            "confidence": 0.9,
            "evidence": "Negative count.",
            "citations": [{"url": "https://example.com", "title": "Test"}],
        }
        ind = _validate_extracted(data, "product_announcements", "ai_fund_health", [])
        assert ind.value_kind == "unknown"

    def test_bool_string_true(self):
        data = {
            "value": "true",
            "value_kind": "bool",
            "confidence": 0.9,
            "evidence": "Insurance rising.",
            "citations": [{"url": "https://example.com", "title": "Test"}],
        }
        ind = _validate_extracted(data, "hormuz_insurance_rising", "oil_proxy", ["true", "false"])
        assert ind.value_kind == "bool"
        assert ind.value is True

    def test_unknown_kind_produces_unknown(self):
        data = {"value": None, "value_kind": "unknown", "confidence": 0.0,
                "evidence": "", "citations": []}
        ind = _validate_extracted(data, "gas_ttf_eur_mwh", "fertilizer_crisis", [])
        assert ind.value_kind == "unknown"


# ── LLMResearchSource ─────────────────────────────────────────────────────────

class TestLLMResearchSource:
    def _source(self, mock_client=None) -> LLMResearchSource:
        return LLMResearchSource(
            sources_config=_sources(),
            cluster_map=_cluster_map(),
            client=mock_client,
        )

    @pytest.mark.asyncio
    async def test_no_client_returns_unknown(self):
        """Missing API key → unknown, never a crash."""
        src = self._source()  # client=None → no API key
        ind = await src.fetch("gas_ttf_eur_mwh")
        assert ind.value_kind == "unknown"

    def _make_response(self, tool_input: dict) -> MagicMock:
        """Build a mock Anthropic response with a tool_use block."""
        tool_block = MagicMock()
        tool_block.type = "tool_use"
        tool_block.name = "record_indicator"
        tool_block.input = tool_input
        response = MagicMock()
        response.content = [tool_block]
        return response

    @pytest.mark.asyncio
    async def test_model_returns_valid_extraction(self):
        """Mock a successful Claude response with a tool call.
        Uses product_announcements (llm_research), not gas_ttf_eur_mwh (price_api).
        """
        response = self._make_response({
            "value": 3,
            "value_kind": "count",
            "confidence": 0.9,
            "evidence": "3 major AI launches this week.",
            "citations": [{"url": "https://techcrunch.com/x", "title": "AI news"}],
        })
        mock_client = MagicMock()
        src = self._source(mock_client=mock_client)
        # Patch _call_client directly so no thread/executor involved in test
        with patch.object(src, "_call_client", return_value=response):
            ind = await src.fetch("product_announcements")
        assert ind.value_kind == "count"
        assert ind.value == 3

    @pytest.mark.asyncio
    async def test_model_returns_no_tool_call_unknown(self):
        """If model doesn't call the tool → unknown (not a crash)."""
        text_block = MagicMock()
        text_block.type = "text"
        response = MagicMock()
        response.content = [text_block]

        mock_client = MagicMock()
        src = self._source(mock_client=mock_client)
        with patch.object(src, "_call_client", return_value=response):
            ind = await src.fetch("product_announcements")
        assert ind.value_kind == "unknown"

    @pytest.mark.asyncio
    async def test_model_raises_unknown(self):
        """Any exception from the client → unknown, never raises."""
        mock_client = MagicMock()
        src = self._source(mock_client=mock_client)
        with patch.object(src, "_call_client", side_effect=RuntimeError("API down")):
            ind = await src.fetch("product_announcements")
        assert ind.value_kind == "unknown"

    @pytest.mark.asyncio
    async def test_unknown_key_returns_unknown(self):
        """Key not in sources config → unknown."""
        src = self._source(mock_client=MagicMock())
        ind = await src.fetch("nonexistent_indicator_xyz")
        assert ind.value_kind == "unknown"
