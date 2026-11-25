import pytest

from baselines.pathreview_pr98 import PIIScrubber as PR98
from pii_shield import PIIScrubber, Shield
from pii_shield.recognizers import Candidate
from pii_shield.scrubber import resolve

shield = Shield()


def test_resolve_prefers_longest_then_priority():
    a = Candidate("PHONE", 0, 15, "x", "phone_us", 1)
    b = Candidate("PHONE", 0, 16, "x", "phone_intl", 2)
    c = Candidate("SSN", 20, 31, "x", "ssn", 0)
    d = Candidate("ADDRESS", 20, 31, "x", "street_address", 3)
    assert resolve([a, b, c, d]) == [b, c]


def test_detect_offsets_match_values():
    text = "Cell (555) 123-4567, office +1 555 987 6543, mail me@example.com."
    for d in shield.detect(text):
        assert text[d["start"] : d["end"]] == d["value"]


def test_scrub_and_detect_agree():
    # PathReview's sequential re.sub can redact differently from what detect() reports.
    text = "Reach (555) 201-3344, me@example.com, 2400 Sixth St NW, card 4111 1111 1111 1111."
    result = shield.scrub(text)
    assert result.text.count("[REDACTED]") == len(result.detections) == 4


def test_typed_placeholders_are_stable_and_numbered():
    text = "a@example.com, b@example.com, again a@example.com, call 555-123-4567"
    r = shield.scrub(text, mode="typed")
    assert r.text == "[EMAIL_1], [EMAIL_2], again [EMAIL_1], call [PHONE_1]"
    assert r.mapping == {"[EMAIL_1]": "a@example.com", "[EMAIL_2]": "b@example.com", "[PHONE_1]": "555-123-4567"}


def test_restore_round_trip():
    text = "Ana, (555) 201-3344, 42 Elm Rd, ana@example.com"
    r = shield.scrub(text, mode="typed")
    assert shield.restore(r.text, r.mapping) == text


def test_restore_leaves_unknown_placeholders():
    assert shield.restore("call [PHONE_7]", {"[PHONE_1]": "555-123-4567"}) == "call [PHONE_7]"


def test_scrub_is_idempotent():
    text = "Call (555) 123-4567 or write jo@example.com from 12 Main St."
    once = shield.scrub(text).text
    assert shield.scrub(once).text == once


def test_empty_and_whitespace():
    assert shield.scrub("").text == ""
    assert shield.detect("   \n ") == []


def test_bad_mode():
    with pytest.raises(ValueError):
        shield.scrub("x", mode="mask")


def test_drop_in_matches_pathreview_interface():
    ours, theirs = PIIScrubber(), PR98()
    text = "Call me at (555) 123-4567"
    assert ours.scrub(text) == theirs.scrub(text) == "Call me at [REDACTED]"
    for d in ours.detect(text):
        assert {"type", "value", "start", "end"} <= set(d)
