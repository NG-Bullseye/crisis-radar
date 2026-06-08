"""ConsoleNotifier — print report to stdout and write a markdown file."""
from __future__ import annotations

from pathlib import Path

from crisis_radar.domain.models import DailyReport
from crisis_radar.reporting.render import render_markdown

_REPO_ROOT = Path(__file__).parent.parent.parent.parent  # crisis-radar/


class ConsoleNotifier:
    """Write the rendered report to stdout and to data/reports/YYYY-MM-DD.md."""

    def __init__(self, reports_dir: Path | None = None) -> None:
        self._dir = reports_dir or (_REPO_ROOT / "data" / "reports")
        self._dir.mkdir(parents=True, exist_ok=True)

    async def emit(self, report: DailyReport, signal_changed: bool = False) -> None:
        md = render_markdown(report)
        print(md)
        md_path = self._dir / f"{report.date.isoformat()}.md"
        md_path.write_text(md, encoding="utf-8")
