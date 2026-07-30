"""Phase B: real-world plaintext format parsing (ISO, syslog, nginx).

Small synthetic fixtures — these formats are well-known, so no downloaded data.
"""

from datetime import datetime

from loglens.detect import detect
from loglens.parsers import AccessLogParser, IsoParser, SyslogParser

ISO_LINES = [
    "2026-07-28T10:00:00Z INFO service started",
    "2026-07-28T10:00:01,123 ERROR db connection failed",
    "2026-07-28 10:00:02 WARN retry scheduled",
]
SYSLOG_LINES = [
    "Oct 10 13:55:36 web1 nginx[1123]: upstream timed out",
    "Oct 10 13:55:37 web1 sshd[2231]: accepted password for root",
]
NGINX_LINES = [
    '127.0.0.1 - - [10/Oct/2026:13:55:36 -0700] "GET /api/users HTTP/1.1" 200 2326',
    '10.0.0.2 - - [10/Oct/2026:13:55:37 -0700] "POST /api/pay HTTP/1.1" 500 17',
]


# -------- ISO ----------------------------------------------------------------

def test_iso_parses_timestamp_and_level():
    r = IsoParser().parse(ISO_LINES[0], 1)
    assert isinstance(r.ts, datetime) and r.level == "INFO"
    assert r.message == "INFO service started"


def test_iso_handles_comma_millis_and_space_separator():
    assert IsoParser().parse(ISO_LINES[1], 1).ts is not None   # comma millis
    assert IsoParser().parse(ISO_LINES[2], 1).ts is not None   # space, no TZ


def test_iso_rejects_non_iso():
    assert IsoParser().parse("not a timestamped line", 1) is None


# -------- syslog -------------------------------------------------------------

def test_syslog_parses():
    r = SyslogParser().parse(SYSLOG_LINES[0], 1)
    assert isinstance(r.ts, datetime)
    assert "upstream timed out" in r.message


# -------- nginx / access -----------------------------------------------------

def test_nginx_parses_bracketed_timestamp():
    r = AccessLogParser().parse(NGINX_LINES[1], 1)
    assert isinstance(r.ts, datetime)
    assert "POST /api/pay" in r.message


def test_nginx_rejects_plain_line():
    assert AccessLogParser().parse("just a sentence", 1) is None


# -------- detection votes for the right format -------------------------------

def test_detection_picks_each_format():
    assert detect(ISO_LINES).name == "iso"
    assert detect(SYSLOG_LINES).name == "syslog"
    assert detect(NGINX_LINES).name == "nginx"
