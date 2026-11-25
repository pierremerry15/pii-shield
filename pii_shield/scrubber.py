"""Span-based PII scrubbing with reversible, typed placeholders.

Two differences from PathReview's ``PIIScrubber`` matter most:

1. Detection runs every recognizer on the *original* text, then resolves overlaps once
   (longest span wins, then recognizer priority). PathReview runs ``re.sub`` pattern by
   pattern, so each pattern sees the previous one's output and ``detect()`` can report
   spans that ``scrub()`` never redacts.
2. ``scrub(mode="typed")`` replaces each value with a numbered placeholder such as
   ``[PHONE_1]`` and returns the mapping. An LLM can still reason about "the phone
   number" without seeing it, and ``restore()`` puts the real values back into the
   model's reply afterwards. The same value always gets the same placeholder.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from pii_shield.recognizers import RECOGNIZERS, Candidate

REDACTED = "[REDACTED]"
PLACEHOLDER = re.compile(r"\[(EMAIL|PHONE|SSN|CARD|ADDRESS)_(\d+)\]")


@dataclass
class ScrubResult:
    text: str
    detections: list[dict]
    mapping: dict[str, str] = field(default_factory=dict)  # placeholder -> original value


def resolve(candidates: list[Candidate]) -> list[Candidate]:
    """Keep a non-overlapping subset: longest first, then lowest priority number."""
    chosen: list[Candidate] = []
    for cand in sorted(candidates, key=lambda c: (-(c.end - c.start), c.priority, c.start)):
        if all(cand.end <= kept.start or cand.start >= kept.end for kept in chosen):
            chosen.append(cand)
    return sorted(chosen, key=lambda c: c.start)


class Shield:
    """Detect and scrub PII. ``Shield().scrub(text)`` is the common entry point."""

    def __init__(self, recognizers=RECOGNIZERS):
        self.recognizers = recognizers

    def detect(self, text: str) -> list[dict]:
        candidates = [c for r in self.recognizers for c in r.find(text)]
        return [
            {
                "type": c.type,
                "value": c.value,
                "start": c.start,
                "end": c.end,
                "recognizer": c.recognizer,
            }
            for c in resolve(candidates)
        ]

    def scrub(self, text: str, mode: str = "redact") -> ScrubResult:
        if mode not in ("redact", "typed"):
            raise ValueError("mode must be 'redact' or 'typed'")
        detections = self.detect(text)
        mapping: dict[str, str] = {}
        by_value: dict[tuple[str, str], str] = {}
        counters: dict[str, int] = {}
        parts: list[str] = []
        pos = 0
        for d in detections:
            parts.append(text[pos : d["start"]])
            if mode == "redact":
                parts.append(REDACTED)
            else:
                key = (d["type"], d["value"])
                if key not in by_value:
                    counters[d["type"]] = counters.get(d["type"], 0) + 1
                    token = f"[{d['type']}_{counters[d['type']]}]"
                    by_value[key] = token
                    mapping[token] = d["value"]
                parts.append(by_value[key])
            pos = d["end"]
        parts.append(text[pos:])
        return ScrubResult(text="".join(parts), detections=detections, mapping=mapping)

    @staticmethod
    def restore(text: str, mapping: dict[str, str]) -> str:
        """Put original values back in place of placeholders. Unknown tokens are left as-is."""
        return PLACEHOLDER.sub(lambda m: mapping.get(m.group(0), m.group(0)), text)


class PIIScrubber:
    """Drop-in replacement for PathReview's ``safety.pii_scrubber.PIIScrubber``.

    Same method names and return shapes: ``scrub(text) -> str`` with ``[REDACTED]``
    tokens, and ``detect(text) -> list[dict]`` with type, value, start and end.
    """

    NAME = "v2"

    def __init__(self):
        self._shield = Shield()

    def scrub(self, text: str) -> str:
        return self._shield.scrub(text).text

    def detect(self, text: str) -> list[dict]:
        return self._shield.detect(text)
