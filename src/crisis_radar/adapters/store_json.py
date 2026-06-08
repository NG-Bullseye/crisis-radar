"""JsonFileStore — persist DailyReports as one JSON file per day.

Layout: data/reports/YYYY-MM-DD.json (ADR-0004).
Files are human-readable and git-friendly; no database required.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from crisis_radar.domain.models import DailyReport

_REPO_ROOT = Path(__file__).parent.parent.parent.parent  # crisis-radar/


class JsonFileStore:
    """Save / load / list DailyReports as JSON files under `data/reports/`."""

    def __init__(self, reports_dir: Path | None = None) -> None:
        self._dir = reports_dir or (_REPO_ROOT / "data" / "reports")
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, report_date: date) -> Path:
        return self._dir / f"{report_date.isoformat()}.json"

    def save(self, report: DailyReport) -> None:
        """Serialize and write to disk. Overwrites any existing file for that date."""
        path = self._path(report.date)
        path.write_text(
            report.model_dump_json(indent=2),
            encoding="utf-8",
        )

    def load(self, report_date: date) -> DailyReport | None:
        """Load a report by date; returns None if the file does not exist."""
        path = self._path(report_date)
        if not path.exists():
            return None
        raw = path.read_text(encoding="utf-8")
        return DailyReport.model_validate_json(raw)

    def history(self, window: int = 30) -> list[DailyReport]:
        """Return up to `window` most-recent reports, ordered oldest-first.

        Reads from disk each call — cheap enough for daily reporting (small window).
        """
        files = sorted(self._dir.glob("????-??-??.json"), reverse=True)[:window]
        reports: list[DailyReport] = []
        for f in files:
            try:
                reports.append(DailyReport.model_validate_json(f.read_text(encoding="utf-8")))
            except Exception:
                # Corrupted file — skip silently; the run log will show it.
                pass
        return list(reversed(reports))  # oldest-first
