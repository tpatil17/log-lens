"""Summarize stage: turn a digest into a plain-English explanation via OpenAI.

This is the ONLY place the tool touches the network or a secret. It is strictly
optional (invoked by `--explain`); everything above it runs offline. The prompt
constrains the model to the digest and forces causes to be framed as hypotheses,
never invented facts (Risk #3 in the design doc).
"""

import json
import os
from dataclasses import dataclass

from loglens.digest import Digest

DEFAULT_MODEL = "gpt-4o-mini"  # cheap + fast; override via --model

SYSTEM_PROMPT = """You are a site-reliability assistant helping an on-call engineer.
You are given a JSON digest of the top anomalies a statistical tool detected in a
log file (NEW = a template that appeared, SPIKE = one that got more frequent,
VANISHED = one that stopped). Explain what changed.

Strict rules:
- Use ONLY the information in the digest. Never invent log lines, service names,
  metrics, or timestamps that are not present.
- Any root cause is a HYPOTHESIS, not a fact — phrase it that way.
- Be concise and practical; write for an engineer mid-incident.

Return ONLY a JSON object with this exact shape:
{"summary": "one or two sentences", "hypotheses": ["..."], "suggested_actions": ["..."]}"""


@dataclass
class Explanation:
    summary: str
    hypotheses: list[str]
    suggested_actions: list[str]


class LLMUnavailable(Exception):
    """Raised when the LLM step can't run (no key, package missing). The CLI
    catches this and degrades gracefully — the pipeline output is unaffected."""


def _default_client():
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise LLMUnavailable("OPENAI_API_KEY is not set")
    try:
        from openai import OpenAI
    except ImportError as e:
        raise LLMUnavailable("openai not installed — run: pip install '.[llm]'") from e
    return OpenAI(api_key=api_key)


def summarize(digest: Digest, model: str = DEFAULT_MODEL, client=None) -> Explanation:
    """Send the digest to the model and parse a structured Explanation.

    `client` is injectable so tests run without network or an API key.
    """
    if client is None:
        client = _default_client()

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": digest.to_json()},
        ],
        response_format={"type": "json_object"},
        temperature=0,
    )
    data = json.loads(response.choices[0].message.content)
    return Explanation(
        summary=data.get("summary", ""),
        hypotheses=list(data.get("hypotheses", [])),
        suggested_actions=list(data.get("suggested_actions", [])),
    )
