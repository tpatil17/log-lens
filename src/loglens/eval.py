"""Evaluation harness for LogLens.

Two evaluations, both reducing to precision / recall / F1:

* Block-level (real labels): group HDFS lines by block id, score each block by
  template surprise vs the global baseline, and compare to anomaly_label.csv.
  This reuses the product's own detector — a block is just a "window" scored
  against the baseline of all blocks (same thesis as the live tool).

* Injection (no external data): inject synthetic bursts of varying size and
  measure detection rank. Runs anywhere, so CI always has a trust number.

Run:
    python -m loglens.eval blocks  <log> <anomaly_label.csv>
    python -m loglens.eval inject  <log>
"""

import csv
import re
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from loglens.ingest import read
from loglens.mining import mine
from loglens.models import LogRecord
from loglens.windowing import diff, split_midpoint

BLOCK_RE = re.compile(r"blk_-?\d+")

# A message absent from any real log, so Drain3 mines it as a single new
# template — the synthetic "anomaly" used by the injection eval.
BURST_MESSAGE = "FATAL disk failure on volume /data/3 blk_-999888777"


def make_burst(after: LogRecord, count: int = 30) -> list[LogRecord]:
    """Return `count` identical synthetic error records timestamped just after
    `after` (typically the last real record in the stream)."""
    base_ts = after.ts
    records = []
    for i in range(count):
        ts = base_ts + timedelta(seconds=i + 1) if base_ts else None
        records.append(
            LogRecord(
                ts=ts,
                level="ERROR",
                message=BURST_MESSAGE,
                raw=f"{BURST_MESSAGE}  (synthetic burst line {i + 1})",
                lineno=after.lineno + i + 1,
            )
        )
    return records


def inject_burst(records: Iterable[LogRecord], count: int = 30) -> list[LogRecord]:
    """Materialize `records`, append a burst at the end, return the new list."""
    records = list(records)
    if not records:
        raise ValueError("cannot inject a burst into an empty stream")
    return records + make_burst(records[-1], count=count)


# --------------------------------------------------------------- metrics ----

@dataclass
class Metrics:
    precision: float
    recall: float
    f1: float
    tp: int
    fp: int
    fn: int
    tn: int


def prf(preds: dict[str, bool], labels: dict[str, bool]) -> Metrics:
    """Precision/recall/F1 over the keys present in BOTH preds and labels."""
    tp = fp = fn = tn = 0
    for key in preds.keys() & labels.keys():
        predicted, actual = preds[key], labels[key]
        if predicted and actual:
            tp += 1
        elif predicted and not actual:
            fp += 1
        elif not predicted and actual:
            fn += 1
        else:
            tn += 1
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return Metrics(precision, recall, f1, tp, fp, fn, tn)


# ---------------------------------------------------- block-level scoring ----

def load_labels(path: str | Path) -> dict[str, bool]:
    """Read anomaly_label.csv (block_id,label) -> {block_id: is_anomaly}."""
    labels: dict[str, bool] = {}
    with open(path, newline="") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        # Tolerate a header row or its absence.
        if header and header[0].strip().lower() not in ("blockid", "block_id"):
            f.seek(0)
            reader = csv.reader(f)
        for row in reader:
            if len(row) >= 2 and row[0].startswith("blk_"):
                labels[row[0]] = row[1].strip().lower() == "anomaly"
    return labels


def score_blocks(pairs) -> dict[str, float]:
    """Score each block by the surprise of its rarest present template.

    Presence (Bernoulli) surprise: -log P(template present). A block scores high
    when it contains a globally-rare event type — the signal HDFS anomalies carry.
    This is the same 'surprise vs baseline' thesis as the live tool, with the
    observable being template *presence* (right for blocks) rather than count.
    Matches score_blocks_from_matrix; used when mining raw logs directly.
    """
    import math

    block_templates: dict[str, set] = defaultdict(set)
    for record, tid in pairs:
        m = BLOCK_RE.search(record.raw)
        if m:
            block_templates[m.group()].add(tid)

    n_blocks = len(block_templates) or 1
    doc_count: Counter = Counter()
    for tids in block_templates.values():
        for tid in tids:
            doc_count[tid] += 1

    return {
        block: max((-math.log(doc_count[tid] / n_blocks) for tid in tids), default=0.0)
        for block, tids in block_templates.items()
    }


