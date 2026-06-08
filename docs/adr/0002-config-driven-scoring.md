# ADR-0002 — Config-driven scoring, no magic numbers

- **Status:** accepted
- **Date:** 2026-06-08

## Context

Every threshold and point value in the framework is a hand-chosen opinion that *will* be revised once the tool produces real history. If those numbers live as literals in the engine, tuning means code edits, reviews, and redeploys — friction that guarantees the weights rot.

## Decision

All scoring parameters live in `config/scoring.yaml`: rule types, thresholds, points, caps, clamps, recommendation bands, total method/weights, and the signal threshold/window. The engine reads config and contains **no** numeric literals related to scoring. Config is validated on load (unknown indicator keys, malformed bands, and bad enums fail loudly).

## Consequences

- Tuning the thesis is a YAML edit + `rescore` over history — no code change.
- The config doubles as precise, version-controlled documentation of the model.
- A `weights` block is reserved so the total can move from mean to weighted without code changes (addresses the cluster-correlation concern in scoring-spec.md §7).
- Cost: a validation layer and a typed config loader — small and worth it.
