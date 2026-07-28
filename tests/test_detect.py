"""Unit tests for sniff-and-vote format detection."""

from loglens.detect import detect
from loglens.parsers import JsonParser, LogfmtParser, PlaintextParser


def test_detects_json():
    sample = ['{"ts":"2026-07-21T10:00:00Z","msg":"a"}'] * 5
    assert isinstance(detect(sample), JsonParser)


def test_detects_logfmt():
    sample = ["ts=2026-07-21T10:00:00Z level=info msg=hello"] * 5
    assert isinstance(detect(sample), LogfmtParser)


def test_detects_plaintext_hdfs():
    sample = ["081109 203615 148 INFO dfs.DataNode: received block"] * 5
    assert isinstance(detect(sample), PlaintextParser)


def test_low_confidence_falls_back_to_plaintext():
    # Unstructured prose matches nothing confidently => plaintext fallback (F4).
    sample = ["just some prose", "more prose", "not a log format"]
    assert isinstance(detect(sample), PlaintextParser)


def test_empty_sample_falls_back():
    assert isinstance(detect([]), PlaintextParser)
