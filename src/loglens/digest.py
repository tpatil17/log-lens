"""Digest stage: compress the top ranked anomalies into a small, structured
object — the ONLY thing the LLM ever sees.

This is the privacy + cost boundary of the whole design (G5): raw logs never
leave the machine; only this ~1-2 KB digest of the top-k anomalies does, and
only when the user opts in with --explain. Deterministic and stdlib-only, so it
stays testable and byte-identical for the same input (N2).
"""

import json
from dataclasses import dataclass

from loglens.windowing import Anomaly


@dataclass
class Digest:
    source: str
    anomaly_count: int
    top: list[dict]

    def to_json(self) -> str:
        """Compact JSON — what gets sent to the model."""
        return json.dumps(
            {"source": self.source, "anomaly_count": self.anomaly_count, "top": self.top},
            separators=(",", ":"),
        )


def build_digest(
    anomalies: list[Anomaly],
    source: str = "",
    top_k: int = 5,
    max_samples: int = 2,
    sample_chars: int = 200,
) -> Digest:
    """Reduce ranked anomalies to a compact digest of the top-k.

    Keeps only what the model needs to explain each anomaly: its kind, score,
    baseline/window counts, and a couple of truncated sample lines. Sample text
    is capped so a pathological log line can't blow up the payload.
    """
    top = []
    for a in anomalies[:top_k]:
        samples = [s[:sample_chars] for s in (a.samples or [])[:max_samples]]
        top.append(
            {
                "kind": a.kind,
                "score": round(a.score, 2),
                "baseline_count": a.base_count,
                "window_count": a.window_count,
                "samples": samples,
            }
        )
    return Digest(source=source, anomaly_count=len(anomalies), top=top)
