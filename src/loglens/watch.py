"""Watch mode (U2): tail a growing log and surface anomalies live.

Model — fixed baseline: the file's existing contents at launch become the frozen
"normal" reference; newly-appended lines form a rolling window compared against
it every `refresh` new lines. Fits the common case (start watching a healthy
service, e.g. right after a deploy). For a log that's already mid-incident at
launch, use one-shot `analyze` instead — the problem would be baked into the
baseline here.
"""

import time
from collections import Counter, deque
from collections.abc import Callable, Iterator
from pathlib import Path

from loglens.detect import detect
from loglens.ingest import sample_lines
from loglens.mining import make_miner
from loglens.parsers import Parser
from loglens.windowing import Anomaly, score_counts

WINDOW = 200          # recent lines forming the window
MIN_BASELINE = 300    # warn (don't block) if the startup baseline is thinner
REFRESH = 50          # re-evaluate every N new lines
THRESHOLD = 10.0      # alert when an anomaly's surprise score clears this
POLL = 0.5            # seconds to sleep when no new lines are available


def evaluate(base_count: Counter, window_pairs, threshold: float) -> list[Anomaly]:
    """Score the current window against the frozen baseline; return only the
    anomalies clearing `threshold`. Pure — the testable heart of watch.

    The baseline spans the whole startup file while the window is only the recent
    N lines, so raw counts aren't comparable. We scale the baseline to the window
    size (baseline rate × window size) first — otherwise a normal-but-sparse
    template missing from a short window would false-alarm as VANISHED."""
    window_pairs = list(window_pairs)
    w = len(window_pairs)
    total = sum(base_count.values())
    if w == 0 or total == 0:
        return []
    scale = w / total
    expected = Counter({tid: c * scale for tid, c in base_count.items()})

    window_count = Counter(tid for _, tid in window_pairs)
    samples: dict[int, list[str]] = {}
    for rec, tid in window_pairs:
        if len(samples.setdefault(tid, [])) < 3:
            samples[tid].append(rec.message)
    return [a for a in score_counts(expected, window_count, samples) if a.score >= threshold]


def _tail_events(path: str | Path, poll: float) -> Iterator[tuple[str, str | None]]:
    """Yield ('baseline', line) for existing content, one ('baseline_end', None)
    marker, then ('live', line) forever as the file grows. readline() keeps the
    position across the EOF boundary, so appended lines are picked up."""
    with open(path, encoding="utf-8", errors="replace") as f:
        phase = "baseline"
        while True:
            line = f.readline()
            if line:
                yield phase, line.rstrip("\n")
            else:
                if phase == "baseline":
                    yield "baseline_end", None
                    phase = "live"
                time.sleep(poll)


def _print_alerts(anomalies: list[Anomaly]) -> None:
    for a in anomalies:
        sample = a.samples[0] if a.samples else ""
        print(
            f"[ALERT] {a.kind} score={a.score:.1f} "
            f"~{a.base_count:.0f}->{a.window_count}  {sample}"
        )


def watch(
    path: str | Path,
    *,
    window: int = WINDOW,
    min_baseline: int = MIN_BASELINE,
    refresh: int = REFRESH,
    threshold: float = THRESHOLD,
    poll: float = POLL,
    parser: Parser | None = None,
    events: Iterator[tuple[str, str | None]] | None = None,
    emit: Callable[[list[Anomaly]], None] | None = None,
    warn: Callable[[str], None] = lambda m: print(m),
) -> None:
    """Tail `path`, freezing existing content as baseline and alerting on
    anomalies in the rolling window. `parser`/`events`/`emit` are injectable so
    tests can drive a finite stream without real files or sleeping."""
    if parser is None:
        parser = detect(sample_lines(path))
    if events is None:
        events = _tail_events(path, poll)
    emit = emit or _print_alerts

    miner = make_miner()
    base_count: Counter = Counter()
    win: deque = deque(maxlen=window)
    since = 0

    for phase, line in events:
        if phase == "baseline_end":
            total = sum(base_count.values())
            if total < min_baseline:
                warn(f"baseline is thin ({total} lines < {min_baseline}); "
                     f"expect noise until it fills. Watching anyway.")
            continue
        record = parser.parse(line, 0)
        if record is None:
            continue
        tid = miner.add_log_message(record.message)["cluster_id"]
        if phase == "baseline":
            base_count[tid] += 1
        else:  # live
            win.append((record, tid))
            since += 1
            if since >= refresh:
                since = 0
                alerts = evaluate(base_count, list(win), threshold)
                if alerts:
                    emit(alerts)
