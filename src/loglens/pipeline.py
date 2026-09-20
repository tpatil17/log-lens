"""End-to-end pipeline glue: wire ingest → mine → score into whole-file helpers.

Keeps the CLI a thin adapter — these functions are plain and unit-testable
without spawning the CLI.
"""

import re
from collections import Counter
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path

from loglens.ingest import read
from loglens.mining import make_miner, mine
from loglens.windowing import Anomaly, diff, score_counts, split_midpoint

_DURATION_RE = re.compile(r"^(\d+)\s*([smhd])$")
_UNITS = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days"}


def parse_duration(text: str) -> timedelta:
    """Parse a duration like '30s', '15m', '2h', '1d' into a timedelta."""
    m = _DURATION_RE.match(text.strip().lower())
    if not m:
        raise ValueError(f"bad duration {text!r} — use e.g. 30s, 15m, 2h, 1d")
    return timedelta(**{_UNITS[m.group(2)]: int(m.group(1))})


def _scored(baseline_pairs, window_pairs) -> list[Anomaly]:
    """Count → ranked anomalies, with the baseline rate-normalized to the window
    size so baseline/window of different lengths compare fairly. Shared by the
    deploy-diff and the time-window analysis."""
    base_count = Counter(t for _, t in baseline_pairs)
    win_count = Counter(t for _, t in window_pairs)
    bt, wt = sum(base_count.values()), sum(win_count.values())
    if bt and wt:
        scale = wt / bt
        base_count = Counter({tid: c * scale for tid, c in base_count.items()})

    samples: dict[int, list[str]] = {}
    for rec, tid in window_pairs:
        if len(samples.setdefault(tid, [])) < 3:
            samples[tid].append(rec.message)
    return score_counts(base_count, win_count, samples)


def split_by_time(pairs, window: timedelta, baseline: timedelta | None):
    """Split pairs into (baseline, window) by timestamp, using the latest
    timestamp in the file as "now". Returns None if no record has a timestamp
    (caller should fall back to a record-count split).

    window   = records in (now - window, now]
    baseline = records in (now - window - baseline_span, now - window],
               where baseline_span defaults to 4× the window.
    """
    timed = [(r, t) for r, t in pairs if r.ts is not None]
    if not timed:
        return None
    now = max(r.ts for r, _ in timed)
    win_start = now - window
    base_start = win_start - (baseline if baseline is not None else window * 4)
    window_pairs = [(r, t) for r, t in timed if r.ts > win_start]
    baseline_pairs = [(r, t) for r, t in timed if base_start < r.ts <= win_start]
    return baseline_pairs, window_pairs


def analyze_file(
    path: str | Path,
    window: timedelta | None = None,
    baseline: timedelta | None = None,
    warn: Callable[[str], None] = lambda m: None,
) -> list[Anomaly]:
    """Analyze a single log file.

    Default (no `window`): split at the record-count midpoint and diff halves.
    With `window`: split by time (baseline vs the recent `window`), using the
    file's own last timestamp as "now". Falls back to the midpoint split — with
    a `warn` — if the log has no timestamps or the time window comes up empty.
    """
    pairs = list(mine(read(path)))
    if window is not None:
        split = split_by_time(pairs, window, baseline)
        if split is None:
            warn("no timestamps found in this log — using a record-count split instead")
        else:
            base_pairs, win_pairs = split
            if not win_pairs or not base_pairs:
                warn("the requested time window is empty — using a record-count split instead")
            else:
                return _scored(base_pairs, win_pairs)

    baseline_half, window_half = split_midpoint(pairs)
    return diff(baseline_half, window_half)


def diff_files(before: str | Path, after: str | Path) -> list[Anomaly]:
    """Compare two logs: `before` = baseline, `after` = window (the deploy-diff).

    Both files are mined through ONE miner so template ids mean the same thing
    across them; scoring rate-normalizes the baseline to the after size."""
    miner = make_miner()
    before_pairs = list(mine(read(before), miner=miner))
    after_pairs = list(mine(read(after), miner=miner))
    return _scored(before_pairs, after_pairs)
