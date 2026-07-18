# src/loglens/windowing.py
from collections import Counter
from dataclasses import dataclass
from typing import Iterable

from loglens.models import LogRecord


@dataclass
class Anomaly:
    template_id: int
    kind: str          # "NEW" | "SPIKE" | "VANISHED"
    base_count: int
    window_count: int
    delta: int


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

    for id in union:
        bc = base_count.get(id, 0)
        wc = window_count.get(id, 0)
        delta = wc - bc
        if bc == 0 and wc > 0:
            kind = "NEW"
        elif bc > 0 and wc == 0:
            kind = "VANISHED"
        elif bc > 0 and wc > 0 and delta > 0:
            kind = "SPIKE"
        result.append(Anomaly(template_id=id, kind=kind, base_count=bc, window_count=wc, delta=delta))
    
    result.sort(key=lambda a: a.delta, reverse=True)

    return result
    # 3. classify NEW / SPIKE / VANISHED, build Anomaly
    # 4. sort by delta descending, return