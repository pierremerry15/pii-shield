import pytest

from pii_shield import Shield
from pii_shield.recognizers import card_network, luhn_ok

shield = Shield()


def found(text):
    return [(d["type"], d["value"]) for d in shield.detect(text)]


@pytest.mark.parametrize(
    "number",
    [
        "555-123-4567",
        "555.123.4567",
        "5551234567",
        "1-555-123-4567",
        "+1 555 123 4567",
        "+1 (555) 123-4567",
        "555 123 4567",
        "(555)123-4567",
        "(555) 123-4567",
    ],
)
def test_us_phone_formats_fully_redacted(number):
    # PR #98's formats must keep working in v2.
    assert shield.scrub(f"Call {number} today").text == "Call [REDACTED] today"


@pytest.mark.parametrize(
    "number",
    ["+44 20 7946 0958", "+33 1 42 68 53 00", "+81 3-1234-5678", "+49 30 901820", "+91 98765 43210"],
)
def test_international_phone_fully_redacted(number):
    assert found(f"Office {number}.") == [("PHONE", number)]


def test_area_code_cannot_start_with_0_or_1():
    # NANP rule: this is a list of numbers, not a phone.
    assert found("listed 100 200 3000 items") == []


def test_phone_does_not_join_across_line_break():
    assert found("Room 555\n123 4567") == []


@pytest.mark.parametrize("text", ["2026-11-11", "20059-1234", "Version 1.2.3", "ID 12345678901234", "555-1234"])
def test_non_pii_numbers_left_alone(text):
    assert found(text) == []


def test_email_variants():
    assert found("Mail DEV.TEAM@EXAMPLE.CO.UK now") == [("EMAIL", "DEV.TEAM@EXAMPLE.CO.UK")]
    assert found("<team@example.dev>") == [("EMAIL", "team@example.dev")]
    assert found("x@example.com.") == [("EMAIL", "x@example.com")]


def test_email_character_class_has_no_pipe():
    # PathReview's [A-Z|a-z] accepted "|" in the TLD.
    assert found("a@b.c|m") == []


def test_ssn_rules():
    assert found("SSN 219-09-9999") == [("SSN", "219-09-9999")]
    assert found("SSN 000-12-3456") == []
    assert found("SSN 666-12-3456") == []
    assert found("SSN 912-34-5678") == []  # 9xx area numbers are never assigned


def test_luhn_and_networks():
    assert luhn_ok("4111111111111111")
    assert not luhn_ok("4111111111111112")
    assert card_network("4111111111111111") == "visa"
    assert card_network("5555555555554444") == "mastercard"
    assert card_network("378282246310005") == "amex"
    assert card_network("6011111111111117") == "discover"
    # Passes Luhn, but a 14-digit number starting with 4 is not a Visa length.
    assert luhn_ok("48213907615523") and card_network("48213907615523") is None


@pytest.mark.parametrize(
    "card", ["4111 1111 1111 1111", "5555-5555-5555-4444", "3782 822463 10005", "6011111111111117"]
)
def test_cards_detected(card):
    assert found(f"Card {card} on file") == [("CARD", card)]


def test_card_followed_by_other_digits():
    assert found("Card 4242 4242 4242 4242 12/27") == [("CARD", "4242 4242 4242 4242")]


def test_invalid_checksum_is_not_a_card():
    assert found("Invoice 4111 1111 1111 1112 was voided") == []


@pytest.mark.parametrize(
    "address",
    [
        "123 Main Street",
        "42 Elm Rd",
        "1600 Pennsylvania Avenue NW",
        "9 W 42nd St",
        "350 Fifth Avenue, Suite 4200",
        "88 Oak Court, Apt 3B",
        "47 St. Marks Place",
        "221B Baker Street",
    ],
)
def test_addresses(address):
    assert found(f"Ship to {address}, thanks") == [("ADDRESS", address)]


@pytest.mark.parametrize(
    "prose",
    [
        "Managed 12 engineers on the Way of Code project.",
        "Ran 5 marathons and like to run on weekends.",
        "Shipped 2 features to the Court reporting tool.",
        "Experienced developer with 5 years developing Python applications.",
        "Ranked top 5 of 200 applicants.",
    ],
)
def test_prose_with_suffix_words_is_not_an_address(prose):
    assert found(prose) == []


def test_sentence_final_period_is_not_swallowed():
    assert shield.scrub("I live at 12 Main St.").text == "I live at [REDACTED]."
