
from drain3.template_miner_config import TemplateMinerConfig
from drain3 import TemplateMiner
from pathlib import Path
from typing import Iterable, Iterator
from loglens.models import LogRecord

INI_PATH = Path(__file__).parent / "drain3.ini"

def mine(records: Iterable[LogRecord]) -> Iterator[tuple[LogRecord, int]]:

    config = TemplateMinerConfig()
    config.load(str(INI_PATH))       
    config = TemplateMinerConfig()

    template_miner = TemplateMiner(config=config)
    
    
    for log_record in records:
        rs = template_miner.add_log_message(log_record.message)
        
        yield ( log_record, rs["cluster_id"] )
    


  

        