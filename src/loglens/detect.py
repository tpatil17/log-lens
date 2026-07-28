"""Format detection by sniff-and-vote.

Read a sample of lines, ask each parser how much of it it can parse, pick the
winner. Detection depends only on the Parser *interface*, never on a specific
format — so it never grows when you add a format.
"""

from collections.abc import Sequence

from loglens.parsers import PARSERS, Parser, PlaintextParser

# If the best parser can't confidently handle at least this fraction of the
# sample, we fall back to plaintext (F4: parse as raw, ts=None, line-count windows).
CONFIDENCE_THRESHOLD = 0.5


def detect(sample: Sequence[str]) -> Parser:
    """Pick the best parser for a sample of lines.

    Scores every parser by confidence over the sample and returns the highest.
    Ties break toward more-structured formats because PARSERS is ordered
    JSON > logfmt > plaintext and max() keeps the first top scorer. If the best
    score is below CONFIDENCE_THRESHOLD, falls back to plaintext (F4).
    """
    # max() returns the FIRST parser achieving the top score, and PARSERS is
    # ordered most-structured-first, so ties break toward JSON > logfmt > plaintext.
    best = max(PARSERS, key=lambda p: p.confidence(sample))
    if best.confidence(sample) < CONFIDENCE_THRESHOLD:
        return PlaintextParser()  # F4 fallback: parse as raw, ts=None
    return best
