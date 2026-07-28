"""Multiline merging: a Java stack trace is ~20 physical lines but ONE logical
log record. This pre-pass (runs on raw lines, before parsing) glues continuation
lines onto the record they belong to, so mining sees one template per exception,
not twenty fragments.
"""

import re
from collections.abc import Iterator

# A continuation line typically either:
#   - starts with whitespace (indented stack frame: "\tat com.foo.Bar..."), or
#   - starts with a known Java continuation marker ("Caused by:", "... N more").
CONTINUATION = re.compile(r"^(\s+|Caused by:|\.\.\.\s*\d+\s+more)")


def merge(lines: Iterator[str]) -> Iterator[str]:
    """Yield logical lines: continuation lines folded into their parent.

    A buffer-and-flush loop: continuation lines (per CONTINUATION — indented or
    "Caused by:") are appended to the current buffer; any other line flushes the
    buffer and starts a new record. The final buffer is flushed after the loop.
    A continuation with no parent (file starts mid-trace) becomes its own record.
    """
    buffer = None
    for line in lines:
        if CONTINUATION.match(line) and buffer is not None:
            # Continuation line: append to the current buffer
            buffer += "\n" + line
        else:
            # New record: yield the previous buffer if it exists
            if buffer is not None:
                yield buffer
            buffer = line  # Start a new buffer with the current line

    # After the loop, yield any remaining buffered line
    if buffer is not None:
        yield buffer
