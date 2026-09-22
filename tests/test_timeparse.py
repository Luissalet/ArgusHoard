from datetime import datetime, timedelta, timezone

import pytest

from argus.timeparse import resolve, resolve_range

TZ = timezone(timedelta(hours=2))
NOW = datetime(2026, 3, 18, 15, 30, tzinfo=TZ)  # a Wednesday


def at(day, hour=0, minute=0):
    return datetime(2026, 3, day, hour, minute, tzinfo=TZ)


@pytest.mark.parametrize(
    "phrase, start, end",
    [
        ("hoy", at(18), at(19)),
        ("today", at(18), at(19)),
        ("ayer", at(17), at(18)),
        ("Yesterday", at(17), at(18)),
        ("anteayer", at(16), at(17)),
        ("esta mañana", at(18, 6), at(18, 12)),
        ("this morning", at(18, 6), at(18, 12)),
        ("esta tarde", at(18, 12), at(18, 20)),
        ("anoche", at(17, 20), at(18)),
        ("2026-03-10", at(10), at(11)),
        ("esta semana", at(16), NOW),
        ("la semana pasada", at(9), at(16)),
        ("últimos 30 minutos", NOW - timedelta(minutes=30), NOW),
        ("last 2 hours", NOW - timedelta(hours=2), NOW),
    ],
)
def test_ranges(phrase, start, end):
    resolved = resolve(phrase, NOW, TZ)
    assert resolved is not None and resolved.is_range
    assert resolved.start == start and resolved.end == end


@pytest.mark.parametrize(
    "phrase, expected",
    [
        ("hace 2 horas", NOW - timedelta(hours=2)),
        ("hace 15 minutos", NOW - timedelta(minutes=15)),
        ("hace una hora", NOW - timedelta(hours=1)),
        ("hace media hora", NOW - timedelta(minutes=30)),
        ("hace 3 días", NOW - timedelta(days=3)),
        ("2 hours ago", NOW - timedelta(hours=2)),
        ("an hour ago", NOW - timedelta(hours=1)),
        ("ahora", NOW),
        ("2026-03-18T10:00:00", at(18, 10)),
        ("2026-03-18T08:00:00Z", datetime(2026, 3, 18, 8, tzinfo=timezone.utc)),
        ("ayer a las 9", at(17, 9)),
        ("hoy a las 14:30", at(18, 14, 30)),
        ("today at 3pm", at(18, 15)),
    ],
)
def test_points(phrase, expected):
    resolved = resolve(phrase, NOW, TZ)
    assert resolved is not None and not resolved.is_range
    assert resolved.start == expected


def test_unknown_phrase():
    assert resolve("el día de la marmota", NOW, TZ) is None
    with pytest.raises(ValueError):
        resolve_range("cuando sea", None, NOW, TZ)


def test_resolve_range_fills_both_ends_from_a_day_phrase():
    lo, hi = resolve_range("ayer", None, NOW, TZ)
    assert (lo, hi) == (at(17), at(18))
    lo, hi = resolve_range(None, "ayer", NOW, TZ)
    assert (lo, hi) == (at(17), at(18))
    lo, hi = resolve_range("ayer", "hoy", NOW, TZ)
    assert (lo, hi) == (at(17), at(19))
    lo, hi = resolve_range("hace 2 horas", "ahora", NOW, TZ)
    assert (lo, hi) == (NOW - timedelta(hours=2), NOW)


def test_resolve_range_swaps_inverted_bounds():
    lo, hi = resolve_range("ahora", "hace 1 hora", NOW, TZ)
    assert lo < hi
