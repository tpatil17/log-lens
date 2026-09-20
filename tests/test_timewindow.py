"""Time-based windows (F5): duration parsing, time split, and analyze fallback."""

from datetime import datetime, timedelta

import pytest

from loglens.models import LogRecord
from loglens.pipeline import analyze_file, parse_duration, split_by_time

# ------------------------------------------------------- parse_duration ----

def test_parse_duration_units():
    assert parse_duration("30s") == timedelta(seconds=30)
    assert parse_duration("15m") == timedelta(minutes=15)
    assert parse_duration("2h") == timedelta(hours=2)
    assert parse_duration("1d") == timedelta(days=1)


def test_parse_duration_rejects_garbage():
    for bad in ["", "15", "m", "1w", "abc"]:
        with pytest.raises(ValueError):
            parse_duration(bad)


# ---------------------------------------------------------- split_by_time ----

def _rec(minute, tid):
    ts = datetime(2026, 8, 1, 10, minute, 0)
    return (LogRecord(ts=ts, level=None, message=f"t{tid}", raw="", lineno=0), tid)


def test_split_by_time_uses_last_ts_as_now():
    # records at 10:00..10:59; window=10m => last 10 minutes (10:50..10:59].
    pairs = [_rec(m, m % 3) for m in range(60)]
    baseline, window = split_by_time(pairs, timedelta(minutes=10), timedelta(minutes=30))
    win_minutes = {r.ts.minute for r, _ in window}
    assert min(win_minutes) >= 50            # only the last 10 minutes
    base_minutes = {r.ts.minute for r, _ in baseline}
    assert max(base_minutes) <= 49 and min(base_minutes) >= 19  # the 30 min before


def test_split_by_time_none_without_timestamps():
    pairs = [(LogRecord(ts=None, level=None, message="x", raw="x", lineno=0), 1)]
    assert split_by_time(pairs, timedelta(minutes=5), None) is None


# ----------------------------------------------- analyze_file end to end ----

def test_analyze_file_time_window_finds_recent_burst(tmp_path):
    # 50 min of routine ISO logs, then a burst in the final 5 minutes.
    lines = [f"2026-08-01T10:{m:02d}:00Z INFO request handled" for m in range(50)]
    lines += [f"2026-08-01T10:5{s}:00Z ERROR redis connection refused" for s in range(5)]
    p = tmp_path / "app.log"
    p.write_text("\n".join(lines) + "\n")

    anomalies = analyze_file(p, window=timedelta(minutes=6), baseline=timedelta(minutes=40))
    assert anomalies and anomalies[0].kind == "NEW"
    assert "redis connection refused" in (anomalies[0].samples[0] if anomalies[0].samples else "")


def test_analyze_file_falls_back_without_timestamps(tmp_path):
    # No parseable timestamps -> should warn and use the midpoint split.
    p = tmp_path / "plain.log"
    p.write_text("\n".join("just a plain line" for _ in range(20)) + "\n")
    warnings = []
    analyze_file(p, window=timedelta(minutes=5), warn=warnings.append)
    assert warnings and "record-count split" in warnings[0]
