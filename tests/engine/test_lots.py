from datetime import date, timedelta
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from depotbuch.engine.fx import FxRates, MissingRate
from depotbuch.engine.holdings import units_held
from depotbuch.engine.lots import MissingCostBasis, Oversold, build_lots
from depotbuch.engine.model import Activity
from depotbuch.engine.money import is_booked

START = date(2024, 1, 1)
END = date(2024, 12, 31)


def buy(day: int, units: str, cash: str, account: str = "A", **kw: str) -> Activity:
    return Activity.model_validate(
        {
            "date": START + timedelta(days=day),
            "type": "buy",
            "account": account,
            "asset": "X1",
            "units": units,
            "cash": cash,
            **kw,
        }
    )


def sell(day: int, units: str, cash: str, account: str = "A", **kw: str) -> Activity:
    return Activity.model_validate(
        {
            "date": START + timedelta(days=day),
            "type": "sell",
            "account": account,
            "asset": "X1",
            "units": units,
            "cash": cash,
            **kw,
        }
    )


amounts = st.decimals(min_value=Decimal("0.00001"), max_value=Decimal(10_000), places=5)
money = st.decimals(min_value=Decimal(0), max_value=Decimal(1_000_000), places=2)


@st.composite
def histories(draw: st.DrawFn) -> list[Activity]:
    """Buys and sales in two accounts; a sale never exceeds what its account holds."""
    held = {"A": Decimal(0), "B": Decimal(0)}
    out = []
    for day in range(draw(st.integers(1, 40))):
        account = draw(st.sampled_from(["A", "B"]))
        if held[account] > 0 and draw(st.booleans()):
            units = draw(
                st.decimals(min_value=Decimal("0.00001"), max_value=held[account], places=5)
            )
            held[account] -= units
            out.append(sell(day, str(-units), str(draw(money)), account))
        else:
            units = draw(amounts)
            held[account] += units
            out.append(buy(day, str(units), str(-draw(money)), account))
    return out


@given(histories())
def test_lots_sum_to_holdings(acts: list[Activity]) -> None:
    book = build_lots(acts, END)
    for account in ("A", "B"):
        raw = sum((a.units for a in acts if a.account == account), Decimal(0))
        assert book.units(asset="X1", account=account) == raw
        assert units_held(acts, END, asset="X1", account=account) == raw


@given(histories())
def test_every_cent_of_cost_is_either_held_or_realized(acts: list[Activity]) -> None:
    book = build_lots(acts, END)
    paid = sum((-a.cash for a in acts if a.type == "buy"), Decimal(0))
    closed = sum((r.cost for r in book.realized), Decimal(0))
    assert book.invested_capital() + closed == paid
    assert all(is_booked(lot.cost) for lot in book.lots)


@given(histories())
def test_each_sale_books_its_proceeds_exactly(acts: list[Activity]) -> None:
    book = build_lots(acts, END)
    assert all(is_booked(r.proceeds) and is_booked(r.cost) for r in book.realized)
    for sale in (a for a in acts if a.type == "sell"):
        slices = [r for r in book.realized if (r.date, r.account) == (sale.date, sale.account)]
        assert sum((r.proceeds for r in slices), Decimal(0)) == sale.cash


def test_a_partial_lot_takes_its_cost_share_in_cents() -> None:
    """Lots of 1 @ 1.00, 1 @ 1.00 and 2 @ 2.01; selling 3 for 3.01 closes the first two lots
    and half of the third: 2.01 x 1/2 = 1.005, booked half up as 1.01, leaving the lot
    exactly 1.00. Cost 1.00 + 1.00 + 1.01 = 3.01, gain 0.00; invested 1.00."""
    acts = [
        buy(0, "1", "-1.00"),
        buy(1, "1", "-1.00"),
        buy(2, "2", "-2.01"),
        sell(3, "-3", "3.01"),
    ]
    book = build_lots(acts, END)
    assert book.realized_gain() == 0
    assert book.invested_capital() == Decimal("1.00")
    # Proceeds of 3.01 over three units, booked cumulatively: 1.00, 2.01, 3.01.
    assert [r.proceeds for r in book.realized] == [
        Decimal("1.00"),
        Decimal("1.01"),
        Decimal("1.00"),
    ]


def test_oversold_is_rejected_with_its_date() -> None:
    acts = [buy(0, "5", "-500"), sell(3, "-6", "700")]
    with pytest.raises(Oversold) as err:
        build_lots(acts, END)
    assert err.value.when == START + timedelta(days=3)
    assert err.value.missing == 1
    assert "6" not in str(err.value)


