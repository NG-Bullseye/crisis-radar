# ADR-0006 — Mandatory citations, confidence, and "unknown ≠ guessed zero"

- **Status:** accepted
- **Date:** 2026-06-08

## Context

An LLM reading the web can confidently state numbers it never actually found. If a hallucinated value enters the score, the whole tool is worthless. Equally, "no data found" must not be silently treated as a benign zero — the absence of information is itself information the operator should see.

## Decision

Enforce three guarantees in adapter code (not just in the prompt):

1. **Citations are mandatory.** Any non-`unknown` indicator value with zero citations is downgraded to `unknown`. The model cannot assert a value it didn't source.
2. **Confidence is recorded.** Every indicator carries a `0–1` confidence; it is surfaced in the report but never used to inflate or hide a value.
3. **Unknown is explicit.** Unresolved indicators are emitted as `value_kind = unknown`, contribute **0 points**, and stay visible in the report with a flag — never dropped, never guessed.

Validation (enum whitelist, type parsing, citation presence) runs after the model responds and is the actual enforcement point.

## Consequences

- The final score is defensible: every contributing point traces to a citation.
- Partial-data days are honest — the report shows what could not be found.
- Slightly more `unknown`s than a guess-friendly system, by design: a visible gap beats an invented number.
