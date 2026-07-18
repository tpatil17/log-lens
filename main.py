from loglens.ingest import read_hdfs
from loglens.mining import mine
pairs = list(mine(read_hdfs("tests/data/HDFS_2k.log")))
print(len(pairs), len({t for _, t in pairs}), "templates")