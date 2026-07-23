"""Unit tests for the source layer (file / gzip / stdin → lines)."""

import gzip
import io
from collections.abc import Iterator

from loglens.sources import open_lines

LINES = ["first line", "second line", "third line"]


def test_plain_file(tmp_path):
    p = tmp_path / "plain.log"
    p.write_text("\n".join(LINES) + "\n")
    assert list(open_lines(p)) == LINES


def test_gzip_file(tmp_path):
    p = tmp_path / "compressed.log.gz"
    with gzip.open(p, "wt", encoding="utf-8") as f:
        f.write("\n".join(LINES) + "\n")
    # .gz is detected by suffix and transparently decompressed.
    assert list(open_lines(p)) == LINES


def test_stdin(monkeypatch):
    # source "-" reads sys.stdin; swap in a fake stdin for the test.
    monkeypatch.setattr("sys.stdin", io.StringIO("\n".join(LINES) + "\n"))
    assert list(open_lines("-")) == LINES


def test_newlines_are_stripped(tmp_path):
    p = tmp_path / "x.log"
    p.write_text("has a newline\n")
    assert list(open_lines(p)) == ["has a newline"]  # no trailing "\n"


def test_is_lazy_generator(tmp_path):
    # N1: open_lines streams — it returns an iterator, not a materialized list.
    p = tmp_path / "x.log"
    p.write_text("a\nb\n")
    result = open_lines(p)
    assert isinstance(result, Iterator)


def test_missing_file_does_not_crash_until_iterated(tmp_path):
    # A generator doesn't run its body until you iterate it — opening a bad path
    # only errors when consumed. (Documents the streaming behavior.)
    gen = open_lines(tmp_path / "does_not_exist.log")
    try:
        list(gen)
        raised = False
    except FileNotFoundError:
        raised = True
    assert raised
