"""Source layer: where bytes come from. Format-agnostic — just yields lines.

This module knows nothing about JSON, logfmt, or timestamps. Its only job is:
  file path | '-' (stdin) | '.gz' file   ->   Iterator[str] (one line at a time)

Keeping this separate means detection and parsing never care about *where* the
lines came from — the same pipeline handles a gzipped file and a stdin pipe.
"""

import gzip
import sys
from collections.abc import Iterator
from pathlib import Path


def open_lines(source: str | Path) -> Iterator[str]:
    """Yield text lines (newline stripped) from a file, stdin, or a .gz file.

    Streams line by line (N1: never loads the whole file). `source == "-"` reads
    stdin (not wrapped in `with`, since we don't own it); a ".gz" suffix is read
    as decompressed text; anything else is a plain UTF-8 file. `errors="replace"`
    keeps a stray bad byte from crashing the read (F4).
    """
    if source == "-":
        # Case 1: read from stdin
        for line in sys.stdin:
            yield line.rstrip("\n")
    else:
        path = Path(source)
        if path.suffix == ".gz":
            # Case 2: read from a gzip file
            opener = gzip.open
            mode = "rt"
        else:
            # Case 3: read from a plain text file
            opener = open
            mode = "r"

        with opener(path, mode, encoding="utf-8", errors="replace") as f:
            for line in f:
                yield line.rstrip("\n")
