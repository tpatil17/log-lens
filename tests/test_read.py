"""Integration tests for the read() dispatcher (open_lines -> merge -> detect -> parse)."""

import gzip
from datetime import datetime

from loglens.ingest import read


def test_read_autodetects_hdfs_plaintext():
    # read() must auto-detect the HDFS plaintext format and fully parse it.
    records = list(read("tests/data/HDFS_2k.log"))
    assert len(records) == 2000
    # First line: 081109 203615 148 INFO ... => a real timestamp + level.
    assert isinstance(records[0].ts, datetime)
    assert records[0].level is not None
    # A3 still holds through the dispatcher: >=99% carry a timestamp.
    with_ts = sum(1 for r in records if r.ts is not None)
    assert with_ts / len(records) >= 0.99


def test_read_json_file(tmp_path):
    p = tmp_path / "app.log"
    p.write_text(
        '{"ts":"2026-07-21T10:00:00Z","level":"error","msg":"disk full"}\n'
        '{"ts":"2026-07-21T10:00:01Z","level":"info","msg":"ok"}\n'
    )
    rs = list(read(p))
    assert len(rs) == 2
    assert rs[0].level == "error" and rs[0].message == "disk full"


def test_read_logfmt_file(tmp_path):
    p = tmp_path / "app.log"
    p.write_text(
        'ts=2026-07-21T10:00:00Z level=info msg="disk full" host=db1\n'
        "ts=2026-07-21T10:00:01Z level=warn msg=heartbeat host=db1\n"
    )
    rs = list(read(p))
    assert len(rs) == 2 and rs[0].message == "disk full"


def test_read_gzip(tmp_path):
    p = tmp_path / "app.log.gz"
    with gzip.open(p, "wt", encoding="utf-8") as f:
        f.write('{"ts":"2026-07-21T10:00:00Z","msg":"compressed"}\n')
    rs = list(read(p))
    assert len(rs) == 1 and rs[0].message == "compressed"


def test_read_empty_file_yields_nothing(tmp_path):
    p = tmp_path / "empty.log"
    p.write_text("")
    assert list(read(p)) == []


def test_read_keeps_unparseable_line_f4(tmp_path):
    # F4: a stray line the detected parser can't handle must be KEPT as a
    # raw (ts=None) record, never silently dropped.
    p = tmp_path / "mixed.log"
    p.write_text(
        '{"ts":"2026-07-21T10:00:00Z","msg":"good"}\n'
        "this line is not json at all\n"
        '{"ts":"2026-07-21T10:00:01Z","msg":"also good"}\n'
    )
    rs = list(read(p))
    assert len(rs) == 3  # nothing dropped
    assert rs[1].ts is None  # the non-JSON line survived as a raw record
    assert rs[1].raw == "this line is not json at all"
