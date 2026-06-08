"""CLI — typer subcommands: run / rescore / trend / backfill."""
from __future__ import annotations

import asyncio
from datetime import date, timedelta
from typing import Optional

import typer

app = typer.Typer(name="crisis-radar", help="Daily crisis scoring and rotation signal detection.")


def _load_defaults():
    """Load default config and adapters (lazy to avoid import cost on --help)."""
    from crisis_radar.adapters.notify_console import ConsoleNotifier
    from crisis_radar.adapters.notify_ha import HomeAssistantNotifier
    from crisis_radar.adapters.price_api import PriceApiSource
    from crisis_radar.adapters.research_llm import LLMResearchSource
    from crisis_radar.adapters.store_json import JsonFileStore
    from crisis_radar.application.orchestrator import DailyRunOrchestrator
    from crisis_radar.config import load_scoring, load_sources

    scoring = load_scoring()
    sources_cfg = load_sources()

    # Build cluster map for sources.
    cluster_map: dict[str, str] = {}
    for ck, cc in scoring.clusters.items():
        for ik in cc.indicators:
            cluster_map[ik] = ck

    price_src = PriceApiSource(sources_cfg, cluster_map)
    llm_src = LLMResearchSource(sources_cfg, cluster_map)
    store = JsonFileStore()
    notifiers = [ConsoleNotifier(), HomeAssistantNotifier()]

    orch = DailyRunOrchestrator(
        scoring_config=scoring,
        sources_config=sources_cfg,
        sources=[price_src, llm_src],
        store=store,
        notifiers=notifiers,
    )
    return orch, store, scoring


@app.command()
def run(
    date_str: Optional[str] = typer.Option(None, "--date", help="Run for a specific date (YYYY-MM-DD); defaults to today."),
) -> None:
    """Run the full daily pipeline: research → score → save → notify."""
    run_date = date.fromisoformat(date_str) if date_str else date.today()

    orch, _, _ = _load_defaults()
    report = asyncio.run(orch.run(run_date))

    typer.echo(f"Done. Score={report.total:+.1f} | {report.recommendation} | {report.risk_level}")
    typer.echo(f"Signal: {report.signal.streak_days}/{report.signal.required_days} days")


@app.command()
def rescore(
    date_str: str = typer.Argument(..., help="Date to rescore (YYYY-MM-DD)."),
) -> None:
    """Re-score stored indicators for a date (no web calls — must reproduce the total)."""
    target = date.fromisoformat(date_str)
    orch, _, _ = _load_defaults()
    report = asyncio.run(orch.rescore(target))

    if report is None:
        typer.echo(f"No stored report for {date_str}.", err=True)
        raise typer.Exit(1)

    typer.echo(f"Rescore {date_str}: total={report.total:+.1f} | {report.recommendation}")


@app.command()
def trend(
    window: int = typer.Option(30, "--window", "-w", help="Number of days to look back."),
) -> None:
    """Print the score trend over the last N stored report days."""
    _, store, scoring = _load_defaults()
    history = store.history(window=window)

    if not history:
        typer.echo("No history found.")
        return

    from crisis_radar.domain.signal import SignalDetector
    detector = SignalDetector(scoring)
    signal = detector.evaluate(history)

    typer.echo(f"Trend ({len(history)} reports, window={window}):")
    typer.echo(f"Signal: active={signal.active}, streak={signal.streak_days}/{signal.required_days}")
    typer.echo("")
    for r in history:
        marker = " *** SIGNAL ***" if r.total > scoring.signal.rotation.threshold else ""
        typer.echo(f"  {r.date}  {r.total:+6.1f}  {r.recommendation}{marker}")


@app.command()
def backfill(
    start: str = typer.Argument(..., help="Start date YYYY-MM-DD."),
    end: str = typer.Option(None, "--end", help="End date YYYY-MM-DD; defaults to yesterday."),
    delay: float = typer.Option(2.0, "--delay", help="Seconds between runs (rate limit)."),
) -> None:
    """Backfill a date range: run the full pipeline for each missing day."""
    import time

    start_date = date.fromisoformat(start)
    end_date = date.fromisoformat(end) if end else date.today() - timedelta(days=1)

    orch, store, _ = _load_defaults()

    current = start_date
    while current <= end_date:
        existing = store.load(current)
        if existing is not None:
            typer.echo(f"Skip {current} (already exists)")
        else:
            typer.echo(f"Running {current}...")
            try:
                report = asyncio.run(orch.run(current))
                typer.echo(f"  → {report.total:+.1f} | {report.recommendation}")
            except Exception as exc:
                typer.echo(f"  ERROR: {exc}", err=True)
            time.sleep(delay)
        current += timedelta(days=1)


if __name__ == "__main__":
    app()
