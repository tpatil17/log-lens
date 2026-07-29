"""Tests for the evaluation harness. The metric math is verified on toy data
with hand-computed answers; the injection eval is checked end to end."""

from loglens.eval import (
    injection_eval,
    load_labels,
    prf,
    score_blocks,
    score_blocks_from_matrix,
)

# ------------------------------------------------------------- metrics ----

def test_prf_perfect():
    labels = {"a": True, "b": False, "c": True}
    preds = {"a": True, "b": False, "c": True}
    m = prf(preds, labels)
    assert m.precision == 1.0 and m.recall == 1.0 and m.f1 == 1.0


def test_prf_hand_computed():
    # actual anomalies: a, b, c, d. predicted: a, b, e.
    labels = {"a": True, "b": True, "c": True, "d": True, "e": False}
    preds = {"a": True, "b": True, "c": False, "d": False, "e": True}
    m = prf(preds, labels)
    # tp=2 (a,b), fp=1 (e), fn=2 (c,d)
    assert (m.tp, m.fp, m.fn) == (2, 1, 2)
    assert m.precision == 2 / 3          # 2/(2+1)
    assert m.recall == 0.5               # 2/(2+2)
    assert round(m.f1, 4) == round(2 * (2 / 3) * 0.5 / (2 / 3 + 0.5), 4)


def test_prf_no_positives_predicted():
    labels = {"a": True, "b": False}
    preds = {"a": False, "b": False}
    m = prf(preds, labels)
    assert m.precision == 0.0 and m.recall == 0.0 and m.f1 == 0.0


# -------------------------------------------------------------- labels ----

def test_load_labels(tmp_path):
    p = tmp_path / "labels.csv"
    p.write_text("BlockId,Label\nblk_1,Normal\nblk_2,Anomaly\nblk_3,Normal\n")
    labels = load_labels(p)
    assert labels == {"blk_1": False, "blk_2": True, "blk_3": False}


def test_load_labels_no_header(tmp_path):
    p = tmp_path / "labels.csv"
    p.write_text("blk_1,Normal\nblk_2,Anomaly\n")
    labels = load_labels(p)
    assert labels["blk_2"] is True and labels["blk_1"] is False


# ------------------------------------------------------- block scoring ----

def test_score_blocks_flags_the_outlier():
    from loglens.models import LogRecord

    def rec(msg, blk):
        raw = f"{msg} {blk}"
        return LogRecord(ts=None, level=None, message=msg, raw=raw, lineno=0)

    # Two normal blocks with one common template; one block repeats a template
    # many times -> should score highest. (Block ids must be numeric to match
    # BLOCK_RE, exactly like real HDFS block ids.)
    pairs = []
    pairs += [(rec("normal", "blk_1"), 1)]
    pairs += [(rec("normal", "blk_2"), 1)]
    pairs += [(rec("weird", "blk_3"), 2) for _ in range(20)]
    scores = score_blocks(pairs)
    assert scores["blk_3"] == max(scores.values())
    assert scores["blk_3"] > scores["blk_1"]


# ---------------------------------------------------------- injection ----

def test_score_blocks_from_matrix(tmp_path):
    # A rare event type (E2, in only one block) should make that block score
    # highest under presence surprise.
    p = tmp_path / "matrix.csv"
    p.write_text(
        "BlockId,Label,Type,E1,E2\n"
        "blk_1,Success,,5,0\n"
        "blk_2,Success,,3,0\n"
        "blk_3,Fail,,1,1\n"      # only block with the rare E2
    )
    scores, labels = score_blocks_from_matrix(p)
    assert labels == {"blk_1": False, "blk_2": False, "blk_3": True}
    assert scores["blk_3"] == max(scores.values())


def test_injection_eval_detects_large_bursts():
    rows = injection_eval("tests/data/HDFS_2k.log", sizes=(3, 40), k=3)
    by_size = {size: (rank, detected) for size, rank, detected in rows}
    # A big burst (40) must be detected within top-3.
    assert by_size[40][1] is True
