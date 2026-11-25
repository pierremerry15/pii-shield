"""Load the labeled splits in eval/data/.

Each non-comment line is one example. Gold PII is written inline as {{TYPE|value}},
and a literal backslash-n is a line break. The parser strips the markup and records the
exact character offsets, so gold spans can never be off by one from a hand count.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
TYPES = ("EMAIL", "PHONE", "SSN", "CARD", "ADDRESS")
TEST_SHA256 = "053c7aa9125642106bc52a0f7fa2e4ca54067724619fbcf84da4d5a5f4b89103"

_MARK = re.compile(r"\{\{([A-Z]+)\|(.+?)\}\}")


@dataclass(frozen=True)
class Span:
    type: str
    start: int
    end: int
    value: str


@dataclass
class Example:
    text: str
    gold: list[Span] = field(default_factory=list)
    line_no: int = 0

    @property
    def is_negative(self) -> bool:
        return not self.gold


def parse_line(raw: str, line_no: int = 0) -> Example:
    raw = raw.replace("\\n", "\n")
    out: list[str] = []
    gold: list[Span] = []
    pos = 0
    length = 0
    for m in _MARK.finditer(raw):
        before = raw[pos : m.start()]
        out.append(before)
        length += len(before)
        pii_type, value = m.group(1), m.group(2)
        if pii_type not in TYPES:
            raise ValueError(f"line {line_no}: unknown type {pii_type!r}")
        gold.append(Span(pii_type, length, length + len(value), value))
        out.append(value)
        length += len(value)
        pos = m.end()
    out.append(raw[pos:])
    text = "".join(out)
    if "{{" in text or "}}" in text:
        raise ValueError(f"line {line_no}: unbalanced markup")
    return Example(text=text, gold=gold, line_no=line_no)


def load_split(name: str) -> list[Example]:
    path = DATA_DIR / f"{name}.txt"
    examples = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        examples.append(parse_line(line, i))
    return examples


def is_test_split_frozen() -> bool:
    digest = hashlib.sha256((DATA_DIR / "test.txt").read_bytes()).hexdigest()
    return digest == TEST_SHA256
