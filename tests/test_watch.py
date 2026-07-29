"""Tests for watch mode. The loop is driven with an injected finite event
stream and a fake parser, so no real files, tailing, or sleeping is involved."""

from collections import Counter

from loglens.models import LogRecord
from loglens.watch import evaluate, watch


class WordParser:
    """Trivial parser: the whole line is the message (no timestamp needed here)."""

    name = "word"

    def parse(self, line, lineno):
        return LogRecord(ts=None, level=None, message=line, raw=line, lineno=lineno)


def _rec(msg):
    return LogRecord(ts=None, level=None, message=msg, raw=msg, lineno=0)


# ------------------------------------------------------------ evaluate ----

def test_evaluate_flags_new_error_over_threshold():
    base = Counter({1: 100})                       # baseline: only "heartbeat"
    window = [(_rec("db pool exhausted"), 2)] * 20  # window: a new error
    alerts = evaluate(base, window, threshold=10.0)
    assert alerts and alerts[0].kind == "NEW"


def test_evaluate_flags_vanished_heartbeat():
    base = Counter({1: 100})                        # heartbeat fired a lot
    window = [(_rec("other"), 2)] * 30              # heartbeat gone from window
    alerts = evaluate(base, window, threshold=10.0)
    kinds = {a.kind for a in alerts}
    assert "VANISHED" in kinds                       # two-sided scoring catches the drop


def test_evaluate_quiet_window_no_alerts():
    base = Counter({1: 100})
    window = [(_rec("heartbeat"), 1)] * 50          # same as baseline → nothing
    assert evaluate(base, window, threshold=10.0) == []


# --------------------------------------------------------------- loop -----

def test_watch_loop_alerts_on_live_burst():
    # 300 baseline heartbeats, then a burst of a NEW error in the live phase.
    events = [("baseline", "heartbeat ok") for _ in range(300)]
    events.append(("baseline_end", None))
    events += [("live", "database connection pool exhausted") for _ in range(60)]

    captured = []
    watch(
        "unused.log",
        parser=WordParser(),
        events=iter(events),
        refresh=50,
        threshold=10.0,
        emit=lambda anomalies: captured.append(anomalies),
    )
    assert captured, "expected at least one alert batch"
    assert any(a.kind == "NEW" for batch in captured for a in batch)


def test_watch_warns_on_thin_baseline():
    events = [("baseline", "only one line"), ("baseline_end", None)]
    warnings = []
    watch(
        "unused.log",
        parser=WordParser(),
        events=iter(events),
        min_baseline=300,
        emit=lambda a: None,
        warn=warnings.append,
    )
    assert warnings and "thin" in warnings[0]
