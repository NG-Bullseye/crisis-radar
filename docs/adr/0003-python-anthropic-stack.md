# ADR-0003 — Python + Anthropic SDK (web search) stack

- **Status:** accepted
- **Date:** 2026-06-08

## Context

The tool needs daily web research with reliable structured extraction, plus simple data modeling and persistence. It runs on a personal home server alongside other Python services.

## Decision

- **Python 3.12+** — matches the surrounding home stack and the data/LLM ecosystem.
- **`anthropic` SDK with the web search tool** — Claude performs the research and returns structured output via tool use, which is exactly the extraction contract this design needs (typed value + citations).
- **pydantic v2** for models/validation and JSON (de)serialization; **PyYAML** for config; **typer** for the CLI; **httpx** for optional direct price feeds; **pytest/ruff/mypy** for quality.

## Consequences

- Structured output gives clean, validated extraction without brittle text parsing.
- pydantic models generate/align with the JSON Schema contract for free.
- Alternatives considered: a generic OpenAI-compatible client (rejected — the design targets Claude's tool use and web search directly); a heavier framework like LangChain (rejected — over-engineered for a small, deterministic-core tool, violates the "small and inspectable" principle).
