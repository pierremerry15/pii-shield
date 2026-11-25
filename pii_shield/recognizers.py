"""One recognizer per PII type.

Each recognizer turns text into candidate spans. Overlaps between recognizers are
resolved later, in one place (``scrubber.resolve``), instead of by running patterns one
after another over each other's output the way PathReview's scrubber does.

What changed relative to PathReview (PR #98 version), and why:

PHONE
    US pattern is PR #98's, plus one rule from the North American Numbering Plan: an
    area code never starts with 0 or 1. That rejects prose like "100 200 3000 items".
    International numbers get their own pattern: a country code, then up to six groups
    separated by a single space, dot or hyphen, with 8 to 15 digits in total (E.164).
    PathReview's ``phone_intl`` only allowed "-" or ".", so "+44 20 7946 0958" was cut
    off after "+44".
EMAIL
    PathReview's character class ``[A-Z|a-z]`` contains a literal "|". Fixed, and the
    match may not start in the middle of a longer token.
SSN
    PathReview's rules, plus area numbers 900-999, which the SSA never assigns.
CARD (new)
    Digit runs of 13-19 digits that pass the Luhn checksum and match a card network's
    prefix and length (Visa, Mastercard, Amex, Discover, JCB, Diners). The network rule
    is what separates a card from a random 14-digit order ID that happens to pass Luhn.
ADDRESS
    Same suffix vocabulary as PathReview. What changed is the structure: the match is
    case-sensitive, and every word between the house number and the suffix must be
    capitalized (or a direction like "NW", or an ordinal like "42nd"). Prose such as
    "Managed 12 engineers on the Way of Code project" no longer matches, because
    "engineers on the" is lowercase. Optional trailing direction and unit
    ("Apt 3B", "Suite 4200", "#5") are included in the span.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass


@dataclass(frozen=True)
class Candidate:
    type: str
    start: int
    end: int
    value: str
    recognizer: str
    priority: int  # lower wins a tie between two spans of the same length


@dataclass(frozen=True)
class Recognizer:
    name: str
    type: str
    pattern: re.Pattern[str]
    priority: int
    validate: Callable[[str], bool] | None = None

    def find(self, text: str) -> Iterator[Candidate]:
        for m in self.pattern.finditer(text):
            value = m.group()
            if self.validate is None or self.validate(value):
                yield Candidate(self.type, m.start(), m.end(), value, self.name, self.priority)


def _digits(value: str) -> str:
    return "".join(c for c in value if c.isdigit())


# ---------------------------------------------------------------- email

EMAIL = Recognizer(
    name="email",
    type="EMAIL",
    pattern=re.compile(r"(?<![\w.%+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}(?![\w-])"),
    priority=0,
)

# ---------------------------------------------------------------- phone

PHONE_US = Recognizer(
    name="phone_us",
    type="PHONE",
    # PR #98's pattern with the area code restricted to [2-9]xx (NANP).
    pattern=re.compile(r"(?<![\w+])(?:\+?1[-. ]?)?(?:\([2-9]\d{2}\)|[2-9]\d{2})[-. ]?\d{3}[-. ]?\d{4}(?!\w)"),
    priority=1,
)


def _valid_intl(value: str) -> bool:
    return 8 <= len(_digits(value)) <= 15


PHONE_INTL = Recognizer(
    name="phone_intl",
    type="PHONE",
    pattern=re.compile(r"(?<![\w+])\+[1-9]\d{0,2}(?:[-. ]?\(?\d{1,8}\)?){1,6}(?![\w(])"),
    priority=2,
    validate=_valid_intl,
)

# ---------------------------------------------------------------- ssn

SSN = Recognizer(
    name="ssn",
    type="SSN",
    pattern=re.compile(r"(?<![\w-])(?!000|666|9\d\d)\d{3}-(?!00)\d{2}-(?!0000)\d{4}(?![\w-])"),
    priority=0,
)

# ---------------------------------------------------------------- card


def luhn_ok(number: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(number)):
        d = int(ch)
        if i % 2:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def card_network(number: str) -> str | None:
    """Return the card network for a digit string, or None if no network fits."""
    n = len(number)

    def prefix(k: int) -> int:
        return int(number[:k])

    if number.startswith("4") and n in (13, 16, 19):
        return "visa"
    if n == 16 and (51 <= prefix(2) <= 55 or 2221 <= prefix(4) <= 2720):
        return "mastercard"
    if n == 15 and prefix(2) in (34, 37):
        return "amex"
    if 16 <= n <= 19 and (
        number.startswith("6011") or number.startswith("65") or 644 <= prefix(3) <= 649 or 622126 <= prefix(6) <= 622925
    ):
        return "discover"
    if 16 <= n <= 19 and 3528 <= prefix(4) <= 3589:
        return "jcb"
    if 14 <= n <= 19 and (300 <= prefix(3) <= 305 or prefix(2) in (36, 38, 39)):
        return "diners"
    return None


class _CardRecognizer:
    """Finds digit runs, then the longest leading group of them that is a valid card.

    A plain regex can't do this well: "4242 4242 4242 4242 12/27" has a trailing digit
    group, and a regex that insists the run end at a non-digit would reject the card.
    """

    name = "card"
    type = "CARD"
    priority = 0
    _run = re.compile(r"(?<![\d-])\d+(?:[ -]\d+)*(?![\d-])")
    _group = re.compile(r"\d+")

    def find(self, text: str) -> Iterator[Candidate]:
        for run in self._run.finditer(text):
            groups = list(self._group.finditer(run.group()))
            # Try the longest prefix of groups first.
            for k in range(len(groups), 0, -1):
                end = groups[k - 1].end()
                value = run.group()[:end]
                digits = _digits(value)
                if 13 <= len(digits) <= 19 and luhn_ok(digits) and card_network(digits):
                    start = run.start()
                    yield Candidate(self.type, start, start + end, value, self.name, self.priority)
                    break


CARD = _CardRecognizer()

# ---------------------------------------------------------------- address

# PathReview's suffix list, de-duplicated. Longer alternatives first so "Parkway" is not
# read as "Park" + "way".
_SUFFIXES = sorted(
    {
        "Street",
        "St",
        "Avenue",
        "Ave",
        "Road",
        "Rd",
        "Boulevard",
        "Blvd",
        "Drive",
        "Dr",
        "Lane",
        "Ln",
        "Court",
        "Ct",
        "Circle",
        "Cir",
        "Park",
        "Pl",
        "Plaza",
        "Place",
        "Way",
        "Parkway",
        "Pkwy",
        "Point",
        "Pt",
        "Pike",
        "Run",
        "Summit",
        "Terrace",
        "Ter",
        "Trail",
        "Trl",
        "Tunnel",
        "Turnpike",
        "View",
        "Vista",
        "Vlg",
        "Village",
        "Vly",
        "Valley",
    },
    key=lambda s: (-len(s), s),
)
_DIR = r"(?:NE|NW|SE|SW|N|S|E|W)"
_WORD = rf"(?:[A-Z][a-z]+\.?|{_DIR}\.?|\d{{1,3}}(?:st|nd|rd|th))"
_SUFFIX = "(?:" + "|".join(_SUFFIXES) + ")"
_UNIT = r"(?:,? (?:Apt|Apartment|Suite|Ste|Unit|Rm|Room|Fl|Floor)\.? ?#?[A-Za-z0-9-]{1,6}|,? #[A-Za-z0-9-]{1,6})"

ADDRESS = Recognizer(
    name="street_address",
    type="ADDRESS",
    pattern=re.compile(
        rf"(?<![\w$#./,-])\d{{1,6}}[A-Z]? (?:{_WORD} ){{1,4}}{_SUFFIX}(?![\w'])"
        rf"(?: {_DIR}(?!\w))?(?:\.?{_UNIT}(?!\w))?"
    ),
    priority=3,
)


RECOGNIZERS = (EMAIL, PHONE_US, PHONE_INTL, SSN, CARD, ADDRESS)
