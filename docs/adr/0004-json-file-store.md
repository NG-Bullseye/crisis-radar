# ADR-0004 — JSON files as the report store (SQLite deferred)

> Stand 2026-11-10 · geprüft gegen 39dfaf2

> **Status 2026-11-10 (wiki-dreamer pma#336):** Repo dormant (monitor-mcp registry.yaml crisis-radar: absicht dormant, keine Laufzeit-Evidenz seit 2026-09-15). Design-Stand 2026-06-08, nicht gegen Laufzeit nachgezogen.

- **Status:** accepted
- **Date:** 2026-06-08

## Context

The tool writes one report per day and reads recent history to detect a sustained signal (~15 days). Storage must support trend queries, survive restarts, and be easy to inspect and back up.

## Decision

Persist each `DailyReport` as a human-readable JSON file at `data/reports/YYYY-MM-DD.json`. `JsonFileStore` implements `save` / `load(date)` / `history(window)` by listing and reading these files. The signal window is small enough that loading recent files into memory is trivial.

## Consequences

- Zero operational overhead: no database to run, migrate, or back up separately. Fits the cloud-heavy backup model (the data dir syncs as plain files).
- Reports are directly inspectable and diff-able; debugging is `cat` and `jq`.
- The `ReportStore` port keeps the door open: if history queries ever outgrow file scans, add a `SqliteStore` adapter without touching the core.
- Cost: no rich querying across long ranges — acceptable for a single-user daily tool.
