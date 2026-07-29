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

Run the test suite (includes the A4 acceptance test) and the linter:

```bash
make test    # pytest
make lint    # ruff
```

## Usage

```bash
loglens analyze app.log            # rank what's new/spiking/vanished
loglens analyze app.log --explain  # + plain-English explanation (OpenAI)
loglens inspect app.log            # detect format + preview (before analyzing)
```

`analyze` and `inspect` auto-detect the log format (JSON, logfmt, plaintext),
handle gzip and stdin, and fold multiline stack traces.

`--explain` is opt-in (tokens are spent only when you ask). It sends a compact
~1–2 KB digest of the *top anomalies only* — never your raw logs — to OpenAI, and
the model is constrained to explain that digest and label causes as hypotheses.
Needs `OPENAI_API_KEY`; without it the report prints as normal and the step is
skipped.

## Evaluation

Two evaluations share one precision/recall/F1 core (`loglens.eval`):

**Injection eval** — needs no external data, so it runs in CI. It injects
synthetic bursts of varying size and reports detection rank:

```
$ make eval
 size   rank   detected@3
    3      3   True
    5      1   True
   10      1   True
   40      1   True
```

So the detector reliably surfaces bursts of ≥5 at rank #1, and even a burst of 3
lands in the top 3.

**Block-level eval** — against the real HDFS_v1 labels (575,061 blocks, 16,838
anomalies). Each block is scored by the surprise of its rarest present event type
(`-log P(template present)` — the same "surprise vs baseline" idea, using template
*presence* as the observable), then compared to the ground-truth labels:

| metric | score |
|---|---|
| precision | 0.87 |
| recall | 0.83 |
| **F1** | **0.85** |

An unsupervised, untrained detector reaching 0.85 F1 on the standard HDFS
benchmark. Reproduce from loghub's precomputed occurrence matrix:

```bash
make eval-matrix MATRIX=data/HDFS_v1/preprocessed/Event_occurrence_matrix.csv
```

(Full labeled HDFS_v1 supplied locally; the ~1.5 GB dataset isn't committed.)

## Project layout

```
src/loglens/
  models.py      # LogRecord — the universal typed contract between stages
  sources.py     # open_lines(): file / stdin / gzip → lines (streaming)
  multiline.py   # merge(): fold stack traces into one logical record
  parsers.py     # JSON / logfmt / plaintext parsers (uniform interface)
  detect.py      # sniff-and-vote format detection
  ingest.py      # read(): auto-detect + parse → Iterator[LogRecord]
  mining.py      # mine(): records → (record, template_id) via Drain3 + masking
  scoring.py     # poisson_surprise(): the statistical surprise metric
  windowing.py   # diff(): baseline vs window → ranked list[Anomaly]
  digest.py      # compress top-k anomalies → compact structured digest
  summarize.py   # digest → OpenAI → English explanation (optional)
  eval.py        # precision/recall harness (injection + block-level)
  cli.py         # loglens analyze / inspect (thin typer/rich adapters)
  drain3.ini     # Drain3 masking config (block IDs, etc.)
tests/           # unit + acceptance tests, HDFS_2k sample data
docs/DESIGN.md   # full design document, decisions, milestones, status
```

## Roadmap

Done: end-to-end pipeline, Poisson scoring, `analyze`/`inspect` CLI, multi-format
ingest, unit + acceptance tests with CI, the evaluation harness (HDFS F1 0.85), and
the optional LLM explanation layer (`--explain`). Next:

1. **JSON output** (`--json`) for scripting.
2. **Lower-tail scoring** so vanished logs can rank (currently one-sided).
3. **Packaging** — PyPI, Docker, a `watch` mode, demo GIF.

## License

MIT
