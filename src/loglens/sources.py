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

    YOUR TASK — three cases to handle, all streaming (N1: never read the whole
    file into memory):

    1. stdin: if `source == "-"`, read from `sys.stdin` line by line.
    2. gzip:  if the path ends in ".gz", open with `gzip.open(path, mode="rt")`
              ("rt" = read *text*, so you get str not bytes).
    3. plain: otherwise `open(path, encoding="utf-8", errors="replace")`.

    In all three, `yield line.rstrip("\\n")` per line.

    Hints:
      - Cases 2 and 3 both use a `with ... as f:` block then `for line in f:`.
        Can you avoid duplicating the loop? (e.g. pick the opener first, then
        one shared loop.)
      - `errors="replace"` keeps a stray bad byte from crashing the read (F4).
      - Think: does stdin need a `with` block? (You don't own sys.stdin — don't
        close it.)
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
