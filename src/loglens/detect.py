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


def score_formats(sample: Sequence[str]) -> list[tuple[str, float]]:
    """Confidence of each parser over the sample, in PARSERS order.

    Returns (name, confidence) pairs — the raw 'vote' that `inspect` displays
    and that `detect` reduces to a single winner."""
    return [(p.name, p.confidence(sample)) for p in PARSERS]


def detect(sample: Sequence[str]) -> Parser:
    """Pick the best parser for a sample of lines.

    Scores every parser by confidence over the sample and returns the highest.
    Ties break toward more-structured formats because PARSERS is ordered
    JSON > logfmt > plaintext and max() keeps the first top scorer. If the best
    score is below CONFIDENCE_THRESHOLD, falls back to plaintext (F4).
    """
    # Compute each confidence once (parsing the sample isn't free).
    scores = {p: p.confidence(sample) for p in PARSERS}
    best = max(PARSERS, key=lambda p: scores[p])
    if scores[best] < CONFIDENCE_THRESHOLD:
        return PlaintextParser()  # F4 fallback: parse as raw, ts=None
    return best
