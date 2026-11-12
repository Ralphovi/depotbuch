from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from depotbuch.engine.money import Money, round_cent, to_decimal


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
