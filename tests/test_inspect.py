"""Tests for the `loglens inspect` command — M3 acceptance: correct on >=5 formats."""

import gzip

from typer.testing import CliRunner

from loglens.cli import app

runner = CliRunner()


def _run(path):
    result = runner.invoke(app, ["inspect", str(path)])
    assert result.exit_code == 0, result.output
    return result.output


def test_inspect_hdfs_plaintext():
    out = _run("tests/data/HDFS_2k.log")
    assert "plaintext-hdfs" in out
    assert "detected" in out


def test_inspect_json(tmp_path):
    p = tmp_path / "app.log"
    p.write_text('{"ts":"2026-07-21T10:00:00Z","level":"error","msg":"disk full"}\n' * 3)
    out = _run(p)
    assert "json" in out and "detected" in out


def test_inspect_logfmt(tmp_path):
    p = tmp_path / "app.log"
    p.write_text("ts=2026-07-21T10:00:00Z level=info msg=hello host=db1\n" * 3)
    out = _run(p)
    assert "logfmt" in out and "detected" in out


def test_inspect_gzip_json(tmp_path):
    p = tmp_path / "app.log.gz"
    with gzip.open(p, "wt", encoding="utf-8") as f:
        f.write('{"ts":"2026-07-21T10:00:00Z","msg":"compressed"}\n' * 3)
    out = _run(p)
    assert "json" in out


def test_inspect_unknown_falls_back_to_plaintext(tmp_path):
    p = tmp_path / "prose.log"
    p.write_text("just some prose\nmore prose\nnothing structured here\n")
    out = _run(p)
    # Low confidence everywhere => plaintext fallback (F4).
    assert "plaintext" in out


def test_inspect_empty_file(tmp_path):
    p = tmp_path / "empty.log"
    p.write_text("")
    result = runner.invoke(app, ["inspect", str(p)])
    assert result.exit_code == 0
    assert "empty" in result.output.lower()
