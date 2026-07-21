# LogLens — Design Document

| | |
|---|---|
| **Author** | Tanishq Patil |
| **Status** | Active — M1 nearly complete, M2 detection proven |
| **Created** | 2026-07-15 |
| **Updated** | 2026-07-21 |
| **Version** | 0.2 |

---

## 0. Current Status (2026-07-21)

The statistical **detection** pipeline is built and its core hypothesis is proven: an
injected error burst is ranked #1 by Poisson surprise, and that result is locked behind a
passing acceptance test.

**Built and verified**

| Module | Status | Notes |
|---|---|---|
| `models.LogRecord` | ✅ | five-field contract: `ts, level, message, raw, lineno` |
| `ingest.read_hdfs` | ✅ | streaming generator; 2000/2000 sample lines parse with a timestamp (**A3 met**) |
| `mining.mine` | ✅ | Drain3 wrapper + `drain3.ini` masking; 17 templates on the 2k sample, within range of the reference CSV (**A2 met**) |
| `windowing.diff` | ✅ | record-count midpoint split; NEW/SPIKE/VANISHED; carries `samples`; ranks by score |
| `scoring.poisson_surprise` | ✅ | `-ln P(X ≥ k \| λ = base + α)`, α = 0.5, log-space via `scipy` |
| `tests/synthetic.py` | ✅ | reusable burst-injection helper |
| `tests/test_pipeline.py` | ✅ | **A4** as an automated acceptance test — burst ranks top-3 (in fact #1) |

**A4 result:** under raw count-delta the injected burst (0→25) ranked #4 (fail); under Poisson
surprise it ranks **#1, score 75.8** vs 7.6 for the next item. This is the D2/D4 thesis
demonstrated empirically.

**Not yet done (closes M1):**
- **A1** — `loglens analyze <file>` CLI does not exist yet (`cli.py` is next).
- **A5** — only the A4 acceptance test exists; unit tests for `ingest`, `mining`,
  `scoring`, plus a GitHub Actions CI workflow (`ruff` + `pytest`), still to write.

**Next course of action (in order):**
1. `cli.py` — thin `typer` app wiring ingest → mine → split → diff, printing a ranked table with sample lines (satisfies **A1**).
2. Unit tests (`poisson_surprise`, ingest parse-rate, Drain3 count) + GitHub Actions CI (satisfies **A5**, closes M1).
3. M3 robust ingest, then M5 LLM summary layer.

---

## 1. Problem Statement

Production systems emit logs at a rate no human can read — millions of lines per hour.
When an incident occurs, the signal (a new error, a spiking warning, a vanished heartbeat)
is buried in noise that is 99.9% routine. Engineers today either:

- grep reactively, guessing at keywords after users complain, or
- pay for heavyweight observability platforms (Datadog, Splunk) that small teams can't afford, or
- pipe raw logs into an LLM, which is slow, expensive, and leaks sensitive data.

**Gap:** there is no lightweight, local-first tool that answers the question
*"what is different about my logs right now, and what does it mean?"*

## 2. Goals

- **G1.** Given a log source, automatically discover its structure (no format config required).
- **G2.** Detect what is *new*, *spiking*, or *vanished* in a recent window relative to a baseline.
- **G3.** Produce a plain-English explanation with probable causes and suggested next steps.
- **G4.** Run on a laptop against multi-GB files; process ≥50k lines/sec for the statistical path.
- **G5.** Keep raw logs local: only a compact statistical digest (~2 KB) may leave the machine
  for LLM summarization, and the LLM step must be fully optional.
- **G6.** Quantified accuracy: report precision/recall against a labeled public dataset (HDFS_v1).

## 3. Non-Goals

- **NG1.** Not a log storage/search system (no indexing, no query language).
- **NG2.** No deep-learning anomaly models (LSTM/transformer detectors) — frequency statistics
  over mined templates is the deliberate design choice (see §7, D3).
- **NG3.** No distributed deployment, agents, or collectors in v1 — single process, single host.
- **NG4.** Not a replacement for alerting infrastructure (PagerDuty etc.); it can feed one.
- **NG5.** No log *repair* or PII scrubbing beyond template masking.

## 4. Users & Use Cases

- **U1 — SRE/backend dev during an incident:** `loglens analyze app.log --window 15m` →
  ranked list of what changed + English summary, in under a minute.
- **U2 — On-call engineer, passive monitoring:** `loglens watch app.log --slack-webhook …`
  posts a summary when anomaly score crosses a threshold.
- **U3 — Developer triaging an unfamiliar service:** `loglens inspect weird.log` →
  what format is this, what's in it, what's noisy.

## 5. Solution Overview

Pipeline of five deterministic stages plus one optional stochastic stage:

```
 source ──► ingest ──► template mining ──► scoring ──► digest ──► report
 (file,     (LogRecord   (Drain3:            (baseline vs          (terminal/JSON)
  stdin,     stream)      log lines →         window: NEW/              │
  gzip)                   templates)          SPIKE/VANISHED)           ▼
                                                              [optional] LLM summary
                                                              (Claude, ~2KB digest in)
```

**Core insight:** template mining collapses millions of raw lines into a few hundred
templates; frequency statistics over templates find anomalies cheaply and deterministically;
the LLM only ever sees the top-k anomaly digest — it explains, it does not detect.

### Components

| Component | Responsibility | Key tech |
|---|---|---|
| `ingest` | any source → `Iterator[LogRecord]`; format & timestamp auto-detection | stdlib, regex library |
| `mining` | messages → template IDs + counts | drain3 |
| `scoring` | baseline/window split; NEW / SPIKE / VANISHED classification | Poisson z-score |
| `digest` | top-k anomalies → compact structured summary | stdlib |
| `summarize` | digest → English narrative (optional) | anthropic SDK |
| `report` | terminal table / `--json` | rich, typer |

### Contracts (stable interfaces between stages)

- `read(source) -> Iterator[LogRecord]` where `LogRecord(ts, level, message, raw, lineno)`
- `mine(records) -> Iterator[tuple[LogRecord, TemplateId]]`
- `score(counts_baseline, counts_window) -> list[Anomaly]`
- `Anomaly(template, kind: NEW|SPIKE|VANISHED, score, count_baseline, count_window, samples)`

## 6. Requirements

### Functional
- **F1.** Accept file path, `-` (stdin), `.gz`, and directory glob as input.
- **F2.** Auto-detect plaintext timestamp formats, JSON-lines, and logfmt; flags override.
- **F3.** Merge continuation lines (stack traces) into their parent record.
- **F4.** Degrade gracefully: no timestamps → line-count windows; unparseable lines counted, never fatal.
- **F5.** Windowing: `--baseline 24h --window 15m` or two-file mode.
- **F6.** Classify per-template anomalies as NEW, SPIKE (statistically significant), VANISHED.
- **F7.** Output: human-readable terminal report and machine-readable `--json`.
- **F8.** `--no-llm` runs the full pipeline minus summary; missing API key ⇒ same behavior + notice.

### Non-Functional
- **N1.** Streaming throughout — memory O(templates), not O(lines).
- **N2.** Deterministic stages 1–5: same input ⇒ byte-identical JSON output.
- **N3.** ≥90% line-level test coverage on ingest and scoring; CI green on every commit.
- **N4.** Raw log lines never sent over the network except the ≤k sample lines in the digest,
  and only when LLM mode is on (documented prominently).

## 7. Key Design Decisions

- **D1 — Template mining before any statistics** (Drain3, not embeddings/k-means):
  deterministic, fast, interpretable, industry-standard (Datadog Log Patterns does the same).
- **D2 — Stats detect, LLM explains:** the LLM is never the detector. Compresses cost ~1000x,
  keeps detection reproducible, keeps raw data local (G5).
- **D3 — No deep learning:** on HDFS-class data, frequency methods approach DL accuracy at a
  fraction of the complexity; the project optimizes for engineering quality, not model novelty.
- **D4 — Poisson z-score over raw ratios for SPIKE:** raw ratios over-rank rare templates
  (2→20 looks like 10x); a significance test scales properly with expected counts.
- **D5 — `LogRecord` as the universal contract:** downstream stages are format-agnostic;
  adding a new input format touches only `ingest`.

## 8. Milestones & Acceptance Criteria

Delivery is vertical-slice first: a working ugly pipeline, then hardening.

| Milestone | Scope | Acceptance criteria |
|---|---|---|
| **M1 — PoC (Slice 1)** | HDFS-only end-to-end | see §9 |
| **M2 — Scoring (Slice 2)** | Poisson z-scores, NEW/SPIKE/VANISHED | injected incident ranks #1; unit-tested |
| **M3 — Robust ingest (Slice 3)** | auto-detection, JSON/logfmt, multiline, stdin/gzip, fallback | `loglens inspect` correct on ≥5 formats |
| **M4 — Evaluation** | precision/recall vs `anomaly_label.csv` | reproducible `make eval`; README table |
| **M5 — LLM layer** | digest → Claude summary | end-to-end `analyze`; `--no-llm` identical minus summary |
| **M6 — Release** | PyPI, Docker, watch mode, README+GIF | fresh machine: `pip install loglens` → useful report on unseen nginx log in <1 min |

## 9. Phase 1 — Proof of Concept (M1)

**Objective:** prove the core hypothesis — *template mining + window frequency diff surfaces
real anomalies* — on one dataset, end to end, before investing in robustness.

**In scope**
- Naive HDFS ingestion: hardcoded regex `^(\d{6}) (\d{6}) \d+ (\w+) (.*)$`, no multiline/gzip.
- Drain3 mining with basic masking config.
- Midpoint split baseline/window; per-template count delta, sorted.
- `loglens analyze <file>` prints a ranked "what changed" table.

**Out of scope (deliberately):** format detection, statistical significance, LLM, packaging polish.

**Acceptance criteria**
- **A1.** `loglens analyze tests/data/HDFS_2k.log` runs end to end and prints a ranked table.
- **A2.** Drain3 recovers ≈ the loghub reference template count on the 2k sample
  (validated against `HDFS_2k.log_templates.csv`; assert within 2x, not 10x).
- **A3.** ≥99% of sample lines parse with a timestamp; unparseable lines are counted, not fatal.
- **A4.** A synthetic error burst spliced into the window half appears in the top 3 rows.
- **A5.** Unit tests for ingest and the diff logic pass in CI.

**Exit review:** demo A1–A4, then decide whether the template/diff signal is strong enough to
proceed to M2 or whether masking/windowing needs rework first.

## 10. Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Drain3 over-fragments templates (IDs/IPs unmasked) | noisy anomalies | tune masking against reference CSV (A2) |
| HDFS labels are per-block, tool is per-window | eval mismatch | map flagged windows→block ids; document methodology |
| LLM summaries hallucinate causes | user mistrust | prompt constrains to provided digest; label as hypotheses |
| Timestamp detection fails on exotic formats | bad windows | override flags + line-count fallback (F4) |
| Scope creep (dashboards, DL models) | never ships | non-goals §3; milestone gates §8 |

## 11. Open Questions & Decision Log

**Decided**
- **D-a (2026-07-21) — PoC split method:** baseline/window split at the **record-count
  midpoint** (`len(pairs)//2`), not the time midpoint. Rationale: on bursty logs a time
  midpoint can starve one side; a count midpoint keeps both sides comparable and is robust to
  records with `ts=None`. Revisit for real windowing in M3 (`--baseline/--window` durations).
- **D-b (2026-07-21) — smoothing constant α = 0.5:** additive/Jeffreys prior on λ. Keeps
  genuine one-off new lines near the score floor while a burst of ≥5–6 rises to the top;
  avoids the λ=0 → infinite-score trap for NEW templates.

**Open**
- **Q1.** Window/baseline defaults: fixed (24h/15m) or derived from the file's time span?
- **Q2.** VANISHED detection threshold: how regular must a template be to count as a heartbeat?
- **Q2b.** *(new)* Poisson surprise is **one-sided** (upper tail), so VANISHED templates
  (`window_count = 0`) always score 0 and cannot rank. A lower-tail / two-sided score is needed
  before VANISHED is meaningful. Deferred — A4 concerns bursts, not disappearances.
- **Q3.** Digest size vs summary quality trade-off: how many samples per anomaly (2? 5?).
  Currently capped at 3 in `diff()`.
- **Q4.** Streamlit demo in v1 or defer to v1.1?

## 12. References

- LogHub / HDFS_v1 dataset: https://github.com/logpai/loghub
- Drain: He et al., *Drain: An Online Log Parsing Approach with Fixed Depth Tree* (ICWS 2017)
- Xu et al., *Detecting Large-Scale System Problems by Mining Console Logs* (SOSP 2009)