def test_a_sale_cannot_use_another_accounts_lots() -> None:
    with pytest.raises(Oversold):
        build_lots([buy(0, "5", "-500", "A"), sell(1, "-1", "100", "B")], END)


def test_a_delivery_in_needs_its_cost_basis() -> None:
    delivery = Activity.model_validate(
        {"date": START, "type": "transfer", "account": "A", "asset": "X1", "units": "3"}
    )
    with pytest.raises(MissingCostBasis):
        build_lots([delivery], END)
    assert units_held([delivery], END, asset="X1") == 3


def test_activities_after_as_of_are_ignored() -> None:
    acts = [buy(0, "5", "-500"), sell(10, "-5", "700")]
    book = build_lots(acts, START + timedelta(days=9))
    assert book.units(asset="X1") == 5
    assert book.realized == []


def test_foreign_currency_without_any_rate_fails_loudly() -> None:
    usd = buy(0, "1", "-100", currency="USD")
    with pytest.raises(MissingRate):
        build_lots([usd], END)
    assert units_held([usd], END, asset="X1") == 1  # units need no rate


def test_fx_rates_carry_forward_and_never_backward() -> None:
    rates = FxRates({"USD": {date(2024, 6, 7): Decimal("1.2")}})
    assert rates.rate("USD", date(2024, 6, 9)) == Decimal("1.2")
    assert rates.rate("EUR", date(2000, 1, 1)) == 1
    with pytest.raises(MissingRate):
        rates.rate("USD", date(2024, 6, 6))
    assert rates.to_eur(Decimal(120), "USD", date(2024, 6, 7)) == 100
    assert rates.to_eur(Decimal(125), "USD", date(2024, 6, 7), Decimal("1.25")) == 100
    assert rates.to_eur(Decimal(100), "USD", date(2024, 6, 7), Decimal("3")) != Decimal("33.33")
    assert rates.book_eur(Decimal(100), "USD", date(2024, 6, 7), Decimal("3")) == Decimal(
        "33.33"
    )
    with pytest.raises(ValueError, match="between"):
        FxRates({"USD": {date(2024, 6, 7): Decimal(0)}})


def test_no_lot_slice_changes_sign() -> None:
    """0.03 over five lots of one unit: cumulative booking gives 0.01, 0.00, 0.01, 0.00,
    0.01, never a negative slice."""
    acts = [buy(i, "1", "-0.01") for i in range(5)] + [sell(5, "-5", "0.03")]
    book = build_lots(acts, END)
    assert all(r.proceeds >= 0 for r in book.realized)
    assert sum(r.proceeds for r in book.realized) == Decimal("0.03")


def test_a_zero_foreign_amount_needs_no_rate() -> None:
    acts = [buy(0, "1", "0.00", currency="USD")]
    assert build_lots(acts, END).invested_capital() == 0


def test_a_conversion_rounds_once_from_the_exact_quotient() -> None:
    """971200517110195.76 / 0.000001370364126214148043810882276 is ...594999... exactly;
    rounded to 28 digits first, it would book a cent up."""
    amount = Decimal("971200517110195.76")
    rate = Decimal("0.000001370364126214148043810882276")
    booked = FxRates().book_eur(amount, "USD", START, rate)
    assert booked == Decimal("708717120166662459099.59")


def test_a_split_beyond_the_unit_bounds_is_rejected_not_rounded() -> None:
    split = Activity.model_validate(
        {
            "date": START + timedelta(days=1),
            "type": "split",
            "account": "A",
            "asset": "X1",
            "ratio": "1000000",
        }
    )
    with pytest.raises(ValueError, match="split"):
        build_lots([buy(0, "1000000000", "-1.00"), split], END)
    tiny = split.model_copy(update={"ratio": Decimal("0.000001")})
    with pytest.raises(ValueError, match="split"):
        build_lots([buy(0, "0.000000000001", "-1.00"), tiny], END)


def test_a_split_result_with_trailing_zeros_is_within_the_bounds() -> None:
    split = Activity.model_validate(
        {
            "date": START + timedelta(days=1),
            "type": "split",
            "account": "A",
            "asset": "X1",
            "ratio": "2.0",
        }
    )
    book = build_lots([buy(0, "1.234567890123", "-1.00"), split], END)
    assert book.units(asset="X1") == Decimal("2.469135780246")


def test_units_held_ignores_other_positions() -> None:
    """An oversold sale of another asset or in another account doesn't stop the count."""
    other_asset = sell(1, "-1", "100").model_copy(update={"asset": "X2"})
    other_account = sell(2, "-9", "100", "B")
    acts = [buy(0, "5", "-500"), other_asset, other_account]
    assert units_held(acts, END, asset="X1", account="A") == 5
