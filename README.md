# LogLens

**Find what's *different* about your logs right now — and, optionally, what it means.**

LogLens is a lightweight, local-first log anomaly analyzer. It mines raw log lines into
templates, compares a recent window against a baseline, and ranks what's **new**, **spiking**,
or **vanished** by statistical surprise — so the signal isn't buried in routine noise. An
optional LLM stage explains the top anomalies in plain English, seeing only a compact digest,
never your raw logs.

> **Core thesis:** *statistics detect, the LLM explains.* Detection is deterministic,
> reproducible, and runs entirely on your machine.

## Status

Early development — the **detection pipeline works end-to-end and its core hypothesis is
proven** by an automated test. The CLI and LLM layers are next. See
[`docs/DESIGN.md`](docs/DESIGN.md) for the full design and current status.

| Stage | State |
|---|---|
| Ingest (HDFS format) | ✅ working |
| Template mining (Drain3 + masking) | ✅ working |
| Windowing + NEW/SPIKE/VANISHED diff | ✅ working |
| Poisson surprise scoring | ✅ working |
| A4 acceptance test (burst ranks #1) | ✅ passing |
| `loglens analyze` CLI | 🔜 next |
| LLM explanation layer | ⏳ planned |

## How it works

```
source ──► ingest ──► template mining ──► scoring ──► digest ──► report
 (file)    (LogRecord   (Drain3:            (baseline vs         (terminal/JSON)
            stream)      lines→templates)    window, Poisson         │
                                             surprise)               ▼
                                                          [optional] LLM summary
                                                          (~2KB digest in, never raw logs)
```

Template mining collapses millions of raw lines into a few hundred templates. Frequency
statistics over those templates find anomalies cheaply and deterministically. Each candidate
is scored by **Poisson surprise** — how improbable its window count is given its baseline rate —
so a rare-but-new error outranks a common template that merely got a bit louder.

## Why Poisson, concretely

On the HDFS 2k sample with a 25-line error burst injected into the window:

| Ranking method | Where the burst lands |
|---|---|
| Raw count delta | #4 — misses it (common templates' normal wobble outranks a real burst) |
| **Poisson surprise** | **#1, score 75.8** (next item: 7.6) |

That gap is the whole point of the project.

## Development

Requires Python ≥ 3.10.

```bash
git clone https://github.com/tpatil17/log-lens
cd log-lens
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

Run the test suite (includes the A4 acceptance test):

```bash
pytest
```

## Project layout

```
src/loglens/
  models.py      # LogRecord — the universal typed contract between stages
  ingest.py      # read_hdfs(): file → Iterator[LogRecord] (streaming)
  mining.py      # mine(): records → (record, template_id) via Drain3 + masking
  scoring.py     # poisson_surprise(): the statistical surprise metric
  windowing.py   # diff(): baseline vs window → ranked list[Anomaly]
  drain3.ini     # Drain3 masking config (block IDs, etc.)
tests/
  synthetic.py       # burst-injection helper for the A4 test
  test_pipeline.py   # A4: injected burst must rank in the top 3
  data/              # HDFS_2k.log + reference templates
docs/
  DESIGN.md      # full design document, decisions, milestones, status
```

## Roadmap

1. **`cli.py`** — `loglens analyze <file>` prints a ranked "what changed" table.
2. **Unit tests + CI** — per-module tests and a GitHub Actions workflow (`ruff` + `pytest`).
3. **Robust ingest** — format auto-detection (JSON, logfmt), multiline, stdin/gzip.
4. **Evaluation** — precision/recall against the labeled HDFS dataset.
5. **LLM layer** — digest → Claude summary, fully optional (`--no-llm`).

## License

MIT
