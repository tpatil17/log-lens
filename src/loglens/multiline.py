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

    YOUR TASK — a classic buffer-and-flush loop:
      1. Keep a `buffer` holding the current logical line (start empty/None).
      2. For each physical line:
           - if it looks like a CONTINUATION and we have a buffer:
                 append it to the buffer (e.g. buffer += "\\n" + line) and move on.
           - otherwise it starts a NEW record:
                 if the buffer is non-empty, `yield` it first, then set
                 buffer = line.
      3. After the loop, don't forget to `yield` the final buffered line
         (the flush — a very common bug is dropping the last record).

    Design question: what decides "is this a continuation"? For now the regex
    above (indented or Caused-by). Keep it dumb; you can make it format-aware
    later. What should happen to a continuation line that appears with NO parent
    (file starts mid-trace)? Decide and handle it.
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
