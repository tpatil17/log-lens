"""End-to-end pipeline glue: wire ingest → mine → score into whole-file helpers.

Keeps the CLI a thin adapter — these functions are plain and unit-testable
without spawning the CLI.
"""

from collections import Counter
from pathlib import Path

from loglens.ingest import read
from loglens.mining import make_miner, mine
from loglens.windowing import Anomaly, diff, score_counts, split_midpoint


def analyze_file(path: str | Path) -> list[Anomaly]:
    """One-shot analysis: split a single file at its record-count midpoint and
    diff the earlier half (baseline) against the later half (window)."""
    pairs = list(mine(read(path)))
    baseline, window = split_midpoint(pairs)
    return diff(baseline, window)


def diff_files(before: str | Path, after: str | Path) -> list[Anomaly]:
    """Compare two logs: `before` = baseline, `after` = window (the deploy-diff).

    Both files are mined through ONE miner so template ids mean the same thing
    across them. The baseline is rate-normalized to the after-file's size, so
    before/after captures of different lengths still compare fairly (the same
    size-confounding fix used in watch and the block eval)."""
    miner = make_miner()
    before_pairs = list(mine(read(before), miner=miner))
    after_pairs = list(mine(read(after), miner=miner))

    before_count = Counter(t for _, t in before_pairs)
    after_count = Counter(t for _, t in after_pairs)
    bt, at = sum(before_count.values()), sum(after_count.values())
    if bt and at:
        scale = at / bt
        before_count = Counter({tid: c * scale for tid, c in before_count.items()})

    samples: dict[int, list[str]] = {}
    for rec, tid in after_pairs:
        if len(samples.setdefault(tid, [])) < 3:
            samples[tid].append(rec.message)
    return score_counts(before_count, after_count, samples)
