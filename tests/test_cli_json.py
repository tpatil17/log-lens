"""Tests for `loglens analyze --json` (machine-readable output)."""

import json

from typer.testing import CliRunner

from loglens.cli import app

runner = CliRunner()


def test_json_output_is_valid_and_shaped():
    result = runner.invoke(app, ["analyze", "data/demo.log", "--json", "--top", "3"])
    # If the demo file isn't present (gitignored), fall back to the sample.
    if result.exit_code != 0:
        result = runner.invoke(app, ["analyze", "tests/data/HDFS_2k.log", "--json", "--top", "3"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)  # stdout must be pure JSON
    assert "source" in data and "anomaly_count" in data
    assert isinstance(data["anomalies"], list) and len(data["anomalies"]) <= 3
    a = data["anomalies"][0]
    assert {"kind", "score", "base_count", "window_count", "samples"} <= a.keys()


def test_json_explain_without_key_degrades(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    result = runner.invoke(
        app, ["analyze", "tests/data/HDFS_2k.log", "--json", "--explain", "--top", "2"]
    )
    assert result.exit_code == 0
    data = json.loads(result.output)          # still valid JSON, no crash
    assert data["explanation"] is None
    assert "llm_error" in data
