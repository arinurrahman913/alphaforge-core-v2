"""
Macro Economic Calendar — 02_LAYER1_SPECS/09_MACRO_CALENDAR.md
Sumber: FRED release calendar resmi (sengaja bukan scraping Investing.com/Forex Factory).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from ..config import DataUnavailableError
from ..providers import fred
from .common import error_reading, make_reading

COMPONENT = "macro_calendar"

HIGH_IMPACT_RELEASE_KEYWORDS = [
    "consumer price index", "employment situation", "gross domestic product",
    "personal income", "federal open market committee", "producer price index",
]


def compute(days_ahead: int = 30) -> dict:
    try:
        releases = fred.get_release_calendar(limit=200)
    except DataUnavailableError as exc:
        return error_reading(COMPONENT, "direct", str(exc))

    today = date.today()
    horizon = today + timedelta(days=days_ahead)
    upcoming = []
    for r in releases:
        try:
            rdate = datetime.strptime(r.get("date", ""), "%Y-%m-%d").date()
        except ValueError:
            continue
        if today <= rdate <= horizon:
            name = (r.get("release_name") or "").strip()
            is_high_impact = any(k in name.lower() for k in HIGH_IMPACT_RELEASE_KEYWORDS)
            upcoming.append({"date": r.get("date"), "release_name": name, "high_impact": is_high_impact})

    upcoming.sort(key=lambda x: x["date"])
    high_impact_count = sum(1 for u in upcoming if u["high_impact"])

    return make_reading(
        COMPONENT, "direct",
        value=f"{high_impact_count} rilis berdampak tinggi dalam {days_ahead} hari ke depan",
        detail={"upcoming_releases": upcoming[:50]},
    )
