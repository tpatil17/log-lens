"""Ingest dispatcher — the public entry point of the ingest layer.

    read(source) -> Iterator[LogRecord]

ties together the four pieces:
    sources.open_lines  →  multiline.merge  →  detect.detect  →  parser.parse
"""

import itertools
from collections.abc import Iterator
from pathlib import Path

from loglens.detect import detect
from loglens.models import LogRecord
from loglens.multiline import merge
from loglens.sources import open_lines

SAMPLE_SIZE = 50  # lines peeked for format detection


def sample_lines(source: str | Path, n: int = SAMPLE_SIZE) -> list[str]:
    """Return the first `n` logical (multiline-merged) lines of a source.

    Used for format detection by both `read()` and the `inspect` command."""
    merged = merge(open_lines(source))
    return list(itertools.islice(merged, n))


def read(source: str | Path) -> Iterator[LogRecord]:
    """Auto-detect the format of `source` and yield LogRecords.

    Pipeline: open the source into lines, fold multiline records, peek a sample
    to detect the format, then parse every line with the chosen parser.

    The peek-then-chain step keeps detection streaming: a generator can't be
    rewound, so islice pulls the first ~50 lines for detection and chain glues
    them back in front of the parse loop. Only ~50 lines are ever held in memory.
    """
    merged = merge(open_lines(source))

    # Peek the first ~50 logical lines to detect the format, then chain them
    # back so the parse loop still sees every line. Streaming is preserved.
    sample = list(itertools.islice(merged, SAMPLE_SIZE))
    if not sample:
        return  # empty source: nothing to yield
    parser = detect(sample)
    merged = itertools.chain(sample, merged)

    for lineno, line in enumerate(merged, start=1):
        record = parser.parse(line, lineno)
        if record is None:
            # F4: the chosen parser rejected this line (e.g. a stray non-JSON
            # line in a JSON file). Keep it as a raw record — never drop it.
            record = LogRecord(ts=None, level=None, message=line, raw=line, lineno=lineno)
        yield record
