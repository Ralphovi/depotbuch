from decimal import Decimal
from fractions import Fraction

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from depotbuch.engine.money import (
    Money,
    allocate,
    book_exact,
    is_booked,
    round_cent,
    share,
    to_decimal,
)


@pytest.mark.parametrize("value", [1.5, 0.0, True, None, [1], "abc", "NaN", "Infinity"])
def test_rejects_floats_and_non_numbers(value: object) -> None:
    with pytest.raises(ValueError, match=r"\S"):
        to_decimal(value)


def test_error_message_never_repeats_the_value() -> None:
    with pytest.raises(ValueError, match=r"\S") as err:
        to_decimal("4321.98x")
    assert "4321" not in str(err.value)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1.10", Decimal("1.10")),
        (" -3 ", Decimal(-3)),
        (7, Decimal(7)),
        (Decimal("2.5"), Decimal("2.5")),
    ],
)
def test_accepts_strings_ints_and_decimals(value: object, expected: Decimal) -> None:
    assert to_decimal(value) == expected


@given(st.decimals(allow_nan=False, allow_infinity=False))
def test_string_round_trip_keeps_every_digit(d: Decimal) -> None:
    assert to_decimal(str(d)) == d


@pytest.mark.parametrize(
    ("amount", "rounded"),
    [
        ("0.005", "0.01"),
        ("0.0049", "0.00"),
        ("-0.005", "-0.01"),
        ("2.675", "2.68"),
        ("10", "10.00"),
    ],
)
def test_round_cent_is_half_up(amount: str, rounded: str) -> None:
    assert round_cent(Decimal(amount)) == Decimal(rounded)
    assert str(round_cent(Decimal(amount))) == rounded


def test_money_validates_currency_and_amount() -> None:
    assert Money(amount="1.00", currency="USD").amount == Decimal("1.00")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        Money(amount="1.00", currency="usd")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        Money(amount=1.0)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("amount", "weights", "parts"),
    [
        ("3.01", ["1", "1", "1"], ["1.00", "1.01", "1.00"]),
        ("10.00", ["1", "2"], ["3.33", "6.67"]),
        ("0.01", ["1", "1"], ["0.01", "0.00"]),
        ("-5.00", ["1", "1", "1"], ["-1.67", "-1.66", "-1.67"]),
        ("0.03", ["1", "1", "1", "1", "1"], ["0.01", "0.00", "0.01", "0.00", "0.01"]),
    ],
)
def test_allocate_books_parts_that_add_up_exactly(
    amount: str, weights: list[str], parts: list[str]
) -> None:
    got = allocate(Decimal(amount), [Decimal(w) for w in weights])
    assert got == [Decimal(p) for p in parts]
    assert sum(got) == Decimal(amount)


@given(
    st.decimals(min_value=-(10**6), max_value=10**6, places=2),
    st.lists(st.decimals(min_value=Decimal("0.00001"), max_value=1000, places=5), min_size=1),
)
def test_allocation_is_always_exact_and_in_cents(
    amount: Decimal, weights: list[Decimal]
) -> None:
    parts = allocate(amount, weights)
    total = sum(weights)
    assert sum(parts) == amount
    assert all(is_booked(p) for p in parts)
    assert all(p * amount >= 0 for p in parts), "no part has the opposite sign"
    assert all(
        abs(p - amount * w / total) < Decimal("0.01")
        for p, w in zip(parts, weights, strict=True)
    )


@pytest.mark.parametrize("weights", [[], ["0", "0"], ["1", "-1"]])
def test_allocation_without_a_positive_weight_is_refused(weights: list[str]) -> None:
    with pytest.raises(ValueError, match="weight"):
        allocate(Decimal("1.00"), [Decimal(w) for w in weights])


def test_share_of_nothing_is_refused() -> None:
    with pytest.raises(ValueError, match="nothing"):
        share(Decimal(1), Decimal(1), Decimal(0))


@pytest.mark.parametrize(
    ("amount", "booked"),
    [
        ("1.10", True),
        ("1.100000", True),
        ("1.105", False),
        ("1E26", True),
        ("1E+40", True),
        ("123456789012345678901234567890.01", True),
        ("123456789012345678901234567890.001", False),
        ("0E-10", True),
        ("NaN", False),
        ("Infinity", False),
    ],
)
def test_is_booked_needs_no_decimal_context(amount: str, booked: bool) -> None:
    assert is_booked(Decimal(amount)) is booked


def test_a_share_is_rounded_once_from_its_exact_value() -> None:
    """971200517110195.76 / 0.000001370364126214148043810882276 is ...99.594999...
    exactly; rounded to 28 digits first it is ...99.595 and would book as .60."""
    amount = Decimal("971200517110195.76")
    whole = Decimal("0.000001370364126214148043810882276")
    assert round_cent(amount / whole) == Decimal("708717120166662459099.60")
    assert share(amount, Decimal(1), whole) == Decimal("708717120166662459099.59")
    assert book_exact(Fraction(1, 200)) == Decimal("0.01")
    assert book_exact(Fraction(-1, 200)) == Decimal("-0.01")
    assert book_exact(Fraction(1, 200) - Fraction(1, 10**40)) == Decimal("0.00")
