# src/loglens/windowing.py
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

from loglens.models import LogRecord
from loglens.scoring import poisson_surprise


@dataclass
class Anomaly:
    template_id: int
    kind: str          # "NEW" | "SPIKE" | "VANISHED"
    base_count: int
    window_count: int
    delta: int
    score: float
    samples: list[str] | None = None

def split_midpoint(pairs: list[tuple[LogRecord, int]]):
    """Split a time-ordered pair stream into (baseline, window) at the record-count midpoint."""
    mid = len(pairs) // 2
    return pairs[:mid], pairs[mid:]

def score_counts(
    base_count: Counter,
    window_count: Counter,
    window_samples: dict[int, list[str]] | None = None,
) -> list[Anomaly]:
    """Compare two template-count Counters → ranked anomalies.

    The shared core of detection: `diff` builds the counters from pair streams;
    `watch` keeps a fixed baseline Counter and calls this each tick. Classifies
    NEW / SPIKE / VANISHED, scores by two-sided surprise, ranks by score."""
    window_samples = window_samples or {}
    result = []
    for tid in set(base_count) | set(window_count):
        bc = base_count.get(tid, 0)
        wc = window_count.get(tid, 0)
        delta = wc - bc
        if bc == 0 and wc > 0:
            kind = "NEW"
        elif bc > 0 and wc == 0:
            kind = "VANISHED"
        elif bc > 0 and wc > 0 and delta > 0:
            kind = "SPIKE"
        else:
            continue
        result.append(
            Anomaly(
                template_id=tid,
                kind=kind,
                base_count=bc,
                window_count=wc,
                delta=delta,
                score=poisson_surprise(bc, wc),
                samples=window_samples.get(tid, []),
            )
        )
    result.sort(key=lambda a: a.score, reverse=True)
    return result


def diff(
    baseline: Iterable[tuple[LogRecord, int]],
    window: Iterable[tuple[LogRecord, int]],
) -> list[Anomaly]:
    """Compare template frequencies between a baseline and a window."""
    # window is walked twice (counts, then samples), so materialize it to stay
    # correct even when passed a one-shot generator. baseline is walked once.
    window = list(window)
    base_count = Counter(t for _, t in baseline)
    window_count = Counter(t for _, t in window)

    window_samples: dict[int, list[str]] = {}
    for rec, tid in window:
        if len(window_samples.setdefault(tid, [])) < 3:
            window_samples[tid].append(rec.message)

    return score_counts(base_count, window_count, window_samples)