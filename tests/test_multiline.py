"""Unit tests for multiline merging (stack-trace folding)."""

from loglens.multiline import merge

STACK_TRACE = [
    "2026-07-21 10:00:00 ERROR NullPointerException",
    "\tat com.foo.Bar.baz(Bar.java:42)",
    "\tat com.foo.Main.main(Main.java:10)",
    "Caused by: java.lang.IllegalStateException",
    "\t... 3 more",
]


def test_stack_trace_collapses_to_one_record():
    # Five physical lines, one logical record.
    out = list(merge(iter(STACK_TRACE)))
    assert len(out) == 1
    assert out[0].startswith("2026-07-21 10:00:00 ERROR")
    assert "at com.foo.Bar.baz" in out[0]
    assert "Caused by:" in out[0]


def test_plain_lines_pass_through_unchanged():
    lines = ["line one", "line two", "line three"]
    assert list(merge(iter(lines))) == lines


def test_final_record_is_flushed():
    # The classic bug: dropping the last buffered record. A trace at EOF must
    # still be yielded.
    lines = ["parent", "\tcontinuation at end of file"]
    out = list(merge(iter(lines)))
    assert len(out) == 1
    assert "continuation at end of file" in out[0]


def test_two_traces_stay_separate():
    lines = [
        "ERROR first",
        "\tat a.b(C.java:1)",
        "ERROR second",
        "\tat d.e(F.java:2)",
    ]
    out = list(merge(iter(lines)))
    assert len(out) == 2
    assert out[0].startswith("ERROR first")
    assert out[1].startswith("ERROR second")


def test_orphan_continuation_becomes_its_own_record():
    # File starts mid-trace (no parent). Must not crash; the orphan line
    # becomes a standalone record rather than being lost.
    lines = ["\tat orphan.frame(X.java:1)", "ERROR real record"]
    out = list(merge(iter(lines)))
    assert out[0].startswith("\tat orphan.frame")
    assert out[1] == "ERROR real record"


def test_empty_input_yields_nothing():
    assert list(merge(iter([]))) == []
