"""Tests for the digest stage (compact, deterministic anomaly summary)."""

import json

from loglens.digest import build_digest
from loglens.windowing import Anomaly


def _anom(kind, score, bc, wc, samples):
    return Anomaly(
        template_id=1, kind=kind, base_count=bc, window_count=wc,
        delta=wc - bc, score=score, samples=samples,
    )


def test_digest_keeps_top_k():
    anomalies = [_anom("NEW", float(i), 0, i, [f"line {i}"]) for i in range(10)]
    d = build_digest(anomalies, top_k=3)
    assert len(d.top) == 3
    assert d.anomaly_count == 10  # total is reported even though only top-k kept


def test_digest_truncates_samples():
    a = _anom("NEW", 9.0, 0, 5, ["x" * 500, "y" * 500, "z" * 500])
    d = build_digest([a], max_samples=2, sample_chars=50)
    assert len(d.top[0]["samples"]) == 2          # capped count
    assert all(len(s) <= 50 for s in d.top[0]["samples"])  # capped length


def test_digest_is_deterministic():
    anomalies = [_anom("SPIKE", 7.5, 100, 130, ["hello"])]
    assert build_digest(anomalies, source="a.log").to_json() == \
        build_digest(anomalies, source="a.log").to_json()


def test_digest_json_is_compact_and_valid():
    a = _anom("NEW", 12.3, 0, 25, ["FATAL disk failure"])
    payload = build_digest([a], source="app.log").to_json()
    parsed = json.loads(payload)
    assert parsed["source"] == "app.log"
    assert parsed["top"][0]["kind"] == "NEW"
    assert ", " not in payload  # compact separators, no wasted whitespace
