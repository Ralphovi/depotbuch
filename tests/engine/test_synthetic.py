"""Synthetic histories (issue #34): the engine against the bank model's documents."""

import tomllib
from datetime import date
from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from depotbuch.testing.bank import Bank, half_up
from depotbuch.testing.casefile import Case, check
from depotbuch.testing.synth import history, to_case


def _failures(seed: int, *, years: int = 6, extreme: bool = False) -> list[str]:
    case = Case.model_validate(
        tomllib.loads(to_case(history(seed, years=years, extreme=extreme)))
    )
    return [
        f"expect[{r.expect}] {r.metric} ({r.mode}): want {r.want}, got {r.got}"
        for r in check(case)
        if not r.ok
    ]


@pytest.mark.parametrize("seed", range(1, 9))
def test_a_synthetic_history_matches_its_documents(seed: int) -> None:
    assert _failures(seed) == []


@pytest.mark.parametrize("seed", range(1, 5))
def test_an_extreme_history_matches_its_documents(seed: int) -> None:
    assert _failures(seed, years=9, extreme=True) == []


@settings(max_examples=20, deadline=None)
@given(
    seed=st.integers(0, 2**32 - 1),
    years=st.integers(1, 10),
    extreme=st.booleans(),
)
def test_any_synthetic_history_matches_its_documents(
    seed: int, years: int, extreme: bool
) -> None:
    assert _failures(seed, years=years, extreme=extreme) == []


def test_a_history_is_the_same_for_the_same_seed() -> None:
    assert to_case(history(11)) == to_case(history(11))
    assert to_case(history(11)) != to_case(history(12))


def test_half_up_rounds_a_tie_away_from_zero() -> None:
    assert half_up(Decimal("0.005")) == Decimal("0.01")
    assert half_up(Decimal("-0.005")) == Decimal("-0.01")
    assert half_up(Decimal("1.234565"), 5) == Decimal("1.23457")


def test_a_savings_plan_buys_units_rounded_to_five_decimals() -> None:
    """50.00 at 33.33: 1.500150015... units -> 1.50015, charged 1.50015 x 33.33 = 50.00."""
    trade = Bank().plan(date(2024, 1, 2), "F", Decimal("50.00"), Decimal("33.33"))
    assert (trade.units, trade.charged, trade.cash) == (
        Decimal("1.50015"),
        Decimal("50.00"),
        Decimal("-50.00"),
    )


def test_a_statement_total_adds_the_rounded_positions() -> None:
    bank = Bank()
    for asset in ("A", "B", "C"):
        bank.buy(date(2024, 1, 2), asset, Decimal(1), Decimal("9.00"))
    st = bank.statement(date(2024, 3, 31), dict.fromkeys("ABC", Decimal("10.005")))
    assert st.total == Decimal("30.03")


def test_the_partial_exemption_is_rounded_per_lot() -> None:
    """Two lots of 1 unit at 10.00 and 10.01; 2 sold for 30.01 after 0.00 fees.
    Price per unit 15.005 -> 15.0050; lot gains 5.01 and 5.00, exemptions at 30 %
    1.503 -> 1.50 and 1.50. Taxable: 30.01 - 20.01 - 3.00 = 7.00."""
    bank = Bank(exemption={"F": Decimal(30)})
    bank.buy(date(2024, 1, 2), "F", Decimal(1), Decimal("10.00"))
    bank.buy(date(2024, 2, 1), "F", Decimal(1), Decimal("10.01"))
    bank.sell(date(2024, 6, 3), "F", Decimal(2), Decimal("15.005"))
    assert bank.sale_taxes[-1].taxable == Decimal("7.00")


def test_a_vorabpauschale_spares_months_before_a_purchase() -> None:
    """Lot 1 held all of 2024, lot 2 bought in October (3/12): 12 per unit-year spread
    as 1 x 1 : 1 x 0.25 -> 9.60 and 2.40. Selling lot 1 for its cost deducts 9.60."""
    bank = Bank(exemption={"F": Decimal(0)})
    bank.buy(date(2023, 5, 2), "F", Decimal(1), Decimal("100.00"))
    bank.buy(date(2024, 10, 1), "F", Decimal(1), Decimal("100.00"))
    bank.vorabpauschale(date(2025, 1, 2), "F", Decimal("12.00"))
    bank.sell(date(2025, 3, 3), "F", Decimal(1), Decimal("100.00"))
    assert bank.sale_taxes[-1].taxable == Decimal("-9.60")


def test_the_bank_entitles_units_held_on_the_schlusstag() -> None:
    bank = Bank()
    bank.buy(date(2024, 1, 2), "F", Decimal("3.5"), Decimal("10.00"))
    one, two = bank.distribute(
        date(2024, 5, 21), date(2024, 6, 6), "F", Decimal("0.3333"), split_at=Decimal(2)
    )
    assert (one.units, one.gross, two.units, two.gross) == (
        Decimal(2),
        Decimal("0.67"),
        Decimal("1.5"),
        Decimal("0.50"),
    )
    with pytest.raises(ValueError, match="nothing held"):
        Bank().distribute(date(2024, 5, 21), date(2024, 6, 6), "F", Decimal("0.1"))
