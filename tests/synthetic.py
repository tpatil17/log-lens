"""Synthetic anomaly injection for the A4 acceptance test.

The helpers now live in `loglens.eval` (they're used by the shipped evaluation
harness too), re-exported here so existing tests keep their import path.

A4: an injected error burst must rank in the top 3 of diff() results. The burst
is brand-new content Drain3 has never seen, appended AFTER the real logs so the
record-count midpoint split drops the whole burst into the *window*.
"""

from loglens.eval import BURST_MESSAGE, inject_burst, make_burst

__all__ = ["BURST_MESSAGE", "inject_burst", "make_burst"]
