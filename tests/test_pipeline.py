# tests/test_pipeline.py
from loglens.ingest import read_hdfs
from loglens.mining import mine
from loglens.windowing import diff
from tests.synthetic import inject_burst, BURST_MESSAGE

def test_injected_burst_ranks_top_3():
    records = inject_burst(read_hdfs("tests/data/HDFS_2k.log"), count=25)
    pairs = list(mine(records))
    mid = len(pairs) // 2
    ranked = diff(pairs[:mid], pairs[mid:])

    top3 = ranked[:3]
    assert any("FATAL disk failure" in s for a in top3 for s in a.samples), \
        f"burst not in top 3: {[(a.kind, a.samples[:1]) for a in top3]}"