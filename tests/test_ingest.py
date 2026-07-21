"""Unit tests for HDFS ingestion.

Covers acceptance criterion A3 (>=99% of lines parse with a timestamp) and
robustness principle F4 (bad lines are counted, never fatal).
"""

from pathlib import Path

from loglens.ingest import read_hdfs
from loglens.models import LogRecord

SAMPLE = Path(__file__).parent / "data" / "HDFS_2k.log"


def test_a3_parse_rate():
    records = list(read_hdfs(SAMPLE))
    assert len(records) == 2000
    with_ts = sum(1 for r in records if r.ts is not None)
    # A3: at least 99% carry a parsed timestamp.
    assert with_ts / len(records) >= 0.99


def test_records_obey_the_contract():
    r = next(iter(read_hdfs(SAMPLE)))
    assert isinstance(r, LogRecord)
    # message is stripped of the timestamp/level prefix; raw keeps the original.
    assert r.ts is not None and r.level is not None
    assert r.raw and r.message and r.message in r.raw
    assert r.lineno == 1


def test_f4_bad_line_is_not_fatal(tmp_path):
    # A garbage line must yield a record with ts=None, not raise.
    p = tmp_path / "junk.log"
    p.write_text("this is not an HDFS line at all\n")
    records = list(read_hdfs(p))
    assert len(records) == 1
    assert records[0].ts is None
    assert records[0].raw == "this is not an HDFS line at all"
