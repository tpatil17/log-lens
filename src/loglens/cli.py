import typer
from rich.console import Console
from rich.table import Table

from loglens.detect import detect, score_formats
from loglens.ingest import read, sample_lines
from loglens.mining import mine
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
def analyze(path: str, top: int = 10):
    """Rank what changed between the baseline and recent window of a log file."""
    pairs = list(mine(read(path)))
    baseline, window = split_midpoint(pairs)
    anomalies = diff(baseline, window)
    _render(anomalies[:top], source=path)


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
