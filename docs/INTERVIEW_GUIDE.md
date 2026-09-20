# LogLens — Technical Walkthrough & Interview Flow

A study guide for talking about this project with confidence. Read it top to
bottom once; each section builds on the last. The goal: you can (1) pitch it in
30 seconds, (2) draw the pipeline from memory, and (3) defend every decision with
its tradeoff. Decisions — not features — are what interviewers probe.

---

## 0. The 30-second pitch (memorize this)

> "LogLens is a local-first CLI that diffs your logs across a deploy to find what
> broke. It mines raw log lines into templates, ranks anomalies by *statistical
> surprise* — what's new, spiking, or vanished — and can optionally explain the
> top findings with an LLM that only ever sees a tiny digest, so your raw logs
> never leave your machine. It hits 0.85 F1 unsupervised on the standard HDFS
> benchmark."

The one sentence that captures the whole design: **statistics detect, the LLM
explains.** If you remember nothing else, remember that.

---

## 1. Why that thesis matters (the core insight)

Everyone's first instinct is "throw the logs at an LLM." That's slow, expensive,
leaks private data, and is non-reproducible. LogLens inverts it: a cheap,
deterministic statistical layer does the *detection* and compresses millions of
lines into a ~2 KB digest of the top anomalies. The LLM only *explains* that
digest. This buys three things at once — say all three in an interview:

- **Cost:** the model sees ~2 KB, not megabytes.
- **Privacy:** raw logs stay local; only the digest can leave, and only if you opt in.
- **Reproducibility:** detection is deterministic; the LLM is a pure add-on.

Framed for an AI-engineering interview: **the statistical layer is context
engineering for the LLM.** You're not dumping data into a model — you're feeding
it a curated, minimal, high-signal summary. That's the senior instinct.

---

## 2. The pipeline (draw this on the whiteboard)

```
source ──► ingest ──► mine ──► score / diff ──► (digest ──► LLM explain)
(file,     (LogRecord  (Drain3   (baseline vs      (~2KB)     (optional,
 stdin,     stream)     template   window: NEW /                OpenAI)
 gzip)                  ids)       SPIKE / VANISHED)
```

The key idea is that **every arrow is a typed contract**, and each stage only
knows the contract, never the stage before it:

- `ingest → mine`: `Iterator[LogRecord]`  (ts, level, message, raw, lineno)
- `mine → score`: `(LogRecord, template_id)` pairs
- `score → report`: `list[Anomaly]` (kind, score, counts, samples)
- `score → LLM`: a compact `Digest`

Why this matters (this is *the* architecture talking point): because stages depend
on abstractions, not each other, I rewrote the entire ingestion layer in M3
(adding JSON, nginx, syslog, gzip, stdin) **without touching mining, scoring, or
the CLI.** That's dependency inversion, and it's the payoff of designing the
`LogRecord` contract up front.

---

## 3. Stage by stage — what it does and the decision behind it

**Ingest (`ingest.py`, `sources.py`, `parsers.py`, `detect.py`, `multiline.py`)**
Turns any source into `LogRecord`s. Decisions:
- *Streaming generators, not lists* — memory is O(templates), not O(lines), so the
  same code handles the 2 KB sample and a 1.5 GB file.
- *Sniff-and-vote format detection* — read ~50 lines, ask each parser "what
  fraction can you parse?", pick the winner; fall back to raw plaintext below a
  confidence threshold. Adding a format = adding one Parser class. (Tradeoff vs
  "try parsers in priority order": voting is more robust to messy/mixed files,
  slightly more code.)
- *Never fatal (F4)* — an unparseable line becomes a `ts=None` record, never a crash.

**Mine (`mining.py`)** Wraps Drain3, which clusters log lines into templates
(recovering the `printf` statement behind `Received block blk_123` and
`Received block blk_456` → one template). Decision: *masking* — normalize block
IDs / IPs / numbers to wildcards *before* clustering, or you get hundreds of junk
templates instead of ~17. Validated against a reference count (acceptance
criterion A2).

**Score (`scoring.py`, `windowing.py`)** The intellectual core — see §5.

