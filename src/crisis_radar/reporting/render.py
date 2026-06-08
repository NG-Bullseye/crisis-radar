"""Report rendering — DailyReport → markdown and Leo's fixed text layout.

The `news_paragraph` function produces TTS-safe German prose (no markdown,
no symbols) ready for the news-agent briefing (mcp-news-and-display.md).
"""
from __future__ import annotations

from crisis_radar.domain.models import DailyReport

_RECOMMENDATION_DE = {
    "rotate": "Rotation erwägen",
    "half_position": "Halbe Position prüfen",
    "observe": "Beobachten",
    "no_rotation": "Keine Rotation",
}

_RISK_DE = {
    "low": "niedrig",
    "medium": "mittel",
    "elevated": "erhöht",
}


def render_text(report: DailyReport) -> str:
    """Leo's fixed text format: CLUSTER 1/2/3 → GESAMTSCORE → HANDLUNGSEMPFEHLUNG."""
    cluster_scores = {c.cluster_key: c.score for c in report.clusters}

    lines = [
        f"KRISE-RADAR {report.date.isoformat()}",
        "",
        f"CLUSTER 1 — KI-FONDS-GESUNDHEIT:  {cluster_scores.get('ai_fund_health', 0):+.0f}",
        f"CLUSTER 2 — DÜNGER-KRISE:          {cluster_scores.get('fertilizer_crisis', 0):+.0f}",
        f"CLUSTER 3 — ÖL-PROXY:              {cluster_scores.get('oil_proxy', 0):+.0f}",
        "",
        f"GESAMTSCORE:         {report.total:+.1f}",
        f"RISIKO-LEVEL:        {_RISK_DE.get(report.risk_level, report.risk_level)}",
        f"HANDLUNGSEMPFEHLUNG: {_RECOMMENDATION_DE.get(report.recommendation, report.recommendation)}",
        "",
    ]

    # Signal line.
    sig = report.signal
    if sig.active:
        lines.append(f"SIGNAL: AKTIV (seit {sig.since}, {sig.streak_days}/{sig.required_days} Tage)")
    elif sig.streak_days > 0:
        lines.append(
            f"SIGNAL: aufbauend — {sig.streak_days}/{sig.required_days} Tage über Schwelle ({sig.threshold:+.0f})"
        )
    else:
        lines.append(f"SIGNAL: inaktiv (0/{sig.required_days} Tage)")

    return "\n".join(lines)


def render_markdown(report: DailyReport) -> str:
    """Full markdown report with indicator breakdown."""
    cluster_scores = {c.cluster_key: c.score for c in report.clusters}
    cluster_breakdowns = {c.cluster_key: c.breakdown for c in report.clusters}

    # Indicator lookup by key.
    ind_map = {i.key: i for i in report.indicators}

    def _cluster_section(key: str, title: str) -> list[str]:
        score = cluster_scores.get(key, 0)  # type: ignore[call-overload]
        breakdown = cluster_breakdowns.get(key, [])  # type: ignore[call-overload]
        lines = [f"### {title} — {score:+.0f}"]
        for item in breakdown:
            ind = ind_map.get(item["key"])
            if ind:
                val_str = str(ind.value) if ind.value is not None else "—"
                pts_str = f"{item['points']:+d}"
                conf_str = f"{ind.confidence:.0%}"
                lines.append(f"- **{item['key']}**: {val_str} → {pts_str} pts ({conf_str} confidence)")
                if ind.evidence:
                    lines.append(f"  > {ind.evidence}")
        return lines

    lines = [
        f"# Krise-Radar — {report.date.isoformat()}",
        "",
        f"**Gesamtscore:** {report.total:+.1f} | **Empfehlung:** {report.recommendation} | **Risiko:** {report.risk_level}",
        "",
    ]
    lines += _cluster_section("ai_fund_health", "Cluster 1 — KI-Fonds-Gesundheit")
    lines += [""]
    lines += _cluster_section("fertilizer_crisis", "Cluster 2 — Dünger-Krise")
    lines += [""]
    lines += _cluster_section("oil_proxy", "Cluster 3 — Öl-Proxy")
    lines += [""]

    # Signal.
    sig = report.signal
    if sig.active:
        lines.append(f"**ROTATION SIGNAL AKTIV** seit {sig.since} ({sig.streak_days}/{sig.required_days} Tage)")
    else:
        lines.append(f"Signal: {sig.streak_days}/{sig.required_days} Tage (Schwelle: {sig.threshold:+.0f})")

    if report.summary:
        lines += ["", f"> {report.summary}"]

    lines += ["", f"_Erstellt: {report.generated_at.strftime('%Y-%m-%d %H:%M UTC')}_"]

    return "\n".join(lines)


def news_paragraph(report: DailyReport) -> str:
    """TTS-safe German prose paragraph for the news-agent briefing.

    No markdown, no symbols, no asterisks. Drops straight into the
    'Krise-Radar.' block and TTS without any further processing.
    """
    cluster_scores = {c.cluster_key: c.score for c in report.clusters}
    ai_score = cluster_scores.get("ai_fund_health", 0)
    fert_score = cluster_scores.get("fertilizer_crisis", 0)
    oil_score = cluster_scores.get("oil_proxy", 0)

    rec_de = _RECOMMENDATION_DE.get(report.recommendation, report.recommendation)
    risk_de = _RISK_DE.get(report.risk_level, report.risk_level)

    # Signal description.
    sig = report.signal
    if sig.active:
        signal_text = f"Das Rotationssignal ist aktiv seit {sig.since}."
    elif sig.streak_days > 0:
        signal_text = (
            f"Der Score liegt bereits seit {sig.streak_days} von "
            f"{sig.required_days} nötigen Tagen über der Schwelle."
        )
    else:
        signal_text = "Das Rotationssignal ist noch nicht aktiv."

    def _sign(v: float) -> str:
        return f"plus {abs(v):.0f}" if v >= 0 else f"minus {abs(v):.0f}"

    return (
        f"Krise-Radar. Der Gesamtscore steht heute bei {_sign(report.total)}. "
        f"Cluster KI-Fonds {_sign(ai_score)}, Dünger-Krise {_sign(fert_score)}, "
        f"Öl-Proxy {_sign(oil_score)}. "
        f"Handlungstendenz: {rec_de}, Risiko-Level {risk_de}. "
        f"{signal_text}"
    )
