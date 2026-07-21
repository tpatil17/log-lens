"""Synthetic anomaly injection for the A4 acceptance test.

A4: an injected error burst must rank in the top 3 of diff() results.
We build brand-new LogRecords (content Drain3 has never seen) and append
them AFTER the real logs so the record-count midpoint split drops the whole
burst into the *window*, with zero occurrences in the baseline.
"""

from datetime import timedelta
from typing import Iterable

from loglens.models import LogRecord

# A message that does not appear anywhere in HDFS_2k.log, so Drain3 mines it
# as a single new template. Numbers here get masked, which is fine — the point
# is the burst is one repeated statement.
BURST_MESSAGE = "FATAL disk failure on volume /data/3 blk_-999888777"


def make_burst(after: LogRecord, count: int = 30) -> list[LogRecord]:
    """Return `count` identical synthetic error records timestamped just
    after `after` (typically the last real record in the stream)."""
    base_ts = after.ts
    records = []
    for i in range(count):
        # 1-second apart so they're ordered and land at the end of the stream.
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