**Digest + LLM (`digest.py`, `summarize.py`)** Compress top-k anomalies into a
small structured object (deterministic, stdlib-only), then optionally send *only
that* to OpenAI with a prompt constrained to explain the digest and label causes
as *hypotheses*, never invented facts. Graceful without a key.

**CLI (`cli.py`) + pipeline glue (`pipeline.py`)** The CLI is a *thin adapter* —
parse args, call the pipeline, format output. Zero logic. Why: logic in a CLI
handler is nearly untestable (subprocess + stdout parsing); logic in a function is
a plain unit test. This is why the test suite is clean.

---

## 4. The four commands (and when each is right)

- `diff before.log after.log` — the flagship. Compare two logs (pre/post deploy).
  Sidesteps the "where's the baseline?" problem entirely.
- `analyze one.log` — split one file at its midpoint, diff halves. Convenient but
  assumes the first half is "normal" (its weakness — know this).
- `inspect one.log` — "what format is this and what's in it?" before analyzing.
- `watch one.log` — tail live, freeze the launch state as baseline, alert on the
  rolling window. Best started on a healthy log (e.g., right after a deploy).

---

## 5. The scoring deep-dive (know this cold — it's the heart)

Each template gets a **surprise score**: how improbable its window count is, given
its baseline rate, under a Poisson model.

- **λ (lambda)** = expected count = baseline count (+ a small smoothing constant α).
- A **NEW/SPIKE** (more than expected) is scored on the **upper tail**:
  `-ln P(X ≥ observed)`.
- A **VANISHED/drop** (fewer than expected) is scored on the **lower tail**:
  `-ln P(X ≤ observed)`. (Two-sided; added later — see the war story in §7.)
- **Smoothing (α = 0.5):** a NEW template has baseline 0, and `-ln P(X ≥ k | λ=0)`
  is infinite. α nudges λ up so "unseen" means *very unlikely*, not *impossible*.
  Small α = twitchy/false-positives; large α = conservative/misses small bursts.
- **Numerical stability:** compute in log space (`scipy` `logsf`/`logcdf`) — a real
  burst has a tail probability like 1e-30 that would underflow to 0 and make every
  big burst tie at infinity.

**Why surprise beats raw counts** (a great talking point): raw count-delta favors
templates that are already loud (135→176 looks big). Surprise measures deviation
*relative to a template's own expected variability* (√λ), so a rare 0→8 error
outranks a common template getting 20% louder. I proved this empirically — an
injected burst ranked #4 under raw delta (missed) and #1 under surprise.

---

## 6. The recurring theme: size normalization (your best cross-cutting story)

The same lesson bit three times, which makes it a strong "what did you learn"
answer: **you can't compare raw counts from differently-sized samples.**

1. **Block eval:** scoring blocks by raw *count* surprise gave F1 0.17 — big normal
   blocks looked anomalous just for being big.
2. **watch:** the baseline is the whole startup file, the window is the last N
   lines — a sparse-but-normal template missing from a short window false-alarmed
   as VANISHED.
3. **diff:** before/after captures can be different lengths.

The fix everywhere: **normalize to a rate** — scale the baseline to the window's
size before scoring (expected = baseline_rate × window_size). Recognizing the same
root cause across three surfaces is exactly the kind of pattern-recognition
interviewers want to hear.

---

## 7. War stories (bugs make the best interview answers)

Interviewers love "tell me about a hard bug." You have real ones:

- **The masking that silently didn't fire.** `drain3.ini` was loaded into a config
  object that was then overwritten by a fresh empty one on the next line — so
  masking never applied. Tests passed anyway because Drain3 wildcards block IDs on
  its own for the small sample. Lesson: *test the behavior (a masked template),
  not just a count.*
- **Count-surprise vs presence-surprise (F1 0.17 → 0.85).** For block-level HDFS
  detection, raw counts were confounded by block size. The fix kept the "surprise
  vs baseline" thesis but changed the *observable* from count (Poisson) to template
  *presence* (`-log P(present)`, i.e. Bernoulli/IDF surprise) — because HDFS
  anomalies are about *which* rare events occur, not how many. One conceptual
  change, F1 from 0.17 to 0.85.
