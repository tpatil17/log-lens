from collections.abc import Iterable, Iterator
from pathlib import Path

from drain3 import TemplateMiner
from drain3.template_miner_config import TemplateMinerConfig

from loglens.models import LogRecord

INI_PATH = Path(__file__).parent / "drain3.ini"


def make_miner() -> TemplateMiner:
    """Build a TemplateMiner with masking loaded from drain3.ini.

    Exposed so callers that stream (e.g. `watch`) can keep ONE miner alive
    across many batches, so template ids stay stable over time."""
    config = TemplateMinerConfig()
    config.load(str(INI_PATH))
    return TemplateMiner(config=config)


def mine(records: Iterable[LogRecord], miner: TemplateMiner | None = None
         ) -> Iterator[tuple[LogRecord, int]]:
    """Assign each record a stable template id via Drain3.

    Pass an existing `miner` to share template ids across calls; otherwise a
    fresh one is created (the batch case)."""
    miner = miner or make_miner()
    for log_record in records:
        result = miner.add_log_message(log_record.message)
        yield (log_record, result["cluster_id"])
