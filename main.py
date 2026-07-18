from loglens.ingest import read_hdfs
from loglens.mining import mine
from loglens.windowing import diff

pairs = list(mine(read_hdfs("tests/data/HDFS_2k.log")))
mid = len(pairs) // 2
for a in diff(pairs[:mid], pairs[mid:])[:5]:
    print(a)