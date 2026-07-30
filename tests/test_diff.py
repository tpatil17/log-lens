"""Tests for the two-file diff (deploy-diff) — pipeline core + CLI."""

import json

from typer.testing import CliRunner

from loglens.cli import app
from loglens.pipeline import diff_files

runner = CliRunner()


def _write(p, normal_n, extra=""):
    lines = [f'ts=2026-07-28T10:00:{i % 60:02d}Z level=info msg="request ok" svc=api'
             for i in range(normal_n)]
    p.write_text("\n".join(lines) + ("\n" + extra if extra else "\n"))


def test_diff_flags_new_error_after(tmp_path):
    before = tmp_path / "before.log"
    after = tmp_path / "after.log"
    _write(before, 120)
    burst = "\n".join(
        f'ts=2026-07-28T10:05:{i:02d}Z level=error msg="redis connection refused" svc=api'
        for i in range(20)
    )
    _write(after, 120, extra=burst)

    anomalies = diff_files(before, after)
    assert anomalies, "expected at least one change"
    top = anomalies[0]
    assert top.kind == "NEW"
    assert "redis connection refused" in (top.samples[0] if top.samples else "")


def test_diff_flags_vanished_after(tmp_path):
    # A template present before but gone after should show as VANISHED.
    before = tmp_path / "before.log"
    after = tmp_path / "after.log"
    before.write_text(
        "\n".join(
            f'ts=2026-07-28T10:00:{i % 60:02d}Z level=info msg="cache warm" svc=api'
            for i in range(60)
        )
        + "\n"
    )
    _write(after, 60)  # "request ok" only; "cache warm" vanished
    kinds = {a.kind for a in diff_files(before, after)}
    assert "VANISHED" in kinds


def test_diff_cli_json(tmp_path):
    before = tmp_path / "before.log"
    after = tmp_path / "after.log"
    _write(before, 100)
    _write(after, 100, extra='ts=2026-07-28T10:09:00Z level=error msg="boom" svc=api')
    result = runner.invoke(app, ["diff", str(before), str(after), "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert "→" in data["source"]
    assert isinstance(data["anomalies"], list)
