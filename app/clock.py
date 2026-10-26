"""All timestamps are stored as UTC ISO-8601 strings and rendered in Phnom Penh time."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

UTC = timezone.utc
LOCAL = timezone(timedelta(hours=7))  # Asia/Phnom_Penh, no DST


def now() -> datetime:
    return datetime.now(UTC)


def iso(moment: datetime | None = None) -> str:
    return (moment or now()).astimezone(UTC).isoformat(timespec="seconds")


def parse(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value).astimezone(UTC)


def local_str(value: str | None, fmt: str = "%d %b %Y, %H:%M") -> str:
    moment = parse(value)
    return moment.astimezone(LOCAL).strftime(fmt) if moment else ""
