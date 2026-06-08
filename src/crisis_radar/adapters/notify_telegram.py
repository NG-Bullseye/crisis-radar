"""TelegramNotifier — optional push via Telegram Bot API.

Opt-in: only active when TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are set.
Never fires on import; never crashes if unconfigured.
"""
from __future__ import annotations

import os

from crisis_radar.domain.models import DailyReport


class TelegramNotifier:
    """Send report + signal changes to a Telegram chat.

    Silently skips if env vars are not set — the run always completes.
    """

    def __init__(self) -> None:
        self._token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self._chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")

    def _configured(self) -> bool:
        return bool(self._token and self._chat_id)

    async def emit(self, report: DailyReport, signal_changed: bool = False) -> None:
        if not self._configured():
            return  # opt-in; no-op when not configured

        try:
            await self._send(report, signal_changed)
        except Exception:
            pass  # Telegram failure never aborts the run

    async def _send(self, report: DailyReport, signal_changed: bool) -> None:
        import httpx

        signal_line = ""
        if signal_changed:
            status = "AKTIV" if report.signal.active else "INAKTIV"
            signal_line = f"\n\n⚡ Signal-Status geändert: {status}"

        summary_line = (
            f"Krise-Radar {report.date.isoformat()}\n"
            f"Score: {report.total:+.1f} | {report.recommendation} | {report.risk_level}\n"
            f"C1={report.clusters[0].score:+.0f} C2={report.clusters[1].score:+.0f} "
            f"C3={report.clusters[2].score:+.0f}"
            f"{signal_line}"
        )

        url = f"https://api.telegram.org/bot{self._token}/sendMessage"
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                url,
                json={
                    "chat_id": self._chat_id,
                    "text": summary_line,
                    "parse_mode": "HTML",
                },
            )
