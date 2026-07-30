"""Per-format parsers. Every parser exposes the SAME two methods so detection
can treat them interchangeably (this uniform interface is what makes
sniff-and-vote possible):

    parse(line, lineno) -> LogRecord | None      # None = "this line isn't mine"
    confidence(sample)  -> float                 # 0..1 = fraction I can parse

Add a new format later => add one class here, register it in PARSERS, and
nothing else in the codebase changes.
"""

import json
import re
from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

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
# Matches the HDFS line format; non-matching lines still return a raw record
# (ts=None) so nothing is ever dropped (F4).

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
        """Parse one JSON-lines record into a LogRecord, or None if not JSON.

        Only JSON *objects* count (valid JSON like "[1,2]" or "42" is rejected);
        broken or empty lines return None (F4). Timestamp/level/message are
        pulled via the shared key hunt; a record with no timestamp is allowed
        (ts=None).
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
        """Parse one logfmt line into a LogRecord, or None if not logfmt.

        Extracts key=value pairs; fewer than two pairs is treated as not logfmt
        (returns None). Quoted values are unquoted, then timestamp/level/message
        are pulled via the shared key hunt.
        """
        pairs = self.KV.findall(line)
        # Fewer than two key=value pairs => almost certainly not logfmt.
        if len(pairs) < 2:
            return None
        data = {k: v.strip('"') for k, v in pairs}
        ts, level, message = _extract(data)
        return LogRecord(
            ts=ts,
            level=level,
            message=message if message is not None else line,
            raw=line,
            lineno=lineno,
        )

    def confidence(self, sample: Sequence[str]) -> float:
        return _confidence_from_parse(self, sample)


# --- plaintext with a leading/embedded timestamp -------------------------
# Real-world plaintext logs: nginx/Apache access, syslog, ISO-8601 app logs.
# Each is a thin subclass — a regex that captures the timestamp + the rest, plus
# how to turn that timestamp string into a datetime.

_LEVEL_RE = re.compile(r"\b(TRACE|DEBUG|INFO|WARN|WARNING|ERROR|FATAL|CRITICAL)\b")


def _find_level(text: str) -> str | None:
    m = _LEVEL_RE.search(text)
    return m.group(1) if m else None


class _TimestampParser:
    """Base for regex-with-timestamp plaintext formats. PATTERN must have named
    groups `ts` and `rest`; `_ts` turns the raw timestamp string into a datetime."""

    name = "timestamp"
    PATTERN: re.Pattern

    def _ts(self, raw: str) -> datetime | None:  # overridden per format
        raise NotImplementedError

    def parse(self, line: str, lineno: int) -> LogRecord | None:
        m = self.PATTERN.match(line)
        if not m:
            return None  # not my format
        rest = m.group("rest")
        return LogRecord(
            ts=self._ts(m.group("ts")),
            level=_find_level(rest),
            message=rest,
            raw=line,
            lineno=lineno,
        )

    def confidence(self, sample: Sequence[str]) -> float:
        return _confidence_from_parse(self, sample)


class IsoParser(_TimestampParser):
    name = "iso"
    # 2026-07-28T10:00:00Z ... / 2026-07-28 10:00:00,123 ...
    PATTERN = re.compile(
        r"^(?P<ts>\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?"
        r"(?:Z|[+-]\d{2}:?\d{2})?)\s+(?P<rest>.*)$"
    )

    def _ts(self, raw: str) -> datetime | None:
        try:
            return datetime.fromisoformat(raw.replace(",", ".").replace("Z", "+00:00"))
        except ValueError:
            return None


class SyslogParser(_TimestampParser):
    name = "syslog"
    # Oct 10 13:55:36 host process[pid]: message   (RFC3164 — no year)
    PATTERN = re.compile(
        r"^(?P<ts>[A-Z][a-z]{2}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+\S+\s+(?P<rest>.*)$"
    )

    def _ts(self, raw: str) -> datetime | None:
        try:
            # RFC3164 omits the year; stamp the current one.
            return datetime.strptime(raw, "%b %d %H:%M:%S").replace(year=datetime.now().year)
        except ValueError:
            return None


class AccessLogParser(_TimestampParser):
    name = "nginx"
    # 127.0.0.1 - - [10/Oct/2000:13:55:36 -0700] "GET / HTTP/1.0" 200 2326 ...
    PATTERN = re.compile(r'^\S+ \S+ \S+ \[(?P<ts>[^\]]+)\] (?P<rest>.*)$')

    def _ts(self, raw: str) -> datetime | None:
        try:
            return datetime.strptime(raw, "%d/%b/%Y:%H:%M:%S %z")
        except ValueError:
            return None


# Registry consumed by detect.py. Order is only a tie-break: more-structured
# formats first (JSON > logfmt), then plaintext families (shapes are distinct).
PARSERS: list[Parser] = [
    JsonParser(),
    LogfmtParser(),
    AccessLogParser(),
    SyslogParser(),
    IsoParser(),
    PlaintextParser(),
]
