from dataclasses import dataclass
from datetime import datetime


@dataclass
class LogRecord:
    ts: datetime | None
    level: str | None
    message: str   # content only, no timestamp/level prefix
    raw: str       # original line, untouched
    lineno: int


