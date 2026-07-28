"""Unit tests for Drain3 template mining.

Covers acceptance criterion A2: the mined template count is in the same
order of magnitude as the loghub reference (assert a band, not an exact number,
so a drain3 version bump doesn't break the suite).
"""

from pathlib import Path

from loglens.ingest import read
from loglens.mining import mine

SAMPLE = Path(__file__).parent / "data" / "HDFS_2k.log"


def test_every_record_gets_a_template():
    pairs = list(mine(read(SAMPLE)))
    assert len(pairs) == 2000
    assert all(isinstance(tid, int) for _, tid in pairs)


def test_a2_template_count_is_sane():
    template_ids = {tid for _, tid in mine(read(SAMPLE))}
    # Reference ~ mid-teens for the 2k sample; assert within 2x, not 10x.
    assert 10 <= len(template_ids) <= 30


def test_masking_collapses_block_ids():
    # Two lines identical but for the block id must land in the SAME template,
    # proving the drain3.ini BLKID mask is actually loaded and firing.
    from loglens.mining import mine as mine_fn
    from loglens.models import LogRecord

    def rec(msg):
        return LogRecord(ts=None, level="INFO", message=msg, raw=msg, lineno=1)

    a = "Received block blk_111 of size 67108864 from /10.0.0.1"
    b = "Received block blk_-999 of size 67108864 from /10.0.0.2"
    pairs = list(mine_fn([rec(a), rec(b)]))
    assert pairs[0][1] == pairs[1][1]