def score_blocks_from_matrix(path: str | Path, alpha: float = 0.5):
    """Score blocks from a precomputed block×template count matrix (loghub's
    Event_occurrence_matrix.csv: BlockId, Label, Type, E1..En).

    Same surprise metric as the live tool, vectorized: for each template the
    baseline rate is its mean count per block; a block scores as the max
    Poisson surprise across its templates. Returns (scores, labels)."""
    import numpy as np

    with open(path, newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        e_cols = [i for i, h in enumerate(header) if h.startswith("E")]
        bid_i, label_i = header.index("BlockId"), header.index("Label")
        block_ids, label_list, rows = [], [], []
        for row in reader:
            block_ids.append(row[bid_i])
            label_list.append(row[label_i].strip().lower() in ("fail", "anomaly"))
            rows.append([int(row[i]) for i in e_cols])

    counts = np.array(rows, dtype=np.int64)          # (n_blocks, n_templates)
    present = counts > 0

    # Presence (Bernoulli) surprise: -log P(template present) is the self-
    # information of seeing a template. A block scores as the surprise of its
    # rarest present template — HDFS anomalies are marked by *which* rare event
    # types occur, not by raw counts (count-surprise is confounded by block size).
    doc_freq = present.mean(axis=0)                  # fraction of blocks with each template
    idf = -np.log(doc_freq + 1e-9)
    block_scores = (present * idf).max(axis=1)

    scores = {b: float(s) for b, s in zip(block_ids, block_scores, strict=True)}
    labels = {b: lbl for b, lbl in zip(block_ids, label_list, strict=True)}
    return scores, labels


def best_threshold(scores: dict[str, float], labels: dict[str, bool]) -> float:
    """Pick the score threshold maximizing F1 over the labeled blocks.

    Sweeps thresholds in one pass (O(n log n)): sort blocks by score descending,
    then lower the cut one block at a time, updating tp/fp incrementally."""
    items = sorted(((s, labels.get(b, False)) for b, s in scores.items()), reverse=True)
    total_pos = sum(1 for _, actual in items if actual)
    if total_pos == 0:
        return items[0][0] + 1.0 if items else 0.0  # nothing to find

    tp = fp = 0
    best_t, best_f1 = items[0][0] + 1.0, -1.0
    for score, actual in items:
        if actual:
            tp += 1
        else:
            fp += 1
        precision = tp / (tp + fp)
        recall = tp / total_pos
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        if f1 > best_f1:
            best_f1, best_t = f1, score
    return best_t


def evaluate_blocks(log_path, labels_path, threshold: float | None = None):
    """Full block-level eval: returns (Metrics, threshold, n_blocks_labeled)."""
    labels = load_labels(labels_path)
    scores = score_blocks(mine(read(log_path)))
    labeled = {b: s for b, s in scores.items() if b in labels}
    if not labeled:
        raise ValueError(
            "No overlap between blocks in the log and blocks in the label file. "
            "Make sure the log and anomaly_label.csv are from the same dataset."
        )
    if threshold is None:
        threshold = best_threshold(labeled, labels)
    preds = {b: s >= threshold for b, s in labeled.items()}
    return prf(preds, labels), threshold, len(labeled)


# ----------------------------------------------------- injection eval --------

def _burst_rank(records, size: int, k: int = 3):
    """Inject a burst of `size` and return (rank_of_burst, detected_within_k)."""
    pairs = list(mine(inject_burst(records, count=size)))
    baseline, window = split_midpoint(pairs)
    ranked = diff(baseline, window)
    for rank, a in enumerate(ranked, start=1):
        if any(BURST_MESSAGE.split()[0] in s for s in (a.samples or [])):
            return rank, rank <= k
    return None, False


def injection_eval(log_path, sizes=(3, 5, 10, 20, 40), k: int = 3):
    """Detection rank of an injected burst as a function of burst size."""
    records = list(read(log_path))
    rows = []
    for size in sizes:
        rank, detected = _burst_rank(records, size, k)
        rows.append((size, rank, detected))
    return rows


# ------------------------------------------------------------- CLI -----------

def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print(__doc__)
        return 1
    mode = argv[0]
    if mode == "blocks":
        m, t, n = evaluate_blocks(argv[1], argv[2])
        print(f"Block-level eval on {n} labeled blocks (threshold={t:.2f}):")
        print(f"  precision={m.precision:.3f}  recall={m.recall:.3f}  f1={m.f1:.3f}")
        print(f"  tp={m.tp} fp={m.fp} fn={m.fn} tn={m.tn}")
    elif mode == "matrix":
        scores, labels = score_blocks_from_matrix(argv[1])
        t = best_threshold(scores, labels)
        m = prf({b: s >= t for b, s in scores.items()}, labels)
        n_anom = sum(labels.values())
        print(f"Block-level eval on {len(scores):,} blocks "
              f"({n_anom:,} anomalies, threshold={t:.2f}):")
        print(f"  precision={m.precision:.3f}  recall={m.recall:.3f}  f1={m.f1:.3f}")
        print(f"  tp={m.tp} fp={m.fp} fn={m.fn} tn={m.tn}")
    elif mode == "inject":
        print(f"Injection eval on {argv[1]}:")
        print(f"  {'size':>5}  {'rank':>5}  detected@3")
        for size, rank, detected in injection_eval(argv[1]):
            print(f"  {size:>5}  {str(rank):>5}  {detected}")
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
