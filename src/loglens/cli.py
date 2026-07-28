import typer
from rich.console import Console
from rich.table import Table

from loglens.ingest import read
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
