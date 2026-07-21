# src/loglens/windowing.py
from collections import Counter
from dataclasses import dataclass
from typing import Iterable

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

def diff(
    baseline: Iterable[tuple[LogRecord, int]],
    window: Iterable[tuple[LogRecord, int]],
) -> list[Anomaly]:
    """Compare template frequencies between two sides; rank by delta."""
    # 1. Counter over template_ids for each side
    base_count = Counter(t for _, t in baseline)
    window_count = Counter(t for _, t in window)

    result = []

    # 2. loop the union of template ids
    union = set(base_count.keys()).union(set(window_count.keys()))

    window_samples: dict[int, list[str]] = {}

    for rec, tid in window:
        if len(window_samples.setdefault(tid, [])) < 3:
            window_samples[tid].append(rec.message)

    for tid in union:
        bc = base_count.get(tid, 0)
        wc = window_count.get(tid, 0)
        delta = wc - bc #legacy scoring
        score = poisson_surprise(bc, wc)
        if bc == 0 and wc > 0:
            kind = "NEW"
        elif bc > 0 and wc == 0:
            kind = "VANISHED"
        elif bc > 0 and wc > 0 and delta > 0:
            kind = "SPIKE"
        else:
            continue
        result.append(Anomaly(template_id=tid, kind=kind, base_count=bc, window_count=wc, delta=delta, score=score, samples=window_samples.get(tid, [])))
    
    result.sort(key=lambda a: a.score, reverse=True)

    return result
    # 3. classify NEW / SPIKE / VANISHED, build Anomaly
    # 4. sort by delta descending, return