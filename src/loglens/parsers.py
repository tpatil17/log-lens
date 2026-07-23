"""Per-format parsers. Every parser exposes the SAME two methods so detection
can treat them interchangeably (this uniform interface is what makes
sniff-and-vote possible):

    parse(line, lineno) -> LogRecord | None      # None = "this line isn't mine"
    confidence(sample)  -> float                 # 0..1 = fraction I can parse

Add a new format later => add one class here, register it in PARSERS, and
nothing else in the codebase changes.
"""

import re
from collections.abc import Sequence
from datetime import datetime
from typing import Protocol
import json
from loglens.models import LogRecord


class Parser(Protocol):
    name: str

    def parse(self, line: str, lineno: int) -> LogRecord | None: ...
    def confidence(self, sample: Sequence[str]) -> float: ...


def _confidence_from_parse(parser: Parser, sample: Sequence[str]) -> float:
    """Shared helper: confidence = fraction of sample lines that parse to a
    record WITH a timestamp. A parser that returns None or ts=None doesn't
    count as a confident match. (Given for you — reuse it in each confidence().)"""
    non_blank = [ln for ln in sample if ln.strip()]
    if not non_blank:
        return 0.0
    ok = sum(1 for ln in non_blank if (r := parser.parse(ln, 0)) and r.ts is not None)
    return ok / len(non_blank)


# --- Shared field extraction (used by JSON and logfmt) --------------------
# Real logs disagree on key names; check several and take the first present.
_TS_KEYS = ("ts", "time", "timestamp", "@timestamp")
_LEVEL_KEYS = ("level", "severity", "lvl")
_MSG_KEYS = ("msg", "message", "event")


def _first(data: dict, keys: tuple[str, ...]):
    """Return the value of the first key that's present, else None."""
    for k in keys:
        if k in data:
            return data[k]
    return None


def _parse_ts(value) -> datetime | None:
    """Parse an ISO-8601 timestamp string to datetime, or None if we can't.

    Handles the trailing 'Z' (UTC) that datetime.fromisoformat rejects on
    older Pythons, and shrugs off non-string / malformed values (F4)."""
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _extract(data: dict) -> tuple[datetime | None, str | None, str | None]:
    """From a parsed record dict, pull (timestamp, level, message)."""
    ts = _parse_ts(_first(data, _TS_KEYS))
    level = _first(data, _LEVEL_KEYS)
    message = _first(data, _MSG_KEYS)
    return ts, (str(level) if level is not None else None), message


# --- Plaintext (HDFS + friends) -------------------------------------------
# This one is DONE — it's your existing read_hdfs logic, now behind the Parser
# interface. Use it as the worked example for the two you write below.

class PlaintextParser:
    name = "plaintext-hdfs"
    # 081109 203615 148 INFO dfs.DataNode$PacketResponder: Received block ...
    PATTERN = re.compile(r"^(\d{6}) (\d{6}) \d+ (\w+) (.*)$")

    def parse(self, line: str, lineno: int) -> LogRecord | None:
        line = line.rstrip("\n")
        m = self.PATTERN.match(line)
        if not m:
            # F4: not a fatal error — hand back a record with no timestamp so
            # the line still flows through and gets counted.
            return LogRecord(ts=None, level=None, message=line, raw=line, lineno=lineno)
        date, time, level, message = m.groups()
        ts = datetime.strptime(date + time, "%y%m%d%H%M%S")
        return LogRecord(ts=ts, level=level, message=message, raw=line, lineno=lineno)

    def confidence(self, sample: Sequence[str]) -> float:
        return _confidence_from_parse(self, sample)


# --- JSON lines -----------------------------------------------------------

class JsonParser:
    name = "json"

    def parse(self, line: str, lineno: int) -> LogRecord | None:
        """YOUR TASK — parse one JSON-lines record.

        Steps to work through:
          1. `line.strip()` — if it doesn't start with '{', it's not JSON; return None.
          2. `json.loads(line)` inside try/except — on failure return None (F4:
             a broken JSON line shouldn't kill the run).
          3. From the resulting dict, pull the fields into a LogRecord:
               - timestamp: real logs use varied keys — check "ts", "time",
                 "timestamp", "@timestamp". Which are present? Parse the first
                 one you find. (ISO 8601 strings: `datetime.fromisoformat` —
                 watch the trailing 'Z', which older Python can't parse.)
               - level:   keys like "level", "severity", "lvl".
               - message: keys like "msg", "message", "event".
          4. `raw` = the original line; `message` = the extracted message (or the
             whole line if there's no message field).

        Design question to answer in code: what if the JSON is valid but has no
        timestamp field? (Hint: ts=None is allowed — same F4 spirit.)
        """
        # .startswith is empty-string-safe; string[0] would IndexError on "".
        # A JSON *object* always starts with '{' — anything else isn't a record.
        if not line.strip().startswith("{"):
            return None
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            return None  # F4: a broken JSON line must not kill the run
        # Your catch: json.loads can return a list/number/str for valid JSON
        # like "[1,2]" or "42". We only want objects.
        if not isinstance(data, dict):
            return None

        ts, level, message = _extract(data)
        # No message field? Fall back to the whole raw line so nothing is blank.
        return LogRecord(
            ts=ts,
            level=level,
            message=message if message is not None else line,
            raw=line,
            lineno=lineno,
        )

    def confidence(self, sample: Sequence[str]) -> float:
        return _confidence_from_parse(self, sample)


# --- logfmt (key=value) ---------------------------------------------------

class LogfmtParser:
    name = "logfmt"
    # logfmt looks like:  ts=2026-07-21T10:00:00Z level=info msg="disk full" host=db1
    KV = re.compile(r'(\w+)=("[^"]*"|\S+)')

    def parse(self, line: str, lineno: int) -> LogRecord | None:
        """YOUR TASK — parse one logfmt line into a LogRecord.

        Steps:
          1. Use `self.KV.findall(line)` -> list of (key, value) pairs. If you
             get fewer than ~2 pairs, this probably isn't logfmt; return None.
          2. Build a dict from the pairs. Strip surrounding quotes from values
             (the regex keeps the quotes on quoted values).
          3. Same field extraction as JSON: ts/time/timestamp, level, msg/message.
          4. Return the LogRecord (raw = original line).

        Think about: logfmt and a plaintext line with one 'foo=bar' in it could
        both match weakly. Your confidence() over a real sample is what breaks
        the tie — a true logfmt file scores high, an accidental match scores low.
        """
        raise NotImplementedError("implement LogfmtParser.parse")

    def confidence(self, sample: Sequence[str]) -> float:
        return _confidence_from_parse(self, sample)


# Registry consumed by detect.py. Order matters only as a tie-break:
# more-structured formats first (JSON > logfmt > plaintext).
PARSERS: list[Parser] = [JsonParser(), LogfmtParser(), PlaintextParser()]
