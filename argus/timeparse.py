"""Resolve ISO datetimes and relative phrases ("ayer", "hace 2 horas") to timestamps.

Everything is resolved in the machine's local timezone; results are aware
datetimes. Phrases return a *point* or a *range* (a whole day, a morning).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone, tzinfo


def local_tz() -> tzinfo:
    return datetime.now().astimezone().tzinfo or timezone.utc


@dataclass(frozen=True)
class Resolved:
    start: datetime
    end: datetime | None = None  # set when the phrase denotes a span

    @property
    def is_range(self) -> bool:
        return self.end is not None


_UNITS = {
    "minuto": "minutes", "minutos": "minutes", "min": "minutes", "minute": "minutes", "minutes": "minutes",
    "hora": "hours", "horas": "hours", "hour": "hours", "hours": "hours", "h": "hours",
    "dia": "days", "dias": "days", "day": "days", "days": "days",
    "semana": "weeks", "semanas": "weeks", "week": "weeks", "weeks": "weeks",
}
_WORD_NUMBERS = {
    "una": 1, "un": 1, "uno": 1, "one": 1, "an": 1, "a": 1, "dos": 2, "two": 2, "tres": 3, "three": 3,
    "cuatro": 4, "four": 4, "cinco": 5, "five": 5, "seis": 6, "six": 6, "siete": 7, "seven": 7,
    "ocho": 8, "eight": 8, "nueve": 9, "nine": 9, "diez": 10, "ten": 10, "media": 0.5, "half": 0.5,
}
_AGO_ES = re.compile(r"^hace\s+(\S+)\s+(\S+)$")
_AGO_EN = re.compile(r"^(\S+)\s+(\S+)\s+ago$")
_LAST_N = re.compile(r"^(?:ultim[oa]s?|last|past)\s+(\S+)\s+(\S+)$")
_TIME_SUFFIX = re.compile(r"\s+(?:a\s+las?|at)\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?$")


def _strip_accents(text: str) -> str:
    return (
        text.replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u").replace("ñ", "n")
    )


def _number(token: str) -> float | None:
    token = token.replace(",", ".")
    try:
        return float(token)
    except ValueError:
        return _WORD_NUMBERS.get(token)


def _day_range(day: date, tz: tzinfo) -> Resolved:
    start = datetime.combine(day, time.min, tzinfo=tz)
    return Resolved(start, start + timedelta(days=1))


def _part_of_day(day: date, tz: tzinfo, first: int, last: int) -> Resolved:
    start = datetime.combine(day, time(first), tzinfo=tz)
    end = datetime.combine(day, time.min, tzinfo=tz) + timedelta(hours=last)
    return Resolved(start, end)


def parse_iso(text: str, tz: tzinfo) -> datetime | None:
    candidate = text.strip().replace("Z", "+00:00")
    try:
        value = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    return value if value.tzinfo else value.replace(tzinfo=tz)


def resolve(phrase: str, now: datetime | None = None, tz: tzinfo | None = None) -> Resolved | None:
    """Return the resolved point/range for `phrase`, or None if unrecognised."""
    tz = tz or local_tz()
    now = (now or datetime.now(tz)).astimezone(tz)
    raw = phrase.strip()
    if not raw:
        return None
    iso = parse_iso(raw, tz)
    if iso is not None:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
            return _day_range(iso.date(), tz)
        return Resolved(iso)

    text = _strip_accents(raw.lower())
    text = re.sub(r"\s+", " ", text)
    for prefix in ("el ", "la ", "por la ", "en la ", "desde ", "since ", "on ", "the "):
        if text.startswith(prefix):
            text = text[len(prefix):]
    today = now.date()

    clock = _TIME_SUFFIX.search(text)
    if clock:
        base = resolve(text[: clock.start()], now, tz)
        if base is not None:
            hour = int(clock.group(1)) % 24
            minute = int(clock.group(2) or 0)
            if clock.group(3) == "pm" and hour < 12:
                hour += 12
            if clock.group(3) == "am" and hour == 12:
                hour = 0
            return Resolved(datetime.combine(base.start.date(), time(hour, minute), tzinfo=tz))

    if text in ("ahora", "ahora mismo", "now", "right now"):
        return Resolved(now)
    if text in ("hoy", "today"):
        return _day_range(today, tz)
    if text in ("ayer", "yesterday"):
        return _day_range(today - timedelta(days=1), tz)
    if text in ("anteayer", "antes de ayer", "the day before yesterday"):
        return _day_range(today - timedelta(days=2), tz)
    if text in ("manana", "tomorrow"):
        return _day_range(today + timedelta(days=1), tz)
    if text in ("esta manana", "this morning"):
        return _part_of_day(today, tz, 6, 12)
    if text in ("esta tarde", "this afternoon"):
        return _part_of_day(today, tz, 12, 20)
    if text in ("esta noche", "tonight", "this evening"):
        return _part_of_day(today, tz, 20, 24)
    if text in ("ayer por la manana", "yesterday morning"):
        return _part_of_day(today - timedelta(days=1), tz, 6, 12)
    if text in ("ayer por la tarde", "yesterday afternoon"):
        return _part_of_day(today - timedelta(days=1), tz, 12, 20)
    if text in ("anoche", "ayer por la noche", "last night"):
        return _part_of_day(today - timedelta(days=1), tz, 20, 24)
    if text in ("hace un rato", "hace un momento", "a while ago", "a moment ago", "just now"):
        return Resolved(now - timedelta(minutes=30), now)
    if text in ("esta semana", "this week"):
        start = today - timedelta(days=today.weekday())
        return Resolved(datetime.combine(start, time.min, tzinfo=tz), now)
    if text in ("semana pasada", "la semana pasada", "last week"):
        start = today - timedelta(days=today.weekday() + 7)
        end = start + timedelta(days=7)
        return Resolved(datetime.combine(start, time.min, tzinfo=tz), datetime.combine(end, time.min, tzinfo=tz))

    for pattern in (_AGO_ES, _AGO_EN):
        match = pattern.match(text)
        if match:
            amount, unit = _number(match.group(1)), _UNITS.get(match.group(2))
            if amount is not None and unit:
                return Resolved(now - timedelta(**{unit: amount}))
    match = _LAST_N.match(text)
    if match:
        amount, unit = _number(match.group(1)), _UNITS.get(match.group(2))
        if amount is not None and unit:
            return Resolved(now - timedelta(**{unit: amount}), now)
    return None


def resolve_range(
    start: str | None,
    end: str | None,
    now: datetime | None = None,
    tz: tzinfo | None = None,
) -> tuple[datetime | None, datetime | None]:
    """Turn optional `from`/`to` inputs into aware datetimes.

    A phrase that denotes a span (e.g. "ayer") fills both ends when the other
    bound is missing. Unrecognised text raises ValueError with the phrase.
    """
    tz = tz or local_tz()
    now = (now or datetime.now(tz)).astimezone(tz)
    lo: datetime | None = None
    hi: datetime | None = None
    if start:
        resolved = resolve(start, now, tz)
        if resolved is None:
            raise ValueError(f"Unrecognised time expression: {start!r}")
        lo = resolved.start
        if resolved.is_range and not end:
            hi = resolved.end
    if end:
        resolved = resolve(end, now, tz)
        if resolved is None:
            raise ValueError(f"Unrecognised time expression: {end!r}")
        hi = resolved.end if resolved.is_range else resolved.start
        if resolved.is_range and not start:
            lo = resolved.start
    if lo and hi and hi < lo:
        lo, hi = hi, lo
    return lo, hi


def to_epoch(value: datetime | None) -> float | None:
    return None if value is None else value.timestamp()


def iso_local(epoch: float, tz: tzinfo | None = None) -> str:
    return datetime.fromtimestamp(epoch, tz or local_tz()).isoformat(timespec="seconds")


def day_of(epoch: float, tz: tzinfo | None = None) -> str:
    return datetime.fromtimestamp(epoch, tz or local_tz()).strftime("%Y-%m-%d")