- **The one-sided score (VANISHED).** The upper-tail score returned 0 for a
  vanished template (`P(X ≥ 0) = 1`), so disappearances couldn't rank. Fixed by
  adding the lower tail (CDF). Bonus: the tests that "failed" afterward weren't
  bugs — they *documented the old limitation*, so fixing the feature meant updating
  the tests on purpose.
- **The CI-only failure.** CI was red but tests passed locally. Root cause: a
  `.gitignore` rule `data/` (no leading slash) matched `tests/data/` too, so the
  test fixtures were never committed — CI checked out a repo with no test data.
  Fix: anchor it to `/data/`. Lesson: reproduce CI in a clean room; a passing local
  suite doesn't mean a passing CI.
- **Silent line-dropping (F4).** When the multiline merger folded a stack trace
  onto a JSON line, the merged blob no longer parsed as JSON and the record was
  *dropped*. Fixed so a rejected line is kept as a raw `ts=None` record. A test
  caught it — a good "why we write tests" story.

---

## 8. Evaluation — how you know it works (and its honest limits)

Two evals sharing one precision/recall/F1 core:
- **Injection eval** (no external data, runs in CI): inject synthetic bursts of
  varying size, measure detection rank. Reproducible everywhere.
- **Block-level eval** (real labels): full HDFS_v1 — 575K blocks, 16.8K anomalies —
  scored by presence-surprise: **P 0.87 / R 0.83 / F1 0.85**, unsupervised.

Be honest about the caveat (this *builds* credibility): the threshold is chosen
in-sample (the F1-optimal operating point), so it characterizes the detector's best
achievable tradeoff; a held-out train/test split would report a stricter number.

---

## 9. Limitations & what's next (maturity signals)

- **Access logs:** Drain3 masks the URL path and status code, so different
  endpoints collapse into one template — endpoint-level regressions (a new 500 on
  `/checkout`) don't surface. It shines on *distinct log messages*, not structured
  access-log fields. Next: an access-log mode keyed on method+path+status.
- **`analyze`'s midpoint split** assumes the first half is normal; real work wants
  time-based windows (`--baseline 24h --window 15m`) — that's why `diff` is the
  flagship.
- **watch** can trip spurious VANISHED alerts when a burst crowds the window.
- **Anomaly type:** it catches template *frequency* changes, not latency or
  value-based anomalies. Know the boundary.

---

## 10. Likely interview questions → your answer in one line

- *"What is it?"* → the §0 pitch.
- *"Why not just use an LLM?"* → cost, privacy, reproducibility (§1).
- *"How does the anomaly detection actually work?"* → template mining + Poisson
  surprise; surprise beats raw counts because it's relative to √λ (§5).
- *"How do you know it works?"* → 0.85 F1 on HDFS_v1, plus a reproducible injection
  eval; and the in-sample caveat (§8).
- *"Hardest bug / biggest lesson?"* → count vs presence surprise, or the size-
  normalization theme (§6, §7).
- *"What would you do differently / next?"* → §9 (access-log mode, time windows).
- *"How is it tested?"* → unit tests per stage + an acceptance test that proves the
  core hypothesis, property-based scoring tests, CI on 3.10/3.12.
- *"Walk me through the architecture."* → draw §2, emphasize typed contracts and
  that M3 rewrote ingestion without touching downstream.

---

## 11. Five-minute pre-interview refresher

1. Thesis: *statistics detect, the LLM explains.*
2. Pipeline: source → ingest → mine → score → (digest → LLM), typed contracts between each.
3. Scoring: Poisson surprise, two-sided, log-space, smoothed; beats raw counts because it's relative to √λ.
4. Result: 0.85 F1 unsupervised on HDFS_v1 (in-sample threshold — say so).
5. Best story: count-surprise → presence-surprise, or size normalization biting three times.
6. Honest limitation: access-log endpoint masking; midpoint split → `diff` is the flagship.
