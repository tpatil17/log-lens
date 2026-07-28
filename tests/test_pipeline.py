# tests/test_pipeline.py
from tests.synthetic import inject_burst

from loglens.ingest import read
from loglens.mining import mine
from loglens.windowing import diff, split_midpoint


def test_injected_burst_ranks_top_3():
    records = inject_burst(read("tests/data/HDFS_2k.log"), count=25)
    pairs = list(mine(records))
    pair1, pair2 = split_midpoint(pairs)
    ranked = diff(pair1, pair2)

    top3 = ranked[:3]
    assert any("FATAL disk failure" in s for a in top3 for s in a.samples), \
        f"burst not in top 3: {[(a.kind, a.samples[:1]) for a in top3]}"