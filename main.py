from loglens.ingest import read_hdfs
from loglens.mining import mine
from loglens.windowing import diff
from tests.synthetic import inject_burst

records = inject_burst(read_hdfs("tests/data/HDFS_2k.log"), count=30)
pairs = list(mine(records))
mid = len(pairs) // 2
ranked = diff(pairs[:mid], pairs[mid:])
for a in ranked[:5]:
    print(a.samples)