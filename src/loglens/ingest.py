"""Ingest dispatcher — the public entry point of the ingest layer.

    read(source) -> Iterator[LogRecord]

ties together the five pieces:
    sources.open_lines  →  multiline.merge  →  detect.detect  →  parser.parse

`read_hdfs` is kept as a thin, always-working shim over PlaintextParser so the
existing tests and CLI don't break while `read()` is being built out.
"""

import itertools
from collections.abc import Iterator
from pathlib import Path

from loglens.models import LogRecord
from loglens.parsers import PlaintextParser


def read_hdfs(path: str | Path) -> Iterator[LogRecord]:
    """Yield LogRecords from an HDFS-format log file, one line at a time.

    DONE — now delegates to PlaintextParser so there's a single copy of the
    HDFS parsing logic. Opens the file directly (independent of the new source
    layer) so it keeps working while `read()` below is under construction.
    """
    parser = PlaintextParser()
    with open(path, encoding="utf-8", errors="replace") as f:
        for lineno, line in enumerate(f, start=1):
            record = parser.parse(line.rstrip("\n"), lineno)
            if record is not None:
                yield record


def read(source: str | Path) -> Iterator[LogRecord]:
    """Auto-detect the format of `source` and yield LogRecords.

    YOUR TASK — assemble the pieces you're building (each is its own module,
    so build+test them bottom-up first, then wire them here):

      1. lines = open_lines(source)                      # sources.py
      2. merged = merge(lines)                            # multiline.py
      3. Peek a sample WITHOUT consuming the stream: `merged` is a generator, so
         pull ~50 lines for detection, then chain them back on. Pattern:
             sample = list(itertools.islice(merged, 50))
             parser = detect(sample)                      # detect.py
             merged = itertools.chain(sample, merged)     # put the peeked lines back
      4. for lineno, line in enumerate(merged, start=1):
             record = parser.parse(line, lineno)
             if record is not None:
                 yield record

    Why peek-then-chain (step 3): detection needs to see lines, but you can't
    rewind a generator. islice takes the first N, and chain glues them back in
    front so the parse loop still sees every line. Streaming is preserved —
    you only ever hold ~50 lines, not the whole file.

    Once `read()` works and is tested across formats, `read_hdfs` can be
    retired (callers switch to `read`), closing the M3 migration.
    """
    raise NotImplementedError("wire together open_lines -> merge -> detect -> parse")
