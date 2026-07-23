"""Unit tests for the per-format parsers (JSON, logfmt) and detection voting."""

from datetime import datetime

from loglens.parsers import JsonParser, LogfmtParser, PlaintextParser

# ---------------------------------------------------------------- JSON ----

def test_json_full_record():
    r = JsonParser().parse('{"ts":"2026-07-21T10:00:00Z","level":"error","msg":"disk full"}', 1)
    assert r is not None
    assert isinstance(r.ts, datetime)
    assert r.level == "error"
    assert r.message == "disk full"


def test_json_alternate_keys():
    # time/message instead of ts/msg — the key hunt must find them.
    r = JsonParser().parse('{"time":"2026-07-21T10:00:01","message":"ok"}', 1)
    assert r is not None and r.message == "ok" and r.ts is not None


def test_json_valid_but_not_an_object_returns_none():
    # "[1,2]" and "42" are valid JSON but not log records.
    assert JsonParser().parse("[1,2,3]", 1) is None
    assert JsonParser().parse("42", 1) is None


def test_json_broken_and_empty_do_not_crash():
    assert JsonParser().parse("{bad json", 1) is None
    assert JsonParser().parse("", 1) is None
    assert JsonParser().parse("not json", 1) is None


def test_json_missing_timestamp_is_allowed():
    r = JsonParser().parse('{"msg":"no ts"}', 1)
    assert r is not None and r.ts is None and r.message == "no ts"


# -------------------------------------------------------------- logfmt ----

def test_logfmt_full_record():
    line = 'ts=2026-07-21T10:00:00Z level=info msg="disk full" host=db1'
    r = LogfmtParser().parse(line, 1)
    assert r is not None
    assert isinstance(r.ts, datetime)
    assert r.level == "info"
    assert r.message == "disk full"   # quotes stripped


def test_logfmt_not_logfmt_returns_none():
    # A plain sentence with no key=value pairs isn't logfmt.
    assert LogfmtParser().parse("just a normal sentence here", 1) is None


def test_logfmt_missing_timestamp_is_allowed():
    r = LogfmtParser().parse("level=warn msg=heartbeat", 1)
    assert r is not None and r.ts is None and r.message == "heartbeat"


# --------------------------------------------------------- confidence ----

def test_confidence_separates_formats():
    json_sample = ['{"ts":"2026-07-21T10:00:00Z","msg":"a"}'] * 5
    text_sample = ["081109 203615 148 INFO dfs.DataNode: hello"] * 5
    # Each parser should be confident on its own format, not the other's.
    assert JsonParser().confidence(json_sample) > 0.9
    assert JsonParser().confidence(text_sample) == 0.0
    assert PlaintextParser().confidence(text_sample) > 0.9
    assert PlaintextParser().confidence(json_sample) == 0.0
