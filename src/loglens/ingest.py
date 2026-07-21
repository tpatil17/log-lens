import re
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

from .models import LogRecord

# 081109 203615 148 INFO dfs.DataNode$PacketResponder: Received block ...
HDFS_PATTERN = re.compile(r"^(\d{6}) (\d{6}) \d+ (\w+) (.*)$")


def read_hdfs(path: str | Path) -> Iterator[LogRecord]:
    """Yield LogRecords from an HDFS-format log file, one line at a time."""
    with open(path, encoding="utf-8", errors="replace") as f:
        for lineno, line in enumerate(f, start=1):
            line = line.rstrip("\n")
            m = HDFS_PATTERN.match(line)
            if m:
                date, time, level, message = m.groups()
                ts = datetime.strptime(date + time, "%y%m%d%H%M%S")
                yield LogRecord(ts=ts, level=level, message=message, raw=line, lineno=lineno)
            else:
                # F4: never fatal — unparsed lines still flow through
                yield LogRecord(ts=None, level=None, message=line, raw=line, lineno=lineno)