# ADR-0001 — LLM extracts; the deterministic engine scores

- **Status:** accepted
- **Date:** 2026-06-08

## Context

The product turns messy public information into a numeric risk score and a rotation recommendation. An LLM is the natural tool for reading scattered news; but if the model also *produces the score*, the output is unauditable, non-reproducible, and untestable — and small prompt changes can swing the number.

## Decision

Split the system at a hard boundary:

- **LLM (fuzzy):** only extracts each indicator's current value from the web, returning a typed value, a confidence, an evidence sentence, and citations.
- **Deterministic core (crisp):** all rules, clamping, cluster sums, the mean total, recommendation banding, and signal detection are pure Python driven by config.

`rescore` re-runs the crisp core over stored indicators and must reproduce the score byte-for-byte.

## Consequences

- The scorer is unit-testable against fixtures with zero network. Correctness of the *number* is independent of model behavior.
- Every point is auditable back to a rule and a cited source.
- The LLM can be swapped, upgraded, or mocked without changing any score.
- Cost: two concepts to maintain (extraction contract + scoring rules) instead of one prompt — accepted, because it buys trust.
