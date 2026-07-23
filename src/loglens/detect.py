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

    YOUR TASK:
      1. Score every parser: `parser.confidence(sample)` for parser in PARSERS.
      2. Choose the highest-scoring parser.
      3. If that top score is below CONFIDENCE_THRESHOLD, return a
         PlaintextParser() as the graceful fallback instead.

    Tie-break (already handled for you *if* you rely on order): PARSERS lists
    the more-structured formats first, and Python's max() keeps the FIRST max it
    sees — so iterate in PARSERS order and JSON wins a tie over logfmt, etc.
    (Careful: does `max(PARSERS, key=...)` preserve that order? Test it — write
    a sample that two parsers tie on and confirm the structured one wins.)

    Return: the chosen Parser instance.
    """
    raise NotImplementedError("implement detect: score parsers, apply threshold")
