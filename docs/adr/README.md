# Architecture Decision Records

Short, dated records of *why* each major choice was made. New decisions append a numbered file; superseded ones are marked, not deleted.

| # | Decision |
|---|---|
| [0001](0001-llm-extracts-deterministic-engine-scores.md) | LLM extracts; the deterministic engine scores |
| [0002](0002-config-driven-scoring.md) | Config-driven scoring, no magic numbers |
| [0003](0003-python-anthropic-stack.md) | Python + Anthropic SDK (web search) stack |
| [0004](0004-json-file-store.md) | JSON files as the report store (SQLite deferred) |
| [0005](0005-pluggable-indicator-sources.md) | Pluggable indicator sources (LLM research vs. structured feeds) |
| [0006](0006-citations-confidence-unknown.md) | Mandatory citations, confidence, and "unknown ≠ guessed zero" |
| [0007](0007-mcp-server-as-integration-surface.md) | One MCP server as the integration surface; the daily call is the trigger |
