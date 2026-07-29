import json
from dataclasses import asdict

import typer
from rich.console import Console
from rich.table import Table

# Load a local .env (project root) so OPENAI_API_KEY can live in a file instead
# of the shell. Optional — if python-dotenv isn't installed we just read os.environ.
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from loglens.detect import detect, score_formats
from loglens.digest import build_digest
from loglens.ingest import read, sample_lines
from loglens.mining import mine
from loglens.summarize import DEFAULT_MODEL, LLMUnavailable, summarize
from loglens.windowing import Anomaly, diff, split_midpoint

app = typer.Typer(help="Find what's new, spiking, or vanished in your logs.")
console = Console()

# Colour per anomaly kind, so the terminal draws the eye to the right rows.
_KIND_STYLE = {"NEW": "bold red", "SPIKE": "yellow", "VANISHED": "dim cyan"}


@app.callback()
def main():
    """LogLens — find what's new, spiking, or vanished in your logs."""
    # Presence of a callback keeps typer in command-group mode, so `analyze`
    # stays an explicit subcommand instead of collapsing to the top level.
    pass


@app.command()
def analyze(
    path: str,
    top: int = 10,
    explain: bool = False,
    model: str = DEFAULT_MODEL,
    as_json: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
):
    """Rank what changed between the baseline and recent window of a log file.

    Pass --explain to send a compact digest of the top anomalies to OpenAI for a
    plain-English explanation (needs OPENAI_API_KEY; tokens spent only on demand).
    Pass --json for machine-readable output (stdout is pure JSON; notices go to stderr).
    """
    pairs = list(mine(read(path)))
    baseline, window = split_midpoint(pairs)
    anomalies = diff(baseline, window)
    top_anoms = anomalies[:top]

    if as_json:
        out = {
            "source": path,
            "anomaly_count": len(anomalies),
            "anomalies": [asdict(a) for a in top_anoms],
        }
        if explain and anomalies:
            try:
                digest = build_digest(anomalies, source=path)
                out["explanation"] = asdict(summarize(digest, model=model))
            except LLMUnavailable as e:
                out["explanation"] = None
                out["llm_error"] = str(e)
        print(json.dumps(out, indent=2))
        return

    _render(top_anoms, source=path)
    if explain and anomalies:
        try:
            explanation = summarize(build_digest(anomalies, source=path), model=model)
        except LLMUnavailable as e:
            # F8: degrade gracefully — the report above is unaffected.
            console.print(f"\n[dim]LLM explanation skipped: {e}[/dim]")
        else:
            _render_explanation(explanation)


@app.command()
def watch(
    path: str,
    window: int = 200,
    min_baseline: int = 300,
    refresh: int = 50,
    threshold: float = 10.0,
):
    """Tail a growing log; alert on anomalies vs the baseline frozen at launch.

    Best started on a currently-healthy log (e.g. right after a deploy). Ctrl-C to stop.
    """
    from loglens import watch as watch_mod

    def emit(anomalies):
        for a in anomalies:
            sample = a.samples[0] if a.samples else ""
            style = _KIND_STYLE.get(a.kind, "")
            console.print(
                f"[{style}]ALERT {a.kind}[/] score={a.score:.1f} "
                f"~{a.base_count:.0f}→{a.window_count}  [dim]{sample}[/dim]"
            )

    console.print(f"[dim]watching {path} — baseline frozen at launch, Ctrl-C to stop[/dim]")
    try:
        watch_mod.watch(
            path, window=window, min_baseline=min_baseline,
            refresh=refresh, threshold=threshold,
            emit=emit, warn=lambda m: console.print(f"[yellow]{m}[/yellow]"),
        )
    except KeyboardInterrupt:
        console.print("\n[dim]stopped.[/dim]")


@app.command()
def inspect(path: str):
    """Detect a log file's format and summarize its structure (no analysis)."""
    sample = sample_lines(path)
    if not sample:
        console.print(f"[yellow]{path} is empty.[/yellow]")
        return
    scores = score_formats(sample)
    chosen = detect(sample)
    records = [chosen.parse(line, i) for i, line in enumerate(sample, start=1)]
    _render_inspect(path, chosen.name, scores, records)


def _render_inspect(path, chosen_name, scores, records) -> None:
    """Render the inspect summary. Pure formatting — no logic."""
    with_ts = sum(1 for r in records if r is not None and r.ts is not None)
    parse_rate = with_ts / len(records) if records else 0.0

    votes = Table(title=f"LogLens inspect — {path}")
    votes.add_column("format")
    votes.add_column("confidence", justify="right")
    for name, conf in scores:
        if name == chosen_name:
            votes.add_row(f"[bold green]{name}[/]", f"[bold green]{conf:.0%}  ◄ detected[/]")
        else:
            votes.add_row(name, f"{conf:.0%}")
    console.print(votes)
    console.print(
        f"Sampled [bold]{len(records)}[/bold] lines · "
        f"detected [bold]{chosen_name}[/bold] · "
        f"[bold]{parse_rate:.0%}[/bold] carry a timestamp"
    )

    preview = Table(title="Preview", show_lines=False)
    preview.add_column("ts", no_wrap=True)
    preview.add_column("level", no_wrap=True)
    preview.add_column("message", overflow="ellipsis", max_width=70)
    for r in records[:3]:
        if r is None:
            continue
        preview.add_row(str(r.ts) if r.ts else "—", r.level or "—", r.message)
    console.print(preview)


def _render_explanation(exp) -> None:
    """Render the LLM explanation. Pure formatting — no logic."""
    console.print("\n[bold]Explanation[/bold] [dim](LLM hypotheses — verify before acting)[/dim]")
    console.print(exp.summary)
    if exp.hypotheses:
        console.print("\n[bold]Possible causes[/bold]")
        for h in exp.hypotheses:
            console.print(f"  • {h}")
    if exp.suggested_actions:
        console.print("\n[bold]Suggested next steps[/bold]")
        for a in exp.suggested_actions:
            console.print(f"  • {a}")


def _render(anomalies: list[Anomaly], source: str = "") -> None:
    """Render ranked anomalies as a terminal table. Pure formatting — no logic."""
    if not anomalies:
        console.print("[green]No anomalies: the window looks like the baseline.[/green]")
        return

    table = Table(title=f"LogLens — what changed in {source}" if source else "LogLens")
    table.add_column("#", justify="right", style="dim")
    table.add_column("kind", no_wrap=True)
    table.add_column("score", justify="right")
    table.add_column("base→win", justify="right")
    table.add_column("example", overflow="ellipsis", max_width=70)

    for rank, a in enumerate(anomalies, start=1):
        sample = a.samples[0] if a.samples else ""
        table.add_row(
            str(rank),
            f"[{_KIND_STYLE.get(a.kind, '')}]{a.kind}[/]",
            f"{a.score:.1f}",
            f"{a.base_count}→{a.window_count}",
            sample,
        )

    console.print(table)


if __name__ == "__main__":
    app()
