"""Scoring a scrubber against gold spans.

A scrubber is anything with ``detect(text) -> list[dict]`` where each dict has
``start`` and ``end``. Labels are ignored on purpose: what matters for redaction is
whether the characters get hidden, not which name the pattern gives them.

Definitions (also in the README):

* protected   a gold entity whose every character falls inside some predicted span
* partial     a gold entity with some characters covered and some exposed
* leaked      a gold entity with no characters covered
* recall      protected / gold entities
* precision   merged predicted spans that overlap any gold entity / merged predicted spans
* clean rate  negative examples (no gold PII) where nothing was redacted
"""

from __future__ import annotations

from dataclasses import dataclass, field

from eval.dataset import TYPES, Example


def merge(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Union overlapping or touching intervals."""
    merged: list[tuple[int, int]] = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def coverage(start: int, end: int, merged: list[tuple[int, int]]) -> int:
    covered = 0
    for s, e in merged:
        covered += max(0, min(end, e) - max(start, s))
    return covered


@dataclass
class Failure:
    line_no: int
    kind: str  # "leaked", "partial" or "false_positive"
    detail: str


@dataclass
class Report:
    name: str
    by_type: dict[str, dict[str, int]] = field(default_factory=dict)
    predicted: int = 0
    predicted_true: int = 0
    negatives: int = 0
    negatives_clean: int = 0
    failures: list[Failure] = field(default_factory=list)

    def _totals(self) -> dict[str, int]:
        t = {"gold": 0, "protected": 0, "partial": 0, "leaked": 0}
        for row in self.by_type.values():
            for k in t:
                t[k] += row[k]
        return t

    @property
    def recall(self) -> float:
        t = self._totals()
        return t["protected"] / t["gold"] if t["gold"] else 1.0

    @property
    def precision(self) -> float:
        return self.predicted_true / self.predicted if self.predicted else 1.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if p + r else 0.0

    @property
    def clean_rate(self) -> float:
        return self.negatives_clean / self.negatives if self.negatives else 1.0

    def type_recall(self, pii_type: str) -> float:
        row = self.by_type[pii_type]
        return row["protected"] / row["gold"] if row["gold"] else float("nan")

    def totals(self) -> dict[str, int]:
        return self._totals()


def evaluate(scrubber, examples: list[Example], name: str) -> Report:
    report = Report(name=name, by_type={t: {"gold": 0, "protected": 0, "partial": 0, "leaked": 0} for t in TYPES})
    for ex in examples:
        predicted = merge([(d["start"], d["end"]) for d in scrubber.detect(ex.text)])
        report.predicted += len(predicted)

        for span in ex.gold:
            row = report.by_type[span.type]
            row["gold"] += 1
            got = coverage(span.start, span.end, predicted)
            if got == span.end - span.start:
                row["protected"] += 1
            elif got > 0:
                row["partial"] += 1
                report.failures.append(Failure(ex.line_no, "partial", f"{span.type} {span.value!r}"))
            else:
                row["leaked"] += 1
                report.failures.append(Failure(ex.line_no, "leaked", f"{span.type} {span.value!r}"))

        for s, e in predicted:
            if any(coverage(g.start, g.end, [(s, e)]) for g in ex.gold):
                report.predicted_true += 1
            else:
                report.failures.append(Failure(ex.line_no, "false_positive", repr(ex.text[s:e])))

        if ex.is_negative:
            report.negatives += 1
            if not predicted:
                report.negatives_clean += 1
    return report
